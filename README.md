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

### 3. Create a virtual environment and install Python packages

A virtual environment keeps FireFly's dependencies separate from your other Python projects.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r main/groundstation/requirements.txt
pip install requests
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r main/groundstation/requirements.txt
pip install requests
```

(You only run `python -m venv .venv` once. After that, just activate it each time you open a new terminal.)

### 4. Start the ground station — Terminal 1

```bash
cd main/groundstation
python server.py
```

You should see:

```text
[gps] listening for UDP broadcasts on :4210
 * Running on http://0.0.0.0:5050
```

Open <http://127.0.0.1:5050> in a browser. You'll see the map UI with "No drones connected" — that's expected, nothing's broadcasting yet.

### 5. Start the simulated drone fleet — Terminal 2

In a **separate** terminal (don't close Terminal 1):

```bash
# activate the venv again in this new terminal
# Windows: .venv\Scripts\Activate.ps1
# Mac/Linux: source .venv/bin/activate

cd main/testing
python simulate_fleet.py
```

You should see:

```text
Fleet Simulator running. Broadcasting raw sensor data...
[Time: 3s] Drone 1 sees smoke!
```

And in Terminal 1 (the server):

```text
[gps] new drone connected: drone_1 from 127.0.0.1
[gps] new drone connected: drone_2 from 127.0.0.1
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