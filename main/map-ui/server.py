import threading
import time
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

_lock = threading.Lock()
_drone = {"lat": None, "lon": None, "alt_m": None, "heading_deg": None, "ts": None}
_fires: list[dict] = []
_fire_id = 0


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    with _lock:
        return jsonify({"drone": dict(_drone), "fires": list(_fires), "server_ts": time.time()})


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
    global _fire_id
    with _lock:
        _fires.clear()
        _fire_id = 0
        for k in _drone:
            _drone[k] = None
        return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
