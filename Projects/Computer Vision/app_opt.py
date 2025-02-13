import os
# Suppress TensorFlow warnings
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import cv2
import time
import logging
import sys
import numpy as np
import atexit
from flask import Flask, Response, render_template_string, jsonify
import torch
from ultralytics import YOLO
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
import mediapipe as mp
from deepface import DeepFace

# -----------------------------
#       Environment Setup
# -----------------------------
os.environ['PATH'] += os.pathsep + os.path.join(sys.exec_prefix, 'Library', 'bin')

# -----------------------------
#       Configure Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# -----------------------------
#       Initialize Flask App
# -----------------------------
app = Flask(__name__)

# -----------------------------
#       Global Variables
# -----------------------------
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    logging.error("Failed to open camera. Exiting.")
    sys.exit(1)
latest_frame = None  # Stores the latest raw frame

# Available modes: "raw", "face", "pose", "emotion", "depth", "object", "segmentation"
mode = "raw"  # Default mode
ALLOWED_MODES = {"raw", "face", "pose", "emotion", "depth", "object", "segmentation"}

# -----------------------------
#       Initialize YOLO Models
# -----------------------------
YOLO_OBJ_WEIGHT = "yolo11n.pt"
yolo_model = YOLO(YOLO_OBJ_WEIGHT)

YOLO_SEG_WEIGHT = "yolo11n-seg.pt"
yolo_seg_model = YOLO(YOLO_SEG_WEIGHT)

# -----------------------------
#    Load Depth Estimation Model
# -----------------------------
device = "cuda" if torch.cuda.is_available() else "cpu"
logging.info(f"Using device: {device}")
depth_processor = AutoImageProcessor.from_pretrained("depth-anything/Depth-Anything-V2-Small-hf", use_fast=False)
depth_model = AutoModelForDepthEstimation.from_pretrained("depth-anything/Depth-Anything-V2-Small-hf")
depth_model.to(device)
depth_model.eval()
logging.info("Depth Anything V2 Small model loaded successfully.")

# -----------------------------
#    Initialize MediaPipe Modules
# -----------------------------
mp_face_detection = mp.solutions.face_detection
mp_pose = mp.solutions.pose
face_detector = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)
pose_estimator = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
drawing_utils = mp.solutions.drawing_utils

# -----------------------------
#    Emotion Detection using DeepFace
# -----------------------------
def analyze_emotion(face_img: np.ndarray) -> str:
    try:
        face_rgb = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
        analysis = DeepFace.analyze(face_rgb, actions=['emotion'], enforce_detection=False)
        if isinstance(analysis, list):
            analysis = analysis[0]
        return analysis.get("dominant_emotion", "N/A")
    except Exception as e:
        logging.error(f"DeepFace emotion error: {e}")
        return "N/A"

