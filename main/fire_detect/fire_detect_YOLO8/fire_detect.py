import cv2
import time
from ultralytics import YOLO

MODEL_PATH = "Trained-Models/last.pt"
VIDEO_PATH = "fire_video.mp4"

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
