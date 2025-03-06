# PX4 SITL and Drone Application Development

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

