#!/usr/bin/env python3
"""
Integrated Drone Control System with Mode Toggle

Features:
- Toggle between Formation Mode and Manual Control Mode
- Formation Mode:
  - Upload image to extract formation points
  - Set formation parameters
  - Spawn and control drone formations
- Manual Control Mode:
  - Individual drone selection
  - Joystick and precise movement controls
  - Velocity control
- Common:
  - Real-time status monitoring
  - System logging
  - Emergency procedures
"""

import os
import uuid
import logging
import numpy as np
import cv2
from flask import Flask, request, render_template_string, url_for, jsonify, Response, redirect
import asyncio
import threading
import subprocess
import time
import math
import json
from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed
import signal


# ----------------------------
# Global Configuration & Setup
# ----------------------------
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# Mode selection
current_mode = "formation"  # "formation" or "manual"

# File paths
UPLOAD_FOLDER = 'static/uploads'
RESULT_FOLDER = 'static/results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# Drone control globals
drone_instances = {}   # Stores spawned drone info
logs = []              # Log messages
current_controlled_drone = 0

# PX4 configuration
PX4_ROOT = "/home/manoh/PX4-Autopilot"
MAVSDK_SERVER_PATH = "/home/manoh/PX4-Autopilot/mavsdk_env/lib/python3.12/site-packages/mavsdk/bin/mavsdk_server"
BASE_MAVLINK_PORT = 14540
BASE_SYSTEM_PORT = 50051

# Control parameters
THRESHOLD = 0.5
MOVE_DISTANCE = 1.0
MOVE_SPEED = 1.0
UPDATE_INTERVAL = 1
DISTANCE_THRESHOLD = 3.0
LOG_INTERVAL = 10
CONNECT_TIMEOUT = 30
HEALTH_TIMEOUT = 30
SPAWN_DELAY = 10.0




class FormationController:
    def __init__(self):
        self.formation_points = []
        # now we define north_min/north_max instead of east
        self.space = {'north_min': 0.0, 'north_max': 0.0}
        self.base_altitude = 5.0
        self.formation_depth = 10.0

    def set_space(self, north_min, north_max, alt_min, alt_max):
        """
        Define your Y-range (North/South) and Z-range (altitude).
        X is always 0 for a pure North–South line.
        """
        self.space['north_min']   = north_min
        self.space['north_max']   = north_max
        self.base_altitude        = alt_min
        self.formation_depth      = alt_max - alt_min
        logging.info(
            f"Formation Y-range: [{north_min} … {north_max}]m, "
            f"Z-range: [{alt_min} … {alt_max}]m (X=0)"
        )

    def set_formation_from_image(self, points, scale=None, base_altitude=None, depth=None):
        if not points:
            return 0
        # update altitudes if provided
        if base_altitude is not None:
            self.base_altitude   = base_altitude
        if depth         is not None:
            self.formation_depth = depth

        pts = np.array(points, dtype=float)
        min_x, min_y = pts.min(axis=0)
        max_x, max_y = pts.max(axis=0)
        w_pix = max_x - min_x or 1.0
        h_pix = max_y - min_y or 1.0

        # SIM-space extents
        Ymin, Ymax = self.space['north_min'], self.space['north_max']
        Zmin = self.base_altitude
        Zmax = self.base_altitude + self.formation_depth
        W = Ymax - Ymin
        H = Zmax - Zmin

        # unified meters-per-pixel to fit without distortion
        mpp = min(W / w_pix, H / h_pix)

        # margins to center
        y_off = Ymin + (W - w_pix * mpp) / 2.0
        z_off = Zmin + (H - h_pix * mpp) / 2.0

        self.formation_points.clear()
        for px, py in pts:
            north = y_off + (px - min_x) * mpp
            # invert Y if image Y grows downward:
            alt   = Zmax - (py - min_y) * mpp
            self.formation_points.append([0.0, north, alt])

        logging.info(
            f"Mapped {len(self.formation_points)} pts → "
            f"Y in [{Ymin:.1f}…{Ymax:.1f}], Z in [{Zmin:.1f}…{Zmax:.1f}] "
            f"using {mpp:.3f} m/px"
        )
        return len(self.formation_points)





    def get_formation_positions(self, home_lat, home_lon, home_alt):
        """
        Convert local [X=0, Y, Z] → GPS.
        Longitude stays at home_lon, latitude shifts with north_m.
        """
        if not self.formation_points:
            raise ValueError("No formation points set")

        poses = []
        for idx, (_, north_m, vert_m) in enumerate(self.formation_points):
            # pass x=0 → no longitude change
            lat, lon = xy_to_latlon(0.0, north_m, home_lat, home_lon)
            alt       = home_alt + vert_m
            poses.append((lat, lon, alt))
            logging.info(
                f"Drone {idx}: N={north_m:.2f}m → lat={lat:.8f}, "
                f"lon={lon:.8f}, alt={alt:.2f}m"
            )
        return poses



formation_controller = FormationController()
formation_controller.set_space(
    north_min=-10.0,  # South edge
    north_max= 10.0,  # North edge
    alt_min=   5.0,   # base altitude
    alt_max=  25.0    # top altitude
)




# ----------------------------
# Async Loop Setup
# ----------------------------
global_loop = asyncio.new_event_loop()
def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()
threading.Thread(target=start_loop, args=(global_loop,), daemon=True).start()

def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(coro, global_loop)
    return future.result()

# ----------------------------
# Image Processing Functions
# ----------------------------
def preprocess_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Image could not be loaded.")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(blurred, 255,
                                 cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 11, 2)
    kernel = np.ones((3, 3), np.uint8)
    morph = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    return image, morph

def optimize_tolerance(contour, penalty_weight=0.001):
    arc_length = cv2.arcLength(contour, True)
    best_score = float('inf')
    best_tol = None
    for tol in np.linspace(0.001, 0.05, 50):
        epsilon = tol * arc_length
        approx = cv2.approxPolyDP(contour, epsilon, True)
        error = cv2.matchShapes(contour, approx, cv2.CONTOURS_MATCH_I1, 0.0)
        score = error + penalty_weight * len(approx)
        if score < best_score:
            best_score = score
            best_tol = tol
    logging.info("Optimized tolerance: %.4f (score: %.4f)", best_tol, best_score)
    return best_tol

def minimal_sampling(contour, tolerance):
    arc_length = cv2.arcLength(contour, True)
    epsilon = tolerance * arc_length
    approx = cv2.approxPolyDP(contour, epsilon, True)
    points = [tuple(map(int, pt[0])) for pt in approx]
    return points

def uniform_sampling(contour, num_dots):
    pts = contour[:, 0, :]
    arc_len = cv2.arcLength(pts, True)
    if arc_len == 0:
        raise ValueError("Contour has zero arc length.")
    cum_dist = [0]
    for i in range(1, len(pts)):
        cum_dist.append(cum_dist[-1] + np.linalg.norm(pts[i] - pts[i-1]))
    cum_dist = np.array(cum_dist)
    targets = np.linspace(0, cum_dist[-1], num_dots, endpoint=False)
    sampled = []
    j = 0
    for t in targets:
        while j < len(cum_dist)-1 and cum_dist[j+1] < t:
            j += 1
        if j < len(pts)-1:
            ratio = (t - cum_dist[j]) / (cum_dist[j+1] - cum_dist[j] + 1e-8)
            interp_pt = (1 - ratio) * pts[j] + ratio * pts[j+1]
            sampled.append((int(interp_pt[0]), int(interp_pt[1])))
        else:
            sampled.append((int(pts[j][0]), int(pts[j][1])))
    return sampled

def draw_dotted_image(image, points):
    img_copy = image.copy()
    for pt in points:
        cv2.circle(img_copy, pt, 3, (0, 0, 255), -1)
    return img_copy

