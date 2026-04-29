import json
import socket
import threading
import time
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

GPS_UDP_PORT = 4210

_lock = threading.Lock()
_drones = {}
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
        drone_id = msg.get("id", "unknown_drone") # Fallback if no ID is sent
        
        if lat is None or lon is None:
            continue
            
        with _lock:
            if drone_id not in _drones:
                _drones[drone_id] = {}
                
            _drones[drone_id]["lat"] = float(lat)
            _drones[drone_id]["lon"] = float(lon)
            _drones[drone_id]["alt_m"] = msg.get("alt_m")
            _drones[drone_id]["sats"] = msg.get("sats")
            _drones[drone_id]["hdop"] = msg.get("hdop")
            # --- NEW DATA POINTS ---
            _drones[drone_id]["heading_deg"] = msg.get("heading_deg")
            _drones[drone_id]["fire_detected"] = msg.get("fire_detected", False)
            # -----------------------
            _drones[drone_id]["ts"] = time.time()


threading.Thread(target=_gps_listener, args=(GPS_UDP_PORT,), daemon=True).start()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    with _lock:
        # Return the whole dictionary of drones
        return jsonify({"drones": dict(_drones), "fires": list(_fires),
                        "camera_url": _camera_url, "server_ts": time.time()})

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
        }
        _fires.append(fire)
        return jsonify(fire)

@app.post("/api/reset")
def reset():
    global _fire_id, _camera_url
    with _lock:
        _fires.clear()
        _fire_id = 0
        _drones.clear() # Clear all tracked drones
        _camera_url = None
        return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
#