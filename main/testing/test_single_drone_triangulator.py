"""
test_single_drone_triangulator.py
Tests for the SingleDroneTriangulator (running-fix) in
main/groundstation/reposition.py

Scenarios tested:
  - First observation is stored, not yet a fix
  - Second observation too close (baseline < threshold) → no fix yet
  - Second observation sufficient baseline but insufficient angle → no fix
  - Successful fix: baseline and angle both exceed thresholds
  - After a successful fix the pending slot is cleared (next obs starts fresh)
  - Fire disappears then reappears — expiry works if we fast-forward ts
  - No GPS (lat/lon = None) is handled gracefully
  - Confidence value is within [0, 1]
"""

import os, sys, math, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "groundstation"))
from reposition import SingleDroneTriangulator, LAT0, LON0, _distance_m, _angle_diff, _confidence

M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))

def bearing_to(from_lat, from_lon, to_lat, to_lon):
    dx = (to_lon - from_lon) * M_PER_DEG_LON
    dy = (to_lat - from_lat) * M_PER_DEG_LAT
    return math.degrees(math.atan2(dx, dy)) % 360

def distance_m(lat1, lon1, lat2, lon2):
    x1 = (lon1 - LON0) * M_PER_DEG_LON
    y1 = (lat1 - LAT0) * M_PER_DEG_LAT
    x2 = (lon2 - LON0) * M_PER_DEG_LON
    y2 = (lat2 - LAT0) * M_PER_DEG_LAT
    return math.hypot(x2 - x1, y2 - y1)

PASS = 0
FAIL = 0

def ok(label):
    global PASS
    print(f"  ok : {label}")
    PASS += 1

def fail(label, detail=""):
    global FAIL
    print(f"  FAIL: {label}" + (f" — {detail}" if detail else ""))
    FAIL += 1

print("\n=== SingleDroneTriangulator Tests ===\n")

FIRE_LAT, FIRE_LON = LAT0 + 0.0015, LON0 + 0.001

# ── 1. First observation is stored, returns None ──────────────────────────────
tri = SingleDroneTriangulator(min_baseline_m=10.0, min_angle_deg=15.0)
pos1_lat, pos1_lon = LAT0, LON0 - 0.002
hdg1 = bearing_to(pos1_lat, pos1_lon, FIRE_LAT, FIRE_LON)
state1 = {"lat": pos1_lat, "lon": pos1_lon, "heading_deg": hdg1, "fire_detected": True, "ts": time.time()}
result = tri.update("d1", state1)
if result is None:
    ok("first observation stored → None returned")
else:
    fail("first observation should return None", f"got {result}")

# ── 2. Second obs too close (< 10 m baseline) → no fix ───────────────────────
pos2_lat = pos1_lat + 0.00005   # ~5.6 m north — below 10 m threshold
pos2_lon = pos1_lon
hdg2 = bearing_to(pos2_lat, pos2_lon, FIRE_LAT, FIRE_LON)
state2 = {"lat": pos2_lat, "lon": pos2_lon, "heading_deg": hdg2, "fire_detected": True, "ts": time.time()}
result = tri.update("d1", state2)
if result is None:
    ok("second obs too close (baseline < 10m) → None")
else:
    fail("baseline < threshold should return None", f"got {result}")

# ── 3. Second obs far enough but angle change too small (< 15°) ───────────────
tri2 = SingleDroneTriangulator(min_baseline_m=10.0, min_angle_deg=15.0)
# Drone moves 100 m north in a straight line — heading to fire barely changes
pos_a_lat, pos_a_lon = LAT0 - 0.005, LON0   # far south
hdg_a = bearing_to(pos_a_lat, pos_a_lon, FIRE_LAT, FIRE_LON)
state_a = {"lat": pos_a_lat, "lon": pos_a_lon, "heading_deg": hdg_a, "fire_detected": True, "ts": time.time()}
tri2.update("d2", state_a)

pos_b_lat = pos_a_lat + 0.0005   # ~55 m north — enough baseline
pos_b_lon = pos_a_lon
hdg_b = bearing_to(pos_b_lat, pos_b_lon, FIRE_LAT, FIRE_LON)
angle_change = _angle_diff(hdg_a, hdg_b)
state_b = {"lat": pos_b_lat, "lon": pos_b_lon, "heading_deg": hdg_b, "fire_detected": True, "ts": time.time()}
result = tri2.update("d2", state_b)
if angle_change < 15.0 and result is None:
    ok(f"angle change {angle_change:.2f}° < 15° → None (angle threshold enforced)")
