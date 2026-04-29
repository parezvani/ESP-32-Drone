import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "groundstation"))

from triangulator import triangulate, LAT0, LON0


def approx(a, b, tol=1e-4):
    return abs(a - b) < tol


def case_symmetric_inward():
    """Two drones equidistant E and W of LAT0, mirrored bearings → intersection on the central meridian."""
    coords = triangulate(LAT0 - 0.001, LON0 - 0.001, 45.0,
                         LAT0 - 0.001, LON0 + 0.001, 315.0)
    assert coords is not None, coords
    assert approx(coords[1], LON0), coords  # intersection lies on the symmetry axis
    assert coords[0] > LAT0 - 0.001, coords  # north of both drones
    print(f"ok: symmetric_inward -> {coords}")


def case_north_south_intersection():
    """Drone south looking ENE, drone north looking ESE → cross east of LAT0/LON0."""
    coords = triangulate(LAT0 - 0.001, LON0, 60.0,
                         LAT0 + 0.001, LON0, 120.0)
    assert coords is not None, coords
    assert coords[1] > LON0, coords
    print(f"ok: north_south_intersection -> {coords}")


def case_parallel_rays():
    """Both drones heading the same direction → no intersection."""
    coords = triangulate(LAT0 - 0.001, LON0, 90.0,
                         LAT0 + 0.001, LON0, 90.0)
    assert coords is None, coords
    print("ok: parallel_rays")


def case_diverging_rays():
    """Drones with crossing tracks but pointed away from each other → None."""
    coords = triangulate(LAT0 - 0.001, LON0 - 0.001, 225.0,
                         LAT0 - 0.001, LON0 + 0.001, 135.0)
    assert coords is None, coords
    print("ok: diverging_rays")


def case_oblique_intersection():
    """SW drone heading NE, SE drone heading NW → cross north of both."""
    coords = triangulate(LAT0 - 0.002, LON0 - 0.002, 45.0,
                         LAT0 - 0.002, LON0 + 0.002, 315.0)
    assert coords is not None, coords
    assert coords[0] > LAT0 - 0.002, coords
    print(f"ok: oblique_intersection -> {coords}")


if __name__ == "__main__":
    case_symmetric_inward()
    case_north_south_intersection()
    case_parallel_rays()
    case_diverging_rays()
    case_oblique_intersection()
    print("\nall tests passed")
