import hashlib
import json
import os
import secrets
import socket
import threading
import time
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from triangulator import triangulate

# Optional: only import if env vars are set. Allows local dev without Postgres.
DATABASE_URL = os.environ.get("DATABASE_URL")
JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")

_db_engine = None
_db_session_maker = None
_models = None

if DATABASE_URL:
    from sqlalchemy import (
        Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
        create_engine, BigInteger, Index,
    )
    from sqlalchemy.orm import declarative_base, sessionmaker, relationship
    from sqlalchemy.dialects.postgresql import UUID
    import uuid

    Base = declarative_base()

    class Drone(Base):
        __tablename__ = "drones"
        id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
        user_id = Column(UUID(as_uuid=True), nullable=False)
        name = Column(Text, nullable=False)
        last_seen = Column(DateTime(timezone=True))
        last_lat = Column(Float)
        last_lon = Column(Float)
        last_heading_deg = Column(Float)
        fire_detected = Column(Boolean, default=False)
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    class ApiKey(Base):
        __tablename__ = "api_keys"
        id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
        drone_id = Column(UUID(as_uuid=True), ForeignKey("drones.id", ondelete="CASCADE"), nullable=False)
        key_hash = Column(Text, nullable=False)
        revoked_at = Column(DateTime(timezone=True))
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    class Telemetry(Base):
        __tablename__ = "telemetry"
        id = Column(BigInteger, primary_key=True, autoincrement=True)
        drone_id = Column(UUID(as_uuid=True), ForeignKey("drones.id", ondelete="CASCADE"), nullable=False)
        lat = Column(Float)
        lon = Column(Float)
        alt_m = Column(Float)
        heading_deg = Column(Float)
        fire_detected = Column(Boolean)
        sats = Column(Integer)
        hdop = Column(Float)
        ts = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    class Fire(Base):
        __tablename__ = "fires"
        id = Column(BigInteger, primary_key=True, autoincrement=True)
        user_id = Column(UUID(as_uuid=True), nullable=False)
        lat = Column(Float, nullable=False)
        lon = Column(Float, nullable=False)
        confidence = Column(Float)
        size_m = Column(Float)
        source = Column(Text)
        detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    _db_engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
    _db_session_maker = sessionmaker(bind=_db_engine, expire_on_commit=False)
    _models = {"Drone": Drone, "ApiKey": ApiKey, "Telemetry": Telemetry, "Fire": Fire}
    print(f"[db] connected to {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'database'}")
else:
    print("[db] no DATABASE_URL set, running in memory-only mode (local dev)")


def _hash_key(key: str) -> str:
    """Hash an API key with SHA256 for storage. Reversible only via brute force."""
    return hashlib.sha256(key.encode()).hexdigest()


_jwks_cache = None
_jwks_cache_ts = 0.0


def _get_jwks():
    """Fetch and cache the Supabase JWKS (public keys for ES256 verification)."""
    global _jwks_cache, _jwks_cache_ts
    if not SUPABASE_URL:
        return None
    if _jwks_cache and (time.time() - _jwks_cache_ts) < 3600:
        return _jwks_cache
    try:
        import requests as _rq
        r = _rq.get(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json", timeout=5)
        r.raise_for_status()
        _jwks_cache = r.json()
        _jwks_cache_ts = time.time()
        return _jwks_cache
    except Exception as e:
        print(f"[auth] failed to fetch JWKS: {e}")
        return None


def _verify_jwt(token: str):
    """Decode and verify a Supabase JWT. Handles both HS256 (legacy) and ES256/RS256."""
    if not token:
        return None
    try:
        from jose import jwt
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")

        if alg == "HS256":
            if not JWT_SECRET:
                print("[auth] HS256 token received but SUPABASE_JWT_SECRET not set")
                return None
            return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience="authenticated")

        # ES256 / RS256 — fetch the JWKS from Supabase
        jwks = _get_jwks()
        if not jwks:
            print(f"[auth] {alg} token received but JWKS unavailable")
            return None
        return jwt.decode(token, jwks, algorithms=[alg], audience="authenticated")
    except Exception as e:
        print(f"[auth] JWT decode failed: {e}")
        return None


