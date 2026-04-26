"""Fake drone publisher — POSTs synthetic GPS+heading to the map server.

Lets you run the full pipeline (fire detect + bearing + map UI) with no
hardware. Drone flies a slow circle around a fixed center at constant altitude.
"""
import math
import time
import requests

SERVER = "http://127.0.0.1:5000"
CENTER_LAT = 36.9914
CENTER_LON = -122.0609
RADIUS_M = 80.0
ALT_M = 100.0
PERIOD_S = 60.0

EARTH_R = 6378137.0


def main():
    t0 = time.time()
    while True:
        t = time.time() - t0
        theta = (t / PERIOD_S) * 2 * math.pi

        lat_rad = math.radians(CENTER_LAT)
        dx = RADIUS_M * math.cos(theta)
        dy = RADIUS_M * math.sin(theta)
        lat = CENTER_LAT + math.degrees(dy / EARTH_R)
        lon = CENTER_LON + math.degrees(dx / (EARTH_R * math.cos(lat_rad)))

        heading = (math.degrees(theta) + 90) % 360

        try:
            requests.post(f"{SERVER}/api/drone", json={
                "lat": lat, "lon": lon, "alt_m": ALT_M, "heading_deg": heading,
            }, timeout=1.0)
        except requests.RequestException as e:
            print(f"post failed: {e}")

        time.sleep(0.5)


if __name__ == "__main__":
    main()
