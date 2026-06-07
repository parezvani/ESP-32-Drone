# FireFly Testing Guide

This folder contains the current automated checks and hardware test scripts for
FireFly. There is no single repo-wide pytest runner yet; each test is an
executable script.

## Quick Automated Tests

Run these after setup and before changing backend, detection, or geometry code.
They do not require the Flask server, ESP32 hardware, or a camera.

From the repo root:

```bash
python main/testing/test_triangulator.py
```

Expected result: each case prints `ok`, then the script ends with
`all tests passed`.

From the fire detector directory:

```bash
cd main/fire_detect/fire_detect_YOLO8
python test_bearing.py
```

Expected result: each camera-bearing case prints `ok`, then the script ends
with `all tests passed`.

From the repo root, the same test can also be run as:

```bash
python main/fire_detect/fire_detect_YOLO8/test_bearing.py
```

If your machine only has `python3` on PATH, use `python3` for the same commands.

## Hardware and Integration Checks

These scripts are useful when testing actual ESP32 hardware. They are not part
of the no-hardware automated test pass.

### ESP32-CAM MJPEG Feed

```bash
python main/testing/test_cam_feed.py --url http://<cam-ip>:81/stream --duration 5
```

This checks that the camera stream is reachable, receives bytes, detects JPEG
frames, and estimates bandwidth/FPS.

`test_cam_connection.py` is an older hardcoded reachability check. Prefer
`test_cam_feed.py --url ...` for normal contributor work because it accepts the
camera URL on the command line.

### ESP32-C3 GPS UDP Data

```bash
python main/testing/test_gps_data.py --port 4210 --timeout 45
```

This listens for GPS telemetry broadcasts and reports success once it receives
a valid non-zero coordinate. It also prints satellite count, altitude, HDOP,
and the source drone ID when available.

### UDP Range / Packet Loss

```bash
python main/testing/test_range.py
```

This listens on UDP port 4210 and uses the telemetry `seq` field to estimate
packet drops. Stop it with `Ctrl+C` to print final totals.

### Simulated Fleet

```bash
python main/testing/simulate_fleet.py
```

This sends local UDP telemetry for two simulated drones on port 4210. It is
used by `run.py` and is helpful when developing the map without hardware.

## What Each Test Covers

| Script | Requires hardware | Purpose |
| --- | --- | --- |
| `test_triangulator.py` | No | Verifies two bearing rays intersect, parallel rays are rejected, and diverging rays return `None`. |
| `../fire_detect/fire_detect_YOLO8/test_bearing.py` | No | Verifies camera bounding-box to bearing/distance math. |
| `test_cam_feed.py` | ESP32-CAM or MJPEG source | Verifies a stream returns complete JPEG frames. |
| `test_cam_connection.py` | ESP32-CAM | Legacy hardcoded camera reachability check. |
| `test_gps_data.py` | ESP32-C3 GPS telemetry | Verifies UDP GPS telemetry and GPS lock data. |
| `test_range.py` | ESP32-C3 GPS telemetry | Estimates packet loss/range using telemetry sequence numbers. |
| `simulate_fleet.py` | No | Generates fake local telemetry for map/backend integration work. |

## Adding New Tests

- Keep tests runnable from a fresh clone after `setup.sh` or `setup.ps1`.
- Put no-hardware tests in scripts that can run in CI later.
- Clearly document any hardware, network, model-weight, or camera-stream
  requirement at the top of the file and in this README.
- Prefer deterministic geometry/math tests for backend and triangulation logic.
