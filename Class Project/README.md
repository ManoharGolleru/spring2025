
# Drone Show Simulation

Team Members:
- Manohar Golleru, manoharg@buffalo.edu

--- 

## Motivation / Overview

Modern drone research often requires rapid prototyping of multi-UAV formations **and** low-level manual control, yet existing tools focus on one or the other. This project:

  - Expedites testing of formation-planning algorithms in simulation  
  - Lets researchers manually override or fine-tune individual drones

Anyone building or teaching UAV formation control, HRI studies with drones, or integrated drone demonstrations will find this useful.

## Demonstration

<table>
  <tr>
    <td><img src="https://github.com/ManoharGolleru/spring2025/blob/main/Class%20Project/tri.png" width="300"/></td>
    <td><img src="https://github.com/ManoharGolleru/spring2025/blob/main/Class%20Project/tri_process.png" width = "300"/></td>
    <td><img src="https://github.com/ManoharGolleru/spring2025/blob/main/Class%20Project/Triangular_formation.png" width="300"/></td>
  </tr>
</table>

Above is a demonstration of how we can make formations using our application by just inputting a image with the formation structure that you desire.
**The image processing step in our application can identify the minimum number of points that are required to form that shape**

More detailed demostration can be found here:

[![Youtube Demonstration](https://img.youtube.com/vi/djIwRS4VLt8/0.jpg)](https://www.youtube.com/watch?v=djIwRS4VLt8&ab_channel=ManoharGolleru)
---
# Setup


## PX4 SITL and Drone Application Development

PX4's Software-in-the-Loop [SITL](https://ardupilot.org/dev/docs/sitl-simulator-software-in-the-loop.html) simulation provides a powerful platform to develop, test, and validate drone software without the need for physical hardware. This environment is essential for rapid prototyping, algorithm development, and mission planning in a risk-free virtual setting.

## What Can You Do with PX4 SITL?

- **Algorithm and Control Development:**  
  Simulate various flight scenarios to test and refine flight control algorithms. This is ideal for developing stabilization, navigation, and autonomous behaviors.

- **Mission Planning and Testing:**  
  Validate complex missions and waypoint navigation by simulating different flight paths, emergency procedures, and environmental conditions.

- **Sensor and Payload Integration:**  
  Emulate sensor data such as GPS, IMU, barometers, and more. Test integration with cameras or other payloads to ensure robust data handling and sensor fusion.

- **Failure Mode Analysis:**  
  Simulate adverse conditions like sensor failures, wind disturbances, or system malfunctions to evaluate system robustness and safety measures.

## Simulation Plugins and Environments

PX4 SITL supports multiple simulation environments and plugins, allowing you to choose the best fit for your development needs:

- **Gazebo:**  
  A high-fidelity 3D simulation environment that provides realistic physics and sensor modeling. Gazebo is well-suited for testing complex environments and can be integrated with ROS for enhanced robotics applications.  
  More details: [PX4 Gazebo Simulation](https://docs.px4.io/main/en/sim_gazebo_gz/)

- **jMAVSim:**  
  A lightweight and fast simulator primarily designed for multicopter simulations. It’s ideal for quick testing of flight dynamics and control loops without the overhead of a full 3D simulation.

- **AirSim:**  
  Developed by Microsoft, AirSim offers realistic visual and physical simulation. It is particularly useful for testing perception algorithms and autonomous navigation in complex environments.

- **Other Integrations:**  
  Depending on your needs, PX4 SITL can also interface with other simulation tools such as JSBSim for fixed-wing aircraft simulation or custom simulators tailored to specific research requirements.

## Drone APIs and SDKs

To build drone applications that interact with PX4, several APIs and SDKs are available:

- **MAVSDK:**  
  MAVSDK provides high-level libraries in various programming languages (C++, Python, Swift, Java) to communicate with MAVLink-enabled systems like drones, cameras, or ground stations. It abstracts the low-level MAVLink protocol and allows you to build drone apps quickly and efficiently.  
  Learn more: [MAVSDK Documentation](https://mavsdk.mavlink.io/main/en/index.html) , [MAVSDK PYTHON QUICKSTART](https://mavsdk.mavlink.io/main/en/python/quickstart.html)

- **ROS 2 Integration:**  
  Use ROS 2 to communicate with PX4 via ROS nodes. This is particularly useful for integrating advanced robotics functionalities, such as perception and planning, into your drone applications.  
  More info: [PX4 ROS 2 Integration](https://docs.px4.io/main/en/ros/ros2_comm.html)

- **ROS 1 and MAVROS:**  
  For legacy systems or specific ROS 1 use cases, MAVROS provides a bridge between ROS and MAVLink, enabling the use of PX4 within the ROS ecosystem.  
  More details: [MAVROS Installation](https://docs.px4.io/main/en/ros/mavros_installation.html)

For a comprehensive comparison of available drone APIs and which one may best suit your project, refer to the PX4 documentation: [What API should I use?](https://docs.px4.io/main/en/robotics/#what-api-should-i-use)

## Installation and Setup

### Prerequisites
- **Operating System:** Linux, macOS, or Windows (with WSL recommended for Windows).
- **Dependencies:** Standard build tools and simulator-specific dependencies (e.g., Gazebo or jMAVSim).

---

## Step 1: Clone the PX4-Autopilot Repository

Open your terminal and run the following command to clone the repository with all its submodules:

```
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
```

---

## Step 2: Install Dependencies

### For Ubuntu/Linux:

Navigate to the PX4-Autopilot directory:

```
cd PX4-Autopilot
```

Run the Ubuntu setup script to install all necessary dependencies:

```
bash ./Tools/setup/ubuntu.sh
```

For macOS or Windows (using WSL), refer to the specific instructions in the PX4 SITL Documentation.

---

## Step 3: Build and Launch SITL

### Option 1: Using Gazebo (3D Simulation)

To run PX4 SITL with Gazebo, run:

```
make px4_sitl gz_x500
```

This command compiles the PX4 firmware and launches the SITL simulation with Gazebo using a quadcopter.


For a practical demonstration and more insights into using ArduPilot's SITL, you might find the following video helpful:


[![PX4 SITL Demo](https://img.youtube.com/vi/Ewh0fKGEJL4/0.jpg)](https://www.youtube.com/watch?v=Ewh0fKGEJL4&ab_channel=ArduPilot)



# Controlling PX4 SITL with MAVSDK: Installation & Code

Note: Everything is running on Ubuntu 24.04, gazebo Harmonic v 8.9.0

This guide explains how to install MAVSDK in a Python virtual environment and write a Python script to control (move and land) a quadcopter in PX4 SITL running in Gazebo.

---

## 1. Running PX4 SITL with Gazebo

Make sure you have started PX4 SITL with Gazebo. For example, from the PX4-Autopilot directory:

```
make px4_sitl gz_x500
```

You should see a window pop up with the drone on the ground

## 2. Installing MAVSDK in a Python Virtual Environment

Since your system is externally managed, it’s best to install MAVSDK in a virtual environment.
I was using Python 3.12.3

Create a Virtual Environment:

```
python3 -m venv mavsdk_env
```

Activate the Virtual Environment On Linux:

```
source mavsdk_env/bin/activate
```

Install MAVSDK

```
pip install mavsdk
```

Now code to move the drone, save it as a python file (eg. move_drone.py) in PX4-Autopilot directory

```
import asyncio
from mavsdk import System
from mavsdk.offboard import (OffboardError, VelocityNedYaw)

async def run():
    # Connect to PX4 SITL (ensure the simulation is running)
    drone = System()
    await drone.connect(system_address="udp://:14540")

    print("Waiting for drone connection...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Drone connected!")
            break

    print("Waiting for global position and home position to be set...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("Global position and home position are set")
            break

    print("Arming drone...")
    await drone.action.arm()

    print("Taking off...")
    await drone.action.takeoff()
    await asyncio.sleep(10)  # Wait for the drone to reach takeoff altitude

    # Set an initial setpoint (required by PX4 for offboard mode)
    print("Setting initial offboard setpoint (zero velocity)...")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, 0.0))
    
    print("Starting offboard mode...")
    try:
        await drone.offboard.start()
    except OffboardError as error:
        print(f"Failed to start offboard mode: {error._result.result}")
        print("Disarming drone...")
        await drone.action.disarm()
        return

    # Command the drone to move forward (1 m/s) for 10 seconds
    print("Sending velocity command: Move forward at 1 m/s")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(1.0, 0.0, 0.0, 0.0))
    await asyncio.sleep(10)

    # Stop movement by sending a zero velocity command
    print("Stopping drone...")
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, 0.0))
    await asyncio.sleep(5)

    # Land the drone
    print("Landing...")
    await drone.action.land()
    await asyncio.sleep(10)

    print("Disarming drone...")
    await drone.action.disarm()
    print("Operation complete.")

if __name__ == "__main__":
    asyncio.run(run())
```

This code will start the drone, take off, stop at 5m, move in x direction and land the drone

You need to run to start Gazebo first in a window

Terminal 1:
```
make px4_sitl gz_x500
```

Then in another window, start the python venv and run the python code to move the drone in simulation

Terminal 2:
```
source mavsdk_env/bin/activate
```
Run the script move_drone.py

```
python move_drone.py
```
----

## Project Setup
Once you have the PX4 installed and you were able to run the able code properly to make the drone move- You would have to create a new python environment so you can use the packages i used.

All the packages will be in requirements.txt with which you can create a new venv:

```
python -m venv mavsdk_env #if you already used this name above, use a different name for the environment
source mavsdk_env/bin/activate
pip install -r requirements.txt

```
#### Requirements
```
aioconsole==0.8.1
aiohappyeyeballs==2.6.1
aiohttp==3.11.16
aiosignal==1.3.2
attrs==25.3.0
blinker==1.9.0
certifi==2025.1.31
charset-normalizer==3.4.1
click==8.1.8
Flask==3.1.0
frozenlist==1.5.0
grpcio==1.70.0
idna==3.10
itsdangerous==2.2.0
Jinja2==3.1.6
MarkupSafe==3.0.2
mavsdk==3.0.1
mss==10.0.0
multidict==6.2.0
numpy==2.2.4
opencv-python-headless==4.11.0.86 #Make sure you get opencv-headless if not the gazebo gui will not open
propcache==0.3.1
protobuf==6.30.0
requests==2.32.3
scipy==1.15.2
shapely==2.1.0
urllib3==2.4.0
Werkzeug==3.1.3
yarl==1.18.3
```

Now all you need to do is change to PX4 directory and run the main.py file

## How to Run the Code

```
# 1. Switch to the PX4 directory
cd ~/PX4-Autopilot

# 2. Launch the demo
python main.py #Download the main.py from the repo

```
This will:

Spawn PX4 SITL & mavsdk_server for drone 0

Start the Flask web server on port 5000

Launch the Gazebo GUI — after a few seconds you should see a single x500 drone at (0,0) on the ground plane

In your terminal you’ll see something like:
```
* Running on http://127.0.0.1:5000 (Press CTRL+C to quit)
```
Open that URL in your browser:

<details>
  <summary><strong>Formation Mode</strong></summary>

  ![Web Interface-Formation Mode](https://github.com/ManoharGolleru/spring2025/blob/main/Class%20Project/R1.jpg)

</details>

<details>
  <summary><strong>Manual Mode</strong></summary>

  ![Web Interface-Manual Mode](https://github.com/ManoharGolleru/spring2025/blob/main/Class%20Project/R2.jpg)

</details>

### UI Overview
At the top you can toggle between Formation and Manual modes:

**Formation Mode**
1. Upload an image of your desired pattern.
2. Click on Process Image: This will show you the processed image with the contours detected and marked in red
3. Click Set Formation to map 2D contour points → 3D waypoints: This will create additional drones if needed
4. Click Make Formation: This will arm, take off, and moves each drone into that formation.
5. Return All Home brings every drone back to its home position.

**Manual Mode**
- ➕ Add New Drone: spawn additional SITL drones.
- Joystick Controls: coarse XYZ moves via arrow buttons.
- Velocity Controls: continuous body-frame velocity commands.
- Precise Movement: enter exact X, Y, Z distances for fine adjustments.
- Return Home: send the selected drone back to home.
Per-drone Actions (Take Off / Land / Remove / Respawn) via the cards at the bottom.


## How does Image to 3D waypoints work?

### 1. Image → 3D Waypoints

When you upload a 2D image, we:

1. **Preprocess**

   * Convert to grayscale, blur, adaptive-threshold, and open-morphology to isolate contours.
   * Functions: `preprocess_image()`, `optimize_tolerance()`, `minimal_sampling()`, `uniform_sampling()`

2. **Extract Pixel Points**

   * Pick contour vertices (minimal sampling) or uniformly sample along contour.
   * We end up with a set of pixel coords `[(px, py), …]`.

3. **Map to “Gazebo” Coordinates**

   ```python
   # pixel extents
   min_x, min_y = pts.min(axis=0)
   max_x, max_y = pts.max(axis=0)
   w_pix = max_x - min_x
   h_pix = max_y - min_y

   # UV-plane extents you choose
   Ymin, Ymax = north_min, north_max   # meters North/South
   Zmin = base_altitude
   Zmax = base_altitude + formation_depth

   # how many meters per pixel (keep aspect ratio)
   mpp = min((Ymax - Ymin) / w_pix,
             (Zmax - Zmin) / h_pix)

   # center-the-shape offsets
   y_off = Ymin + ((Ymax - Ymin) - w_pix*mpp) / 2
   z_off = Zmin + ((Zmax - Zmin) - h_pix*mpp) / 2

   # for each pixel (px,py):
   north = y_off + (px - min_x) * mpp
   altitude = Zmax - (py - min_y) * mpp  # invert Y-axis
   self.formation_points.append([0.0, north, altitude])
   ```

   X is fixed at 0 for a pure North–South line.
   You now have a list of local `[X=0, Y=north, Z=alt]` waypoints.

4. **Convert to GPS**

   ```python
   def xy_to_latlon(x, y, home_lat, home_lon):
       R = 6_378_137.0  # WGS84 radius
       lat = home_lat + math.degrees(y / R)
       lon = home_lon + math.degrees(x / (R * cos(radians(home_lat))))
       return lat, lon
   ```

   Each `(0, north, alt)` → `(lat, lon, alt + home_alt)`.
   Called in `FormationController.get_formation_positions()`.

---

## Core Functions

| Function                                 | What it does                                                    |
| ---------------------------------------- | --------------------------------------------------------------- |
| `preprocess_image(path)`                 | Grayscale → blur → adaptive threshold → morphology              |
| `optimize_tolerance(cnt)`                | Find best poly-approx tolerance for contour simplification      |
| `minimal_sampling(cnt, tol)`             | Sample contour vertices at `tol * arcLength`                    |
| `uniform_sampling(cnt, n)`               | Sample `n` evenly-spaced points along contour                   |
| `set_formation_from_image(points…)`      | Map pixel points → local 3D coords (meters)                     |
| `get_formation_positions(lat, lon…)`     | Convert local coords → GPS (lat/lon/alt)                        |
| `spawn_and_wait(drone_id)`               | Launch PX4 SITL + `mavsdk_server`, connect & health-check drone |
| `arm_and_takeoff(drone, h)`              | Ensure armable → take off to `h` meters, monitor ascent         |
| `move_drone_to_position(id,lat,lon,alt)` | Fly to formation waypoint                                       |
| `velocity_control(id,vx,vy,vz)`          | Body-frame velocity commands via offboard mode                  |


---
### Application Workflow


```mermaid
flowchart LR
  A["Upload Image"] --> B["preprocess_image()"]
  B --> C["findContours() & filter by area"]
  C --> D["optimize_tolerance(), minimal_sampling()"]
  D --> E["set_formation_from_image()"]
  E --> F["formation_points"]
  F --> G["get_formation_positions()"]
  G --> H["spawn_and_wait() & make_formation()"]
```

## Limitations

Due to hardware limitations, I was not able to test more complex shapes but the functions(process image/ set formation from image) can be modified to accomodate them.

## Next Steps
- Adding a camera stream into the world to stream the world view into the interface, Using gazebo classic might be a better idea if we want to do this in the future. Harmonic doesnt have this support easily- we would have to look for workarounds
- Being able to import the shape into Blender and design a drone formation using the Skybrush Studio plugin.
- Being able to Export the formation file (.skyc) for 2D and 3D formations.
- Simulate a drone swarm forming the exported 2D/3D formations with collision avoidance.
- In a later phases, develop sequences for dynamic transitioning once 3D formations are stable.

## References

- [PX4 Simulation Docs](https://docs.px4.io/main/en/simulation/)
- [Gazebo Simulation Docs](https://gazebosim.org/docs/latest/getstarted/)
- [OpenCV Docs](https://docs.opencv.org/4.x/)
- [Python asyncio Docs](https://docs.python.org/3/library/asyncio.html)
- [Edge detection](https://huggingface.co/spaces/ml-bench/edge-detection) was used as a reference for edge detection
