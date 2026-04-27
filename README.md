# ESP-32-Drone / FireFly

FireFly is a student-built drone and ground-station project for fire-risk monitoring in areas without existing sensor coverage. The repository currently contains ESP-IDF firmware prototypes, a simple telemetry server, a Flask/Leaflet map UI, fire-detection experiments, hardware documentation, and a LiteWing reference submodule.

## Repository Layout

- `main/`: source code, firmware experiments, and hardware tests.
  - `groundstation/`: Python Flask base-station — receives GPS telemetry, hosts the Leaflet map UI, proxies the camera feed, and ingests fire detections.
  - `firmware/`: ESP-IDF projects flashed to the on-drone microcontrollers.
    - `gps_telemetry/`: GPS UART reader + WiFi UDP broadcaster.
  - `fire_detect/`: YOLOv8 fire/smoke detection, bearing math, and synthetic drone simulator for offline testing.
  - `scripts/`: ESP-NOW communication and control prototypes.
  - `testing/`: hardware test firmware (motor/PWM, range tests).
  - `lab4_1/`: earlier lab firmware kept for reference.
  - `scrapped/`: older discarded experiments and scratch files (includes the deprecated Rust fire-server and ESP-NOW prototypes).
- `docs/`: project documentation and design artifacts.
  - `design-document/`: design-document source and exported PDFs.
  - `drone-designs/`: frame dimensions, CAD, STL, G-code, and design images.
  - `circuit-design/`: schematics, wiring diagrams, and circuit images.
  - `bill-of-materials/`: bill-of-materials revisions.
  - `status-reports/`: weekly reports and project planning artifacts.
  - `meeting-notes/`: team notes, decisions, and action items.
  - `research-notes/`: reference material gathered during development, including `project_review_findings.md`.
  - `testing_logs/`: prototype testing logs and PDFs.
- `esp/esp-idf/`: local ESP-IDF checkout, when present in the working tree.
- `litewing/LiteWing/`: LiteWing firmware/hardware reference project submodule.

## Running the Pipeline (No Hardware Required)

The full detection + geolocation pipeline runs end-to-end with synthetic GPS and a recorded fire video — no drone, no camera, no GPS module needed. Three terminals from the repo root.

### 1. Install Python dependencies

```bash
pip install -r main/groundstation/requirements.txt
pip install ultralytics opencv-python requests
```

### 2. Start the ground station (Terminal 1)

```bash
cd main/groundstation
python server.py
```

Open <http://127.0.0.1:5000> in a browser. You should see the map UI and the console should print `[gps] listening for UDP broadcasts on :4210`.

### 3. Start the fake drone (Terminal 2)

```bash
cd main/fire_detect/fire_detect_YOLO8
python fake_drone.py
```

Posts a synthetic GPS position to `/api/drone` every 500 ms. The drone marker should appear on the map and trace a slow circle around UCSC.

### 4. Start fire detection (Terminal 3)

```bash
cd main/fire_detect/fire_detect_YOLO8
python fire_detect.py
```

Runs YOLOv8 on `test_videos/palisades_fire.mp4` by default. After 3 seconds of sustained detection, a fire marker is POSTed to `/api/fire` and shows up on the map.

To use a different video or a live MJPEG stream (e.g. ESP32-CAM):

```bash
FIREFLY_VIDEO=http://192.168.1.47:81/stream python fire_detect.py
```

### 5. Run the bearing unit tests

```bash
cd main/fire_detect/fire_detect_YOLO8
python test_bearing.py
```

Five geometry test cases. Should end with `all tests passed`.

### Stopping

Close the OpenCV window (or press `q`) for fire_detect, then `Ctrl+C` the other two terminals. To wipe drone/fire state without restarting the server:

```bash
curl -X POST http://127.0.0.1:5000/api/reset
```

## Firmware (Real Hardware)

The on-drone firmware lives in `main/firmware/gps_telemetry/`. Build and flash with ESP-IDF 5.x:

```bash
cd main/firmware/gps_telemetry
idf.py set-target esp32c3   # or esp32s3
idf.py menuconfig            # set WiFi SSID/password under "FireFly GPS Broadcaster"
idf.py build flash monitor
```

The firmware reads NMEA from a GPS module on UART1 (RX=GPIO4, TX=GPIO5, 9600 baud) and broadcasts JSON fixes over UDP on port 4210. The ground station picks them up automatically when both devices are on the same WiFi network.
