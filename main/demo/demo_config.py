"""Edit the three coordinates below before the demo.

Pick POSITION_A and POSITION_B as two real outdoor spots near the lab, and
TARGET_FIRE as where you want the pin to drop. Aim for an intersection
angle of >=30 degrees as seen from the fire — the worker prints the actual
angle at startup and warns if it's too narrow.
"""

POSITION_A  = (36.9956, -122.0589)
POSITION_B  = (36.9956, -122.0540)
TARGET_FIRE = (36.9985, -122.0565)

# ESP-CAM (OV3660) horizontal field of view.
CAMERA_HFOV_DEG = 60.0

# Telemetry: cadence and reported altitude (alt only affects GSD sizing,
# not triangulation).
TELEMETRY_INTERVAL_S = 1.0
DRONE_ALT_M = 50.0

# Cloud camera relay: JPEG frames per second pushed to /api/camera/frame.
# Higher = smoother dashboard video, more bandwidth on Render free tier.
CAMERA_RELAY_FPS = 2.0

# Sustained-detection gating — fire must be visible this long before
# capture, with a grace period to bridge brief detection gaps.
SUSTAINED_DETECTION_S = 3.0
DETECTION_GRACE_S = 1.0

# YOLO inference params. imgsz=640 is the default YOLOv8 size and roughly
# 2x faster than 960 on CPU; for a lighter held 20-30cm from the lens the
# fire still occupies plenty of pixels.
YOLO_CONF = 0.25
YOLO_IMGSZ = 640
