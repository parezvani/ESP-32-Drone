import math

EARTH_R = 6378137.0


def fire_position(drone_state, bbox, frame_size, camera):
    """Estimate fire lat/lon + bearing/distance from a drone-mounted camera.

    Assumes flat ground at the drone's altitude reference, fixed camera tilt
    (no pitch/roll from the airframe), and a pinhole camera model.

    Returns None if the bbox center maps to a ray that doesn't intersect the
    ground plane (e.g. aimed at or above the horizon).
    """
    lat = drone_state["lat"]
    lon = drone_state["lon"]
    alt = drone_state["alt_m"]
    heading = drone_state["heading_deg"]

    if lat is None or lon is None or alt is None or heading is None:
        return None
    if alt <= 0:
        return None

    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    W, H = frame_size
    nx = (cx - W / 2) / W
    ny = (cy - H / 2) / H

    yaw_rel = nx * camera["hfov_deg"]
    pitch_rel = ny * camera["vfov_deg"]

    angle_below_horizontal = camera["tilt_deg"] + pitch_rel
    if angle_below_horizontal <= 0:
        return None

    angle_from_vertical_rad = math.radians(90 - angle_below_horizontal)
    distance_m = alt * math.tan(angle_from_vertical_rad)
    if distance_m < 0:
        return None

    bearing_deg = (heading + yaw_rel) % 360
    bearing_rad = math.radians(bearing_deg)
    lat_rad = math.radians(lat)

    dx = distance_m * math.sin(bearing_rad)
    dy = distance_m * math.cos(bearing_rad)

    fire_lat = lat + math.degrees(dy / EARTH_R)
    fire_lon = lon + math.degrees(dx / (EARTH_R * math.cos(lat_rad)))

    return {
        "fire_lat": fire_lat,
        "fire_lon": fire_lon,
        "bearing_deg": bearing_deg,
        "distance_m": distance_m,
    }
