import hashlib
import json
import os
import secrets
import socket
import threading
import time
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from triangulator import triangulate

DATABASE_URL = os.environ.get("DATABASE_URL")
JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
CAMERA_API_TOKEN = os.environ.get("FIREFLY_CAMERA_TOKEN", "").strip()
MAX_CAMERA_URL_LEN = 2048

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
    return hashlib.sha256(key.encode()).hexdigest()


_jwks_cache = None
_jwks_cache_ts = 0.0


def _get_jwks():
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

        jwks = _get_jwks()
        if not jwks:
            print(f"[auth] {alg} token received but JWKS unavailable")
            return None
        return jwt.decode(token, jwks, algorithms=[alg], audience="authenticated")
    except Exception as e:
        print(f"[auth] JWT decode failed: {e}")
        return None


def _extract_jwt_token() -> str | None:
    """Pull JWT from Authorization header or session."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return session.get("jwt")


def require_jwt(f):
    """
    Decorator: require a valid Supabase JWT.
    Sets request.user_id to the authenticated user's UUID string.
    In local dev (no JWT_SECRET), passes through with user_id=None.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not JWT_SECRET:
            request.user_id = None
            return f(*args, **kwargs)

        token = _extract_jwt_token()
        claims = _verify_jwt(token) if token else None
        if not claims:
            if request.path.startswith("/api/"):
                return jsonify({"error": "auth required"}), 401
            return redirect(url_for("login_page"))

        request.user_id = claims.get("sub")
        return f(*args, **kwargs)
    return wrapper


def _resolve_api_key() -> tuple[str | None, dict | None]:
    """
    Validate the X-API-Key header against the database.
    Returns (drone_id_str, drone_row_dict) on success, or (None, None) on failure.
    Also verifies the key is not revoked.
    """
    if not _db_session_maker:
        return None, None

    api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key:
        return None, None

    Drone = _models["Drone"]
    ApiKey = _models["ApiKey"]

    key_hash = _hash_key(api_key)
    with _db_session_maker() as db:
        key_row = (
            db.query(ApiKey)
            .filter_by(key_hash=key_hash, revoked_at=None)
            .first()
        )
        if not key_row:
            return None, None

        drone = db.query(Drone).filter_by(id=key_row.drone_id).first()
        if not drone:
            return None, None

        return str(drone.id), {
            "id": str(drone.id),
            "user_id": str(drone.user_id),
            "name": drone.name,
        }


def _camera_token_from_request() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return request.headers.get("X-Camera-Token", "").strip()


def require_camera_token(f):
    """Require the shared camera-control token."""
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


def _validate_coords(lat, lon):
    """Return (lat_float, lon_float, error_msg). Reject NaN/infinite/out-of-range."""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None, None, "lat and lon must be numeric"
    import math
    if not (math.isfinite(lat_f) and math.isfinite(lon_f)):
        return None, None, "lat and lon must be finite"
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None, None, "lat must be in [-90,90], lon in [-180,180]"
    return lat_f, lon_f, None


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


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# Security hardening
IS_PRODUCTION = os.environ.get("RENDER", "") != "" or os.environ.get("FLASK_ENV") == "production"
app.config.update(
    # Cookie flags — Render terminates HTTPS at the edge, so Secure works there.
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Reject any POST body larger than 64 KB — telemetry packets are <1 KB,
    # camera URLs <500 B; nobody legitimate sends megabytes.
    MAX_CONTENT_LENGTH=64 * 1024,
)
# Honor Render's X-Forwarded-Proto so `request.is_secure` is correct
# (without this, Secure cookies wouldn't be sent because Flask would think
# the connection is plain HTTP).
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1)
except ImportError:
    pass

# Production sanity warning — if JWT_SECRET is missing, every JWT-gated
# endpoint becomes a no-op pass-through. Loudly refuse to start.
if IS_PRODUCTION and not JWT_SECRET:
    raise RuntimeError(
        "Refusing to start in production without SUPABASE_JWT_SECRET set. "
        "Auth would be bypassed."
    )


@app.after_request
def _security_headers(resp):
    # No caching of authenticated API responses
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    # Defense-in-depth headers for every response
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp

GPS_UDP_PORT = 4210
TRIANGULATE_COOLDOWN_S = 5.0
TRIANGULATE_FRESHNESS_S = 10.0
DRONE_TIMEOUT_S = 600.0  # 10 minutes — keep drones visible as "offline" before dropping

_lock = threading.Lock()

# In-memory drone state is now keyed by drone_id (UUID string).
# Each entry also carries the owning user_id so /api/state can filter by user.
# Shape: { drone_id: { "user_id": ..., "lat": ..., ... } }
_drones: dict[str, dict] = {}

# In-memory fires are also keyed by user_id so each user only sees their own.
# Shape: { user_id: [ fire_dict, ... ] }
_fires_by_user: dict[str, list[dict]] = {}
_fire_id = 0

_camera_url: str | None = None
_last_triangulation: dict[str, float] = {}  # per user_id
_warned_ids: set[str] = set()


def _get_user_fires(user_id: str | None) -> list[dict]:
    """Return the fire list for this user (empty list if no fires yet)."""
    if not user_id:
        # local dev with no auth — return all fires flattened
        return [f for fires in _fires_by_user.values() for f in fires]
    return _fires_by_user.get(user_id, [])


def _maybe_triangulate(user_id: str | None) -> None:
    """
    Run triangulation for drones belonging to user_id.
    Caller must hold _lock.
    """
    global _fire_id
    now = time.time()

    last = _last_triangulation.get(user_id or "__local__", 0.0)
    if now - last < TRIANGULATE_COOLDOWN_S:
        return

    # Look for drones that have a valid "fire_memory" snapshot
    seers = []
    for d_id, d in _drones.items():
        if user_id is None or d.get("user_id") == user_id:
            mem = d.get("fire_memory")
            if mem and mem.get("heading_deg") is not None and (now - mem["ts"] < TRIANGULATE_FRESHNESS_S):
                seers.append((d_id, mem))

    if len(seers) < 2:
        return

    (id1, mem1), (id2, mem2) = seers[:2]
    
    try:
        coords = triangulate(
            mem1["lat"], mem1["lon"], mem1["heading_deg"],
            mem2["lat"], mem2["lon"], mem2["heading_deg"],
        )
    except Exception as e:
        print(f"[triangulate] Math error: {e}")
        return

    if coords is None:
        return

    lat, lon = coords
    _fire_id += 1
    fire = {
        "id": _fire_id,
        "lat": lat,
        "lon": lon,
        "size_m": 12.0,
        "area_m2": 75.0,
        "confidence": 0.88,
        "ts": now,
        "source": "triangulation",
    }

    uid = user_id or "__local__"
    _fires_by_user.setdefault(uid, []).append(fire)
    _last_triangulation[uid] = now
    print(f"[triangulate] user={uid} {id1} x {id2} -> ({lat:.5f}, {lon:.5f})")


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

        drone_id = msg.get("id", "unknown_drone")

        resolved_user_id = None
        resolved_drone_id = drone_id

        if _db_session_maker and msg.get("api_key"):
            Drone = _models["Drone"]
            ApiKey = _models["ApiKey"]
            key_hash = _hash_key(msg["api_key"])
            try:
                with _db_session_maker() as db:
                    key_row = db.query(ApiKey).filter_by(key_hash=key_hash, revoked_at=None).first()
                    if key_row:
                        drone_row = db.query(Drone).filter_by(id=key_row.drone_id).first()
                        if drone_row:
                            resolved_user_id = str(drone_row.user_id)
                            resolved_drone_id = str(drone_row.id)
            except Exception as e:
                print(f"[gps] db lookup error: {e}")

        if drone_id == "unknown_drone" and addr[0] not in _warned_ids:
            print(f"[warn] UDP packet from {addr[0]} has no 'id' field")
            _warned_ids.add(addr[0])
        elif resolved_drone_id not in _drones and resolved_drone_id not in _warned_ids:
            print(f"[gps] new drone: {resolved_drone_id} from {addr[0]}")
            _warned_ids.add(resolved_drone_id)

        with _lock:
            existing = _drones.get(resolved_drone_id, {})
            current_fire = msg.get("fire_detected", False)
            heading = msg.get("heading_deg")
            
            # --- THE MEMORY BANK ---
            if current_fire and heading is not None:
                memory = {
                    "lat": float(lat),
                    "lon": float(lon),
                    "heading_deg": heading,
                    "ts": time.time()
                }
            else:
                memory = existing.get("fire_memory")
                if memory and (time.time() - memory["ts"] > 10.0):
                    memory = None
            # -----------------------

            _drones[resolved_drone_id] = {
                "user_id": resolved_user_id,
                "lat": float(lat),
                "lon": float(lon),
                "alt_m": msg.get("alt_m"),
                "sats": msg.get("sats"),
                "hdop": msg.get("hdop"),
                "heading_deg": heading,
                "fire_detected": current_fire,
                "fire_memory": memory,
                "ts": time.time(),
            }
            _maybe_triangulate(resolved_user_id)


