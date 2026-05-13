import cv2
import os
import time
import requests
from ultralytics import YOLO
from bearing import fire_position

MODEL_PATH = "Trained-Models/last.pt"
VIDEO_PATH = os.environ.get("FIREFLY_VIDEO", "test_videos/palisades_fire.mp4")
MAP_SERVER = os.environ.get("FIREFLY_SERVER", "http://127.0.0.1:5050")
FIREFLY_JWT = os.environ.get("FIREFLY_JWT", "").strip()
FIREFLY_API_KEY = os.environ.get("FIREFLY_API_KEY", "").strip()
CAMERA = {"hfov_deg": 60.0, "vfov_deg": 40.0, "tilt_deg": 90.0}


def _auth_headers():
    if FIREFLY_API_KEY:
        return {"X-API-Key": FIREFLY_API_KEY}
    if FIREFLY_JWT:
        return {"Authorization": f"Bearer {FIREFLY_JWT}"}
    return {}

#cam - spped cont - vtx - pc reciever - python

# Note: model.names reports {0: 'Fire', 1: 'Smoke'} but the trained weights
# were actually annotated the other way around. Empirically this model
# outputs class 1 for fire and class 0 for smoke, so the mapping is flipped
# from what the embedded names claim. Don't "fix" this back.
CLASS_MAP = {
    0: "Smoke",
    1: "Fire",
}

COLOR_MAP = {
    "Smoke": (255, 255, 0),
    "Fire": (0, 0, 255),
}

# --- Config ---
ALERT_THRESHOLD_SECONDS = 3  # how long Fire must be present before logging
GRACE_PERIOD_S = 1.0         # tolerate this long of "no detection" before we treat the streak as ended
YOLO_CONF = 0.25             # detection confidence threshold (was 0.4 — lower = fewer flicker drops)
YOLO_IMGSZ = 960             # input size YOLO resizes to (was 640 — larger = better small-target recall)

# --- Camera / GSD Config ---
# GSD (Ground Sampling Distance, m/pixel) = (altitude_m * sensor_width_mm)
# / (focal_length_mm * image_width_px). It tells us how many real-world
# meters each pixel of the image covers on the ground, which lets us turn
# a bounding-box pixel size into a real-world size.
#
# These two values are intrinsic to the ESP32-CAM (OV3660 sensor) and don't
# change between captures. The OTHER two inputs to GSD — altitude and image
# width — vary per frame and per flight, so we read them live in report_fire
# instead of baking them in here.
CAM_SENSOR_WIDTH_MM  = 2.95   # OV3660: 1/4" optical format, ~2.95 mm wide
CAM_FOCAL_LENGTH_MM  = 2.5    # OV3660 standard lens

# Fallback altitude used only if the drone telemetry has no alt_m. Set to a
# small non-zero number so the math doesn't blow up on a desk demo. For a
# real flight, drone.alt_m from the GPS chip is used directly.
DEFAULT_ALTITUDE_M   = 1.0