# -----------------------------
#    Depth Estimation Function
# -----------------------------
def estimate_depth(frame: np.ndarray) -> np.ndarray:
    try:
        rgb_img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)
        inputs = depth_processor(images=pil_img, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = depth_model(**inputs)
        predicted_depth = outputs.predicted_depth
        depth_map = torch.nn.functional.interpolate(
            predicted_depth.unsqueeze(1),
            size=(frame.shape[0], frame.shape[1]),
            mode="bicubic",
            align_corners=False
        ).squeeze().cpu().numpy()
        depth_min = depth_map.min()
        depth_max = depth_map.max()
        if depth_max - depth_min > 0:
            depth_norm = ((depth_map - depth_min) / (depth_max - depth_min) * 255).astype(np.uint8)
        else:
            depth_norm = np.zeros_like(depth_map, dtype=np.uint8)
        depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
        blended = cv2.addWeighted(frame, 0.6, depth_color, 0.4, 0)
        return blended
    except Exception as e:
        logging.error(f"Depth estimation error: {e}")
        return frame

# -----------------------------
#    Frame Processing Function
# -----------------------------
def process_frame(frame: np.ndarray) -> np.ndarray:
    global latest_frame, mode
    latest_frame = frame.copy()
    h, w, _ = frame.shape
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    if mode == "raw":
        return frame

    elif mode == "face":
        face_results = face_detector.process(frame_rgb)
        if face_results.detections:
            for detection in face_results.detections:
                bbox = detection.location_data.relative_bounding_box
                x1 = int(bbox.xmin * w)
                y1 = int(bbox.ymin * h)
                bw = int(bbox.width * w)
                bh = int(bbox.height * h)
                x2, y2 = x1 + bw, y1 + bh
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        return frame

    elif mode == "pose":
        pose_results = pose_estimator.process(frame_rgb)
        if pose_results.pose_landmarks:
            drawing_utils.draw_landmarks(frame, pose_results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
        return frame

    elif mode == "emotion":
        face_results = face_detector.process(frame_rgb)
        if face_results.detections:
            for detection in face_results.detections:
                bbox = detection.location_data.relative_bounding_box
                x1 = int(bbox.xmin * w)
                y1 = int(bbox.ymin * h)
                bw = int(bbox.width * w)
                bh = int(bbox.height * h)
                x2, y2 = x1 + bw, y1 + bh
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                # Crop face ROI and analyze emotion
                x1_c = max(x1, 0)
                y1_c = max(y1, 0)
                x2_c = min(x2, w)
                y2_c = min(y2, h)
                face_roi = frame[y1_c:y2_c, x1_c:x2_c]
                if face_roi.size > 0:
                    emotion = analyze_emotion(face_roi)
                    cv2.putText(frame, emotion, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
        return frame

    elif mode == "depth":
        return estimate_depth(frame)

    elif mode == "object":
        resized = cv2.resize(frame, (320, 240))
        try:
            results = yolo_model(resized)[0]
            boxes = results.boxes
            class_names = results.names
            scale_x, scale_y = w / 320, h / 240
            for i, box in enumerate(boxes):
                coords = box.xyxy.cpu().numpy()[0]
                x1_obj = int(coords[0] * scale_x)
                y1_obj = int(coords[1] * scale_y)
                x2_obj = int(coords[2] * scale_x)
                y2_obj = int(coords[3] * scale_y)
                conf = float(box.conf.cpu().numpy()[0])
                cls = int(box.cls.cpu().numpy()[0])
                label = class_names[cls] if class_names else str(cls)
                cv2.rectangle(frame, (x1_obj, y1_obj), (x2_obj, y2_obj), (0, 255, 255), 2)
                cv2.putText(frame, f"ID:{i} {label} {conf:.2f}", (x1_obj, y1_obj - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        except Exception as e:
            logging.error(f"YOLO processing error: {e}")
        return frame

    elif mode == "segmentation":
        try:
            results = yolo_seg_model(frame)[0]
            seg_frame = results.plot()
            return seg_frame
        except Exception as e:
            logging.error(f"Segmentation processing error: {e}")
            return frame

    else:
        return frame

# -----------------------------
#    MJPEG Stream Generator
# -----------------------------
def generate_frames():
    frame_count = 0
    fps_accum = 0
    prev_time = time.time()
    while True:
        loop_start = time.time()
        ret, frame = cap.read()
        if not ret:
            logging.error("Failed to capture frame.")
            break
        processed_frame = process_frame(frame)
        loop_end = time.time()
        delta = loop_end - loop_start
        frame_fps = 1.0 / delta if delta > 0 else 0.0
        fps_accum += frame_fps
        frame_count += 1

        cv2.putText(processed_frame, f"FPS: {frame_fps:.2f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(processed_frame, f"Mode: {mode.upper()}", (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

        if time.time() - prev_time >= 1.0:
            avg_fps = fps_accum / frame_count if frame_count > 0 else 0
            logging.info(f"Average FPS: {avg_fps:.2f}")
            fps_accum = 0
            frame_count = 0
            prev_time = time.time()

        ret2, buffer = cv2.imencode('.jpg', processed_frame)
        if not ret2:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# -----------------------------
#    Flask Routes
# -----------------------------
@app.route('/')
def index():
    model_info = {
        "raw": "No model used",
        "face": "MediaPipe Face Detection",
        "pose": "MediaPipe Pose Estimation",
        "emotion": "MediaPipe Face Detection + DeepFace Emotion Analysis",
        "depth": "Depth Anything V2 Small",
        "object": "YOLO11n Object Detection",
        "segmentation": "YOLO11n Segmentation"
    }
    return render_template_string('''
    <!doctype html>
    <html lang="en">
      <head>
        <title>Integrated CV Stream</title>
        <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
        <style>
          body { background-color: #f8f9fa; }
          .container { margin-top: 20px; }
          .nav-pills .nav-link.active { background-color: #007bff; }
          .card { margin-top: 20px; }
          .info-header { font-size: 1.3em; margin-bottom: 10px; }
        </style>
        <script>
          function setMode(newMode) {
            fetch('/set_mode/' + newMode, { method: 'POST' })
              .then(response => response.json())
              .then(data => { 
                document.getElementById("modeStatus").innerText = data.message;
                var btns = document.getElementsByClassName("nav-link");
                for (let i = 0; i < btns.length; i++) {
                  btns[i].classList.remove("active");
                }
                document.getElementById("btn-" + newMode).classList.add("active");
              });
          }
        </script>
      </head>
      <body>
        <div class="container">
          <div class="row">
            <!-- Video and Navigation Column -->
            <div class="col-md-8">
              <h1>Integrated CV Stream</h1>
              <img src="{{ url_for('video_feed') }}" class="img-fluid" style="max-width:640px;"/>
              <ul class="nav nav-pills justify-content-center mt-3">
                {% for m in ['raw','face','pose','emotion','depth','object','segmentation'] %}
                  <li class="nav-item">
                    <a id="btn-{{m}}" class="nav-link {% if mode == m %}active{% endif %}" href="javascript:setMode('{{m}}')">
                      {{ m.upper() }}
                    </a>
                  </li>
                {% endfor %}
              </ul>
            </div>
            <!-- Side Info Column -->
            <div class="col-md-4">
              <div class="card">
                <div class="card-header info-header">Status & Model Information</div>
                <div class="card-body">
                  <p id="modeStatus"><strong>Current Mode:</strong> {{ mode.upper() }}</p>
                  {{ info|safe }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </body>
    </html>
    ''', mode=mode, info=model_info_to_html(model_info))

def model_info_to_html(info_dict):
    html = "<table class='table table-sm table-bordered'><thead><tr><th>Mode</th><th>Model Info</th></tr></thead><tbody>"
    for m, desc in info_dict.items():
        html += f"<tr><td>{m.upper()}</td><td>{desc}</td></tr>"
    html += "</tbody></table>"
    return html

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/set_mode/<new_mode>', methods=['POST'])
def set_mode(new_mode):
    global mode
    allowed_modes = {"raw", "face", "pose", "emotion", "depth", "object", "segmentation"}
    if new_mode in allowed_modes:
        mode = new_mode
        logging.info(f"Mode set to: {mode}")
        return jsonify({"message": f"Mode set to: {mode.upper()}"}), 200
    else:
        logging.warning(f"Invalid mode: {new_mode}")
        return jsonify({"message": f"Invalid mode: {new_mode}"}), 400

# -----------------------------
#    MJPEG Stream Generator
# -----------------------------
def generate_frames():
    frame_count = 0
    fps_accum = 0
    prev_time = time.time()
    while True:
        loop_start = time.time()
        ret, frame = cap.read()
        if not ret:
            logging.error("Failed to capture frame.")
            break
        processed_frame = process_frame(frame)
        loop_end = time.time()
        delta = loop_end - loop_start
        frame_fps = 1.0 / delta if delta > 0 else 0.0
        fps_accum += frame_fps
        frame_count += 1

        cv2.putText(processed_frame, f"FPS: {frame_fps:.2f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(processed_frame, f"Mode: {mode.upper()}", (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

        if time.time() - prev_time >= 1.0:
            avg_fps = fps_accum / frame_count if frame_count > 0 else 0
            logging.info(f"Average FPS: {avg_fps:.2f}")
            fps_accum = 0
            frame_count = 0
            prev_time = time.time()

        ret2, buffer = cv2.imencode('.jpg', processed_frame)
        if not ret2:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# -----------------------------
#    Cleanup on Exit
# -----------------------------
@atexit.register
def cleanup():
    logging.info("Cleaning up resources...")
    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()
    face_detector.close()
    pose_estimator.close()
    logging.info("Camera and resources released.")

if __name__ == '__main__':
    logging.info("Starting Flask app. Open http://localhost:5000 in your browser.")
    app.run(host='0.0.0.0', port=5000, debug=False)
