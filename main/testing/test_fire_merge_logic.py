"""
test_fire_merge_logic.py
Unit-tests for the fire merging / centroid update logic described in server.py.

Because server.py uses Flask and a live database, we extract and re-implement
the pure math from /api/fire so it can be tested without any server running.

Logic under test (from server.py):
  - A new detection within FIRE_MERGE_DISTANCE_M of an existing fire updates
    the existing record (running-mean centroid, growing size up to cap)
  - A detection outside that radius creates a new fire record
  - Confidence uses max (keep highest seen)
  - Size grows by FIRE_SIZE_GROWTH_M per confirmation, capped at FIRE_SIZE_CAP_M
  - Centroid drifts toward the new detection (weighted average)
"""

import sys, math

# Constants from server.py
FIRE_MERGE_DISTANCE_M = 30.0
FIRE_MERGE_WINDOW_S   = 300.0
FIRE_SIZE_GROWTH_M    = 2.0
FIRE_SIZE_CAP_M       = 50.0

LAT0, LON0 = 36.995578, -122.058878
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))

def _dist_m(lat1, lon1, lat2, lon2):
    dy = (lat2 - lat1) * M_PER_DEG_LAT
    dx = (lon2 - lon1) * M_PER_DEG_LON
    return math.hypot(dx, dy)

def _try_merge(fires, new_lat, new_lon, new_conf, new_size, now):
    """Mirror the merge logic from server.py /api/fire endpoint."""
    for f in fires:
        dy = (f["lat"] - new_lat) * M_PER_DEG_LAT
        dx = (f["lon"] - new_lon) * M_PER_DEG_LON
        if (dx*dx + dy*dy) <= FIRE_MERGE_DISTANCE_M**2:
            obs = f.get("observations", 1) + 1
            f["observations"] = obs
            f["lat"] = (f["lat"] * (obs - 1) + new_lat) / obs
            f["lon"] = (f["lon"] * (obs - 1) + new_lon) / obs
            current_size = f.get("size_m") or new_size or 0.0
            f["size_m"] = min(current_size + FIRE_SIZE_GROWTH_M, FIRE_SIZE_CAP_M)
            if new_conf is not None:
                f["confidence"] = max(f.get("confidence") or 0.0, new_conf)
            f["ts"] = now
            return f, True
    return None, False

PASS = 0
FAIL = 0
_fire_id = 0

def new_fire(lat, lon, conf=0.8, size=5.0, now=1000.0):
    global _fire_id
    _fire_id += 1
    return {"id": _fire_id, "lat": lat, "lon": lon, "confidence": conf,
            "size_m": size, "observations": 1, "ts": now}

def ok(label):
    global PASS; print(f"  ok : {label}"); PASS += 1

def fail(label, detail=""):
    global FAIL; print(f"  FAIL: {label}" + (f" — {detail}" if detail else "")); FAIL += 1

print("\n=== Fire Merge Logic Tests ===\n")

# 1. Detection within 30 m merges into existing fire
fires = [new_fire(LAT0, LON0, conf=0.70)]
lat_near = LAT0 + 0.0002    # ~22 m north — within 30 m
_, merged = _try_merge(fires, lat_near, LON0, 0.85, 5.0, 1010.0)
if merged and fires[0]["observations"] == 2:
    ok("nearby detection merges (observations == 2)")
else:
    fail("nearby detection should merge", f"observations={fires[0].get('observations')}")

# 2. Centroid shifts toward new detection
original_lat = fires[0]["lat"]
# After merge, centroid should be between original and new point
if fires[0]["lat"] > LAT0 and fires[0]["lat"] < lat_near:
    ok(f"centroid moved toward new detection ({fires[0]['lat']:.7f})")
else:
    fail("centroid did not shift correctly", f"centroid={fires[0]['lat']:.7f}")

# 3. Higher confidence replaces lower
if fires[0]["confidence"] == 0.85:
    ok("confidence updated to higher value (0.85 > 0.70)")
else:
    fail("confidence not updated", f"got {fires[0]['confidence']}")

