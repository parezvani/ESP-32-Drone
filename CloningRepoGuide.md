# FireFly Contributor Guide

This guide is for those who want to clone the repo, install dependencies,
run tests, and start contributing to any part of FireFly.

## 1. Local Setup

Install Git and Python 3.10 or newer, then clone the repository:

```bash
git clone https://github.com/parezvani/FireFly.git
cd FireFly
```

Create the local virtual environment and install Python dependencies:

```bash
# macOS / Linux / Git Bash
bash setup.sh

# Windows PowerShell
.\setup.ps1
```

Activate the virtual environment in each new terminal:

```bash
source .venv/bin/activate        # macOS / Linux / Git Bash
.\.venv\Scripts\Activate.ps1     # Windows PowerShell
```

The setup script installs the top-level `requirements.txt`, which covers the
local server, simulator, YOLO worker, OpenCV, and request clients used by the
demo path. If you are working on production-style backend features with the
database, Supabase auth, or Gunicorn, also install:

```bash
pip install -r main/groundstation/requirements.txt
```

If `python` is not available on your machine, use `python3` in the commands
below. Inside an activated virtual environment, `python` should normally work.

## 2. Run the Project

No-hardware local path:

```bash
python run.py --no-cam
```

This starts the Flask ground station and simulated drone fleet, but skips
ESP32-CAM discovery and YOLO inference.

Full local launcher:

```bash
python run.py
```

This starts the server on `http://127.0.0.1:5050`, scans the local subnet for
an ESP32-CAM MJPEG stream, starts simulated drone telemetry, starts YOLO if a
camera is found, and opens the map UI.

Backend-only workflow:

```bash
cd main/groundstation
python server.py
```

Use this while editing Flask routes, templates, static map behavior, dashboard
pages, or API contracts. Local development works without `DATABASE_URL` or
Supabase secrets; in that mode the backend keeps drones and fires in memory.

YOLO worker workflow:

```bash
cd main/fire_detect/fire_detect_YOLO8
FIREFLY_VIDEO=http://<cam-ip>:81/stream \
FIREFLY_SERVER=http://127.0.0.1:5050 \
python fire_detect.py
```

For the deployed Render site, set `FIREFLY_SERVER` to the cloud URL and set
`FIREFLY_API_KEY` to a drone API key from the dashboard.

Indoor demo workflow:

```bash
export FIREFLY_API_KEY="<dashboard-api-key>"
python demo.py
```

On Windows PowerShell:

```powershell
$env:FIREFLY_API_KEY = "<dashboard-api-key>"
python demo.py
```

## 3. Subsystems

Ground station website/backend: `main/groundstation/`

- `server.py` is the production-capable Flask app.
- `templates/` contains the landing page, login, dashboard, mission log, and map UI.
- `static/app.js` polls `/api/state` and renders drones, trails, fire pins,
  sight lines, camera preview, and alerts with Leaflet.
- `triangulator.py` intersects two bearing rays to estimate a fire coordinate.
- `cam_relay.py` pulls local ESP32-CAM MJPEG frames and pushes JPEGs to the cloud.

Fire detection worker: `main/fire_detect/fire_detect_YOLO8/`

- `fire_detect.py` pulls video from `FIREFLY_VIDEO`, runs YOLOv8/OpenCV, waits
  for sustained fire detection, calculates fire location, and posts to `/api/fire`.
- `bearing.py` converts a fire bounding box plus drone GPS, heading, altitude,
  camera field of view, and tilt into a bearing/distance estimate.
- `Trained-Models/` stores YOLO weights used by the worker.

ESP32-C3 GPS firmware: `main/firmware/gps_telemetry/`

- Built with ESP-IDF.
- Reads NMEA GPS over UART, computes heading from movement, broadcasts UDP JSON
  on port 4210, and can POST telemetry to `/api/drone`.
- Uses BLE provisioning to receive WiFi credentials and the dashboard API key
  from the iOS app.
