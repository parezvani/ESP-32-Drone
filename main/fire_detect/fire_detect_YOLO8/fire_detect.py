import cv2
import os
import time
import requests
from ultralytics import YOLO
from bearing import fire_position

MODEL_PATH = "Trained-Models/last.pt"
VIDEO_PATH = os.environ.get("FIREFLY_VIDEO", "test_videos/palisades_fire.mp4")
MAP_SERVER = os.environ.get("FIREFLY_SERVER", "http://localhost:5000")
CAMERA = {"hfov_deg": 60.0, "vfov_deg": 40.0, "tilt_deg": 90.0}

#cam - spped cont - vtx - pc reciever - python

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

# --- Camera / GSD Config ---
# GSD = Ground Sampling Distance (meters per pixel)
# Formula: GSD = (altitude_m * sensor_width_mm) / (focal_length_mm * image_width_px)
# Defaults assume: 50m altitude, DJI Mavic-class camera (4.5mm focal, 6.3mm sensor, 1920px wide)
# Update ALTITUDE_M and FOCAL_LENGTH_MM when real drone specs are known
ALTITUDE_M       = 50.0
SENSOR_WIDTH_MM  = 6.3
FOCAL_LENGTH_MM  = 4.5
IMAGE_WIDTH_PX   = 1920
GSD = (ALTITUDE_M * SENSOR_WIDTH_MM) / (FOCAL_LENGTH_MM * IMAGE_WIDTH_PX)  # m/px


def report_fire(frame_shape, boxes):
    """POST a fire detection to the map server, geo-located via bearing.py."""
    fire_box = next((b for b in boxes if int(b.cls[0].item()) == 1), None)
    if fire_box is None:
        return
    x1, y1, x2, y2 = fire_box.xyxy[0].tolist()
    confidence = float(fire_box.conf[0])

    real_w = (x2 - x1) * GSD
    real_h = (y2 - y1) * GSD
    real_area = real_w * real_h

    try:
        drone = requests.get(f"{MAP_SERVER}/api/state", timeout=1.0).json().get("drone", {})
    except requests.RequestException as e:
        print(f"[warn] could not fetch drone state: {e}")
        drone = {}

    H, W = frame_shape[:2]
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

    try:
        r = requests.post(f"{MAP_SERVER}/api/fire", json=payload, timeout=1.0)
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

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        #can remove the "verbose = False" if you want the full spam logs
        results = model(frame, imgsz=640, conf=0.4, verbose=False)
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

            elapsed = time.time() - fire_start_time

            if elapsed >= ALERT_THRESHOLD_SECONDS and not alert_triggered:
                print(f"[ALERT] Fire detected for {elapsed:.1f}s — sustained fire presence!")
                alert_triggered = True
                report_fire(frame.shape, boxes)

            # Optional: keep logging every N seconds after the first alert
            # Remove this block if you only want one alert per streak
            elif alert_triggered and int(elapsed) % 5 == 0:
                print(f"[ALERT] Fire still present — {elapsed:.0f}s elapsed")

        else:
            if fire_start_time is not None:
                duration = time.time() - fire_start_time
                print(f"[INFO] Fire gone after {duration:.1f}s")
            fire_start_time = None     # reset clock
            alert_triggered = False    # reset so next streak can trigger again

        cv2.imshow("Forest Fire Detection", frame)
        if cv2.waitKey(1) & 0xFF in (27, ord('q')):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