def _drone_reaper() -> None:
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
#  Public routes (no auth needed)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    if JWT_SECRET and "jwt" not in session:
        return render_template("landing.html")
    return render_template("index.html")

@app.get("/landing")
def landing_page():
    return render_template("landing.html")

@app.get("/login")
def login_page():
    return render_template("login.html",
                           supabase_url=SUPABASE_URL,
                           supabase_key=SUPABASE_PUBLISHABLE_KEY)


@app.post("/login")
def login_submit():
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
    return redirect(url_for("landing_page"))


# ─────────────────────────────────────────────────────────────────────────────
#  ESP32 firmware uplink — authenticated by X-API-Key
#  Only the drone's own key can post telemetry for that drone.
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/drone")
def post_drone():
    """
    Telemetry endpoint for ESP32 firmware.
    Auth: X-API-Key header (issued at drone registration time).
    The key is hashed and looked up in api_keys; the matching drone row
    determines which user owns this drone — no user can spoof another's drone.
    """
    if not _db_session_maker:
        return jsonify({"error": "database not configured"}), 503

    api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key:
        return jsonify({"error": "X-API-Key required"}), 401

    msg = request.get_json(force=True, silent=True) or {}
    lat, lon, err = _validate_coords(msg.get("lat"), msg.get("lon"))
    if err:
        return jsonify({"error": err}), 400

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

        drone.last_lat = lat
        drone.last_lon = lon
        drone.last_heading_deg = msg.get("heading_deg")
        drone.fire_detected = bool(msg.get("fire_detected", False))
        drone.last_seen = datetime.now(timezone.utc)

        db.add(Telemetry(
            drone_id=drone.id,
            lat=lat, lon=lon,
            alt_m=msg.get("alt_m"),
            heading_deg=msg.get("heading_deg"),
            fire_detected=bool(msg.get("fire_detected", False)),
            sats=msg.get("sats"),
            hdop=msg.get("hdop"),
        ))
        db.commit()

        drone_id_str = str(drone.id)
        user_id_str = str(drone.user_id)

        with _lock:
            _drones[drone_id_str] = {
                "user_id": user_id_str,
                "lat": lat,
                "lon": lon,
                "alt_m": msg.get("alt_m"),
                "heading_deg": msg.get("heading_deg"),
                "fire_detected": bool(msg.get("fire_detected", False)),
                "sats": msg.get("sats"),
                "hdop": msg.get("hdop"),
                "ts": time.time(),
                "name": drone.name,
            }
            _maybe_triangulate(user_id_str)

    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
#  Dashboard — JWT required, data scoped to the authenticated user
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
        # Filter strictly by the authenticated user's UUID
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
    if not _db_session_maker:
        return jsonify({"error": "database not configured"}), 503

    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    if len(name) > 64:
        return jsonify({"error": "name must be 64 characters or fewer"}), 400

    Drone = _models["Drone"]
    ApiKey = _models["ApiKey"]

    raw_key = secrets.token_urlsafe(48)

    with _db_session_maker() as db:
        # Drone is created with the authenticated user's ID baked in
        drone = Drone(user_id=request.user_id, name=name)
        db.add(drone)
        db.flush()
        db.add(ApiKey(drone_id=drone.id, key_hash=_hash_key(raw_key)))
        db.commit()

        return jsonify({
            "id": str(drone.id),
            "name": drone.name,
            "api_key": raw_key,
        })


