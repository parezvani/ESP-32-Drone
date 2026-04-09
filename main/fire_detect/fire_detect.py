import cv2
import numpy as np

# ---- settings you can tweak ----
VIDEO_PATH = "fire_video.mp4"   # or 0 for webcam
MIN_CONTOUR_AREA = 500     # ignore very small blobs
FIRE_THRESHOLD = 1000      # min total fire-like area (in pixels) before we say "FIRE!"
# -------------------------------

def main():
    cap = cv2.VideoCapture(VIDEO_PATH)

    if not cap.isOpened():
        print("Error: could not open video/source")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break  # end of video

        # Resize (optional, faster)
        frame = cv2.resize(frame, (640, 480))

        # Convert to HSV color space
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Fire-like color range in HSV (approximate, you should tune for your data)
        # Lower and upper bounds for orange/yellowish flames
        lower = np.array([0, 150, 150])    # H, S, V
        upper = np.array([50, 255, 255])

        # Create mask for fire-like colors
        mask = cv2.inRange(hsv, lower, upper)

        # Optional: remove noise and fill gaps
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)

        # Find contours of fire-like regions
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        fire_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < MIN_CONTOUR_AREA:
                continue
            fire_area += area
            x, y, w, h = cv2.boundingRect(cnt)
            # draw bounding boxes where fire-like color is detected
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)

        # Decide if fire is present based on total area
        if fire_area > FIRE_THRESHOLD:
            cv2.putText(frame, "FIRE DETECTED", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            print("Fire detected in current frame (area =", fire_area, ")")
        else:
            cv2.putText(frame, "No fire", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

        # Show original frame and mask
        cv2.imshow("Fire Detection - Frame", frame)
        cv2.imshow("Fire Mask", mask)

        key = cv2.waitKey(1) & 0xFF
        if key == 27 or key == ord('q'):  # ESC or q to quit
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
