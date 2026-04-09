import cv2
from ultralytics import YOLO

# Path to your trained fire/smoke weights
MODEL_PATH = "Trained-Models/last.pt"   # change to actual name
VIDEO_PATH = "fire_video.mp4"           # your preexisting video

# Here you decide what each class ID means *visually*
# If the model internally has {0: 'Fire', 1: 'Smoke'}
# but appears reversed to you, flip them here:
CLASS_MAP = {
    0: "Smoke",   # show 'Smoke' when model predicts class 0
    1: "Fire",    # show 'Fire' when model predicts class 1
}

COLOR_MAP = {
    "Smoke": (255, 255, 0),  # yellow/cyan
    "Fire": (0, 0, 255),     # red
}

def main():
    model = YOLO(MODEL_PATH)
    print("Model names (from weights):", model.names)

    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print("Error: could not open video")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Run YOLOv8 inference
        results = model(frame, imgsz=640, conf=0.4)
        boxes = results[0].boxes

        # Draw detections ourselves instead of results[0].plot()
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0].item())
            label = CLASS_MAP.get(cls_id, f"class_{cls_id}")
            color = COLOR_MAP.get(label, (0, 255, 0))

            cv2.rectangle(
                frame,
                (int(x1), int(y1)),
                (int(x2), int(y2)),
                color,
                2,
            )
            cv2.putText(
                frame,
                label,
                (int(x1), int(y1) - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
            )

        cv2.imshow("Forest Fire Detection", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27 or key == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()