def report_fire(frame_shape, boxes):
    """POST a fire detection to the map server, geo-located via bearing.py."""
    fire_box = next((b for b in boxes if int(b.cls[0].item()) == 1), None)
    if fire_box is None:
        return
    x1, y1, x2, y2 = fire_box.xyxy[0].tolist()
    confidence = float(fire_box.conf[0])

    drone = {}
    try:
        drones = requests.get(f"{MAP_SERVER}/api/state", headers=_auth_headers(), timeout=1.0).json().get("drones", {})
        drone = next(iter(drones.values()), {}) if drones else {}
    except requests.RequestException as e:
        print(f"[warn] could not fetch drone state: {e}")

    if not drone:
        print(f"[warn] no drone in /api/state response — skipping fire report")
        return

    print(f"[debug] drone state: lat={drone.get('lat')} lon={drone.get('lon')} "
          f"alt_m={drone.get('alt_m')} heading_deg={drone.get('heading_deg')}")

    H, W = frame_shape[:2]

    # Compute GSD live using the ACTUAL drone altitude (from telemetry) and
    # the ACTUAL captured frame width. This replaces the previous hard-coded
    # 50 m / Mavic-class / 1920 px assumptions, so size estimates reflect
    # the real flight conditions instead of a fictional UAV.
    altitude_m = drone.get("alt_m") or DEFAULT_ALTITUDE_M
    if altitude_m <= 0:
        altitude_m = DEFAULT_ALTITUDE_M
    gsd_m_per_px = (altitude_m * CAM_SENSOR_WIDTH_MM) / (CAM_FOCAL_LENGTH_MM * W)

    real_w = (x2 - x1) * gsd_m_per_px
    real_h = (y2 - y1) * gsd_m_per_px
    real_area = real_w * real_h

    pos = fire_position(drone, (x1, y1, x2, y2), (W, H), CAMERA)

    payload = {
        "size_m": real_w,
        "area_m2": real_area,
        "confidence": confidence,
    }
    if pos is not None:
        payload["lat"] = pos["fire_lat"]
        payload["lon"] = pos["fire_lon"]
        print(f"[map] fire @ ({pos['fire_lat']:.6f}, {pos['fire_lon']:.6f}) "
              f"bearing={pos['bearing_deg']:.0f}° dist={pos['distance_m']:.0f}m")
    else:
        # Fallback: use the drone's own GPS so the fire still plots, even
        # without a valid bearing/distance solution (e.g. missing alt_m or
        # heading_deg in the drone state).
        d_lat, d_lon = drone.get("lat"), drone.get("lon")
        if d_lat is None or d_lon is None:
            print(f"[warn] drone has no GPS — cannot place fire on map")
            return
        payload["lat"] = d_lat
        payload["lon"] = d_lon
        print(f"[map] fire @ drone position ({d_lat:.6f}, {d_lon:.6f}) "
              f"(no bearing solution — alt or heading missing)")

    try:
        r = requests.post(f"{MAP_SERVER}/api/fire", json=payload, headers=_auth_headers(), timeout=1.0)
        if not r.ok:
            print(f"[warn] /api/fire returned {r.status_code}: {r.text}")
    except requests.RequestException as e:
        print(f"[warn] /api/fire post failed: {e}")


def main():
    model = YOLO(MODEL_PATH)
    print("Model names (from weights):", model.names)

    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print("Error: could not open video")
        return

    fire_start_time = None       # when Fire was first detected in current streak
    alert_triggered = False      # prevents spamming the log once threshold is hit
    last_report_at = 0.0         # elapsed-time of the most recent /api/fire POST in this streak
    fire_last_seen = 0.0         # wall-clock time we last saw a Fire detection in the current streak

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Tracking mode (BoT-SORT under the hood) maintains persistent track
        # IDs across frames. With persist=True, a momentary low-confidence
        # frame doesn't break the tracker's lock on the fire, so the streak
        # survives brief detection gaps.
        results = model.track(frame, imgsz=YOLO_IMGSZ, conf=YOLO_CONF,
                              persist=True, verbose=False)
        boxes = results[0].boxes

        fire_detected_this_frame = False

        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0].item())
            label = CLASS_MAP.get(cls_id, f"class_{cls_id}")
            color = COLOR_MAP.get(label, (0, 255, 0))

            if label == "Fire":
                fire_detected_this_frame = True

            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(frame, label, (int(x1), int(y1) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        # --- Fire duration tracking ---
        if fire_detected_this_frame:
            if fire_start_time is None:
                fire_start_time = time.time()   # start the clock
            fire_last_seen = time.time()

            elapsed = time.time() - fire_start_time

            if elapsed >= ALERT_THRESHOLD_SECONDS and not alert_triggered:
                print(f"[ALERT] Fire detected for {elapsed:.1f}s — sustained fire presence!")
                alert_triggered = True
                last_report_at = elapsed
                report_fire(frame.shape, boxes)

            # Periodic re-confirmation while a fire keeps burning. The server
            # merges this with the existing fire row (same drone, same area)
            # and grows the perimeter up to the cap, instead of creating a
            # new fire every time YOLO momentarily loses tracking.
            elif alert_triggered and (elapsed - last_report_at) >= 5.0:
                print(f"[ALERT] Fire still present — {elapsed:.0f}s elapsed, sending confirmation")
                last_report_at = elapsed
                report_fire(frame.shape, boxes)

        else:
            # Grace period: a single missed frame (or a few) shouldn't end
            # the streak. Only reset once we've been without detections for
            # longer than GRACE_PERIOD_S.
            if fire_start_time is not None and (time.time() - fire_last_seen) >= GRACE_PERIOD_S:
                duration = time.time() - fire_start_time
                print(f"[INFO] Fire gone after {duration:.1f}s")
                fire_start_time = None
                alert_triggered = False
                last_report_at = 0.0

        cv2.imshow("Forest Fire Detection", frame)
        if cv2.waitKey(1) & 0xFF in (27, ord('q')):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
