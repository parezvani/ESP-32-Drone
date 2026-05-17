"""reposition.py

Triangulates a fire's GPS position using two observations from the same drone
taken from meaningfully different positions. Single drone equivalent of
triangulator.py.

How it works:

1. When a drone first reports fire_detected=True, we store that position +
   heading as a "pending" observation.
2. On every subsequent fire_detected=True report we check:
      a. Has the drone moved at least MIN_BASELINE_M metres?
      b. Has the heading-to-fire changed by at least MIN_ANGLE_DEG degrees?
   If both thresholds are met, we intersect the two bearing rays (identical
   math to triangulator.py) and emit a fire fix.
3. If the drone stops seeing fire for more than PENDING_EXPIRY_S seconds the
   pending observation is discarded — it's stale and the geometry may have
   changed.
4. After a successful triangulation the pending slot is cleared so the drone
   can start a fresh pair of observations for the same or a new fire.

Drop-in usage in server_live_video.py

Replace (or run alongside) the import of triangulator with:

    from single_drone_triangulator import SingleDroneTriangulator
    _sdtri = SingleDroneTriangulator()

Then inside _gps_listener, after updating _drones[drone_id], call:

    fix = _sdtri.update(drone_id, _drones[drone_id])
    if fix:
        _fire_id += 1
        _fires.append({
            "id":         _fire_id,
            "lat":        fix["lat"],
            "lon":        fix["lon"],
            "confidence": fix["confidence"],
            "size_m":     None,
            "area_m2":    None,
            "ts":         now,
            "source":     "single_drone_triangulation",
        })
"""

import math
import time

# ── Reference origin (flat-earth projection)
# Must match the value in triangulator.py if running both together.
LAT0, LON0 = 36.995578, -122.058878

# Thresholds
MIN_BASELINE_M = 10.0   # drone must move at least this far between observations
MIN_ANGLE_DEG = 15.0   # bearing-to-fire must change by at least this many degrees
PENDING_EXPIRY_S = 30.0  # discard pending obs if fire unseen for this long


# Geometry Helpers

def _to_local(lat, lon):
    """Convert (lat, lon) to local flat-earth (x_m, y_m) relative to LAT0/LON0."""
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(LAT0))
    return (lon - LON0) * m_per_deg_lon, (lat - LAT0) * m_per_deg_lat


def _from_local(x_m, y_m):
    """Convert local flat-earth (x_m, y_m) back to (lat, lon)."""
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(LAT0))
    return LAT0 + y_m / m_per_deg_lat, LON0 + x_m / m_per_deg_lon


def _distance_m(lat1, lon1, lat2, lon2):
    x1, y1 = _to_local(lat1, lon1)
    x2, y2 = _to_local(lat2, lon2)
    return math.hypot(x2 - x1, y2 - y1)