def save_image(image, prefix):
    filename = f"{prefix}_{str(uuid.uuid4())}.png"
    path = os.path.join(RESULT_FOLDER, filename)
    cv2.imwrite(path, image)
    return url_for('static', filename='results/' + filename)

def process_image(image_path, desired_num_drones=None):
    image, morph = preprocess_image(image_path)
    contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    outer_contours = [cnt for cnt in contours if cv2.contourArea(cnt) >= 100]
    if not outer_contours:
        raise ValueError("No significant outer contours found.")
    minimal_points = []
    for cnt in outer_contours:
        tol = optimize_tolerance(cnt)
        pts = minimal_sampling(cnt, tol)
        minimal_points.extend(pts)
    minimal_count = len(minimal_points)
    logging.info("Total minimal structure has %d points", minimal_count)
    minimal_dotted = draw_dotted_image(image, minimal_points)
    minimal_url = save_image(minimal_dotted, "minimal")
    if desired_num_drones is None or desired_num_drones <= minimal_count:
        final_points = minimal_points
    else:
        final_points = []
        total_length = sum(cv2.arcLength(cnt, True) for cnt in outer_contours)
        for cnt in outer_contours:
            length = cv2.arcLength(cnt, True)
            prop = length / total_length if total_length > 0 else 0
            num_pts = int(round(prop * desired_num_drones))
            if num_pts < 2 and length > 1:
                num_pts = 2
            elif num_pts < 1:
                num_pts = 1
            pts = uniform_sampling(cnt, num_pts)
            final_points.extend(pts)
    final_count = len(final_points)
    final_dotted = draw_dotted_image(image, final_points)
    final_url = save_image(final_dotted, "final")
    results = {
        "original_image": url_for('static', filename='uploads/' + os.path.basename(image_path)),
        "preprocessed_image": save_image(cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR), "preprocessed"),
        "minimal_image": minimal_url,
        "final_image": final_url,
        "coords": final_points,
        "num_minimal_points": minimal_count,
        "num_final_points": final_count
    }
    return None, results

# ----------------------------
# Coordinate Conversion Utilities
# ----------------------------
def xy_to_latlon(x, y, home_lat, home_lon):
    """Convert XY meters offset from home position to latitude/longitude"""
    earth_radius = 6378137.0  # WGS84 equatorial radius in meters

    # Convert offsets to radians
    lat_offset = y / earth_radius
    lon_offset = x / (earth_radius * math.cos(math.radians(home_lat)))

    # Calculate new position
    lat = home_lat + math.degrees(lat_offset)
    lon = home_lon + math.degrees(lon_offset)

    return lat, lon


def latlon_to_xy(lat, lon, home_lat, home_lon):
    """Convert latitude/longitude to XY meters offset from home position"""
    earth_radius = 6378137.0  # WGS84 equatorial radius in meters

    # Convert to radians
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    home_lat_rad = math.radians(home_lat)
    home_lon_rad = math.radians(home_lon)

    # Calculate offsets in meters
    x = earth_radius * (lon_rad - home_lon_rad) * math.cos(home_lat_rad)
    y = earth_radius * (lat_rad - home_lat_rad)

    return x, y

def compute_distance(lat1, lon1, lat2, lon2):
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


# ----------------------------
# Drone Control Functions
# ----------------------------

def kill_processes_on_port(port, protocol="UDP"):
    """
    Find any processes listening on the given port & protocol and kill them.
    """
    try:
        # get PIDs listening on port
        cmd = f"lsof -t -i {protocol}:{port}"
        pids = subprocess.check_output(cmd, shell=True).decode().split()
        for pid in pids:
            os.kill(int(pid), signal.SIGTERM)
            logs.append(f"Killed leftover process {pid} on {protocol} port {port}")
    except subprocess.CalledProcessError:
        # no process found
        pass

async def connect_drone(system_address, i):
    logs.append(f"[{system_address}] Starting connection process…")
    drone = System(port=BASE_SYSTEM_PORT + i)
    await drone.connect(system_address=system_address)
    logs.append(f"[{system_address}] Connection attempt initiated…")

    # wait for connection
    connected = False
    start = time.time()
    while time.time() - start < CONNECT_TIMEOUT:
        async for state in drone.core.connection_state():
            if state.is_connected:
                connected = True
                break
        if connected:
            break
        await asyncio.sleep(0.1)
    if not connected:
        raise ConnectionError(f"Failed to connect to {system_address} after {CONNECT_TIMEOUT}s")

    logs.append(f"[{system_address}] Drone connected. Waiting for GPS…")
    # wait for global position OK
    gps_ok = False
    start = time.time()
    while time.time() - start < HEALTH_TIMEOUT:
        async for health in drone.telemetry.health():
            if health.is_global_position_ok:
                gps_ok = True
                break
        if gps_ok:
            break
        await asyncio.sleep(0.1)
    if not gps_ok:
        logs.append(f"[{system_address}] Warning: global_position not OK after {HEALTH_TIMEOUT}s")
    else:
        logs.append(f"[{system_address}] Global position OK.")

    # --- NEW: wait for home_position_ok too ---
    logs.append(f"[{system_address}] Waiting for home position…")
    home_ok = False
    start = time.time()
    while time.time() - start < HEALTH_TIMEOUT:
        async for health in drone.telemetry.health():
            if health.is_home_position_ok:
                home_ok = True
                break
        if home_ok:
            break
        await asyncio.sleep(0.2)
    if not home_ok:
        logs.append(f"[{system_address}] Warning: home_position not OK after {HEALTH_TIMEOUT}s")
    else:
        logs.append(f"[{system_address}] Home position OK.")

    return drone


async def arm_and_takeoff(drone, system_address, height):
    logs.append(f"[{system_address}] Attempting to arm...")

    # First ensure we can arm
    if not await ensure_drone_armed(drone._port - BASE_SYSTEM_PORT):
        raise Exception("Failed to arm after multiple attempts")

    logs.append(f"[{system_address}] Taking off...")
    try:
        await drone.action.set_takeoff_altitude(height)
        await drone.action.takeoff()

        # Monitor takeoff progress
        start_time = time.time()
        while time.time() - start_time < 10:  # 10 second timeout
            pos = await drone.telemetry.position().__anext__()
            if pos.relative_altitude_m >= height * 0.9:  # 90% of target
                break
            await asyncio.sleep(0.2)
        else:
            raise Exception("Takeoff timeout")

        logs.append(f"[{system_address}] Height {height} reached.")
    except Exception as e:
        logs.append(f"[{system_address}] Takeoff failed: {e}")
        raise


async def hold_position(drone, hold_time=3):
    try:
        pos = await drone.telemetry.position().__anext__()
        logs.append(f"Holding position at lat: {pos.latitude_deg:.6f}, lon: {pos.longitude_deg:.6f}, alt: {pos.absolute_altitude_m:.2f}")
        start_time = time.time()
        while time.time() - start_time < hold_time:
            await drone.action.hold()
            await asyncio.sleep(1)
    except Exception as e:
        logs.append(f"Error in hold_position: {e}")

async def land_and_disarm(drone, system_address):
    logs.append(f"[{system_address}] Initiating landing sequence...")
    try:
        await drone.offboard.stop()
        logs.append(f"[{system_address}] Offboard mode stopped.")
    except Exception as e:
        logs.append(f"[{system_address}] Error stopping offboard: {e}")
    logs.append(f"[{system_address}] Holding position for stabilization (3s)...")
    await hold_position(drone, hold_time=3)
    logs.append(f"[{system_address}] Landing...")
    await drone.action.land()
    async for position in drone.telemetry.position():
        if position.relative_altitude_m < THRESHOLD:
            break
    logs.append(f"[{system_address}] Disarming...")
    await drone.action.disarm()
    logs.append(f"[{system_address}] Landed and disarmed.")


