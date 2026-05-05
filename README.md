# FireFly

FireFly is a student-built drone + ground-station project for early wildfire detection. Two ESP32-based drones with cameras and GPS observe the same fire from different angles. The base station triangulates the bearings to compute the fire's GPS coordinates and shows the result on a live map.

The demo focuses on the **geolocation pipeline**, not flight control — drones are de-prioritized per the project's scope.

## Quick Start (no hardware required)

The pipeline runs end-to-end with simulated drones and a recorded fire video. Two terminals.

### 1. Install prerequisites

You need **Python 3.10+** and **git**. Pick your platform:

#### Windows

```powershell
# install python (one-time)
winget install Python.Python.3.12
winget install Git.Git
# or download from https://www.python.org/downloads/ and https://git-scm.com/
```

#### macOS

```bash
# install homebrew first (one-time): https://brew.sh
brew install python git
```

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

Verify:

```bash
python --version    # should print 3.10 or higher
git --version
```

### 2. Clone the repo

```bash
git clone https://github.com/parezvani/FireFly.git
cd FireFly
```

### 3. Run the setup script

The setup script creates a virtual environment and installs all Python dependencies in one shot.

**macOS / Linux / Git Bash:**

```bash
bash setup.sh
```

**Windows PowerShell:**

```powershell
.\setup.ps1
```

(You only run setup once per machine. After that, just activate the venv each new terminal.)

After setup completes, activate the venv in any new terminal:

```powershell
.\.venv\Scripts\Activate.ps1     # Windows PowerShell
source .venv/bin/activate        # macOS / Linux / Git Bash
```

### 4. Run the whole stack with one command

From the repo root:

```bash
python run.py
```

That's it. The launcher will:

1. Start the FireFly server on `http://127.0.0.1:5050`
2. Scan the local network for an ESP32-CAM (port 81 MJPEG) and auto-register the URL
3. Start the simulated drone fleet
4. Start YOLOv8 fire detection (only if a camera is found)
5. Open your browser at the map UI

Press `Ctrl+C` once to stop everything cleanly.

### Optional flags

```bash
python run.py --no-cam        # skip camera discovery and YOLO (sim-only demo)
python run.py --no-yolo       # register camera in UI but skip fire detection
python run.py --no-sim        # skip the fake drone fleet (real hardware only)
python run.py --no-browser    # don't auto-open the browser
```

If your camera isn't on the same subnet (rare), set the URL explicitly:

```bash
# Mac/Linux
FIREFLY_CAM_URL=http://10.0.0.137:81/stream python run.py

# Windows PowerShell
$env:FIREFLY_CAM_URL="http://10.0.0.137:81/stream"; python run.py
```

`run.py` generates a local camera token automatically. If you start the Flask server manually or configure the Render service, set a long `FIREFLY_CAMERA_TOKEN` and include it when changing the camera URL:

```bash
export FIREFLY_CAMERA_TOKEN="replace-with-a-long-random-secret"
curl -X POST http://localhost:5050/api/camera \
  -H "Content-Type: application/json" \
  -H "X-Camera-Token: $FIREFLY_CAMERA_TOKEN" \
  -d '{"url": "http://10.0.0.137:81/stream"}'
```

---

## Optional: run the real fire detector with a fire video

The simulator fakes fire detection geometrically. To run the actual YOLOv8 model on a recorded fire video:

```bash
pip install ultralytics opencv-python
cd main/fire_detect/fire_detect_YOLO8
python fire_detect.py
```

YOLOv8 will open `test_videos/palisades_fire.mp4` in an OpenCV window with bounding boxes. After 3 seconds of sustained detection, it POSTs the fire to the ground station and the pin appears on the map.

To point at a different video or a live ESP32-CAM stream:

```bash
# Mac/Linux
FIREFLY_VIDEO=http://192.168.1.47:81/stream python fire_detect.py

# Windows PowerShell
$env:FIREFLY_VIDEO="http://192.168.1.47:81/stream"; python fire_detect.py
```

---

## Run the unit tests

Verifies the triangulation math without needing the server or simulator.

```bash
cd main/testing
python test_triangulator.py
```

Should end with `all tests passed`.

---