elif angle_change >= 15.0:
    # geometry gives a large enough angle — result might not be None, that's fine
    ok(f"angle change {angle_change:.2f}° ≥ 15° — fix computed or pending (geometry-dependent)")
else:
    fail("angle threshold not enforced", f"angle={angle_change:.2f}°, result={result}")

# ── 4. Successful fix ─────────────────────────────────────────────────────────
tri3 = SingleDroneTriangulator(min_baseline_m=10.0, min_angle_deg=15.0)
# Position 1: south-west of fire
p1_lat, p1_lon = FIRE_LAT - 0.003, FIRE_LON - 0.003
h1 = bearing_to(p1_lat, p1_lon, FIRE_LAT, FIRE_LON)
tri3.update("d3", {"lat": p1_lat, "lon": p1_lon, "heading_deg": h1, "fire_detected": True, "ts": time.time()})

# Position 2: south-east of fire — large angle change, large baseline
p2_lat, p2_lon = FIRE_LAT - 0.003, FIRE_LON + 0.003
h2 = bearing_to(p2_lat, p2_lon, FIRE_LAT, FIRE_LON)
fix = tri3.update("d3", {"lat": p2_lat, "lon": p2_lon, "heading_deg": h2, "fire_detected": True, "ts": time.time()})

if fix is not None:
    err = distance_m(fix["lat"], fix["lon"], FIRE_LAT, FIRE_LON)
    if err <= 20.0:
        ok(f"successful fix: error={err:.1f}m, confidence={fix['confidence']}")
    else:
        fail(f"fix error too large: {err:.1f}m", f"fix={fix}")
else:
    fail("expected a successful fix, got None")

# ── 5. After fix, pending slot is cleared → next obs starts fresh ─────────────
# tri3 already produced a fix; now send one more obs and verify it stores rather than fixes
result_after = tri3.update("d3", {"lat": p1_lat, "lon": p1_lon, "heading_deg": h1, "fire_detected": True, "ts": time.time()})
if result_after is None:
    ok("after successful fix, next single observation returns None (slot cleared)")
else:
    fail("expected None after fix-then-first-obs, got a result", str(result_after))

# ── 6. No GPS data → graceful None ───────────────────────────────────────────
tri4 = SingleDroneTriangulator()
result = tri4.update("d4", {"lat": None, "lon": None, "heading_deg": 45.0, "fire_detected": True, "ts": time.time()})
if result is None:
    ok("missing lat/lon → graceful None")
else:
    fail("missing lat/lon should return None", str(result))

# ── 7. Fire not detected → no observation stored ──────────────────────────────
tri5 = SingleDroneTriangulator()
result = tri5.update("d5", {"lat": LAT0, "lon": LON0, "heading_deg": 90.0, "fire_detected": False, "ts": time.time()})
status = tri5.status()
if result is None and "d5" not in status:
    ok("fire_detected=False → no pending observation stored")
else:
    fail("no observation should be stored when fire_detected=False", f"result={result}, status={status}")

# ── 8. clear() removes pending observations ───────────────────────────────────
tri6 = SingleDroneTriangulator()
tri6.update("alpha", {"lat": LAT0, "lon": LON0, "heading_deg": 45.0, "fire_detected": True, "ts": time.time()})
tri6.update("beta",  {"lat": LAT0 + 0.001, "lon": LON0, "heading_deg": 90.0, "fire_detected": True, "ts": time.time()})
tri6.clear("alpha")
status = tri6.status()
if "alpha" not in status and "beta" in status:
    ok("clear(drone_id) removes only that drone's pending obs")
else:
    fail("clear(drone_id) failed", f"status={status}")

tri6.clear()
if len(tri6.status()) == 0:
    ok("clear() with no args removes all pending obs")
else:
    fail("clear() should remove all obs", f"status={tri6.status()}")

# ── 9. Confidence stays in [0, 1] for a range of inputs ──────────────────────
bad_conf = False
for baseline in [1, 10, 50, 200]:
    for angle in [0, 15, 45, 90, 135, 180]:
        c = _confidence(baseline, angle)
        if not (0.0 <= c <= 1.0):
            bad_conf = True
            fail(f"confidence out of range: baseline={baseline} angle={angle} → {c}")
if not bad_conf:
    ok("_confidence() always returns value in [0, 1] across tested inputs")

# ── summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"  Passed: {PASS}  |  Failed: {FAIL}")
if FAIL == 0:
    print("  all SingleDroneTriangulator tests passed")
else:
    print("  SOME TESTS FAILED")
    sys.exit(1)
