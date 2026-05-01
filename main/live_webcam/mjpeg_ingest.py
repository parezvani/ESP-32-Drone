"""mjpeg_ingest.py — MJPEG live-feed fire detector.

Pulls frames from an MJPEG stream (phone / laptop / IP cam), runs the YOLO
fire model, and POSTs detections to the FireFly map server via /api/fire.

Usage (standalone):
    python mjpeg_ingest.py --url http://192.168.1.42:8080/video \
                           --server http://127.0.0.1:5050 \
                           --drone-id drone_1

Or import and call start() / stop() from server.py.
"""

import argparse
import threading
import time
from typing import Optional

import cv2
import numpy as np
import requests

# ── Config ────────────────────────────────────────────────────────────────────
MODEL_PATH = "../fire_detect/fire_detect_YOLO8/Trained-Models/best.pt"          # same weights used by app.py / webcam_stream.py
CONF_THRESH = 0.25                      # minimum confidence to count as a detection
FIRE_COOLDOWN_S = 5.0                   # minimum seconds between successive POSTs
SUSTAINED_S = 2.0                      # fire must be visible for this long before posting
RECONNECT_DELAY_S = 3.0                # wait before reconnecting on stream error
FRAME_SKIP = 2                         # run model every Nth frame (1 = every frame)

CLASS_MAP = {0: "Smoke", 1: "Fire"}
COLORS    = {"Fire": (0, 0, 255), "Smoke": (0, 255, 255)}

CAMERA_PARAMS = {                       # defaults — override via set_camera_params()
    "hfov_deg": 60.0,
    "vfov_deg": 40.0,
    "tilt_deg": 90.0,                   # 90° = nadir (straight down)
}

# ── Module-level state (used when embedded in server.py) ──────────────────────
_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_status: dict = {"running": False, "url": None, "last_fire_ts": None,
                 "frames_processed": 0, "fires_posted": 0, "error": None}
_status_lock = threading.Lock()


def get_status() -> dict:
    with _status_lock:
        return dict(_status)


def _update_status(**kw):
    with _status_lock:
        _status.update(kw)


# ── Geo-location helper (mirrors bearing.py) ──────────────────────────────────
def _fire_position(drone_state: dict, bbox: tuple, frame_size: tuple,
                   camera: dict) -> Optional[dict]:
    """Thin wrapper — import bearing.fire_position when available."""
    try:
        from bearing import fire_position
        return fire_position(drone_state, bbox, frame_size, camera)
    except ImportError:
        pass

    import math
    lat  = drone_state.get("lat")
    lon  = drone_state.get("lon")
    alt  = drone_state.get("alt_m")
    hdg  = drone_state.get("heading_deg")
    if None in (lat, lon, alt, hdg) or alt <= 0:
        return None

    x1, y1, x2, y2 = bbox
    W, H = frame_size
    nx = ((x1 + x2) / 2 - W / 2) / W
    ny = ((y1 + y2) / 2 - H / 2) / H

    import math
    yaw_rel   = nx * camera["hfov_deg"]
    pitch_rel = ny * camera["vfov_deg"]
    angle_below = camera["tilt_deg"] + pitch_rel
    if angle_below <= 0:
        return None
    dist_m = alt * math.tan(math.radians(90 - angle_below))
    if dist_m < 0:
        return None

    bearing_deg = (hdg + yaw_rel) % 360
    EARTH_R = 6_378_137.0
    bearing_rad = math.radians(bearing_deg)
    lat_rad = math.radians(lat)
    fire_lat = lat + math.degrees(dist_m * math.cos(bearing_rad) / EARTH_R)
    fire_lon = lon + math.degrees(dist_m * math.sin(bearing_rad) /
                                  (EARTH_R * math.cos(lat_rad)))
    return {"fire_lat": fire_lat, "fire_lon": fire_lon,
            "bearing_deg": bearing_deg, "distance_m": dist_m}


# ── GSD (ground-sampling-distance) for fire size estimate ────────────────────
def _gsd(alt_m: float, hfov_deg: float, frame_w: int) -> float:
    """Approx metres/pixel using horizontal FOV."""
    import math
    ground_width_m = 2 * alt_m * math.tan(math.radians(hfov_deg / 2))
    return ground_width_m / max(frame_w, 1)


# ── Core ingest loop ──────────────────────────────────────────────────────────
def _ingest_loop(url: str, server: str, drone_id: Optional[str],
                 camera: dict, stop: threading.Event) -> None:
    """Runs in a daemon thread."""
    # Lazy-load YOLO so the module can be imported without ultralytics installed
    try:
        from ultralytics import YOLO
        model = YOLO(MODEL_PATH)
        model.to("cpu")
    except Exception as e:
        _update_status(running=False, error=f"Model load failed: {e}")
        print(f"[mjpeg] model load error: {e}")
        return

    _update_status(running=True, url=url, error=None)
    print(f"[mjpeg] starting ingest from {url}")

    fire_start_ts: Optional[float] = None
    last_fire_post_ts: float = 0.0
    frame_n = 0

    while not stop.is_set():
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            _update_status(error=f"Cannot open stream: {url}")
            print(f"[mjpeg] cannot open {url}, retrying in {RECONNECT_DELAY_S}s")
            stop.wait(RECONNECT_DELAY_S)
            continue

        _update_status(error=None)
        print(f"[mjpeg] stream opened OK")

        while not stop.isSet() if hasattr(stop, 'isSet') else not stop.is_set():
            ret, frame = cap.read()
            if not ret:
                print("[mjpeg] stream ended / read error — reconnecting")
                break

            frame_n += 1
            if frame_n % FRAME_SKIP != 0:
                continue

            H, W = frame.shape[:2]
            results = model(frame, imgsz=640, conf=CONF_THRESH, verbose=False)
            boxes = results[0].boxes

            fire_boxes = [b for b in boxes if CLASS_MAP.get(int(b.cls[0].item())) in ("Fire", "Smoke")]
            now = time.time()

            if fire_boxes:
                if fire_start_ts is None:
                    fire_start_ts = now
                elapsed = now - fire_start_ts

                if elapsed >= SUSTAINED_S and now - last_fire_post_ts >= FIRE_COOLDOWN_S:
                    _post_fire(fire_boxes[0], frame.shape, server, drone_id,
                               camera, W, H)
                    last_fire_post_ts = now
                    last_fire_post_ts = now
                    with _status_lock:
                        _status["last_fire_ts"] = now
                        _status["fires_posted"] += 1
            else:
                fire_start_ts = None

            with _status_lock:
                _status["frames_processed"] = frame_n

        cap.release()
        if not stop.is_set():
            stop.wait(RECONNECT_DELAY_S)

    _update_status(running=False)
    print("[mjpeg] ingest stopped")


