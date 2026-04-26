import json
import socket
import threading
import time
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

GPS_UDP_PORT = 4210

_lock = threading.Lock()
_drone = {"lat": None, "lon": None, "alt_m": None, "heading_deg": None,
          "sats": None, "hdop": None, "ts": None}
_fires: list[dict] = []
_fire_id = 0
_camera_url: str | None = None


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
        if lat is None or lon is None:
            continue
        with _lock:
            _drone["lat"] = float(lat)
            _drone["lon"] = float(lon)
            _drone["alt_m"] = msg.get("alt_m")
            _drone["sats"] = msg.get("sats")
            _drone["hdop"] = msg.get("hdop")
            _drone["ts"] = time.time()


threading.Thread(target=_gps_listener, args=(GPS_UDP_PORT,), daemon=True).start()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    with _lock:
        return jsonify({"drone": dict(_drone), "fires": list(_fires),
                        "camera_url": _camera_url, "server_ts": time.time()})


@app.post("/api/camera")
def set_camera():
    global _camera_url
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url")
    if url is not None and not isinstance(url, str):
        return jsonify({"error": "url must be a string or null"}), 400
    with _lock:
        _camera_url = url or None
        return jsonify({"camera_url": _camera_url})


@app.post("/api/drone")
def post_drone():
    data = request.get_json(force=True, silent=True) or {}
    lat, lon = data.get("lat"), data.get("lon")
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon required"}), 400
    with _lock:
        _drone["lat"] = float(lat)
        _drone["lon"] = float(lon)
        _drone["alt_m"] = data.get("alt_m")
        _drone["heading_deg"] = data.get("heading_deg")
        _drone["ts"] = time.time()
        return jsonify(dict(_drone))


@app.post("/api/fire")
def post_fire():
    global _fire_id
    data = request.get_json(force=True, silent=True) or {}
    with _lock:
        lat = data.get("lat", _drone["lat"])
        lon = data.get("lon", _drone["lon"])
        if lat is None or lon is None:
            return jsonify({"error": "no coords provided and no drone position known"}), 400
        _fire_id += 1
        fire = {
            "id": _fire_id,
            "lat": float(lat),
            "lon": float(lon),
            "size_m": data.get("size_m"),
            "area_m2": data.get("area_m2"),
            "confidence": data.get("confidence"),
            "ts": time.time(),
        }
        _fires.append(fire)
        return jsonify(fire)


@app.post("/api/reset")
def reset():
    global _fire_id, _camera_url
    with _lock:
        _fires.clear()
        _fire_id = 0
        for k in _drone:
            _drone[k] = None
        _camera_url = None
        return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