# ----------------------------
# Health-check helper
# ----------------------------
async def check_drone_health(drone_id, attempts=10, interval=0.5):
    """
    Poll telemetry.health() up to `attempts` times.
    Return True only once global+home+armable are all OK.
    """
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        return False
    drone = instance["drone"]

    for _ in range(attempts):
        try:
            health = await drone.telemetry.health().__anext__()
            if (health.is_global_position_ok
                and health.is_home_position_ok
                and health.is_armable):
                return True
        except Exception:
            pass
        await asyncio.sleep(interval)

    logs.append(f"Drone {drone_id}: health check FAILED after {attempts} attempts")
    return False



async def ensure_drone_armed(drone_id, max_attempts=3):
    """Ensure drone is armed with retry logic"""
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        return False

    for attempt in range(max_attempts):
        try:
            await instance["drone"].action.arm()
            return True
        except Exception as e:
            logs.append(f"Drone {drone_id} arming attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)
    return False


async def respawn_and_reconnect(drone_id):
    """
    High-level: respawn, wait for connect, then restart status monitor.
    """
    respawn_drone(drone_id)
    if spawn_and_wait(drone_id, base=(drone_id == 0)):
        logs.append(f"Drone {drone_id} successfully respawned & connected")
        run_async(update_drone_status(drone_id))
    else:
        logs.append(f"Drone {drone_id} respawn FAILED")




def respawn_drone(drone_id):
    """Cleanly respawn a drone, killing any stale listeners first."""
    logs.append(f"Attempting to respawn drone {drone_id}")

    # 1) Kill any leftover SITL or server on those ports
    kill_processes_on_port(BASE_MAVLINK_PORT + drone_id, protocol="UDP")
    kill_processes_on_port(BASE_SYSTEM_PORT + drone_id, protocol="TCP")

    # 2) Tear down any existing instance
    if drone_id in drone_instances:
        inst = drone_instances.pop(drone_id)
        for proc_key in ("sitl_proc", "mavsdk_server_proc"):
            proc = inst.get(proc_key)
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                    logs.append(f"Terminated old {proc_key} for drone {drone_id}")
                except Exception as e:
                    logs.append(f"Error terminating old {proc_key} for drone {drone_id}: {e}")

    # 3) Give ports a moment to free
    time.sleep(1.0)

    # 4) Spawn fresh instance
    spawn_drone(drone_id, base=(drone_id == 0))



async def update_drone_status(drone_id):
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        logs.append(f"Drone {drone_id}: No drone instance for status updates.")
        return

    drone = instance["drone"]

    # Initialize home position if not set
    if not instance.get("home_position"):
        try:
            home = await drone.telemetry.home().__anext__()
            instance["home_position"] = (
                home.latitude_deg,
                home.longitude_deg,
                home.absolute_altitude_m
            )
            logs.append(
                f"Drone {drone_id}: Home set → "
                f"lat={home.latitude_deg:.6f}, lon={home.longitude_deg:.6f}"
            )
        except:
            pos = await drone.telemetry.position().__anext__()
            instance["home_position"] = (
                pos.latitude_deg,
                pos.longitude_deg,
                pos.absolute_altitude_m
            )
            logs.append(
                f"Drone {drone_id}: Fallback home → "
                f"lat={pos.latitude_deg:.6f}, lon={pos.longitude_deg:.6f}"
            )

    home_lat, home_lon, home_alt = instance["home_position"]
    prev_log = time.time()

    while True:
        try:
            # 1) Telemetry snapshots
            pos    = await drone.telemetry.position().__anext__()
            health = await drone.telemetry.health().__anext__()
            # 2) Detailed health logging
            logs.append(
                f"[Drone {drone_id} Health] "
                f"global_ok={health.is_global_position_ok}, "
                f"home_ok={health.is_home_position_ok}, "
                f"armable={health.is_armable}"
            )

            # 3) Only respawn on lost GPS
            if not health.is_global_position_ok:
                logs.append(
                    f"Drone {drone_id}: Lost GPS "
                    f"(global_ok={health.is_global_position_ok}) → respawning"
                )
                respawn_and_reconnect(drone_id)
                return

            # 4) Wait for home + armable without respawning
            if not (health.is_home_position_ok and health.is_armable):
                logs.append(
                    f"Drone {drone_id}: waiting for home/armable; "
                    f"home_ok={health.is_home_position_ok}, "
                    f"armable={health.is_armable}"
                )
                await asyncio.sleep(0.5)
                continue

            # 5) Other telemetry
            battery     = await drone.telemetry.battery().__anext__()
            flight_mode = await drone.telemetry.flight_mode().__anext__()
            in_air      = await drone.telemetry.in_air().__anext__()

            # Compute local offsets
            x, y = latlon_to_xy(
                pos.latitude_deg, pos.longitude_deg,
                home_lat, home_lon
            )
            z = pos.relative_altitude_m

            # Distances
            h_dist = math.hypot(x, y)
            d3     = math.sqrt(x*x + y*y + z*z)

            # Speed estimate
            if 'last_xy' in instance and 'last_time' in instance:
                dt = time.time() - instance['last_time']
                if dt > 0:
                    lx, ly = instance['last_xy']
                    speed = math.hypot(x-lx, y-ly) / dt
                    instance["speed"] = f"{speed:.2f} m/s"

            # Save for next iteration
            instance['last_xy']   = (x, y)
            instance['last_time'] = time.time()

            # Update status dict
            instance.update({
                "position": {
                    "latlon": f"Lat: {pos.latitude_deg:.6f}, Lon: {pos.longitude_deg:.6f}",
                    "xyz":    f"X: {x:.2f}m, Y: {y:.2f}m, Z: {z:.2f}m"
                },
                "battery":            f"{battery.remaining_percent*100:.1f}%",
                "status":             flight_mode.name,
                "distance_from_home": f"{h_dist:.2f}m (3D: {d3:.2f}m)",
                "in_air":             in_air
            })

            # Periodic detailed logging
            now = time.time()
            if now - prev_log >= LOG_INTERVAL:
                logs.append(
                    f"[Drone {drone_id}] "
                    f"X={x:.2f} Y={y:.2f} Z={z:.2f} | "
                    f"Dist={h_dist:.2f}m | "
                    f"Battery={instance['battery']} | "
                    f"Mode={flight_mode.name} | "
                    f"InAir={in_air}"
                )
                prev_log = now

            await asyncio.sleep(0.2)

        except Exception as ex:
            logs.append(f"Drone {drone_id}: Error in status loop: {ex}")
            await asyncio.sleep(1)




async def move_relative(drone_id, dx, dy, dz):
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        logs.append(f"Drone {drone_id} not connected for move_relative!")
        return
    drone = instance["drone"]
    current_pos = await drone.telemetry.position().__anext__()
    base_lat = current_pos.latitude_deg
    base_lon = current_pos.longitude_deg
    alt = current_pos.absolute_altitude_m
    new_lat, new_lon = xy_to_latlon(dx, dy, base_lat, base_lon)
    logs.append(f"Drone {drone_id} -> MoveRelative: target lat={new_lat:.6f}, lon={new_lon:.6f}, alt={alt+dz:.2f}")
    await drone.action.goto_location(new_lat, new_lon, alt+dz, 0)
    instance["status"] = "Moving"

async def velocity_control(drone_id, vx, vy, vz, yaw=0):
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        logs.append(f"Drone {drone_id} not connected for velocity_control!")
        return
    drone = instance["drone"]
    try:
        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(vx, vy, vz, yaw))
        if not instance.get("offboard_active", False):
            await drone.offboard.start()
            instance["offboard_active"] = True
            logs.append(f"Drone {drone_id}: Offboard mode started.")
        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(vx, vy, vz, yaw))
        logs.append(f"Drone {drone_id}: Velocity (body) set -> vx={vx}, vy={vy}, vz={vz}, yaw={yaw}")
        instance["status"] = "Velocity Control"
    except OffboardError as e:
        logs.append(f"Drone {drone_id}: Offboard error: {e}")
        instance["status"] = "Error"

