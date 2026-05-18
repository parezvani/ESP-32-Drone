"""Indoor lab demo worker — running-fix triangulation with one drone.

  Phase A: drone reports POSITION_A + heading_A. Hold lighter in frame.
  Phase B: drone reports POSITION_B + heading_B. Hold lighter again.
  Worker: captures bearing each phase, triangulates locally, POSTs fire.

Strategy 1: heading_A and heading_B are computed so a centered lighter makes
the rays cross exactly at TARGET_FIRE — predictable pin every run.

Keys (focus the OpenCV window):
  A : phase A      B : phase B      R : reset      Q / Esc : quit
"""
import math
import os
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "main" / "groundstation"))
from triangulator import triangulate  # noqa: E402

import demo_config as cfg  # noqa: E402

MODEL_PATH = str(REPO_ROOT / "main" / "fire_detect" / "fire_detect_YOLO8" /
                 "Trained-Models" / "last.pt")

# Empirically class 1 == Fire in our trained weights; see fire_detect.py.
CLASS_FIRE = 1


def bearing_between(from_lat, from_lon, to_lat, to_lon):
    # Flat-earth approximation matching triangulator.py, so headings and
    # ray-intersection math agree at the sub-meter level.
    LAT0 = 36.995578
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(LAT0))
    dx = (to_lon - from_lon) * m_per_deg_lon
    dy = (to_lat - from_lat) * m_per_deg_lat
    deg = math.degrees(math.atan2(dx, dy))
    return deg + 360.0 if deg < 0 else deg


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.phase = "A"
        self.observations = {}        # {'A': (lat, lon, bearing), 'B': ...}
        self.latest_raw = None        # most recent frame from capture thread
        self.latest_annotated = None  # YOLO-annotated frame for cloud relay
        self.triangulated = False
        self.quit = False


def capture_loop(state, url):
    # Direct MJPEG reader. Replaces cv2.VideoCapture, which goes through
    # FFmpeg and blocks for 30+ seconds on ESP-CAM stream hiccups. We pull
    # raw bytes and scan for JPEG SOI/EOI markers ourselves, decoding with
    # cv2.imdecode. Auto-reconnects on any failure within ~1s.
    SOI, EOI = b"\xff\xd8", b"\xff\xd9"
    while not state.quit:
        try:
            r = requests.get(url, stream=True, timeout=(3, 5))
            buf = b""
            for chunk in r.iter_content(chunk_size=16384):
                if state.quit:
                    return
                buf += chunk
                while True:
                    start = buf.find(SOI)
                    if start < 0:
                        if len(buf) > 65536:  # trim runaway pre-SOI noise
                            buf = buf[-32768:]
                        break
                    end = buf.find(EOI, start + 2)
                    if end < 0:
                        break
                    arr = np.frombuffer(buf[start:end + 2], dtype=np.uint8)
                    buf = buf[end + 2:]
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        with state.lock:
                            state.latest_raw = frame
        except requests.RequestException as e:
            print(f"[capture] {e} — reconnecting")
        except Exception as e:
            print(f"[capture] unexpected {type(e).__name__}: {e}")
        time.sleep(1.0)


def telemetry_loop(state, api_key, cloud_url, headings):
    url = f"{cloud_url}/api/drone"
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    while not state.quit:
        with state.lock:
            phase = state.phase
        pos = cfg.POSITION_A if phase == "A" else cfg.POSITION_B
        payload = {
            "lat": pos[0], "lon": pos[1],
            "heading_deg": headings[phase],
            "alt_m": cfg.DRONE_ALT_M,
            "fire_detected": False,
        }
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=2.0)
            if not r.ok:
                print(f"[telemetry] HTTP {r.status_code}: {r.text[:80]}")
        except requests.RequestException as e:
            print(f"[telemetry] {e}")
        time.sleep(cfg.TELEMETRY_INTERVAL_S)


