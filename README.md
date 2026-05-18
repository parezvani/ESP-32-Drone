# FireFly

FireFly is a student-built drone + ground-station project for early wildfire detection. Two ESP32-based drones with cameras and GPS observe the same fire from different angles. The base station triangulates the bearings to compute the fire's GPS coordinates and shows the result on a live map.

The demo focuses on the **geolocation pipeline**, not flight control — drones are de-prioritized per the project's scope.
[FireFly Website](https://firefly-j68i.onrender.com/)

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

## Run the full live demo (real hardware → Render website)

This is the path that produces fires on the live FireFly site at
`https://firefly-j68i.onrender.com/` using the actual ESP32-C3 GPS chip,
the ESP32-CAM (or any MJPEG source on your WiFi), and YOLOv8 fire
detection running on your laptop. Two pieces of hardware running, one
Python process on your laptop, viewing on the cloud site.

### 0. One-time setup per teammate

1. **Go to the FireFly website**, sign in with Google.
2. **Open the dashboard** (top-right). Click "Add drone", give it a name
   (e.g. `kenny_drone`). The site issues you a long **API key** — copy
   it once; you won't see it again. This key authorizes both your GPS
   chip and your laptop to POST data to your drone row.
3. **Flash the GPS firmware** (`main/firmware/gps_telemetry/`) onto your
   ESP32-C3. Before flashing, run `idf.py menuconfig` → "FireFly GPS
   Broadcaster" and set:
   - `Drone ID` → the name you used in step 2
   - `Enable HTTPS POST to cloud server` → **y**
   After flashing, open the FireFLY iOS app and send your WiFi credentials
   plus the API key from step 2 over Bluetooth.
4. **Flash a generic MJPEG source onto your ESP32-CAM** (stock Arduino
   `CameraWebServer` example) and configure it for your WiFi. Confirm
   the cam shows live video at `http://<cam-ip>:81/stream` in your
   browser.

### 1. Power everything on

1. **Plug in the GPS chip**. It'll auto-connect to your WiFi using the
   credentials from the FireFLY iOS App and within ~10 seconds start POSTing GPS
   fixes to Render.
2. **Open the FireFly website** and check the drone panel — your drone
   should show **LIVE** with GPS coordinates and a marker on the map.
   *If it shows OFFLINE, the chip isn't reaching the cloud. Check
   power, WiFi range, and that the API key sent from the iOS app matches.*
3. **Plug in the ESP32-CAM** to a wall charger (not laptop USB — too
   weak, causes brownouts). Wait ~15 s.
4. **Verify the cam in your browser**: open `http://<cam-ip>:81/stream`.
   You should see live video. *If the page hangs or never shows video,
   power-cycle the cam. Stock CameraWebServer only allows one MJPEG
   client at a time, so close the tab after confirming.*

### 2. Start the YOLO worker on your laptop

The worker pulls MJPEG from the cam, runs YOLOv8, geo-locates any fire
it sees using the live drone GPS, and POSTs detections to the cloud.

Set three environment variables, then launch:

```powershell
cd main/fire_detect/fire_detect_YOLO8

# Windows PowerShell
$env:FIREFLY_VIDEO   = "http://<cam-ip>:81/stream"
$env:FIREFLY_SERVER  = "https://firefly-j68i.onrender.com"
$env:FIREFLY_API_KEY = "<your-api-key-from-the-dashboard>"
python fire_detect.py
```

```bash
# macOS / Linux / Git Bash
cd main/fire_detect/fire_detect_YOLO8
FIREFLY_VIDEO=http://<cam-ip>:81/stream \
FIREFLY_SERVER=https://firefly-j68i.onrender.com \
FIREFLY_API_KEY=<your-api-key-from-the-dashboard> \
python fire_detect.py
```

You should see:

```text
Model names (from weights): {0: 'Fire', 1: 'Smoke'}
```

…followed by silence until a fire is detected. An OpenCV preview window
opens showing what the cam sees with YOLOv8 bounding boxes drawn live.

### 3. Trigger a detection

Point the cam at any of:

- A real flame held within ~30 cm of the lens (lighter, candle)
- A phone or second monitor playing a clear fire video
- A printed image of fire

After **3 seconds of sustained Fire-class detection**, the worker logs:

```text
[ALERT] Fire detected for 3.1s — sustained fire presence!
[debug] drone state: lat=36.95... lon=-122.04... alt_m=12.5 heading_deg=185.4
[map] fire @ (36.95..., -122.04...) bearing=184° dist=2m
```

…and a **red fire pin** appears on the live Render map. Every 5 seconds
the fire keeps burning, the worker sends a confirmation POST and the
server's merge logic grows the fire's perimeter on the map (capped at
50 m so a static cam can't inflate it indefinitely).

### 4. Stop

`Ctrl+C` in the YOLO terminal. The GPS chip and the cam keep running
on their own — unplug whenever.

### Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Drone shows OFFLINE on dashboard | Chip not POSTing | Check power; check WiFi credentials and API key sent from the iOS app |
| `Error: could not open video` | Cam URL is wrong, or cam crashed | Open `http://<cam-ip>:81/stream` in browser; power-cycle if hung |
| `/api/fire returned 401` | API key invalid or revoked | Check `FIREFLY_API_KEY` matches one in the dashboard; rotate if needed |
| `/api/fire returned 400 lat and lon must be numeric` | Bearing math failed AND drone has no GPS | Wait for the chip to acquire a fix; check the `[debug]` log line |
| Fires keep flickering / `Fire gone after 0.x s` | Cam image too low-quality, or fire too small in frame | Open the cam's control panel (`http://<cam-ip>/`) and raise resolution / lower JPEG quality value; hold the fire source closer |
| Video stutters on the website's camera panel | Render free-tier bandwidth ceiling | Expected — drop cam to QVGA and quality 15+; or skip the camera relay and rely on the YOLO map-pin output |

---

## Run the indoor demo (running-fix triangulation, no GPS)

This is the path for an indoor demo where the ESP32-C3 can't lock onto
satellites and a second drone isn't available. One drone observes a flame
from two scripted positions, the worker triangulates the bearings, and a
single fire pin drops on the cloud map.

It's a one-command launcher: `python demo.py`. It wakes the cloud, finds
your ESP-CAM, fabricates telemetry for a single registered drone, runs
YOLOv8 against the live MJPEG stream, captures bearing observations on
key press, and POSTs the triangulated result to `/api/fire`.

### 0. One-time setup

1. Register **one drone** on the cloud dashboard (e.g. `demo_drone`) and
   copy its API key.
2. Edit [`main/demo/demo_config.py`](main/demo/demo_config.py) so
   `POSITION_A`, `POSITION_B`, and `TARGET_FIRE` are three real outdoor
   coordinates near where you'll demo. The worker prints the
   intersection angle on startup and warns if it's narrower than 20° —
   aim for ≥30°.

### 1. Launch

```powershell
# Windows PowerShell
$env:FIREFLY_API_KEY = "<paste-from-dashboard>"
python demo.py
```

```bash
# macOS / Linux / Git Bash
export FIREFLY_API_KEY="<paste-from-dashboard>"
python demo.py
```

If the LAN scan can't find your ESP-CAM (some firmware variants put the
control panel on a non-standard port), set the stream URL explicitly:

```powershell
$env:FIREFLY_CAM_URL = "http://<cam-ip>:81/stream"
python demo.py
```

You should see:

```text
[1/3] waking cloud https://firefly-j68i.onrender.com...
[2/3] found camera at http://10.0.0.173:81/stream
[3/3] launching worker (this opens an OpenCV window)
```

…followed by the worker banner with positions, headings, and the
intersection angle. A browser tab opens to the cloud map.

### 2. Run the demo

Click the OpenCV window so it has focus, then:

| Key | Action |
| --- | --- |
| `A` | Set drone to position A (default at launch) — telemetry POSTs as A |
| `B` | Set drone to position B — drone marker slides on the cloud map |
| `R` | Reset both observations (lets you re-demo) |
| `Q` / Esc | Quit |

1. Hold a lighter or candle centered in the camera frame (~20-30 cm
   from the lens). After **3 seconds of sustained detection**, the
   console logs `[CAPTURE] phase A bearing=...` and the OpenCV status
   bar updates to `A:OK`.
2. Press `B`. Reposition the camera to a different angle, hold the
   lighter centered again. After 3 seconds the console logs
   `[CAPTURE] phase B`, immediately followed by `[triangulate] fire pin
   POSTed`.
3. The cloud map shows a **red fire pin** at the triangulated location,
   a red banner slides in at the top, and a desktop notification fires
   (after you've granted permission on first click).

### 3. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `[capture] reconnecting` loops | ESP-CAM stream wedged or another MJPEG client connected | Close any browser tab on `http://<cam-ip>:81/stream`; power-cycle the cam if it persists |
| `[yolo] FATAL: cannot open camera` | Wrong stream URL | Test the URL in a browser, then set `$env:FIREFLY_CAM_URL` |
| Keys do nothing | Terminal has focus, not the OpenCV window | Click the OpenCV window once |
| `[triangulate] rays did not intersect` | Lighter was way off-center in one phase, or same phase captured twice | Press `R` and try again; aim for `lighter_offset` <5° |
| Pin lands far from `TARGET_FIRE` | Lighter wasn't centered (offset > a few degrees rotates the ray) | Center the lighter carefully both phases, or use `R` to retry |
| Render cold-start delay | Free tier sleeps after 15 min idle | Hit the cloud URL in a browser ~1 minute before demo |

### Why this approach

Real triangulation needs two simultaneous observers. The "running fix"
technique substitutes one observer at two different positions, treating
the fire as stationary (true for wildfires, trivially true for a
lighter). The math in [`main/groundstation/triangulator.py`](main/groundstation/triangulator.py)
doesn't care whether the two bearings came from one drone over time or
two drones at once — it just intersects them.

The bearing rays are pre-aimed by computing the compass heading from
each position to `TARGET_FIRE`, so when the lighter is held centered
the system reproduces the planned geometry. Demonstrates the production
pipeline (real firmware, real YOLO, real cloud roundtrip, real
triangulation) with only the satellite portion faked, because we're
indoors.

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
