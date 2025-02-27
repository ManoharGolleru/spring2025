
# Drone Show Simulation

Team Members:
- Manohar Golleru, manoharg@buffalo.edu

--- 

## Project Objective
Develop a simulation environment that transforms an input image (e.g., a logo) into a drone show formation. Initially, we will focus on creating accurate 2D and 3D formations. Once 3D formations are achieved, we will explore dynamic transitioning between formations in future phases.

## Contributions
**Image Processing Module:**
- Use OpenCV to extract and simplify contours from an input image, generating a 2D shape.

**Formation Design:**
- Import the 2D shape into Blender and employ the Skybrush Studio for Blender plugin to design and export a drone formation file (e.g., “.skyc”). For 3D formations, extend the design process to incorporate depth information.

**Drone Simulation:**
- Build a simulation (using Gazebo) that reads the exported formation files and controls a drone swarm to form the desired 2D or 3D structure with effective collision avoidance.

**Next Steps:**
After successfully achieving 3D formations, will work on dynamic transitioning of 3D formations.

## Project Plan

Simulation: Gazebo
Formation Design: Skybrush Studio for Blender
Image Processing: OpenCV / other lightweight models
Scripting: Python

## Workflow:

1. Process the input image to extract a 2D shape using computer vision.
2. Import the shape into Blender and design a drone formation using the Skybrush Studio plugin.
3. Export the formation file (.skyc) for 2D and 3D formations.
4. Simulate a drone swarm forming the exported 2D/3D formations with collision avoidance.
5. In a later phases, develop sequences for dynamic transitioning once 3D formations are stable.

## Milestones/Schedule Checklist

- [x] Complete this proposal document.  *Due Feb. 28*
- [ ] Develop the image processing module for 2D shape extraction. Due Mar. 10
- [ ] Integrate the extracted shape into Blender and test the Skybrush Studio plugin for 2D formation design. Due Mar. 17
- [ ] Design and export 2D formation files (.skyc). Due Mar. 24
- [ ] Extend formation design to create 3D formations in Blender using the plugin. Due Apr. 7
- [ ] Set up the simulation environment and implement drone swarm formation (2D & 3D) with collision avoidance. Due Apr. 21
- [ ] Create progress report. Due May 6
- [ ] Finalize simulation demonstration and document results. Due May 13

## Measures of Success
- Successful extraction of a clear 2D shape from the input image.
- Accurate design and export of drone formation files for both 2D and 3D formations using Skybrush Studio for Blender.
- A simulated drone swarm that reliably forms the desired 2D and 3D structures with smooth, collision-free behavior.
- A modular system that lays the groundwork for future development of dynamic transitioning between formations.
