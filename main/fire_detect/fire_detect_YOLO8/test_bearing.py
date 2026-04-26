import math
from bearing import fire_position

CAM = {"hfov_deg": 60.0, "vfov_deg": 40.0, "tilt_deg": 90.0}
W, H = 1920, 1080


def approx(a, b, tol=1e-3):
    return abs(a - b) < tol


def case_directly_below():
    """Fire centered in frame, camera straight down → distance ~ 0."""
    drone = {"lat": 36.95, "lon": -122.04, "alt_m": 100.0, "heading_deg": 0.0}
    bbox = (W / 2 - 20, H / 2 - 20, W / 2 + 20, H / 2 + 20)
    out = fire_position(drone, bbox, (W, H), CAM)
    assert out is not None
    assert approx(out["distance_m"], 0.0, tol=0.5), out
    assert approx(out["fire_lat"], drone["lat"], tol=1e-5), out
    assert approx(out["fire_lon"], drone["lon"], tol=1e-5), out
    print("ok: directly_below")


def case_forward_tilt_centered():
    """Camera tilted 45° forward, fire centered → distance == altitude."""
    cam = {**CAM, "tilt_deg": 45.0}
    drone = {"lat": 0.0, "lon": 0.0, "alt_m": 100.0, "heading_deg": 0.0}
    bbox = (W / 2 - 20, H / 2 - 20, W / 2 + 20, H / 2 + 20)
    out = fire_position(drone, bbox, (W, H), cam)
    assert approx(out["distance_m"], 100.0, tol=0.5), out
    assert approx(out["bearing_deg"], 0.0, tol=0.1), out
    print("ok: forward_tilt_centered")


def case_heading_east_right_edge():
    """Heading east, fire at right edge → bearing ~ 90 + hfov/2."""
    drone = {"lat": 0.0, "lon": 0.0, "alt_m": 100.0, "heading_deg": 90.0}
    bbox = (W - 40, H / 2 - 20, W, H / 2 + 20)
    out = fire_position(drone, bbox, (W, H), CAM)
    expected_bearing = (90.0 + CAM["hfov_deg"] * (W - 20 - W / 2) / W) % 360
    assert approx(out["bearing_deg"], expected_bearing, tol=0.5), (out, expected_bearing)
    print("ok: heading_east_right_edge")


def case_above_horizon():
    """Fire above center of frame with shallow tilt → above horizon, returns None."""
    cam = {**CAM, "tilt_deg": 10.0}
    drone = {"lat": 0.0, "lon": 0.0, "alt_m": 100.0, "heading_deg": 0.0}
    bbox = (W / 2 - 20, 0, W / 2 + 20, 40)
    out = fire_position(drone, bbox, (W, H), cam)
    assert out is None, out
    print("ok: above_horizon")


def case_missing_drone_state():
    """Missing GPS or heading → None."""
    drone = {"lat": None, "lon": None, "alt_m": None, "heading_deg": None}
    bbox = (W / 2, H / 2, W / 2 + 10, H / 2 + 10)
    assert fire_position(drone, bbox, (W, H), CAM) is None
    print("ok: missing_drone_state")


if __name__ == "__main__":
    case_directly_below()
    case_forward_tilt_centered()
    case_heading_east_right_edge()
    case_above_horizon()
    case_missing_drone_state()
    print("\nall tests passed")