- See `main/firmware/gps_telemetry/BLE_PROVISIONING.md` for firmware details.

ESP32-CAM stream:

- The ESP32-CAM runs camera firmware such as Arduino `CameraWebServer`.
- It serves MJPEG at `http://<cam-ip>:81/stream`.
- It does not run YOLO or triangulation on-device; the laptop worker consumes
  its stream and performs the heavy processing.

iOS provisioning app: `main/firefly_ios_app/`

- SwiftUI app for sending WiFi SSID, WiFi password, and drone API key to the
  ESP32-C3 over BLE.
- Open `main/firefly_ios_app/FireFLY/FireFLY.xcodeproj` in Xcode.

## 4. Environment Variables

Backend/server variables:

| Variable | Used by | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `main/groundstation/server.py` | Enables SQLAlchemy/Postgres persistence for drones, API keys, telemetry, and fires. Without it, local dev uses in-memory state. |
| `SUPABASE_JWT_SECRET` | `server.py` | Verifies Supabase JWTs for protected browser/API routes. Required in production. |
| `SUPABASE_URL` | `server.py`, templates | Provides Supabase auth URL and JWKS discovery. |
| `SUPABASE_PUBLISHABLE_KEY` | `server.py`, templates | Browser-side Supabase key for login/dashboard pages. |
| `FLASK_SECRET_KEY` | `server.py` | Flask session signing secret. A random value is generated locally if omitted. |
| `FIREFLY_CAMERA_TOKEN` | `server.py`, `run.py` | Shared token for changing the stored camera URL through `/api/camera`. |
| `DISCORD_WEBHOOK_URL` | `server.py` | Optional fire alert webhook for new fires. |

Worker/demo variables:

| Variable | Used by | Purpose |
| --- | --- | --- |
| `FIREFLY_VIDEO` | YOLO worker, demo worker | Camera/video source such as `http://<cam-ip>:81/stream`. |
| `FIREFLY_SERVER` | YOLO worker, demo launcher | FireFly server base URL, local or cloud. |
| `FIREFLY_API_KEY` | YOLO worker, demo worker | Dashboard-issued drone key for authenticated `/api/state`, `/api/drone`, `/api/fire`, and camera frame POSTs. |
| `FIREFLY_JWT` | YOLO worker | Alternate auth path using a Supabase JWT. |
| `FIREFLY_CAM_URL` | `run.py`, `demo.py` | Explicit camera stream URL that skips subnet scanning. |

Firmware build settings live in `main/firmware/gps_telemetry/main/Kconfig.projbuild`.
Use `idf.py menuconfig` to set the drone ID, UDP port, and optional cloud URL.

## 5. Tests and Checks

Run the quick automated tests from the repo root:

```bash
python main/testing/test_triangulator.py
python main/fire_detect/fire_detect_YOLO8/test_bearing.py
```

Equivalent directory-local form for the bearing test:

```bash
cd main/fire_detect/fire_detect_YOLO8
python test_bearing.py
```

Optional hardware checks:

```bash
python main/testing/test_cam_feed.py --url http://<cam-ip>:81/stream --duration 5
python main/testing/test_gps_data.py --port 4210 --timeout 45
python main/testing/test_range.py
```

There is no single repo-wide pytest suite yet; the current tests are executable
scripts. Keep new tests easy to run from a clean clone, and document any
hardware requirement beside the command.

## 6. Contribution Notes

- Keep runtime API changes small and document them in both README-facing usage
  docs and `docs/backend-architecture.md`.
- Avoid committing local secrets, dashboard API keys, Supabase secrets, camera
  tokens, generated virtual environments, or build outputs.
- Prefer local simulator paths before testing against live hardware or Render.
- For ESP32 work, record board type, ESP-IDF version, serial port, and any
  `menuconfig` changes in the PR or commit notes.
- For camera/YOLO work, record the stream URL type, resolution, lighting, and
  whether the test used a real flame, fire video, or printed image.