async def stop_velocity_control(drone_id):
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        return
    if instance.get("offboard_active", False):
        try:
            await instance["drone"].offboard.stop()
            instance["offboard_active"] = False
            logs.append(f"Drone {drone_id}: Offboard mode stopped, now hovering.")
            instance["status"] = "Hovering"
        except Exception as e:
            logs.append(f"Drone {drone_id}: Error stopping offboard: {e}")

async def return_home(drone_id):
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        logs.append(f"Drone {drone_id} not connected. Cannot return home.")
        return
    drone = instance["drone"]
    start_wait = time.time()
    while instance.get("home_position") is None and (time.time() - start_wait) < 10:
        logs.append(f"Drone {drone_id}: Waiting for home position to be set...")
        await asyncio.sleep(1.0)
    home = instance.get("home_position")
    if not home:
        logs.append(f"Drone {drone_id}: Home position not set after waiting. Aborting Return Home.")
        return
    home_lat, home_lon, _ = home
    try:
        current_pos = await drone.telemetry.position().__anext__()
        current_alt = current_pos.absolute_altitude_m
        logs.append(f"Drone {drone_id}: Returning home to lat={home_lat:.6f}, lon={home_lon:.6f} at alt={current_alt:.2f}")
        await drone.action.goto_location(home_lat, home_lon, current_alt, 0)
        while True:
            pos = await drone.telemetry.position().__anext__()
            if abs(pos.latitude_deg - home_lat) < 0.00001 and abs(pos.longitude_deg - home_lon) < 0.00001:
                logs.append(f"Drone {drone_id}: Reached home vicinity. Holding before landing.")
                await hold_position(drone, hold_time=3)
                logs.append(f"Drone {drone_id}: Initiating landing...")
                break
        await drone.action.land()
        async for position in drone.telemetry.position():
            if position.relative_altitude_m < THRESHOLD:
                logs.append(f"Drone {drone_id}: Landed at home location.")
                instance["status"] = "Landed"
                break
    except Exception as e:
        logs.append(f"Drone {drone_id}: Error returning home: {e}")
        instance["status"] = "Error"

async def arm_takeoff(drone_id, altitude):
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        logs.append(f"Drone {drone_id} not available for takeoff.")
        return
    drone = instance["drone"]
    system_address = instance["system_address"]
    try:
        await arm_and_takeoff(drone, system_address, altitude)
        instance["status"] = "Hovering"
    except Exception as e:
        logs.append(f"Takeoff failed for drone {drone_id}: {e}")
        instance["status"] = "Error"

async def land_and_disarm_async(drone_id):
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        logs.append(f"Drone {drone_id} not available for landing.")
        return
    drone = instance["drone"]
    system_address = instance["system_address"]
    try:
        await land_and_disarm(drone, system_address)
        instance["status"] = "Landed"
    except Exception as e:
        logs.append(f"Landing failed for drone {drone_id}: {e}")
        instance["status"] = "Error"

async def move_drone_to_position(drone_id, lat, lon, alt):
    instance = drone_instances.get(drone_id)
    if not instance or not instance["drone"]:
        logs.append(f"Drone {drone_id} not available for formation move.")
        return
    drone = instance["drone"]
    if instance.get("status") != "Hovering":
        logs.append(f"Drone {drone_id} is not airborne. Initiating takeoff before formation move.")
        await arm_takeoff(drone_id, formation_controller.base_altitude)
        await asyncio.sleep(3)
    logs.append(f"Drone {drone_id}: Moving to formation position lat={lat:.6f}, lon={lon:.6f}, alt={alt:.2f}")
    await drone.action.goto_location(lat, lon, alt, 0)
    instance["status"] = "Moving to Formation"

# ----------------------------
# Drone Spawning & Process Handling
# ----------------------------
def read_output(drone_id, proc, label):
    for line in proc.stdout:
        logs.append(f"Drone {drone_id} [{label}]: {line.strip()}")

