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

### 6. Watch the demo

In the browser at <http://127.0.0.1:5050>:

- Two drone markers (🛩️) appear on the map and start moving in circles
- Each drone card in the sidebar shows its lat, lon, altitude, heading, GPS satellites, HDOP
- When a drone "sees smoke," a red dashed line projects from it in its viewing direction
- When **both** drones see smoke at the same time, the system triangulates and a fire pin (🔥) drops on the map at the calculated location
- The top banner pulses red whenever any drone is currently seeing fire

### 7. Stop everything

`Ctrl+C` in each terminal.

To clear the map without restarting:

```bash
curl -X POST http://127.0.0.1:5050/api/reset
```

Or click the "Reset all state" button in the sidebar.

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

## Real hardware (when ready)

### ESP32 GPS telemetry firmware

Lives in `main/firmware/gps_telemetry/`. Requires **ESP-IDF 5.x** ([install guide](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/index.html)).

```bash
cd main/firmware/gps_telemetry
idf.py set-target esp32c3      # or esp32s3
idf.py menuconfig              # set WiFi SSID/password under "FireFly GPS Broadcaster"
idf.py build flash monitor
```

The firmware reads NMEA sentences from a GPS module on UART1 (RX=GPIO4, TX=GPIO5, 9600 baud) and broadcasts JSON over UDP port 4210. **Change `DRONE_ID` in `main/read_pos_data.c` before flashing each board** — every drone needs a unique ID or they'll silently overwrite each other on the server.

### ESP32-CAM video stream

Flash the standard `CameraWebServer` example (Arduino IDE → File → Examples → ESP32 → Camera) with your WiFi credentials. Once the camera boots, it serves MJPEG at `http://<cam-ip>:81/stream`. Register that URL with the ground station:

```bash
curl -X POST http://127.0.0.1:5050/api/camera \
     -H "Content-Type: application/json" \
     -d '{"url": "http://192.168.1.47:81/stream"}'
```

Then click "Open camera" in the sidebar.

---

## Repository layout

- `main/`: source code and firmware
  - `groundstation/`: Python Flask base station — UDP listener, map UI, triangulation, REST API
  - `firmware/gps_telemetry/`: ESP-IDF project for the on-drone GPS broadcaster
  - `fire_detect/fire_detect_YOLO8/`: YOLOv8 fire detection + bearing math
  - `testing/`: simulators and unit tests (`simulate_fleet.py`, `test_triangulator.py`)
  - `scripts/`: ESP-NOW prototypes
  - `lab4_1/`: older lab firmware kept for reference
  - `scrapped/`: deprecated experiments (Rust server, ESP-NOW prototypes)
- `docs/`: design documents, posters, schematics, BOMs, status reports, research notes, testing logs
- `litewing/LiteWing/`: LiteWing reference firmware (git submodule)

---

## Architecture at a glance

```text
ESP32-C3 + GPS  ─UDP:4210─┐
ESP32-CAM       ─MJPEG────┤
simulate_fleet  ─UDP:4210─┤
                          │
                          ▼
                   ┌─────────────┐
                   │ server.py   │  ← single Flask process
                   │  • UDP rx   │
                   │  • multi-   │
                   │    drone    │
                   │    state    │
                   │  • triangu- │
                   │    lation   │
                   └──────┬──────┘
                          │ HTTP :5050
                          ▼
                  Browser at /
                  Leaflet map + sidebar
```

- The **server** keeps all state in memory (no database). Restart = clean slate. Intentional for demo simplicity.
- **Triangulation** runs automatically every time a UDP packet arrives. If 2+ drones report `fire_detected=True` within 10 seconds of each other, the server crosses their bearing rays and adds a fire to the map.
- Manual triangulation is also available via the sidebar button or `POST /api/triangulate`.

---

## Common issues

| Symptom | Cause | Fix |
| --- | --- | --- |
| Browser at :5050 doesn't load | Port already in use | Kill anything on :5050, restart `server.py` |
| "Address already in use" on Mac | macOS uses :5000 for AirPlay | We already use :5050 — should be fine. If still blocked, change `app.run(port=...)` in `server.py` |
| `pip install` fails | Wrong Python | Check `python --version` is 3.10+ |
| Drones never appear on map | `simulate_fleet.py` not running, or firewall blocking UDP loopback | Restart `simulate_fleet.py`; on Windows allow Python through firewall |
| Map tiles don't load | No internet | Tiles come from openstreetmap.org — needs internet |
| Fire pin never appears | Drones aren't simultaneously seeing fire | Wait 30+ seconds; the simulated drones must align with the fake fire from both angles |
