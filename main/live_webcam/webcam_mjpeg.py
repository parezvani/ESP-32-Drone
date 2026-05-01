"""webcam_mjpeg.py — Serve your laptop (or phone) camera as an MJPEG stream.

Run this on the machine with the camera:
    python webcam_mjpeg.py                  # webcam 0, port 8080
    python webcam_mjpeg.py --cam 1          # second camera
    python webcam_mjpeg.py --port 8888
    python webcam_mjpeg.py --source rtsp://... # any OpenCV-compatible source

Then POST the URL to the map server:
    curl -X POST http://localhost:5050/api/camera \
         -H 'Content-Type: application/json' \
         -d '{"url": "http://<THIS-MACHINE-LAN-IP>:8080/video"}'

The stream is reachable at:
    http://<LAN-IP>:<port>/video        ← MJPEG feed (use this as camera URL)
    http://<LAN-IP>:<port>/             ← simple HTML preview page
"""

import argparse
import socket
import threading
import time
from typing import Generator

import cv2
from flask import Flask, Response, render_template_string

# ── HTML preview page ─────────────────────────────────────────────────────────
_INDEX_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>FireFly MJPEG preview</title>
  <style>
    body { background: #111; color: #eee; font-family: monospace;
           display: flex; flex-direction: column; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0; }
    img  { max-width: 100%; border: 2px solid #f60; border-radius: 4px; }
    p    { margin-top: 12px; font-size: 0.85rem; color: #aaa; }
  </style>
</head>
<body>
  <img src="/video" alt="live feed">
  <p>POST <code>http://{{ lan_ip }}:{{ port }}/video</code>
     to <code>/api/camera</code> on the FireFly server.</p>
</body>
</html>"""


app = Flask(__name__)
_cap: cv2.VideoCapture | None = None
_cap_lock = threading.Lock()
_latest_frame: bytes | None = None
_frame_lock = threading.Lock()
_args = None


def _capture_loop(source) -> None:
    """Continuously read frames into _latest_frame."""
    global _cap, _latest_frame
    with _cap_lock:
        _cap = cv2.VideoCapture(source)
        if not _cap.isOpened():
            print(f"[mjpeg-server] ERROR: cannot open source: {source}")
            return
        _cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    print(f"[mjpeg-server] capture started from {source}")
    while True:
        with _cap_lock:
            if _cap is None:
                break
            ret, frame = _cap.read()
        if not ret:
            print("[mjpeg-server] capture read failed — retrying")
            time.sleep(0.5)
            continue
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with _frame_lock:
                _latest_frame = buf.tobytes()


def _gen_mjpeg() -> Generator[bytes, None, None]:
    """Yield MJPEG boundary frames."""
    while True:
        with _frame_lock:
            frame = _latest_frame
        if frame is None:
            time.sleep(0.02)
            continue
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(0.033)   # ~30 fps cap


@app.get("/")
def index():
    lan_ip = _get_lan_ip()
    return render_template_string(_INDEX_HTML, lan_ip=lan_ip, port=_args.port)


@app.get("/video")
def video():
    return Response(_gen_mjpeg(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/snapshot")
def snapshot():
    """Single JPEG frame — useful for testing."""
    with _frame_lock:
        frame = _latest_frame
    if frame is None:
        return "No frame yet", 503
    return Response(frame, mimetype="image/jpeg")


def _get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main() -> None:
    global _args
    ap = argparse.ArgumentParser(description="Serve a local camera as MJPEG over HTTP")
    ap.add_argument("--cam",    type=int,   default=0,    help="OpenCV camera index (default 0)")
    ap.add_argument("--source", type=str,   default=None, help="Override cam with any OpenCV source URL/path")
    ap.add_argument("--port",   type=int,   default=8080, help="HTTP port (default 8080)")
    ap.add_argument("--host",   type=str,   default="0.0.0.0")
    _args = ap.parse_args()

    source = _args.source if _args.source else _args.cam
    lan_ip = _get_lan_ip()

    # Start capture in background thread
    t = threading.Thread(target=_capture_loop, args=(source,), daemon=True)
    t.start()
    time.sleep(0.5)  # give the capture thread a moment to open

    print(f"\n{'─'*55}")
    print(f"  MJPEG feed :  http://{lan_ip}:{_args.port}/video")
    print(f"  Preview    :  http://{lan_ip}:{_args.port}/")
    print(f"\n  POST this to /api/camera on FireFly server:")
    print(f'  curl -X POST http://FIREFLY-SERVER:5050/api/camera \\')
    print(f'       -H "Content-Type: application/json" \\')
    print(f'       -d \'{{"url": "http://{lan_ip}:{_args.port}/video"}}\'')
    print(f"{'─'*55}\n")

    app.run(host=_args.host, port=_args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
    