def _angle_diff(a, b):
    """Smallest absolute difference between two bearings (0-360°), result in [0, 180]."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def _intersect(lat1, lon1, hdg1, lat2, lon2, hdg2):
    """
    Intersect two bearing rays.  Identical to triangulator.triangulate() —
    returns (fire_lat, fire_lon) or None if rays are parallel / intersection
    is behind either drone.
    """
    x1, y1 = _to_local(lat1, lon1)
    x2, y2 = _to_local(lat2, lon2)

    dx1, dy1 = math.sin(math.radians(hdg1)), math.cos(math.radians(hdg1))
    dx2, dy2 = math.sin(math.radians(hdg2)), math.cos(math.radians(hdg2))

    det = dx1 * dy2 - dy1 * dx2
    if abs(det) < 1e-6:
        return None  # parallel rays

    t1 = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / det
    t2 = ((x2 - x1) * dy1 - (y2 - y1) * dx1) / det

    if t1 < 0 or t2 < 0:
        return None  # intersection is behind one of the drones

    fire_x = x1 + t1 * dx1
    fire_y = y1 + t1 * dy1
    return _from_local(fire_x, fire_y)


def _confidence(baseline_m, angle_deg):
    """
    Heuristic confidence score in [0, 1].

    Geometry is best when the baseline is long and the angle between rays is
    near 90°.  We penalise both a short baseline and a very shallow or very
    obtuse crossing angle.

    Score components:
      - baseline_score: saturates at 1.0 for baselines >= 50 m
      - angle_score: peaks at 1.0 for 90° crossing, falls to 0 at 0° / 180°
    """
    baseline_score = min(baseline_m / 50.0, 1.0)
    # angle_deg is the difference in headings; ideal crossing angle is 90°
    crossing = min(angle_deg, 180 - angle_deg) # map to [0, 90]
    angle_score = crossing / 90.0
    return round(baseline_score * angle_score, 3)


# Main Class

class SingleDroneTriangulator:
    """
    Stateful per-drone triangulator.  Thread-safe if you hold _lock before
    calling update() (the server already does this inside _gps_listener).

    Attributes

    _pending : dict[drone_id -> observation]
        observation = {
            "lat": float, "lon": float, "heading_deg": float, "ts": float
        }
    """

    def __init__(
        self,
        min_baseline_m:   float = MIN_BASELINE_M,
        min_angle_deg:    float = MIN_ANGLE_DEG,
        pending_expiry_s: float = PENDING_EXPIRY_S,
    ):
        self.min_baseline_m   = min_baseline_m
        self.min_angle_deg    = min_angle_deg
        self.pending_expiry_s = pending_expiry_s
        self._pending: dict   = {}

    def update(self, drone_id: str, drone_state: dict) -> dict | None:
        """
        Call once per telemetry packet for a drone.

        Parameters
        ----------
        drone_id    : unique string identifier for the drone
        drone_state : the drone's current state dict from _drones[drone_id]
                      Must contain: lat, lon, heading_deg, fire_detected, ts

        Returns
        -------
        A fix dict on successful triangulation:
            {"lat", "lon", "confidence", "baseline_m", "angle_deg"}
        None otherwise.
        """
        now = time.time()
        lat = drone_state.get("lat")
        lon = drone_state.get("lon")
        heading = drone_state.get("heading_deg")
        fire_seen = drone_state.get("fire_detected", False)

        if lat is None or lon is None or heading is None:
            return None

        pending = self._pending.get(drone_id)

        # No visible fire
        if not fire_seen:
            if pending and (now - pending["ts"]) > self.pending_expiry_s:
                print(f"[sdtri] {drone_id}: pending obs expired (no fire for "
                      f"{self.pending_expiry_s:.0f}s), discarding")
                del self._pending[drone_id]
            return None

        # Fire visible, no pending observation yet, store first observation
        if pending is None:
            self._pending[drone_id] = {
                "lat": lat, "lon": lon, "heading_deg": heading, "ts": now,
            }
            print(f"[sdtri] {drone_id}: stored first observation "
                  f"@ ({lat:.6f}, {lon:.6f}) hdg={heading:.1f}°")
            return None

        # Fire visible, pending exists, check thresholds
        baseline_m = _distance_m(pending["lat"], pending["lon"], lat, lon)
        angle_deg  = _angle_diff(pending["heading_deg"], heading)

        if baseline_m < self.min_baseline_m:
            return None # drone hasn't moved far enough yet
        if angle_deg < self.min_angle_deg:
            return None # heading hasn't changed enough yet

        # Both thresholds met, attempt intersection
        result = _intersect(
            pending["lat"], pending["lon"], pending["heading_deg"],
            lat, lon, heading,
        )

        if result is None:
            print(f"[sdtri] {drone_id}: rays parallel or behind drone "
                  f"(baseline={baseline_m:.1f}m angle={angle_deg:.1f}°), "
                  f"updating pending obs")
            # Update the pending obs to the current position so we keep trying
            self._pending[drone_id] = {
                "lat": lat, "lon": lon, "heading_deg": heading, "ts": now,
            }
            return None

        fire_lat, fire_lon = result
        conf = _confidence(baseline_m, angle_deg)

        print(f"[sdtri] {drone_id}: triangulated fire @ "
              f"({fire_lat:.6f}, {fire_lon:.6f}) "
              f"baseline={baseline_m:.1f}m angle={angle_deg:.1f}° "
              f"confidence={conf:.2f}")

        # Clear pending so next sighting starts a fresh pair
        del self._pending[drone_id]

        return {
            "lat":        fire_lat,
            "lon":        fire_lon,
            "confidence": conf,
            "baseline_m": round(baseline_m, 2),
            "angle_deg":  round(angle_deg,  2),
        }

    def clear(self, drone_id: str | None = None) -> None:
        """Discard pending observations. Pass drone_id to clear one drone,
        or None to clear all (e.g. on /api/reset)."""
        if drone_id is None:
            self._pending.clear()
        else:
            self._pending.pop(drone_id, None)

    def status(self) -> dict:
        """Return a snapshot of pending observations (for /api/state debug)."""
        now = time.time()
        return {
            drone_id: {
                "lat":         obs["lat"],
                "lon":         obs["lon"],
                "heading_deg": obs["heading_deg"],
                "age_s":       round(now - obs["ts"], 1),
            }
            for drone_id, obs in self._pending.items()
        }


# Standalone smoke test

if __name__ == "__main__":
    """
    Simulates a drone orbiting around a known fire and checks that the
    triangulator recovers the fire position.

    Expected output: a fix within a few metres of (36.9960, -122.0580).
    """
    import random

    FIRE_LAT, FIRE_LON = 36.9960, -122.0580

    def _bearing_to_fire(drone_lat, drone_lon):
        """Ground-truth bearing from drone to fire (degrees from N)."""
        x1, y1 = _to_local(drone_lat, drone_lon)
        x2, y2 = _to_local(FIRE_LAT, FIRE_LON)
        angle = math.degrees(math.atan2(x2 - x1, y2 - y1))
        return angle % 360

    tri = SingleDroneTriangulator(min_baseline_m=10, min_angle_deg=15)

    # Simulate drone orbiting at ~120 m radius, reporting every 0.5 s at 5 m/s
    orbit_radius_m = 120
    m_per_deg_lat  = 111_320.0
    m_per_deg_lon  = 111_320.0 * math.cos(math.radians(LAT0))

    fixes = []
    for step in range(200):
        theta = math.radians(step * 3)          # 3° per step → full orbit in 120 steps
        dlat = orbit_radius_m * math.cos(theta) / m_per_deg_lat
        dlon = orbit_radius_m * math.sin(theta) / m_per_deg_lon
        drone_lat = FIRE_LAT + dlat
        drone_lon = FIRE_LON + dlon

        # Add small GPS noise (±1 m)
        noise_lat = random.gauss(0, 1 / m_per_deg_lat)
        noise_lon = random.gauss(0, 1 / m_per_deg_lon)
        bearing = _bearing_to_fire(drone_lat + noise_lat, drone_lon + noise_lon)
        # Add small bearing noise (±1°)
        bearing += random.gauss(0, 1.0)

        state = {
            "lat":          drone_lat + noise_lat,
            "lon":          drone_lon + noise_lon,
            "heading_deg":  bearing,
            "fire_detected": True,
            "ts":           time.time(),
        }

        fix = tri.update("drone_sim", state)
        if fix:
            fixes.append(fix)
            err_x, err_y = _to_local(fix["lat"], fix["lon"])
            true_x, true_y = _to_local(FIRE_LAT, FIRE_LON)
            error_m = math.hypot(err_x - true_x, err_y - true_y)
            print(f"  -> fix #{len(fixes)}: error={error_m:.1f}m  conf={fix['confidence']:.2f}  "
                  f"baseline={fix['baseline_m']:.1f}m  angle={fix['angle_deg']:.1f}°")
            if len(fixes) >= 3:
                break

    if not fixes:
        print("No fix produced — check thresholds or orbit parameters.")