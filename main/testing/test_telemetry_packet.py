"""
test_telemetry_packet.py
Tests for the telemetry JSON packet format produced by the ESP32-C3 firmware
(read_pos_data.c) and consumed by the Flask server (server.py).

Since we cannot run firmware here, we test:
  1. The packet structure matches what the server expects at /api/drone and /api/state
  2. Coordinate validation logic (ported from server.py _validate_coords)
  3. Priority queue / data-type classification rules described in the design doc
  4. Packet JSON serialization round-trips without loss
  5. Edge cases: NaN, Inf, out-of-range lat/lon, missing fields
"""

import sys, json, math

PASS = 0
FAIL = 0

def ok(label):
    global PASS; print(f"  ok : {label}"); PASS += 1

def fail(label, detail=""):
    global FAIL; print(f"  FAIL: {label}" + (f" — {detail}" if detail else "")); FAIL += 1

# ── _validate_coords (ported from server.py) ──────────────────────────────────

def validate_coords(lat, lon):
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None, None, "lat and lon must be numeric"
    if not (math.isfinite(lat_f) and math.isfinite(lon_f)):
        return None, None, "lat and lon must be finite"
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None, None, "lat must be in [-90,90], lon in [-180,180]"
    return lat_f, lon_f, None

print("\n=== Telemetry Packet Tests ===\n")

# ── 1. Valid Santa Cruz coordinate ────────────────────────────────────────────
lat_f, lon_f, err = validate_coords(36.995578, -122.058878)
if err is None and abs(lat_f - 36.995578) < 1e-6:
    ok("valid Santa Cruz coordinate accepted")
else:
    fail("valid coordinate rejected", str(err))

# ── 2. NaN rejected ───────────────────────────────────────────────────────────
_, _, err = validate_coords(float('nan'), -122.0)
if err and "finite" in err:
    ok("NaN lat rejected")
else:
    fail("NaN lat should be rejected", str(err))

_, _, err = validate_coords(36.9, float('nan'))
if err and "finite" in err:
    ok("NaN lon rejected")
else:
    fail("NaN lon should be rejected", str(err))

# ── 3. Infinity rejected ──────────────────────────────────────────────────────
_, _, err = validate_coords(float('inf'), -122.0)
if err and "finite" in err:
    ok("Inf lat rejected")
else:
    fail("Inf lat should be rejected", str(err))

# ── 4. Out-of-range lat/lon rejected ─────────────────────────────────────────
for lat, lon, label in [
    (91.0,  -122.0, "lat > 90"),
    (-91.0, -122.0, "lat < -90"),
    (36.9,   181.0, "lon > 180"),
    (36.9,  -181.0, "lon < -180"),
    (90.001, 0.0,   "lat just above +90"),
]:
    _, _, err = validate_coords(lat, lon)
    if err and ("lat" in err or "lon" in err):
        ok(f"out-of-range coord rejected: {label}")
    else:
        fail(f"out-of-range coord should be rejected: {label}", str(err))

# ── 5. String-numeric accepted ────────────────────────────────────────────────
lat_f, lon_f, err = validate_coords("36.9956", "-122.0589")
if err is None:
    ok("string-encoded numerics accepted (JSON parse robustness)")
else:
    fail("string numerics should be accepted", str(err))

# ── 6. None lat/lon rejected ──────────────────────────────────────────────────
_, _, err = validate_coords(None, -122.0)
if err:
    ok("None lat rejected")
else:
    fail("None lat should be rejected")

# ── 7. Telemetry packet has required fields ───────────────────────────────────
REQUIRED_FIELDS = {"id", "lat", "lon", "heading_deg", "fire_detected", "ts_ms"}
OPTIONAL_FIELDS = {"seq", "alt_m", "sats", "hdop"}

