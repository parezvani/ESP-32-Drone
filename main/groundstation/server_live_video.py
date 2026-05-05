import json
import os
import secrets
import socket
import threading
import time
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

from triangulator import triangulate

app = Flask(__name__)

CAMERA_API_TOKEN = os.environ.get("FIREFLY_CAMERA_TOKEN", "").strip()
MAX_CAMERA_URL_LEN = 2048

GPS_UDP_PORT = 4210
TRIANGULATE_COOLDOWN_S = 5.0
TRIANGULATE_FRESHNESS_S = 10.0
DRONE_TIMEOUT_S = 30.0

_lock = threading.Lock()
_drones = {}
_fires: list[dict] = []
_fire_id = 0
_camera_url: str | None = None
_last_triangulation = 0.0
_warned_ids: set[str] = set()

# ── MJPEG ingest (optional — gracefully absent if ultralytics not installed) ──
try:
    import mjpeg_ingest
    _HAS_INGEST = True
except Exception as e:
    _HAS_INGEST = False
    print(f"[warn] mjpeg_ingest failed to load: {type(e).__name__}: {e}")


def _camera_token_from_request() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return request.headers.get("X-Camera-Token", "").strip()


def require_camera_token(f):
    """Require the shared camera-control token before accepting stream changes."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not CAMERA_API_TOKEN:
            return jsonify({
                "error": "camera API token not configured",
                "hint": "set FIREFLY_CAMERA_TOKEN on the server",
            }), 503

        token = _camera_token_from_request()
        if not token or not secrets.compare_digest(token, CAMERA_API_TOKEN):
            return jsonify({"error": "camera auth required"}), 401

        return f(*args, **kwargs)
    return wrapper


def _validate_camera_url(url):
    if url is None:
        return None, None
    if not isinstance(url, str):
        return None, "url must be a string or null"

    url = url.strip()
    if not url:
        return None, None
    if len(url) > MAX_CAMERA_URL_LEN:
        return None, "url is too long"

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None, "url must be an http(s) URL"
    return url, None


def _maybe_triangulate() -> None:
    """Run triangulation if 2+ drones recently flagged fire_detected.

    Caller must hold _lock. Mutates _fires and _last_triangulation.
    """
    global _last_triangulation, _fire_id
    now = time.time()
    if now - _last_triangulation < TRIANGULATE_COOLDOWN_S:
        return

    seers = [
        (d_id, d) for d_id, d in _drones.items()
        if d.get("fire_detected")
        and d.get("heading_deg") is not None
        and now - d.get("ts", 0) < TRIANGULATE_FRESHNESS_S
    ]
    if len(seers) < 2:
        return

    (id1, d1), (id2, d2) = seers[:2]
    coords = triangulate(
        d1["lat"], d1["lon"], d1["heading_deg"],
        d2["lat"], d2["lon"], d2["heading_deg"],
    )
    if coords is None:
        return

    lat, lon = coords
    _fire_id += 1
    _fires.append({
        "id": _fire_id,
        "lat": lat,
        "lon": lon,
        "size_m": 12.0,
        "area_m2": 75.0,
        "confidence": 0.88,
        "ts": now,
        "source": "triangulation",
    })
    _last_triangulation = now
    print(f"[triangulate] {id1} x {id2} -> ({lat:.5f}, {lon:.5f})")


def _gps_listener(port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    print(f"[gps] listening for UDP broadcasts on :{port}")
    while True:
        try:
            data, addr = sock.recvfrom(512)
        except OSError:
            continue
        try:
            msg = json.loads(data.decode("utf-8", "ignore"))
        except json.JSONDecodeError:
            continue

        lat, lon = msg.get("lat"), msg.get("lon")
        drone_id = msg.get("id", "unknown_drone")

        if lat is None or lon is None:
            continue

        if drone_id == "unknown_drone" and addr[0] not in _warned_ids:
            print(f"[warn] UDP packet from {addr[0]} has no 'id' field — set DRONE_ID before flashing")
            _warned_ids.add(addr[0])
        elif drone_id not in _drones and drone_id not in _warned_ids:
            print(f"[gps] new drone connected: {drone_id} from {addr[0]}")
            _warned_ids.add(drone_id)

        with _lock:
            if drone_id not in _drones:
                _drones[drone_id] = {}

            _drones[drone_id]["lat"] = float(lat)
            _drones[drone_id]["lon"] = float(lon)
            _drones[drone_id]["alt_m"] = msg.get("alt_m")
            _drones[drone_id]["sats"] = msg.get("sats")
            _drones[drone_id]["hdop"] = msg.get("hdop")
            _drones[drone_id]["heading_deg"] = msg.get("heading_deg")
            _drones[drone_id]["fire_detected"] = msg.get("fire_detected", False)
            _drones[drone_id]["ts"] = time.time()

            _maybe_triangulate()


def _drone_reaper() -> None:
    """Drop drones that haven't broadcast within DRONE_TIMEOUT_S."""
    while True:
        time.sleep(5.0)
        now = time.time()
        with _lock:
            stale = [k for k, v in _drones.items() if now - v.get("ts", 0) > DRONE_TIMEOUT_S]
            for k in stale:
                del _drones[k]
                _warned_ids.discard(k)
                print(f"[gps] dropped stale drone: {k}")


