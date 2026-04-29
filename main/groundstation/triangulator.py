import math

LAT0, LON0 = 36.995578, -122.058878


def triangulate(lat1, lon1, hdg1, lat2, lon2, hdg2):
    """Intersect two bearing rays on a local flat-earth approximation.

    Each drone reports a position (lat, lon) and a heading-to-fire (deg from N).
    Returns (fire_lat, fire_lon) where the rays cross, or None if the rays
    are parallel or the intersection is behind the drones.
    """
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(LAT0))

    x1 = (lon1 - LON0) * m_per_deg_lon
    y1 = (lat1 - LAT0) * m_per_deg_lat
    x2 = (lon2 - LON0) * m_per_deg_lon
    y2 = (lat2 - LAT0) * m_per_deg_lat

    dx1, dy1 = math.sin(math.radians(hdg1)), math.cos(math.radians(hdg1))
    dx2, dy2 = math.sin(math.radians(hdg2)), math.cos(math.radians(hdg2))

    det = dx1 * dy2 - dy1 * dx2
    if abs(det) < 1e-6:
        return None

    t1 = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / det
    if t1 < 0:
        return None

    return (
        LAT0 + ((y1 + t1 * dy1) / m_per_deg_lat),
        LON0 + ((x1 + t1 * dx1) / m_per_deg_lon),
    )
