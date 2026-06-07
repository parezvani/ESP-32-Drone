# FireFly

FireFly is a student-built drone + ground-station project for early wildfire detection. Two ESP32-based drones with cameras and GPS observe the same fire from different angles. The base station triangulates the bearings to compute the fire's GPS coordinates and shows the result on a live map.

The demo focuses on the **geolocation pipeline**, not flight control — drones are de-prioritized per the project's scope.
[FireFly Website](https://firefly-j68i.onrender.com/)

## Project Map

| Area | Path | What lives there |
| --- | --- | --- |
| Ground station website/backend | `main/groundstation/` | Flask routes, dashboard pages, Leaflet map state, camera frame relay |
| Fire detection worker | `main/fire_detect/fire_detect_YOLO8/` | YOLOv8/OpenCV detection, bearing math from camera frames, fire POSTs |
| Indoor demo | `demo.py`, `main/demo/` | Running-fix triangulation demo using one camera from two scripted positions |
| ESP32-C3 GPS firmware | `main/firmware/gps_telemetry/` | GPS parsing, BLE provisioning, UDP telemetry, optional cloud POSTs |
| ESP32-CAM / webcam tools | `main/live_webcam/`, `main/groundstation/cam_relay.py` | MJPEG camera sources and local-to-cloud frame relay helpers |
| iOS provisioning app | `main/firefly_ios_app/` | SwiftUI BLE app for sending WiFi credentials and API keys to ESP32 |
| Tests and hardware checks | `main/testing/` | Math tests, camera stream checks, GPS UDP checks, range tests |
| Project docs | `docs/` | Architecture notes, reports, hardware designs, meeting notes |

Contributor details are in [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md). The backend and fire-location pipeline are explained in [`docs/backend-architecture.md`](docs/backend-architecture.md).

## Quick Start (No Hardware Required)

The pipeline runs end-to-end with simulated drones and a recorded fire video.

### 1. Install Prerequisites & Clone Repo

You need **Python 3.10+** and **git**.

**Windows:**
```powershell
winget install Python.Python.3.12
winget install Git.Git
```

**macOS:**
```bash
brew install python git
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

Clone the repository:
```bash
git clone https://github.com/parezvani/FireFly.git
cd FireFly
```

### 2. Setup Virtual Environment

Run the setup script once per machine to create a virtual environment and install dependencies.

**macOS / Linux / Git Bash:**
```bash
bash setup.sh
source .venv/bin/activate
```

**Windows PowerShell:**
```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

### 3. Run Automated Tests

Verify math and logic:
```bash
python main/testing/test_triangulator.py
python main/fire_detect/fire_detect_YOLO8/test_bearing.py
```
*(Both should output `all tests passed`.)*

### 4. Launch the Local Stack

Run the whole stack with one command from the repo root:
```bash
python run.py
```

**What this does:**
1. Starts the FireFly server on `http://127.0.0.1:5050`
2. Scans the local network for an ESP32-CAM and auto-registers the URL.
3. Starts the simulated drone fleet.
4. Starts YOLOv8 fire detection (if a camera is found).
5. Opens the map UI in your browser.

*Press `Ctrl+C` to stop.*

**Optional Flags:**
- `--no-cam`: Skip camera discovery and YOLO (sim-only demo).
- `--no-yolo`: Register camera in UI but skip fire detection.
- `--no-sim`: Skip fake drone fleet (real hardware only).
- `--no-browser`: Don't auto-open the browser.

---

## Run the Full Live Demo (Real Hardware → Cloud)

Produces fires on the live FireFly site using an ESP32-C3 (GPS), ESP32-CAM (video), and YOLOv8 on your laptop.

### 1. One-Time Setup
1. Sign in at the [FireFly Website](https://firefly-j68i.onrender.com/).
2. In the dashboard, click "Add drone", name it, and copy the **API key**.
3. Flash the GPS firmware (`main/firmware/gps_telemetry/`) to your ESP32-C3 (Configure `Drone ID` and `Enable HTTPS POST` via `idf.py menuconfig`). Use the iOS app to send WiFi credentials and the API key via BLE.
4. Flash the stock Arduino `CameraWebServer` example to your ESP32-CAM.

### 2. Run
1. **Power on GPS & Camera:** The GPS connects to WiFi and POSTs to the cloud. View the camera feed at `http://<cam-ip>:81/stream`.
2. **Check Dashboard:** Confirm the drone shows **LIVE** on the website map.
3. **Start YOLO Worker:**

```bash
# macOS / Linux / Git Bash
cd main/fire_detect/fire_detect_YOLO8
FIREFLY_VIDEO=http://<cam-ip>:81/stream \
FIREFLY_SERVER=https://firefly-j68i.onrender.com \
FIREFLY_API_KEY=<your-api-key-from-dashboard> \
python fire_detect.py
```
*(Use `$env:VAR="value"` syntax for Windows PowerShell).*

4. **Trigger Detection:** Point the camera at a real flame or fire video. After 3 seconds, a red fire pin will appear on the live Render map.

---

## Run the Indoor Demo (No GPS)

A one-command launcher for demonstrating the running-fix triangulation indoors using one camera from two scripted positions.

### 1. Setup & Launch
Register **one drone** on the dashboard and copy its API key. Edit `main/demo/demo_config.py` with three local coordinates.

```bash
# macOS / Linux / Git Bash
export FIREFLY_API_KEY="<paste-from-dashboard>"
python demo.py
```
*(Use `$env:VAR="value"` syntax for Windows PowerShell).*

### 2. Run the Demo
Click the OpenCV window to focus it.
- Hold a lighter centered in the frame. After 3 seconds, it captures **Phase A**.
- Press `B`. Reposition the camera, hold the lighter centered again. It captures **Phase B** and POSTs the triangulated fire pin to the cloud map.
- Press `R` to reset or `Q` to quit.

---

## Optional: Run Real Fire Detector with Video

Test the YOLOv8 model on a recorded video:

```bash
cd main/fire_detect/fire_detect_YOLO8
python fire_detect.py
```
This opens `test_videos/palisades_fire.mp4` and POSTs the fire to the ground station. You can point it to an ESP32-CAM stream by setting `FIREFLY_VIDEO=http://<ip>:81/stream`.