"""
test_geo_utils.py
Tests for the coordinate math used throughout the codebase:
  - latlon_to_local (flat-earth projection used in triangulator.py + reposition.py)
  - bearing_to computation used in simulate_fleet.py + reposition.py
  - GPS heading derivation used in firmware (compute_heading in read_pos_data.c
    ported here as Python for verification)
  - NMEA coordinate parsing logic (nmea_to_deg from read_pos_data.c)
  - distance_m consistency (used in reposition.py and server.py)
"""

import sys, math

LAT0, LON0 = 36.995578, -122.058878
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))

# ── re-implementations of firmware / server math ──────────────────────────────

def latlon_to_local(lat, lon):
    """Flat-earth projection to (x_m, y_m) from LAT0/LON0."""
    return (lon - LON0) * M_PER_DEG_LON, (lat - LAT0) * M_PER_DEG_LAT

def local_to_latlon(x_m, y_m):
    return LAT0 + y_m / M_PER_DEG_LAT, LON0 + x_m / M_PER_DEG_LON

def distance_m(lat1, lon1, lat2, lon2):
    x1, y1 = latlon_to_local(lat1, lon1)
    x2, y2 = latlon_to_local(lat2, lon2)
    return math.hypot(x2 - x1, y2 - y1)

def bearing_to(from_lat, from_lon, to_lat, to_lon):
    """True bearing (0–360° from N) — matches simulate_fleet.py."""
    dx = (to_lon - from_lon) * M_PER_DEG_LON
    dy = (to_lat - from_lat) * M_PER_DEG_LAT
    return math.degrees(math.atan2(dx, dy)) % 360

def compute_heading(prev_lat, prev_lon, curr_lat, curr_lon, min_move_m=1.0):
    """Port of compute_heading() from read_pos_data.c firmware."""
    lat_rad = prev_lat * math.pi / 180.0
    dy_m = (curr_lat - prev_lat) * 111320.0
    dx_m = (curr_lon - prev_lon) * 111320.0 * math.cos(lat_rad)
    moved_m = math.sqrt(dx_m**2 + dy_m**2)
    if moved_m < min_move_m:
        return None  # below jitter threshold — firmware returns last heading
    heading = math.degrees(math.atan2(dx_m, dy_m))
    return heading % 360.0

def nmea_to_deg(nmea_str, hemi):
    """Port of nmea_to_deg() from read_pos_data.c firmware."""
    dot = nmea_str.find('.')
    if dot < 3:
        return 0.0
    whole = int(nmea_str[:dot - 2] + nmea_str[dot - 2:dot])  # DDDMM
    # Actually: degrees = int(DDDMM / 100), minutes = DDDMM % 100 + decimals
    degrees = int(nmea_str[:dot - 2])
    minutes = float(nmea_str[dot - 2:])
    result = degrees + minutes / 60.0
    if hemi in ('S', 'W'):
        result = -result
    return result

PASS = 0
FAIL = 0

def ok(label):
    global PASS; print(f"  ok : {label}"); PASS += 1

def fail(label, detail=""):
    global FAIL; print(f"  FAIL: {label}" + (f" — {detail}" if detail else "")); FAIL += 1

def approx(a, b, tol):
    return abs(a - b) <= tol

print("\n=== Geo Utility Tests ===\n")

# ── latlon_to_local / local_to_latlon round-trip ─────────────────────────────
for lat_off, lon_off in [(0, 0), (0.01, -0.01), (-0.005, 0.003), (0, 0.002)]:
    lat = LAT0 + lat_off
    lon = LON0 + lon_off
    x, y = latlon_to_local(lat, lon)
    lat2, lon2 = local_to_latlon(x, y)
    if approx(lat, lat2, 1e-8) and approx(lon, lon2, 1e-8):
        ok(f"round-trip ({lat_off:+.3f}, {lon_off:+.3f})")
    else:
        fail(f"round-trip failed ({lat_off:+.3f}, {lon_off:+.3f})", f"got ({lat2:.8f},{lon2:.8f})")

# ── distance_m cardinal directions ───────────────────────────────────────────
# 1 degree of latitude ≈ 111 320 m
dist_1deg_lat = distance_m(LAT0, LON0, LAT0 + 1.0, LON0)
if approx(dist_1deg_lat, 111320.0, 5.0):
    ok(f"1 deg lat = {dist_1deg_lat:.0f}m (expected ~111320m)")