def camera_relay_loop(state, api_key, cloud_url):
    # Push the YOLO-annotated frame to the cloud so the dashboard's camera
    # panel shows live video (with bounding boxes) alongside the map.
    url = f"{cloud_url}/api/camera/frame"
    headers = {"X-API-Key": api_key, "Content-Type": "image/jpeg"}
    interval = 1.0 / cfg.CAMERA_RELAY_FPS
    while not state.quit:
        with state.lock:
            frame = state.latest_annotated
        if frame is not None:
            ok, jpeg = cv2.imencode(".jpg", frame,
                                    [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                try:
                    requests.post(url, data=jpeg.tobytes(),
                                  headers=headers, timeout=2.0)
                except requests.RequestException as e:
                    print(f"[relay] {e}")
        time.sleep(interval)


def post_fire(api_key, cloud_url, lat, lon):
    url = f"{cloud_url}/api/fire"
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    payload = {"lat": lat, "lon": lon, "confidence": 0.95,
               "size_m": 8.0, "source": "triangulation"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=3.0)
        if not r.ok:
            print(f"[fire] HTTP {r.status_code}: {r.text[:120]}")
            return False
        return True
    except requests.RequestException as e:
        print(f"[fire] {e}")
        return False


def maybe_triangulate(state, api_key, cloud_url):
    with state.lock:
        if state.triangulated or len(state.observations) < 2:
            return
        a = state.observations["A"]
        b = state.observations["B"]

    result = triangulate(a[0], a[1], a[2], b[0], b[1], b[2])
    if result is None:
        print("[triangulate] rays did not intersect — press R to reset")
        return

    fire_lat, fire_lon = result
    print(f"[triangulate] fire @ ({fire_lat:.6f}, {fire_lon:.6f})  "
          f"target ({cfg.TARGET_FIRE[0]:.6f}, {cfg.TARGET_FIRE[1]:.6f})")
    if post_fire(api_key, cloud_url, fire_lat, fire_lon):
        with state.lock:
            state.triangulated = True
        print("[triangulate] fire pin POSTed — check the cloud map")


def capture_observation(state, frame, fire_box, headings):
    with state.lock:
        phase = state.phase
        if phase in state.observations:
            return False
    W = frame.shape[1]
    x1, _, x2, _ = fire_box.xyxy[0].tolist()
    pixel_offset = ((x1 + x2) / 2 - W / 2) / W
    angular_offset = pixel_offset * cfg.CAMERA_HFOV_DEG
    drone_heading = headings[phase]
    fire_bearing = (drone_heading + angular_offset) % 360
    pos = cfg.POSITION_A if phase == "A" else cfg.POSITION_B
    with state.lock:
        state.observations[phase] = (pos[0], pos[1], fire_bearing)
    print(f"[CAPTURE] phase {phase}  bearing={fire_bearing:.1f}°  "
          f"(drone_hdg={drone_heading:.1f}°, lighter_offset={angular_offset:+.1f}°)")
    return True


def handle_key(key, state):
    if key == ord('a'):
        with state.lock:
            state.phase = "A"
        print("[keys] PHASE -> A")
    elif key == ord('b'):
        with state.lock:
            state.phase = "B"
        print("[keys] PHASE -> B")
    elif key == ord('r'):
        with state.lock:
            state.observations.clear()
            state.triangulated = False
        print("[keys] observations reset")
    elif key in (27, ord('q')):
        state.quit = True


def yolo_loop(state, api_key, cloud_url, headings):
    print("[yolo] loading model...")
    model = YOLO(MODEL_PATH)
    print("[yolo] waiting for first camera frame...")
    while not state.quit:
        with state.lock:
            if state.latest_raw is not None:
                break
        time.sleep(0.1)
    print("[yolo] ready — press A, hold lighter centered, wait 3s")

    fire_start = None
    fire_last_seen = 0.0
    captured = False

    while not state.quit:
        with state.lock:
            raw = state.latest_raw
        if raw is None:
            time.sleep(0.05)
            continue
        frame = raw.copy()

        results = model.track(frame, imgsz=cfg.YOLO_IMGSZ, conf=cfg.YOLO_CONF,
                              persist=True, verbose=False)
        boxes = results[0].boxes

        fire_box = None
        for b in boxes:
            cls_id = int(b.cls[0].item())
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            color = (0, 0, 255) if cls_id == CLASS_FIRE else (255, 255, 0)
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            if cls_id == CLASS_FIRE and fire_box is None:
                fire_box = b

        now = time.time()
        if fire_box is not None:
            if fire_start is None:
                fire_start = now
                captured = False
            fire_last_seen = now
            if (not captured
                    and (now - fire_start) >= cfg.SUSTAINED_DETECTION_S):
                if capture_observation(state, frame, fire_box, headings):
                    maybe_triangulate(state, api_key, cloud_url)
                captured = True
        else:
            if (fire_start is not None
                    and (now - fire_last_seen) >= cfg.DETECTION_GRACE_S):
                fire_start = None
                captured = False

        with state.lock:
            ph = state.phase
            a_ok = "OK" if "A" in state.observations else "--"
            b_ok = "OK" if "B" in state.observations else "--"
            done = state.triangulated

        status = f"PHASE {ph}   A:{a_ok}  B:{b_ok}   {'FIRE PIN POSTED' if done else ''}"
        cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (255, 255, 255), 2)
        with state.lock:
            state.latest_annotated = frame
        cv2.imshow("FireFly Demo — running-fix triangulation", frame)
        handle_key(cv2.waitKey(1) & 0xFF, state)

    cv2.destroyAllWindows()


def main():
    api_key = os.environ.get("FIREFLY_API_KEY", "").strip()
    cloud_url = os.environ.get("FIREFLY_SERVER", "https://firefly-j68i.onrender.com").rstrip("/")
    camera_url = os.environ.get("FIREFLY_VIDEO", "").strip()

    if not api_key:
        print("ERROR: FIREFLY_API_KEY env var is required.")
        print('   $env:FIREFLY_API_KEY = "<paste-from-dashboard>"')
        sys.exit(1)
    if not camera_url:
        print("ERROR: FIREFLY_VIDEO env var is required.")
        print('   $env:FIREFLY_VIDEO = "http://<cam-ip>:81/stream"')
        sys.exit(1)

    headings = {
        "A": bearing_between(*cfg.POSITION_A, *cfg.TARGET_FIRE),
        "B": bearing_between(*cfg.POSITION_B, *cfg.TARGET_FIRE),
    }
    intersection_angle = abs((headings["A"] - headings["B"] + 180) % 360 - 180)

    print("=" * 68)
    print(" FireFly Demo — Running-Fix Triangulation")
    print("=" * 68)
    print(f"  Cloud:       {cloud_url}")
    print(f"  Camera:      {camera_url}")
    print(f"  Position A:  {cfg.POSITION_A}   heading {headings['A']:6.1f}°")
    print(f"  Position B:  {cfg.POSITION_B}   heading {headings['B']:6.1f}°")
    print(f"  Fire target: {cfg.TARGET_FIRE}   intersection {intersection_angle:.1f}°")
    if intersection_angle < 20:
        print(f"  WARNING: intersection angle is small — rays may be unstable.")
    print(f"  Keys:  A | B | R (reset) | Q (quit)")
    print("=" * 68)

    state = State()
    threading.Thread(target=capture_loop, args=(state, camera_url),
                     daemon=True).start()
    threading.Thread(target=telemetry_loop,
                     args=(state, api_key, cloud_url, headings),
                     daemon=True).start()
    threading.Thread(target=camera_relay_loop,
                     args=(state, api_key, cloud_url),
                     daemon=True).start()

    try:
        yolo_loop(state, api_key, cloud_url, headings)
    except KeyboardInterrupt:
        pass
    finally:
        state.quit = True

    print("[main] done")


if __name__ == "__main__":
    main()