sample_packet = {
    "id": "drone_1",
    "seq": 42,
    "lat": 36.995578,
    "lon": -122.058878,
    "alt_m": 50.0,
    "heading_deg": 142.5,
    "fire_detected": False,
    "sats": 9,
    "hdop": 1.2,
    "ts_ms": 1718000000123,
}

missing = REQUIRED_FIELDS - set(sample_packet.keys())
if not missing:
    ok("sample telemetry packet contains all required fields")
else:
    fail("sample packet missing required fields", str(missing))

# ── 8. JSON round-trip preserves float precision ──────────────────────────────
serialized = json.dumps(sample_packet)
parsed = json.loads(serialized)
if abs(parsed["lat"] - sample_packet["lat"]) < 1e-7 and abs(parsed["lon"] - sample_packet["lon"]) < 1e-7:
    ok("JSON round-trip preserves lat/lon to 7 decimal places")
else:
    fail("JSON round-trip lost precision", f"lat={parsed['lat']}")

# ── 9. fire_detected is boolean-compatible ─────────────────────────────────────
for val, expected_bool, label in [
    (True,  True,  "True"),
    (False, False, "False"),
    (1,     True,  "integer 1"),
    (0,     False, "integer 0"),
]:
    result = bool(val)
    if result == expected_bool:
        ok(f"fire_detected={label} → bool({result})")
    else:
        fail(f"fire_detected={label} bool conversion", f"got {result}")

# ── 10. Priority queue classification (from design doc) ──────────────────────
# Critical: detection alerts, battery failsafe (low bandwidth, high redundancy)
# High: video stream (high bandwidth)
# Normal: GPS updates, health metrics

PRIORITY_CRITICAL = 0
PRIORITY_HIGH     = 1
PRIORITY_NORMAL   = 2

def classify_packet(packet_type):
    if packet_type in ("fire_alert", "battery_failsafe", "manual_override"):
        return PRIORITY_CRITICAL
    if packet_type in ("video_frame", "mjpeg_stream"):
        return PRIORITY_HIGH
    return PRIORITY_NORMAL

for ptype, expected, label in [
    ("fire_alert",      PRIORITY_CRITICAL, "fire alert is CRITICAL"),
    ("battery_failsafe",PRIORITY_CRITICAL, "battery failsafe is CRITICAL"),
    ("manual_override", PRIORITY_CRITICAL, "manual override is CRITICAL"),
    ("video_frame",     PRIORITY_HIGH,     "video frame is HIGH"),
    ("mjpeg_stream",    PRIORITY_HIGH,     "MJPEG stream is HIGH"),
    ("gps_telemetry",   PRIORITY_NORMAL,   "GPS telemetry is NORMAL"),
    ("health_metric",   PRIORITY_NORMAL,   "health metric is NORMAL"),
]:
    if classify_packet(ptype) == expected:
        ok(f"priority: {label}")
    else:
        fail(f"priority wrong for {ptype}", f"got {classify_packet(ptype)}, expected {expected}")

# ── 11. Boundary coordinates (poles, dateline) ────────────────────────────────
for lat, lon, should_pass, label in [
    ( 90.0,    0.0,  True,  "+90 lat (North Pole)"),
    (-90.0,    0.0,  True,  "-90 lat (South Pole)"),
    (  0.0,  180.0,  True,  "+180 lon (dateline)"),
    (  0.0, -180.0,  True,  "-180 lon (dateline)"),
    (  0.0,    0.0,  True,  "null island (0,0)"),
]:
    _, _, err = validate_coords(lat, lon)
    passed = (err is None)
    if passed == should_pass:
        ok(f"boundary coord {label}: {'accepted' if passed else 'rejected'} as expected")
    else:
        fail(f"boundary coord {label}", f"err={err}")

print(f"\n{'='*40}")
print(f"  Passed: {PASS}  |  Failed: {FAIL}")
if FAIL == 0:
    print("  all telemetry packet tests passed")
else:
    print("  SOME TESTS FAILED")
    sys.exit(1)