def _post_fire(box, frame_shape, server: str, drone_id: Optional[str],
               camera: dict, W: int, H: int) -> None:
    """Fetch drone state, compute geo-coords, POST to /api/fire."""
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    conf = float(box.conf[0])

    # Fetch drone state from server
    drone_state: dict = {}
    if drone_id:
        try:
            r = requests.get(f"{server}/api/state", timeout=1.0)
            drones = r.json().get("drones", {})
            drone_state = drones.get(drone_id, {})
        except Exception as e:
            print(f"[mjpeg] could not fetch drone state: {e}")
    
    # Also try legacy single-drone key
    if not drone_state:
        try:
            r = requests.get(f"{server}/api/state", timeout=1.0)
            drone_state = r.json().get("drone", {})
        except Exception:
            pass

    # Estimate fire size via GSD
    alt = drone_state.get("alt_m") or 50.0
    gsd = _gsd(alt, camera.get("hfov_deg", 60.0), W)
    real_w = (x2 - x1) * gsd
    real_h = (y2 - y1) * gsd

    payload: dict = {
        "confidence": round(conf, 3),
        "size_m":    round(real_w, 2),
        "area_m2":   round(real_w * real_h, 2),
    }

    pos = _fire_position(drone_state, (x1, y1, x2, y2), (W, H), camera)
    if pos:
        payload["lat"] = pos["fire_lat"]
        payload["lon"] = pos["fire_lon"]
        print(f"[mjpeg] fire @ ({pos['fire_lat']:.6f}, {pos['fire_lon']:.6f}) "
              f"bearing={pos['bearing_deg']:.0f}° dist={pos['distance_m']:.0f}m "
              f"conf={conf:.2f}")
    else:
        print(f"[mjpeg] fire detected (no geo-location available) conf={conf:.2f}")

    try:
        r = requests.post(f"{server}/api/fire", json=payload, timeout=1.5)
        if not r.ok:
            print(f"[mjpeg] /api/fire -> {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[mjpeg] POST failed: {e}")


# ── Public API (called from server.py) ───────────────────────────────────────
def start(url: str, server: str = "http://127.0.0.1:5050",
          drone_id: Optional[str] = None,
          camera: Optional[dict] = None) -> None:
    """Start the ingest thread. Safe to call if already running (restarts)."""
    global _thread, _stop_event
    stop()  # kill any existing thread first

    _stop_event = threading.Event()
    cam = {**CAMERA_PARAMS, **(camera or {})}
    _thread = threading.Thread(
        target=_ingest_loop,
        args=(url, server, drone_id, cam, _stop_event),
        daemon=True,
        name="mjpeg-ingest",
    )
    _thread.start()


def stop() -> None:
    """Signal the ingest thread to stop and wait briefly."""
    global _thread
    if _thread and _thread.is_alive():
        _stop_event.set()
        _thread.join(timeout=4.0)
    _thread = None
    _update_status(running=False, url=None)


# ── CLI entry point ───────────────────────────────────────────────────────────
def _cli() -> None:
    global CONF_THRESH, FRAME_SKIP
    ap = argparse.ArgumentParser(description="MJPEG fire ingest — stream → YOLO → /api/fire")
    ap.add_argument("--url",      required=True, help="MJPEG stream URL, e.g. http://phone-ip:8080/video")
    ap.add_argument("--server",   default="http://127.0.0.1:5050", help="FireFly map server base URL")
    ap.add_argument("--drone-id", default=None,  help="Drone ID whose state to use for geo-location")
    ap.add_argument("--hfov",     type=float, default=60.0)
    ap.add_argument("--vfov",     type=float, default=40.0)
    ap.add_argument("--tilt",     type=float, default=90.0,  help="Camera tilt below horizontal (deg). 90=nadir")
    ap.add_argument("--conf",     type=float, default=CONF_THRESH)
    ap.add_argument("--skip",     type=int,   default=FRAME_SKIP, help="Run model every Nth frame")
    args = ap.parse_args()
    CONF_THRESH = args.conf
    FRAME_SKIP  = args.skip

    cam = {"hfov_deg": args.hfov, "vfov_deg": args.vfov, "tilt_deg": args.tilt}
    stop_ev = threading.Event()
    try:
        _ingest_loop(args.url, args.server, args.drone_id, cam, stop_ev)
    except KeyboardInterrupt:
        stop_ev.set()
        print("\n[mjpeg] stopped by user")


if __name__ == "__main__":
    _cli()
    