def require_jwt(f):
    """Decorator: require a valid Supabase JWT in Authorization or session."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not JWT_SECRET:
            # Auth disabled in local mode — pass through
            request.user_id = None
            return f(*args, **kwargs)

        token = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        elif "jwt" in session:
            token = session["jwt"]

        claims = _verify_jwt(token) if token else None
        if not claims:
            if request.path.startswith("/api/"):
                return jsonify({"error": "auth required"}), 401
            return redirect(url_for("login_page"))

        request.user_id = claims.get("sub")
        return f(*args, **kwargs)
    return wrapper


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

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


# ─────────────────────────────────────────────────────────────────────────────
#  Public routes (no auth)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    if JWT_SECRET and "jwt" not in session:
        return redirect(url_for("login_page"))
    return render_template("index.html")


@app.get("/login")
def login_page():
    return render_template("login.html",
                           supabase_url=SUPABASE_URL,
                           supabase_key=SUPABASE_PUBLISHABLE_KEY)


@app.post("/login")
def login_submit():
    """Browser POSTs the JWT it got from Supabase JS. We stash it in session."""
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("token")
    if not token:
        return jsonify({"error": "missing token"}), 400
    claims = _verify_jwt(token)
    if not claims:
        return jsonify({"error": "invalid token"}), 401
    session["jwt"] = token
    session["user_id"] = claims.get("sub")
    return jsonify({"ok": True})


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ─────────────────────────────────────────────────────────────────────────────
#  Drone HTTPS uplink (API key auth — used by ESP32 firmware)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/drone")
def post_drone():
    """Telemetry endpoint for drones. Requires X-API-Key header."""
    if not _db_session_maker:
        return jsonify({"error": "database not configured"}), 503

    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return jsonify({"error": "X-API-Key required"}), 401

    msg = request.get_json(force=True, silent=True) or {}
    lat = msg.get("lat")
    lon = msg.get("lon")
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon required"}), 400

    Drone = _models["Drone"]
    ApiKey = _models["ApiKey"]
    Telemetry = _models["Telemetry"]

    key_hash = _hash_key(api_key)
    with _db_session_maker() as db:
        key_row = db.query(ApiKey).filter_by(key_hash=key_hash, revoked_at=None).first()
        if not key_row:
            return jsonify({"error": "invalid or revoked API key"}), 403

        drone = db.query(Drone).filter_by(id=key_row.drone_id).first()
        if not drone:
            return jsonify({"error": "drone not found"}), 404

        # Update drone snapshot
        drone.last_lat = float(lat)
        drone.last_lon = float(lon)
        drone.last_heading_deg = msg.get("heading_deg")
        drone.fire_detected = bool(msg.get("fire_detected", False))
        drone.last_seen = datetime.now(timezone.utc)

        # Insert telemetry row
        db.add(Telemetry(
            drone_id=drone.id,
            lat=float(lat), lon=float(lon),
            alt_m=msg.get("alt_m"),
            heading_deg=msg.get("heading_deg"),
            fire_detected=bool(msg.get("fire_detected", False)),
            sats=msg.get("sats"),
            hdop=msg.get("hdop"),
        ))
        db.commit()

        # Mirror into in-memory state so the live map sees it
        drone_id_str = str(drone.id)
        with _lock:
            _drones[drone_id_str] = {
                "lat": float(lat),
                "lon": float(lon),
                "alt_m": msg.get("alt_m"),
                "heading_deg": msg.get("heading_deg"),
                "fire_detected": bool(msg.get("fire_detected", False)),
                "sats": msg.get("sats"),
                "hdop": msg.get("hdop"),
                "ts": time.time(),
                "name": drone.name,
            }
            _maybe_triangulate()

    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
#  User dashboard (JWT auth — manage drones + API keys)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/dashboard")
@require_jwt
def dashboard_page():
    return render_template("dashboard.html",
                           supabase_url=SUPABASE_URL,
                           supabase_key=SUPABASE_PUBLISHABLE_KEY)


@app.get("/api/dashboard/drones")
@require_jwt
def list_drones():
    if not _db_session_maker:
        return jsonify({"drones": []})
    Drone = _models["Drone"]
    with _db_session_maker() as db:
        drones = db.query(Drone).filter_by(user_id=request.user_id).all()
        return jsonify({"drones": [{
            "id": str(d.id),
            "name": d.name,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "last_lat": d.last_lat,
            "last_lon": d.last_lon,
            "fire_detected": d.fire_detected,
        } for d in drones]})


@app.post("/api/dashboard/drones")
@require_jwt
def create_drone():
    """Register a new drone, return a fresh API key (shown ONCE)."""
    if not _db_session_maker:
        return jsonify({"error": "database not configured"}), 503

    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400

    Drone = _models["Drone"]
    ApiKey = _models["ApiKey"]

    raw_key = secrets.token_urlsafe(48)  # ~64 char URL-safe key

    with _db_session_maker() as db:
        drone = Drone(user_id=request.user_id, name=name)
        db.add(drone)
        db.flush()  # populate drone.id

        db.add(ApiKey(drone_id=drone.id, key_hash=_hash_key(raw_key)))
        db.commit()

        return jsonify({
            "id": str(drone.id),
            "name": drone.name,
            "api_key": raw_key,  # the only time the raw key is ever returned
        })


@app.delete("/api/dashboard/drones/<drone_id>")
@require_jwt
def delete_drone(drone_id):
    if not _db_session_maker:
        return jsonify({"error": "database not configured"}), 503
    Drone = _models["Drone"]
    with _db_session_maker() as db:
        drone = db.query(Drone).filter_by(id=drone_id, user_id=request.user_id).first()
        if not drone:
            return jsonify({"error": "not found"}), 404
        db.delete(drone)
        db.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
#  Existing routes — unchanged behavior (work with or without DB)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/state")
def get_state():
    with _lock:
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


@app.post("/api/triangulate")
def manual_triangulate():
    with _lock:
        before = len(_fires)
        _maybe_triangulate()
        new_fire = _fires[-1] if len(_fires) > before else None
    return jsonify({"fire": new_fire})


@app.post("/api/reset")
def reset():
    global _fire_id, _camera_url
    with _lock:
        _fires.clear()
        _fire_id = 0
        _drones.clear()
        _camera_url = None
        global _last_triangulation
        _last_triangulation = 0.0
        return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