else:
    fail("1 deg lat distance wrong", f"got {dist_1deg_lat:.0f}m")

dist_100m = distance_m(LAT0, LON0, LAT0 + 100.0/M_PER_DEG_LAT, LON0)
if approx(dist_100m, 100.0, 0.1):
    ok(f"100m north: computed {dist_100m:.2f}m")
else:
    fail("100m north distance wrong", f"got {dist_100m:.2f}m")

# distance is symmetric
d_fwd = distance_m(LAT0, LON0, LAT0 + 0.001, LON0 + 0.001)
d_rev = distance_m(LAT0 + 0.001, LON0 + 0.001, LAT0, LON0)
if approx(d_fwd, d_rev, 0.001):
    ok("distance is symmetric")
else:
    fail("distance not symmetric", f"{d_fwd} vs {d_rev}")

# ── bearing_to cardinal points ────────────────────────────────────────────────
for (dlat, dlon, expected_hdg, label) in [
    ( 0.001,  0.0,    0.0,   "due North → 0°"),
    ( 0.0,    0.001,  90.0,  "due East → 90°"),
    (-0.001,  0.0,    180.0, "due South → 180°"),
    ( 0.0,   -0.001,  270.0, "due West → 270°"),
    ( 0.001,  0.001,  None,  "NE → ~45° (approx)"),
]:
    hdg = bearing_to(LAT0, LON0, LAT0 + dlat, LON0 + dlon)
    if expected_hdg is None:
        if 35.0 < hdg < 50.0:
            ok(f"NE bearing {hdg:.1f}° in expected range [35, 50] (compressed lon at LAT0)")
        else:
            fail(f"NE bearing out of expected range [35,50]", f"got {hdg:.1f}°")
    else:
        if approx(hdg, expected_hdg, 0.5):
            ok(f"bearing {label}: {hdg:.1f}°")
        else:
            fail(f"bearing {label}", f"expected {expected_hdg}°, got {hdg:.1f}°")

# ── compute_heading (firmware port) ──────────────────────────────────────────
# Moving due East
hdg = compute_heading(LAT0, LON0, LAT0, LON0 + 0.001)
if hdg is not None and approx(hdg, 90.0, 1.0):
    ok(f"firmware compute_heading East: {hdg:.1f}°")
else:
    fail("firmware compute_heading East", f"got {hdg}")

# Moving due North
hdg = compute_heading(LAT0, LON0, LAT0 + 0.001, LON0)
if hdg is not None and approx(hdg, 0.0, 1.0):
    ok(f"firmware compute_heading North: {hdg:.1f}°")
else:
    fail("firmware compute_heading North", f"got {hdg}")

# Sub-threshold movement → returns None
hdg = compute_heading(LAT0, LON0, LAT0 + 0.000005, LON0, min_move_m=1.0)
if hdg is None:
    ok("compute_heading below jitter threshold → None")
else:
    fail("should return None for sub-threshold movement", f"got {hdg}")

# ── NMEA coordinate parsing (firmware port) ───────────────────────────────────
# Santa Cruz: 36°59.7347'N, 122°03.5327'W → 36.9955783, -122.0588783
nmea_lat = "3659.7347"
nmea_lon = "12203.5327"
lat = nmea_to_deg(nmea_lat, 'N')
lon = nmea_to_deg(nmea_lon, 'W')
if approx(lat, 36.9955783, 0.001):
    ok(f"NMEA lat parse: {lat:.6f}°")
else:
    fail("NMEA lat parse", f"got {lat:.6f}°, expected ~36.9956°")

if approx(lon, -122.0588783, 0.001):
    ok(f"NMEA lon parse (W): {lon:.6f}°")
else:
    fail("NMEA lon parse", f"got {lon:.6f}°, expected ~-122.0589°")

# Southern hemisphere
lat_s = nmea_to_deg("0330.0000", 'S')
if approx(lat_s, -3.5, 0.001):
    ok(f"NMEA S hemisphere: {lat_s:.4f}°")
else:
    fail("NMEA S hemisphere", f"got {lat_s}")

print(f"\n{'='*40}")
print(f"  Passed: {PASS}  |  Failed: {FAIL}")
if FAIL == 0:
    print("  all geo utility tests passed")
else:
    print("  SOME TESTS FAILED")
    sys.exit(1)