@app.delete("/api/dashboard/drones/<drone_id>")
@require_jwt
def delete_drone(drone_id):
    if not _db_session_maker:
        return jsonify({"error": "database not configured"}), 503
    Drone = _models["Drone"]
    with _db_session_maker() as db:
        # The user_id filter ensures you can only delete your own drones.
        # Without it, any logged-in user could delete any drone by guessing its UUID.
        drone = db.query(Drone).filter_by(id=drone_id, user_id=request.user_id).first()
        if not drone:
            return jsonify({"error": "not found"}), 404
        db.delete(drone)
        db.commit()

    # Also evict from in-memory state
    with _lock:
        _drones.pop(drone_id, None)

    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
#  Live map API — JWT required, all responses scoped to the authenticated user
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/state")
@require_jwt
def get_state():
    """
    Returns only the drones and fires belonging to the authenticated user.
    An unauthenticated caller gets a 401 before reaching this code.
    """
    uid = request.user_id  # None in local dev (no JWT_SECRET)
    with _lock:
        if uid:
            user_drones = {
                k: {key: v for key, v in d.items() if key != "user_id"}
                for k, d in _drones.items()
                if d.get("user_id") == uid
            }
        else:
            # Local dev fallback — strip user_id field but show everything
            user_drones = {
                k: {key: v for key, v in d.items() if key != "user_id"}
                for k, d in _drones.items()
            }

        user_fires = list(_get_user_fires(uid))

    return jsonify({
        "drones": user_drones,
        "fires": user_fires,
        "camera_url": _camera_url,
        "server_ts": time.time(),
    })


@app.post("/api/fire")
@require_jwt
def post_fire():
    """
    Accept a fire detection from the YOLO detector or ingest worker.
    Requires a valid JWT so anonymous callers cannot inject fake fire events.
    The fire is stored under the authenticated user's ID.
    """
    global _fire_id
    data = request.get_json(force=True, silent=True) or {}
    lat, lon, err = _validate_coords(data.get("lat"), data.get("lon"))
    if err:
        return jsonify({"error": err}), 400

    uid = request.user_id or "__local__"

    with _lock:
        _fire_id += 1
        fire = {
            "id": _fire_id,
            "lat": lat,
            "lon": lon,
            "size_m": data.get("size_m"),
            "area_m2": data.get("area_m2"),
            "confidence": data.get("confidence"),
            "ts": time.time(),
            "source": data.get("source", "detection"),
        }
        _fires_by_user.setdefault(uid, []).append(fire)

    return jsonify(fire)


@app.post("/api/camera")
@require_jwt
@require_camera_token
def set_camera():
    """
    Requires both a valid user JWT and the camera-control token.
    Double-decorator pattern: JWT is checked first, then the camera token.
    """
    global _camera_url
    data = request.get_json(force=True, silent=True) or {}
    url, error = _validate_camera_url(data.get("url"))
    if error:
        return jsonify({"error": error}), 400
    with _lock:
        _camera_url = url
    return jsonify({"camera_url": _camera_url})


@app.post("/api/triangulate")
@require_jwt
def manual_triangulate():
    """
    Manually trigger triangulation for the authenticated user's drones only.
    """
    uid = request.user_id
    with _lock:
        fires_before = len(_get_user_fires(uid))
        _maybe_triangulate(uid)
        user_fires = list(_get_user_fires(uid))
        new_fire = user_fires[-1] if len(user_fires) > fires_before else None
    return jsonify({"fire": new_fire})


@app.post("/api/reset")
@require_jwt
def reset():
    """
    Clears only the authenticated user's drones and fires from in-memory state.
    Does not touch other users' data.
    """
    global _fire_id
    uid = request.user_id or "__local__"

    with _lock:
        # Remove only this user's drones from in-memory state
        to_remove = [k for k, v in _drones.items() if v.get("user_id") == uid]
        for k in to_remove:
            del _drones[k]

        # Clear only this user's fires
        _fires_by_user.pop(uid, None)
        _last_triangulation.pop(uid, None)

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