threading.Thread(target=_gps_listener, args=(GPS_UDP_PORT,), daemon=True).start()
threading.Thread(target=_drone_reaper, daemon=True).start()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    with _lock:
        ingest_status = mjpeg_ingest.get_status() if _HAS_INGEST else {"running": False}
        return jsonify({
            "drones": dict(_drones),
            "fires": list(_fires),
            "camera_url": _camera_url,
            "server_ts": time.time(),
            "ingest": ingest_status,
        })


@app.post("/api/fire")
def post_fire():
    global _fire_id
    data = request.get_json(force=True, silent=True) or {}
    with _lock:
        lat = data.get("lat")
        lon = data.get("lon")
        if lat is None or lon is None:
            return jsonify({"error": "Coords required"}), 400

        _fire_id += 1
        fire = {
            "id": _fire_id,
            "lat": float(lat),
            "lon": float(lon),
            "size_m": data.get("size_m"),
            "area_m2": data.get("area_m2"),
            "confidence": data.get("confidence"),
            "ts": time.time(),
            "source": data.get("source", "detection"),
        }
        _fires.append(fire)
        return jsonify(fire)


@app.post("/api/camera")
@require_camera_token
def set_camera():
    """Set (or clear) the camera URL.

    Body: {"url": "http://phone-ip:8080/video"}
    Passing url=null or omitting it clears the camera and stops ingest.
    Optional fields forwarded to the ingest worker:
        drone_id  – which drone's state to use for geo-location
        hfov_deg, vfov_deg, tilt_deg – camera intrinsics
        autostart – if true (default), start MJPEG ingest immediately
    """
    global _camera_url
    data = request.get_json(force=True, silent=True) or {}
    url, error = _validate_camera_url(data.get("url"))
    if error:
        return jsonify({"error": error}), 400

    with _lock:
        _camera_url = url

    # ── Ingest lifecycle ──────────────────────────────────────────────────────
    if _HAS_INGEST:
        if _camera_url is None:
            mjpeg_ingest.stop()
            print("[camera] ingest stopped (URL cleared)")
        elif data.get("autostart", True):
            camera_params = {}
            for key in ("hfov_deg", "vfov_deg", "tilt_deg"):
                if key in data:
                    camera_params[key] = float(data[key])
            mjpeg_ingest.start(
                url=_camera_url,
                server=request.host_url.rstrip("/"),
                drone_id=data.get("drone_id"),
                camera=camera_params or None,
            )
            print(f"[camera] ingest started -> {_camera_url}")

    resp = {"camera_url": _camera_url}
    if _HAS_INGEST:
        resp["ingest"] = mjpeg_ingest.get_status()
    return jsonify(resp)


@app.post("/api/camera/ingest/stop")
@require_camera_token
def stop_ingest():
    """Stop the MJPEG ingest worker without clearing the URL."""
    if not _HAS_INGEST:
        return jsonify({"error": "mjpeg_ingest not available"}), 501
    mjpeg_ingest.stop()
    return jsonify({"ok": True, "ingest": mjpeg_ingest.get_status()})


@app.post("/api/camera/ingest/start")
@require_camera_token
def start_ingest():
    """(Re)start ingest using the currently stored camera URL."""
    if not _HAS_INGEST:
        return jsonify({"error": "mjpeg_ingest not available"}), 501
    with _lock:
        url = _camera_url
    if not url:
        return jsonify({"error": "No camera URL set — POST to /api/camera first"}), 400
    data = request.get_json(force=True, silent=True) or {}
    camera_params = {k: float(data[k]) for k in ("hfov_deg", "vfov_deg", "tilt_deg") if k in data}
    mjpeg_ingest.start(
        url=url,
        server=request.host_url.rstrip("/"),
        drone_id=data.get("drone_id"),
        camera=camera_params or None,
    )
    return jsonify({"ok": True, "ingest": mjpeg_ingest.get_status()})


@app.get("/api/camera/ingest/status")
def ingest_status():
    if not _HAS_INGEST:
        return jsonify({"error": "mjpeg_ingest not available"}), 501
    return jsonify(mjpeg_ingest.get_status())


@app.post("/api/triangulate")
def manual_triangulate():
    with _lock:
        before = len(_fires)
        _maybe_triangulate()
        new_fire = _fires[-1] if len(_fires) > before else None
    return jsonify({"fire": new_fire})


@app.post("/api/reset")
def reset():
    global _fire_id, _camera_url, _last_triangulation
    if _HAS_INGEST:
        mjpeg_ingest.stop()
    with _lock:
        _fires.clear()
        _fire_id = 0
        _drones.clear()
        _camera_url = None
        _last_triangulation = 0.0
        return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)


# Add camera ip via terminal using this format:
# curl -s -X POST http://localhost:5050/api/camera \
#   -H "Content-Type: application/json" \
#   -H "X-Camera-Token: $FIREFLY_CAMERA_TOKEN" \
#   -d '{"url": "http://10.0.0.232:8080/video", "drone_id": "drone_1"}' | python -m json.tool