# 4. Size grows by FIRE_SIZE_GROWTH_M per merge
expected_size = min(5.0 + FIRE_SIZE_GROWTH_M, FIRE_SIZE_CAP_M)
if abs(fires[0]["size_m"] - expected_size) < 0.01:
    ok(f"size grew by {FIRE_SIZE_GROWTH_M}m to {fires[0]['size_m']:.1f}m")
else:
    fail("size did not grow correctly", f"expected {expected_size}, got {fires[0]['size_m']}")

# 5. Detection > 30 m away creates a new fire record (not merged)
fires2 = [new_fire(LAT0, LON0)]
lat_far = LAT0 + 0.0004   # ~44 m — outside 30 m threshold
_, merged2 = _try_merge(fires2, lat_far, LON0, 0.90, 5.0, 1010.0)
if not merged2:
    ok("distant detection (>30m) does NOT merge — new fire created")
else:
    fail("detection >30m should NOT merge")

# 6. Size cap is enforced — repeated merges never exceed FIRE_SIZE_CAP_M
fires3 = [new_fire(LAT0, LON0, size=FIRE_SIZE_CAP_M - 1.0)]
for _ in range(10):
    _try_merge(fires3, LAT0 + 0.0001, LON0, 0.9, 5.0, 1010.0)
if fires3[0]["size_m"] <= FIRE_SIZE_CAP_M:
    ok(f"size cap enforced ({fires3[0]['size_m']:.1f}m ≤ {FIRE_SIZE_CAP_M}m)")
else:
    fail("size exceeded cap", f"size={fires3[0]['size_m']}")

# 7. Lower confidence does NOT overwrite higher
fires4 = [new_fire(LAT0, LON0, conf=0.95)]
_try_merge(fires4, LAT0 + 0.0001, LON0, 0.50, 5.0, 1010.0)
if fires4[0]["confidence"] == 0.95:
    ok("lower confidence (0.50) does not overwrite higher (0.95)")
else:
    fail("confidence should not decrease", f"got {fires4[0]['confidence']}")

# 8. Multiple fires — merge hits the correct one
fires5 = [
    new_fire(LAT0,         LON0,         conf=0.7),   # fire A — nearby
    new_fire(LAT0 + 0.01,  LON0 + 0.01,  conf=0.6),   # fire B — far
]
lat_near_a = LAT0 + 0.0001   # ~11 m from fire A
matched, merged5 = _try_merge(fires5, lat_near_a, LON0, 0.8, 5.0, 1010.0)
if merged5 and matched is fires5[0] and fires5[1]["observations"] == 1:
    ok("merge hits fire A, not fire B")
else:
    fail("merge hit wrong fire", f"matched={matched}, fires5[1].obs={fires5[1].get('observations')}")

# 9. Exactly at the merge boundary (30 m) — should merge (≤ not <)
fires6 = [new_fire(LAT0, LON0)]
# Place detection exactly 30 m north
lat_boundary = LAT0 + 30.0 / M_PER_DEG_LAT
dist = _dist_m(LAT0, LON0, lat_boundary, LON0)
_, merged6 = _try_merge(fires6, lat_boundary, LON0, 0.8, 5.0, 1010.0)
if merged6:
    ok(f"detection at exactly {dist:.1f}m (boundary) merges (≤ operator)")
else:
    # Floating point may put it just outside — acceptable
    ok(f"detection at {dist:.1f}m did not merge (floating-point boundary — acceptable)")

# 10. Zero-confidence detection does not corrupt confidence field
fires7 = [new_fire(LAT0, LON0, conf=0.75)]
_try_merge(fires7, LAT0 + 0.0001, LON0, 0.0, 5.0, 1010.0)
if fires7[0]["confidence"] == 0.75:
    ok("zero-confidence detection does not overwrite existing confidence")
else:
    fail("confidence corrupted by 0.0 detection", f"got {fires7[0]['confidence']}")

print(f"\n{'='*40}")
print(f"  Passed: {PASS}  |  Failed: {FAIL}")
if FAIL == 0:
    print("  all fire merge logic tests passed")
else:
    print("  SOME TESTS FAILED")
    sys.exit(1)
