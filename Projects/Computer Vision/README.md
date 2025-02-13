# Computer Vision Flask App

## Introduction
This application integrates multiple computer vision models to process real-time video from your webcam.  
It supports various modes, including:
- **Raw Video** (Unprocessed)
- **Face Detection** (MediaPipe)
- **Pose Estimation** (MediaPipe)
- **Emotion Recognition** (DeepFace)
- **Depth Estimation** (Depth Anything V2)
- **Object Detection** (YOLO11n)
- **Segmentation** (YOLO Segmentation: YOLO11n-seg)


The app runs a Flask web server and streams the processed video feed to a browser interface.

---

## 1. Installation & Setup

### **Using Conda (Recommended)**
1. **Create and activate the environment**:
   ```bash
   conda create --name myenv python=3.11 -y
   conda activate myenv
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install PyTorch (If Needed)**
   - **For CPU**: It should already be installed with other packages but just in case you get an error
     ```bash
     pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
     ```
   - **For GPU**:  
     You need to find a **GPU-compatible** version of `torch` based on your CUDA version.  
     Visit [PyTorch's official website](https://pytorch.org/get-started/locally/) for the correct installation command.

---

## 2. Running the Application
Once the installation is complete, start the Flask app: Once the application starts it will download yolo11n.pt and yolo11n-seg.pt which are model weights needed for object detection and segmentation
```bash
python app.py
```
The server will run on **http://localhost:5000**. Open this URL in your web browser to access the app.

---

## 3. How to Use the App
- The video stream will load automatically.
- Select the processing mode from the navigation bar:
  - **Raw** - No processing, just the camera feed.
  - **Face** - Detects faces in the video.
  - **Pose** - Estimates body pose.
  - **Emotion** - Analyzes facial expressions.
  - **Depth** - Estimates depth using a Transformer model.
  - **Object** - Detects objects using YOLO.
  - **Segmentation** - Performs instance segmentation.

---

## 4. Troubleshooting
- **Camera not working?**  
  - Ensure no other applications are using the webcam.
  - Restart your system and try again.

- **Missing modules?**  
  - Install any missing package manually:
    ```bash
    pip install <module_name>
    ```

- **Torch not installed?**  
  - Verify with:
    ```bash
    python -c "import torch; print(torch.__version__)"
    ```

- **CUDA not detected for GPU?**  
  - Check if GPU acceleration is available:
    ```bash
    python -c "import torch; print(torch.cuda.is_available())"
    ```
  - If it returns `False`, ensure you installed a compatible `torch` version.

---

## 5. Closing the App
To properly shut down the application:
1. Close the browser tab.
2. Stop the Flask process in the terminal (`Ctrl + C`).
3. Conda users can deactivate the environment with:
   ```bash
   conda deactivate
   ```
## 6. Conclusions

Mediapipe is better optimised for cpu's so we used that for Face and Pose, Yolo models perform far better than other's at object detection and segmentation but requires more resources. Depth Anything requires the most resources as the frame rate goes below 1 FPS - atleast on my Device (Intel i7, 16GB RAM)