def spawn_drone(drone_id, base=False):
    if not base:
        time.sleep(SPAWN_DELAY)
    # ensure clean ports on first attempt
    kill_processes_on_port(BASE_MAVLINK_PORT + drone_id, protocol="UDP")
    kill_processes_on_port(BASE_SYSTEM_PORT + drone_id, protocol="TCP")
    mavlink_port = BASE_MAVLINK_PORT + drone_id
    system_address = f"udp://:{mavlink_port}"
    env_vars = os.environ.copy()
    env_vars["MAVLINK_UDP_BIND_PORT"] = str(mavlink_port)
    env_vars["MAV_SYS_ID"] = str(drone_id + 1)
    if not base:
        env_vars["HEADLESS"] = "1"
    env_vars["PX4_GZ_MODEL_POSE"] = f"0,{drone_id}"
    cmd_sitl = f"./build/px4_sitl_default/bin/px4 -i {drone_id}"
    logs.append(f"Spawning drone {drone_id}: {cmd_sitl} (MAVLink port: {mavlink_port})")
    sitl_proc = subprocess.Popen(cmd_sitl, cwd=PX4_ROOT, env=env_vars, shell=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    cmd_server = f"{MAVSDK_SERVER_PATH} udpin://:{mavlink_port} -p {BASE_SYSTEM_PORT + drone_id}"
    logs.append(f"Launching mavsdk_server for drone {drone_id}: {cmd_server}")
    server_proc = subprocess.Popen(cmd_server, cwd=PX4_ROOT, shell=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    drone_instances[drone_id] = {
        "sitl_proc": sitl_proc,
        "mavsdk_server_proc": server_proc,
        "mavlink_port": mavlink_port,
        "system_address": system_address,
        "drone": None,
        "status": "Initializing",
        "position": {"latlon": "Initializing...", "xyz": "Initializing..."},
        "battery": "N/A",
        "offboard_active": False,
        "home_position": None,
        "speed": "0.00 m/s",
        "distance_from_home": "0.00 m"
    }
    logs.append(f"Drone {drone_id}: SITL + mavsdk_server processes started.")
    threading.Thread(target=read_output, args=(drone_id, sitl_proc, "SITL"), daemon=True).start()
    threading.Thread(target=read_output, args=(drone_id, server_proc, "mavsdk_server"), daemon=True).start()
    def connect_and_monitor():
        try:
            drone = run_async(connect_drone(system_address, drone_id))
            drone_instances[drone_id]["drone"] = drone
            drone_instances[drone_id]["status"] = "Connected"
            run_async(update_drone_status(drone_id))
        except Exception as e:
            logs.append(f"Drone {drone_id} - connect_and_monitor failed: {e}")
            drone_instances[drone_id]["status"] = f"Error: {e}"
    threading.Thread(target=connect_and_monitor, daemon=True).start()

def spawn_and_wait(drone_id, base=False):
    if not base:
        time.sleep(SPAWN_DELAY)
    spawn_drone(drone_id, base=base)
    start = time.time()
    while time.time() - start < CONNECT_TIMEOUT:
        if drone_instances[drone_id]["status"] == "Connected":
            logs.append(f"[Spawn] Drone {drone_id} CONNECTED after {time.time()-start:.1f}s")
            return True
        time.sleep(0.2)
    logs.append(f"[Spawn] TIMEOUT waiting for drone {drone_id}")
    return False

def cleanup():
    logs.append("Cleaning up all drone processes...")
    for did, inst in list(drone_instances.items()):
        try:
            inst["sitl_proc"].terminate()
            inst["mavsdk_server_proc"].terminate()
        except Exception as e:
            logs.append(f"Error terminating drone {did}: {e}")

# ----------------------------
# Flask Endpoints
# ----------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    processing_results = None
    if request.method == 'POST':
        if 'toggle_mode' in request.form:
            global current_mode
            current_mode = "manual" if current_mode == "formation" else "formation"
            logs.append(f"Switched to {current_mode} mode")
        elif 'image' in request.files:
            file = request.files.get('image')
            if file and file.filename != '':
                filename = str(uuid.uuid4()) + os.path.splitext(file.filename)[1]
                upload_path = os.path.join(UPLOAD_FOLDER, filename)
                try:
                    file.save(upload_path)
                except Exception as e:
                    return f"Failed to save image: {e}", 500
                try:
                    num_drones_input = request.form.get('num_drones', '').strip()
                    num_drones = int(num_drones_input) if num_drones_input else None
                except ValueError:
                    return "Invalid numeric input", 400
                _, processing_results = process_image(upload_path, desired_num_drones=num_drones)

    extra_script = ""
    if processing_results:
        extra_script = "<script>window.processedCoordinates = " + json.dumps(processing_results['coords']) + ";</script>"

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Drone Control System</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }
            .container { max-width: 1200px; margin: auto; background: white; padding: 20px; border-radius: 8px; }
            h1 { text-align: center; }
            .mode-toggle { text-align: center; margin-bottom: 20px; }
            .mode-toggle button { padding: 10px 20px; font-size: 16px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; }
            .mode-toggle button:hover { background: #2980b9; }
            .mode-indicator { display: inline-block; padding: 5px 10px; margin-left: 10px; border-radius: 3px; font-weight: bold; }
            .formation { background-color: #d4edda; color: #155724; }
            .manual { background-color: #fff3cd; color: #856404; }
            .section { margin-bottom: 30px; border-top: 1px solid #ccc; padding-top: 20px; }
            .form-group { margin-bottom: 10px; }
            label { display: block; margin-bottom: 5px; }
            input[type="file"], input[type="number"] { width: 100%; padding: 8px; }
            button { padding: 10px 15px; margin-top: 10px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #2980b9; }
            .images img { max-width: 200px; margin-right: 10px; }
            .log-container { background-color: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; max-height: 300px; overflow-y: auto; font-family: monospace; }
            .joystick-controls { background-color: #f0f0f0; padding: 15px; border-radius: 5px; margin: 20px 0; }
            .joystick-grid { display: grid; grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 1fr); gap: 10px; max-width: 300px; margin: 0 auto; }
            .joystick-btn { padding: 15px; font-size: 1.2em; text-align: center; background-color: #3498db; color: white; border: none; border-radius: 5px; cursor: pointer; }
            .joystick-btn:hover { background-color: #2980b9; }
            .joystick-btn:active { background-color: #1d6fa5; }
            .joystick-center { grid-column: 2; grid-row: 2; background-color: #7f8c8d; }
            .joystick-up { grid-column: 2; grid-row: 1; }
            .joystick-down { grid-column: 2; grid-row: 3; }
            .joystick-left { grid-column: 1; grid-row: 2; }
            .joystick-right { grid-column: 3; grid-row: 2; }
            .drone-card { background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 5px; padding: 15px; margin-bottom: 15px; }
            .drone-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
            .drone-id { font-weight: bold; font-size: 1.2em; color: #3498db; }
            .drone-status { padding: 5px 10px; border-radius: 3px; font-weight: bold; }
            .status-connected { background-color: #d4edda; color: #155724; }
            .status-initializing { background-color: #fff3cd; color: #856404; }
            .status-error { background-color: #f8d7da; color: #721c24; }
            .drone-info { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 15px; }
            .info-box { background-color: white; border: 1px solid #eee; padding: 10px; border-radius: 4px; min-height: 60px; }
            .info-label { font-size: 0.8em; color: #7f8c8d; margin-bottom: 5px; }
            .info-value { font-size: 1.1em; }
            .control-form { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
            .form-group { display: flex; align-items: center; gap: 5px; }
            input[type="text"], input[type="number"] { padding: 5px; border: 1px solid #ddd; border-radius: 3px; width: 60px; }
            button.danger { background-color: #e74c3c; }
            button.danger:hover { background-color: #c0392b; }
            button.success { background-color: #2ecc71; }
            button.success:hover { background-color: #27ae60; }
            .log-entry { margin-bottom: 5px; border-bottom: 1px solid #34495e; padding-bottom: 5px; }
            .add-drone-btn { background-color: #2ecc71; padding: 10px 15px; font-size: 1.1em; margin-bottom: 20px; }
            .control-selector { margin: 10px 0; padding: 8px; border-radius: 4px; border: 1px solid #ddd; }
            .control-section { margin-top: 20px; padding: 15px; background-color: #f0f7ff; border-radius: 5px; }
            .hidden { display: none; }
            .controls-wrapper {
                display: flex;
                gap: 20px;              /* space between them */
                align-items: flex-start;/* top-align the headings/buttons */
            }
            .controls-wrapper .control-section {
                flex: 1;                /* each takes equal share */
                box-sizing: border-box; /* so padding/margins don’t blow out the width */
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Drone Control System</h1>
            <div class="mode-toggle">
                <form action="/" method="post">
                    <button type="submit" name="toggle_mode">Switch Mode</button>
                    <span class="mode-indicator {{ current_mode }}">{{ current_mode|capitalize }} Mode</span>
                </form>
            </div>

            <div id="formation-section" class="{{ 'hidden' if current_mode == 'manual' else '' }}">
                <h2>Formation Control</h2>
                <form method="post" enctype="multipart/form-data">
                    <div class="form-group">
                        <label for="image">Select Image:</label>
                        <input type="file" name="image" id="image">
                    </div>
                    <div class="form-group">
                        <label for="num_drones">Desired Number of Drones (optional):</label>
                        <input type="number" name="num_drones" id="num_drones" min="1" placeholder="Leave blank for minimal structure">
                    </div>
                    <button type="submit">Process Image</button>
                </form>
                {% if processing_results %}
                    <div class="images" style="margin-top:20px;">
                        <div><strong>Original:</strong> <img src="{{ processing_results.original_image }}"></div>
                        <div><strong>Preprocessed:</strong> <img src="{{ processing_results.preprocessed_image }}"></div>
                        <div><strong>Minimal Dots:</strong> <img src="{{ processing_results.minimal_image }}"></div>
                        <div><strong>Final Dots:</strong> <img src="{{ processing_results.final_image }}"></div>
                    </div>
                    <div>
                        <p>Number of Minimal Points: {{ processing_results.num_minimal_points }}</p>
                        <p>Number of Final Points: {{ processing_results.num_final_points }}</p>
                        <p>Coordinates:</p>
                        <ul>
                            {% for pt in processing_results.coords %}
                                <li>({{ pt[0] }}, {{ pt[1] }})</li>
                            {% endfor %}
                        </ul>
                    </div>
                    <script>
                        // Store the processed coordinates in a format the frontend can use
                        window.processedCoordinates = {{ processing_results.coords|tojson|safe }};
                    </script>
                {% endif %}

                <div class="section">
                    <div class="form-group">
                        <label for="formation-scale">Scale (m/pixel):</label>
                        <input type="number" id="formation-scale" step="0.1" value="0.1" min="0.01">
                    </div>
                    <div class="form-group">
                        <label for="formation-altitude">Base Altitude (m):</label>
                        <input type="number" id="formation-altitude" step="0.1" value="5.0" min="5.0">
                    </div>
                    <div class="form-group">
                        <label for="formation-depth">Formation Depth (m):</label>
                        <input type="number" id="formation-depth" step="0.1" value="10.0" min="1.0">
                    </div>
                    <button onclick="setFormation()">Set Formation from Image Points</button>
                    <button onclick="makeFormation()">Make Formation</button>
                    <button onclick="returnAllHome()">Return All Home</button>


                </div>
            </div>

            <div id="manual-section" class="{{ 'hidden' if current_mode == 'formation' else '' }}">
                <h2>Manual Control</h2>
                <form action="/add" method="post">
                    <button type="submit" class="add-drone-btn">➕ Add New Drone</button>
                </form>

                <div class="control-section">
                    <h3>Drone Selection</h3>
                    <div class="form-group">
                        <label for="drone-select">Control Drone:</label>
                        <select id="drone-select" class="control-selector">
                            {% for did in drone_instances.keys() %}
                            <option value="{{ did }}" {% if did == current_controlled_drone %}selected{% endif %}>
                                Drone {{ did }}
                            </option>
                            {% endfor %}
                        </select>
                    </div>
                </div>

                <div class = "controls-wrapper">


                    <div class="control-section">
                        <h3>Position Control</h3>
                        <div class="joystick-controls">
                            <div class="joystick-grid">
                                <button class="joystick-btn joystick-up" onclick="moveDrone(0, 1, 0)">↑</button>
                                <button class="joystick-btn joystick-left" onclick="moveDrone(-1, 0, 0)">←</button>
                                <div class="joystick-btn joystick-center" onclick="stopVelocity()">STOP</div>
                                <button class="joystick-btn joystick-right" onclick="moveDrone(1, 0, 0)">→</button>
                                <button class="joystick-btn joystick-down" onclick="moveDrone(0, -1, 0)">↓</button>
                            </div>
                            <div style="margin-top: 15px; text-align: center;">
                                <button class="joystick-btn" onclick="moveDrone(0, 0, 1)">UP</button>
                                <button class="joystick-btn" onclick="moveDrone(0, 0, -1)">DOWN</button>
                            </div>
                        </div>
                    </div>

                    <div class="control-section">
                        <h3>Velocity Control</h3>
                        <div class="joystick-controls">
                            <div class="joystick-grid">
                                <button class="joystick-btn joystick-up" onmousedown="startVelocity(0, 1, 0)" onmouseup="stopVelocity()">↑</button>
                                <button class="joystick-btn joystick-left" onmousedown="startVelocity(-1, 0, 0)" onmouseup="stopVelocity()">←</button>
                                <div class="joystick-btn joystick-center" onclick="stopVelocity()">STOP</div>
                                <button class="joystick-btn joystick-right" onmousedown="startVelocity(1, 0, 0)" onmouseup="stopVelocity()">→</button>
                                <button class="joystick-btn joystick-down" onmousedown="startVelocity(0, -1, 0)" onmouseup="stopVelocity()">↓</button>
                            </div>
                            <div style="margin-top: 15px; text-align: center;">
                                <button class="joystick-btn" onmousedown="startVelocity(0, 0, 1)" onmouseup="stopVelocity()">UP</button>
                                <button class="joystick-btn" onmousedown="startVelocity(0, 0, -1)" onmouseup="stopVelocity()">DOWN</button>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="control-section">
                    <h3>Precise Movement</h3>
                    <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                        <div class="form-group">
                            <label>X (m):</label>
                            <input type="number" id="move-x" step="0.1" value="1.0" style="width: 60px;">
                        </div>
                        <div class="form-group">
                            <label>Y (m):</label>
                            <input type="number" id="move-y" step="0.1" value="1.0" style="width: 60px;">
                        </div>
                        <div class="form-group">
                            <label>Z (m):</label>
                            <input type="number" id="move-z" step="0.1" value="1.0" style="width: 60px;">
                        </div>
                    </div>
                    <button onclick="preciseMove()" class="success">Move Precise Distance</button>
                </div>

                <div class="control-section">
                    <h3>Return Home</h3>
                    <button onclick="returnHome()" class="success">Return Home</button>
                </div>
            </div>

            <div class="section">
                <h2>Connected Drones</h2>
                <div id="drones-container">
                    {% for did, inst in drone_instances.items() %}
                    <div class="drone-card" data-drone-id="{{ did }}">
                        <div class="drone-header">
                            <span class="drone-id">Drone #{{ did }}</span>
                            <span class="drone-status status-{{ inst.status|lower }}">
                                {{ inst.status }}
                            </span>
                        </div>

                        <div class="drone-info">
                            <div class="info-box">
                                <div class="info-label">Position (Lat/Lon)</div>
                                <div class="info-value">
                                    {{ inst.position.latlon if inst.position and inst.position.latlon else 'N/A' }}
                                </div>
                            </div>
                            <div class="info-box">
                                <div class="info-label">Position (X/Y/Z)</div>
                                <div class="info-value">
                                    {{ inst.position.xyz if inst.position and inst.position.xyz else 'N/A' }}
                                </div>
                            </div>
                            <div class="info-box">
                                <div class="info-label">Speed/Distance</div>
                                <div class="info-value">
                                    {{ inst.speed if inst.speed else '0.00 m/s' }}<br>
                                    {{ inst.distance_from_home if inst.distance_from_home else '0.00 m' }} from home
                                </div>
                            </div>
                            <div class="info-box">
                                <div class="info-label">MAVLink Port</div>
                                <div class="info-value">{{ inst.mavlink_port }}</div>
                            </div>
                            <div class="info-box">
                                <div class="info-label">Battery</div>
                                <div class="info-value">{{ inst.battery }}</div>
                            </div>
                        </div>
                        <div class="control-form">
                            <form action="/takeoff" method="post">
                                <input type="hidden" name="drone_id" value="{{ did }}">
                                <div class="form-group">
                                    <label>Altitude:</label>
                                    <input type="text" name="altitude" value="5" size="3">
                                    <button type="submit" class="success">Take Off</button>
                                </div>
                            </form>
                            <form action="/land" method="post">
                                <input type="hidden" name="drone_id" value="{{ did }}">
                                <button type="submit" class="danger">Land</button>
                            </form>
                            <form action="/remove" method="post">
                                <input type="hidden" name="drone_id" value="{{ did }}">
                                <button type="submit" class="danger">Remove Drone</button>
                            </form>
                            <form action="/respawn" method="post" style="display:inline">
                                <input type="hidden" name="drone_id" value="{{ did }}">
                                <button type="submit" class="danger">🛠️ Respawn</button>
                            </form>

                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <div class="section">
                <h2>System Logs</h2>
                <div id="log-container" class="log-container">
                    {% for line in logs[-100:] %}
                    <div class="log-entry">{{ line }}</div>
                    {% endfor %}
                </div>
            </div>
        </div>
        <script>
            const evtSource = new EventSource("/stream");
            let current_controlled_drone = {{ current_controlled_drone }};

            // Mode-specific functions
            function setFormation() {
                // Check if we have processed coordinates
                if (!window.processedCoordinates || window.processedCoordinates.length === 0) {
                    alert("Please upload and process an image first!");
                    return;
                }

                // Convert coordinates to the format expected by the backend
                const points = window.processedCoordinates.map(pt => ({x: pt[0], y: pt[1]}));

                const scale = parseFloat(document.getElementById('formation-scale').value);
                const altitude = parseFloat(document.getElementById('formation-altitude').value);
                const depth = parseFloat(document.getElementById('formation-depth').value);

                fetch('/set_formation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        points: points,
                        scale: scale,
                        base_altitude: altitude,
                        depth: depth
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        alert(`Error: ${data.error}`);
                    } else {
                        alert(`Formation set with ${data.num_points} points`);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Failed to set formation');
                });
            }


            function makeFormation() {
                fetch('/make_formation', { method: 'POST' })
                .then(response => response.json())
                .then(data => { alert(data.status); })
                .catch(error => { console.error('Error:', error); alert('Failed to make formation'); });
            }

            function returnAllHome() {
                fetch('/return_all_home', { method: 'POST' })
                .then(response => response.json())
                .then(data => { alert(data.status); })
                .catch(error => { console.error('Error:', error); alert('Failed to return home'); });
            }

            // Manual control functions
            function moveDrone(dx, dy, dz) {
                const sel = document.getElementById('drone-select');
                const drone_id = parseInt(sel.value);
                fetch('/move_relative', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drone_id: drone_id,
                        dx: dx * {{ MOVE_DISTANCE }},
                        dy: dy * {{ MOVE_DISTANCE }},
                        dz: dz * {{ MOVE_DISTANCE }}
                    })
                });
            }

            function startVelocity(vx, vy, vz) {
                const sel = document.getElementById('drone-select');
                const drone_id = parseInt(sel.value);
                fetch('/start_velocity', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drone_id: drone_id,
                        vx: vx * {{ MOVE_SPEED }},
                        vy: vy * {{ MOVE_SPEED }},
                        vz: vz * {{ MOVE_SPEED }}
                    })
                });
            }

            function stopVelocity() {
                const sel = document.getElementById('drone-select');
                const drone_id = parseInt(sel.value);
                fetch('/stop_velocity', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ drone_id: drone_id })
                });
            }

            function preciseMove() {
                const sel = document.getElementById('drone-select');
                const drone_id = parseInt(sel.value);
                const x = parseFloat(document.getElementById('move-x').value);
                const y = parseFloat(document.getElementById('move-y').value);
                const z = parseFloat(document.getElementById('move-z').value);
                fetch('/move_precise', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        drone_id: drone_id,
                        x: x,
                        y: y,
                        z: z
                    })
                });
            }

            function returnHome() {
                const sel = document.getElementById('drone-select');
                const drone_id = parseInt(sel.value);
                fetch('/return_home', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ drone_id: drone_id })
                });
            }

            // Update UI with SSE data
            evtSource.onmessage = function(e) {
                const data = JSON.parse(e.data);

                // Update drone status cards
                for (const [drone_id, drone_data] of Object.entries(data.drones)) {
                    const droneElement = document.querySelector(`.drone-card[data-drone-id="${drone_id}"]`);
                    if (!droneElement) continue;

                    // Update status text + CSS class
                    const statusElement = droneElement.querySelector('.drone-status');
                    statusElement.textContent = drone_data.status;
                    statusElement.className = 'drone-status status-' + drone_data.status.toLowerCase();

                    // Position, Battery, Speed
                    const positionBoxes = droneElement.querySelectorAll('.info-value');
                    if (positionBoxes.length >= 3) {
                        positionBoxes[0].textContent = drone_data.position.latlon || 'N/A';
                        positionBoxes[1].textContent = drone_data.position.xyz || 'N/A';
                        positionBoxes[2].innerHTML =
                            (drone_data.speed || '0.00 m/s') + '<br>' +
                            (drone_data.distance_from_home || '0.00 m') + ' from home';
                    }
                    if (positionBoxes.length >= 5) {
                        positionBoxes[4].textContent = drone_data.battery || 'Unknown';
                    }
                }

                // Update logs
                const logContainer = document.querySelector('.log-container');
                logContainer.innerHTML = data.logs.map(log => `<div class="log-entry">${log}</div>`).join('');

                // Update drone selector dropdown
                updateDroneSelector();
            };

            function updateDroneSelector() {
                const sel = document.getElementById('drone-select');
                const currentOpts = Array.from(sel.options).map(o => parseInt(o.value));
                const currentDrones = Object.keys(drone_instances).map(Number);

                if (JSON.stringify(currentOpts.sort()) !== JSON.stringify(currentDrones.sort())) {
                    sel.innerHTML = currentDrones.map(did =>
                        `<option value="${did}" ${did == current_controlled_drone ? 'selected' : ''}>
                            Drone ${did}
                        </option>`
                    ).join('');
                }
            }

            document.getElementById('drone-select').addEventListener('change', function() {
                current_controlled_drone = parseInt(this.value);
                fetch('/set_controlled_drone', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ drone_id: current_controlled_drone })
                });
            });
        </script>
        """ + extra_script + """
    </body>
    </html>
    """
    return render_template_string(
        html,
        current_mode=current_mode,
        processing_results=processing_results,
        drone_instances=drone_instances,
        logs=logs[-100:],
        current_controlled_drone=current_controlled_drone,
        MOVE_DISTANCE=MOVE_DISTANCE,
        MOVE_SPEED=MOVE_SPEED
    )



@app.route('/set_formation', methods=['POST'])
def set_formation_endpoint():
    try:
        data = request.get_json()
        if not data:
            return jsonify(error="No data received"), 400

        pts = data.get('points', [])
        if not pts:
            return jsonify(error="No formation points provided"), 400

        # Convert points to consistent format
        clean = []
        for p in pts:
            if isinstance(p, dict):
                # Handle {x, y} format
                if 'x' in p and 'y' in p:
                    clean.append((float(p['x']), float(p['y'])))
                else:
                    return jsonify(error="Invalid point format - expected {x, y}"), 400
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                # Handle [x, y] format
                clean.append((float(p[0]), float(p[1])))
            else:
                return jsonify(error=f"Invalid point format: {p}"), 400

        scale = float(data.get('scale', 1.0))
        base_alt = max(float(data.get('base_altitude', 5.0)), 5.0)
        depth = float(data.get('depth', 10.0))

        # Validate parameters
        if scale <= 0:
            return jsonify(error="Scale must be positive"), 400
        if depth <= 0:
            return jsonify(error="Depth must be positive"), 400

        count = formation_controller.set_formation_from_image(clean, scale, base_alt, depth)

        # Spawn drones if needed
        for drone_id in range(len(drone_instances), count):
            if not spawn_and_wait(drone_id, base=(drone_id == 0)):
                break

        return jsonify(num_points=count)

    except Exception as e:
        logging.error(f"Error in set_formation: {str(e)}", exc_info=True)
        return jsonify(error=f"Internal server error: {str(e)}"), 500

@app.route('/make_formation', methods=['POST'])
def make_formation_endpoint():
    base = drone_instances.get(0)
    if not base or base.get('home_position') is None:
        return jsonify(
            status="Error: Drone 0 home not set. Spawn & connect first.",
            num_drones=0
        ), 400

    try:
        poses = formation_controller.get_formation_positions(*base['home_position'])
    except Exception as e:
        return jsonify(
            status=f"Error: {e}",
            num_drones=0
        ), 500

    # inside your make_formation_endpoint(), replace ensure_and_move with this:

    def ensure_and_move(d_id, lat, lon, alt):
        """
        Try to arm & takeoff up to 2 times. On failure, kill leftovers, respawn & retry.
        Returns True on success, False otherwise.
        """
        for attempt in range(1, 3):
            inst = drone_instances.get(d_id)
            # 1) If never connected or lost connection, respawn from scratch
            if not inst or inst.get("drone") is None:
                logs.append(f"[Attempt {attempt}] Drone {d_id}: no connection → respawning")
                respawn_drone(d_id)
                if not spawn_and_wait(d_id, base=(d_id == 0)):
                    logs.append(f"[Attempt {attempt}] Drone {d_id}: spawn failed")
                    continue

            # 2) Give the new instance a moment to initialize
            time.sleep(1.0)

            # 3) Wait for all health flags
            start = time.time()
            while time.time() - start < HEALTH_TIMEOUT:
                health_ok = run_async(check_drone_health(d_id))
                if health_ok:
                    break
                # log missing flags
                h = run_async(drone_instances[d_id]["drone"].telemetry.health().__anext__())
                logs.append(
                    f"[Attempt {attempt}] Drone {d_id} health: "
                    f"global={h.is_global_position_ok}, "
                    f"home={h.is_home_position_ok}, "
                    f"armable={h.is_armable}"
                )
                time.sleep(1.0)
            else:
                logs.append(f"[Attempt {attempt}] Drone {d_id}: health timeout → retrying")
                continue

            # 4) Arm & takeoff
            try:
                logs.append(f"[Attempt {attempt}] Drone {d_id}: arming & takeoff to {alt}m")
                run_async(arm_takeoff(d_id, alt))

                # 5) Verify altitude
                pos = run_async(drone_instances[d_id]["drone"]
                                .telemetry.position().__anext__())
                if pos.relative_altitude_m < alt * 0.8:
                    raise RuntimeError(f"only reached {pos.relative_altitude_m:.1f}m")

                # 6) Move into formation
                run_async(move_drone_to_position(d_id, lat, lon, alt))
                logs.append(f"[Attempt {attempt}] Drone {d_id} → formation position OK")
                return True

            except Exception as e:
                logs.append(f"[Attempt {attempt}] Drone {d_id} failed: {e}")
                # kill any leftover processes & tear down before retry
                respawn_drone(d_id)
                time.sleep(2.0)

        logs.append(f"Drone {d_id}: all attempts failed, skipping")
        return False



    # run each drone in sequence
    success = 0
    for idx, (lat, lon, alt) in enumerate(poses):
        logs.append(f"--- Starting sequence for Drone {idx} ---")
        if ensure_and_move(idx, lat, lon, alt):
            success += 1
        # small gap between drones
        time.sleep(5.0)

    return jsonify(
        status=f"Formation completed ({success}/{len(poses)} drones succeeded)",
        num_drones=success
    )



@app.route('/return_all_home', methods=['POST'])
def return_all_home_endpoint():
    for drone_id in list(drone_instances.keys()):
        threading.Thread(target=lambda d=drone_id: run_async(return_home(d)), daemon=True).start()
    return jsonify({"status": "Return home command sent for all drones"})




@app.route('/set_controlled_drone', methods=['POST'])
def set_controlled_drone_endpoint():
    global current_controlled_drone
    data = request.get_json()
    current_controlled_drone = data["drone_id"]
    return jsonify({"status": "success"})

@app.route("/add", methods=["POST"])
def add_drone():
    drone_id = max(drone_instances.keys(), default=-1) + 1
    spawn_drone(drone_id, base=(drone_id == 0))
    return redirect('/')

# Improved remove_drone endpoint for x500 drones
@app.route("/remove", methods=["POST"])
def remove_drone():
    drone_id = int(request.form.get("drone_id"))
    instance = drone_instances.pop(drone_id, None)

    if instance:
        logs.append(f"Removing x500 drone {drone_id}")
        try:
            # Terminate processes
            if instance.get("sitl_proc"):
                instance["sitl_proc"].terminate()
                instance["sitl_proc"].wait(timeout=2)
            if instance.get("mavsdk_server_proc"):
                instance["mavsdk_server_proc"].terminate()
                instance["mavsdk_server_proc"].wait(timeout=2)

            # Gazebo cleanup for x500 model
            cleanup_cmd = f"gz model -m x500_{drone_id} -d"
            subprocess.run(cleanup_cmd, shell=True, timeout=5)

        except Exception as e:
            logs.append(f"Error removing drone {drone_id}: {e}")

    return redirect('/')



@app.route("/takeoff", methods=["POST"])
def takeoff_endpoint():
    try:
        drone_id = int(request.form["drone_id"])
        altitude = float(request.form.get("altitude", 5))
        if drone_id not in drone_instances:
            logs.append(f"Invalid drone ID: {drone_id}")
            return redirect('/')
        threading.Thread(target=lambda: run_async(arm_takeoff(drone_id, altitude)), daemon=True).start()
        return redirect('/')
    except Exception as e:
        logs.append(f"Takeoff request error: {str(e)}")
        return redirect('/')

@app.route("/land", methods=["POST"])
def land_endpoint():
    try:
        drone_id = int(request.form["drone_id"])
        if drone_id not in drone_instances:
            logs.append(f"Invalid drone ID: {drone_id}")
            return redirect('/')
        threading.Thread(target=lambda: run_async(land_and_disarm_async(drone_id)), daemon=True).start()
        return redirect('/')
    except Exception as e:
        logs.append(f"Land request error: {str(e)}")
        return redirect('/')

@app.route('/respawn', methods=['POST'])
def respawn_endpoint():
    d = int(request.form['drone_id'])
    threading.Thread(
        target=lambda d=d: run_async(respawn_and_reconnect(d)),
        daemon=True
    ).start()
    return redirect('/')



@app.route('/move_relative', methods=['POST'])
def move_relative_endpoint():
    data = request.get_json()
    dx = data["dx"]
    dy = data["dy"]
    dz = data["dz"]
    drone_id = data["drone_id"]
    threading.Thread(target=lambda: run_async(move_relative(drone_id, dx, dy, dz)), daemon=True).start()
    return jsonify({"status": "command sent"})

@app.route('/start_velocity', methods=['POST'])
def start_velocity_endpoint():
    data = request.get_json()
    vx = data["vx"]
    vy = data["vy"]
    vz = data["vz"]
    drone_id = data["drone_id"]
    threading.Thread(target=lambda: run_async(velocity_control(drone_id, vx, vy, vz)), daemon=True).start()
    return jsonify({"status": "command sent"})

@app.route('/stop_velocity', methods=['POST'])
def stop_velocity_endpoint():
    data = request.get_json()
    drone_id = data["drone_id"]
    threading.Thread(target=lambda: run_async(stop_velocity_control(drone_id)), daemon=True).start()
    return jsonify({"status": "command sent"})

@app.route('/move_precise', methods=['POST'])
def move_precise_endpoint():
    data = request.get_json()
    x = data["x"]
    y = data["y"]
    z = data["z"]
    drone_id = data["drone_id"]
    threading.Thread(target=lambda: run_async(move_relative(drone_id, x, y, z)), daemon=True).start()
    return jsonify({"status": "command sent"})

@app.route('/return_home', methods=['POST'])
def return_home_endpoint():
    data = request.get_json()
    drone_id = data["drone_id"]
    threading.Thread(target=lambda: run_async(return_home(drone_id)), daemon=True).start()
    return jsonify({"status": "return home command sent"})

@app.route('/stream')
def stream():
    def event_stream():
        while True:
            status_data = {
                'drones': {
                    d_id: {
                        'status': inst.get('status', 'Unknown'),
                        'position': inst.get('position', {'latlon': 'N/A', 'xyz': 'N/A'}),
                        'battery': inst.get('battery', 'Unknown'),
                        'speed': inst.get('speed', '0.00 m/s'),
                        'distance_from_home': inst.get('distance_from_home', '0.00 m')
                    }
                    for d_id, inst in drone_instances.items()
                },
                'logs': logs[-10:]
            }
            yield "data: " + json.dumps(status_data) + "\n\n"
            time.sleep(UPDATE_INTERVAL)
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/get_drones')
def get_drones():
    return jsonify(list(drone_instances.keys()))

@app.after_request
def after_request(response):
    response.headers.add('Cache-Control', 'no-store')
    return response

if __name__ == '__main__':
    try:
        spawn_drone(0, base=True)
        app.run(host="0.0.0.0", port=5000, debug=True)
    except KeyboardInterrupt:
        logs.append("KeyboardInterrupt detected, shutting down...")
    finally:
        cleanup()
