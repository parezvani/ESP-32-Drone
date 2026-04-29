import argparse
import math
import random
import time

import requests


def parse_center(s: str) -> tuple[float, float]:
    lat, lon = s.split(",")
    return float(lat.strip()), float(lon.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulate a drone flying a circle and occasionally detecting fires.")
    ap.add_argument("--server", default="http://127.0.0.1:5050")
    ap.add_argument("--center", type=parse_center, default=(43.2609, -79.9192),
                    help="lat,lon of the orbit center (default: McMaster-ish)")
    ap.add_argument("--radius-m", type=float, default=120.0)
    ap.add_argument("--period-s", type=float, default=45.0, help="seconds per full orbit")
    ap.add_argument("--alt-m", type=float, default=50.0)
    ap.add_argument("--drone-hz", type=float, default=5.0, help="drone position updates per second")
    ap.add_argument("--fire-every-s", type=float, default=20.0, help="mean seconds between simulated fires")
    args = ap.parse_args()

    lat0, lon0 = args.center
    # 1 deg lat ~ 111_320 m; 1 deg lon ~ 111_320 * cos(lat)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))

    start = time.time()
    next_fire_at = start + random.expovariate(1.0 / args.fire_every_s)
    dt = 1.0 / args.drone_hz

    print(f"Simulating drone around ({lat0}, {lon0}), orbit radius {args.radius_m}m, posting to {args.server}")

    try:
        while True:
            now = time.time()
            theta = 2 * math.pi * ((now - start) % args.period_s) / args.period_s
            dx = args.radius_m * math.cos(theta)
            dy = args.radius_m * math.sin(theta)
            lat = lat0 + dy / m_per_deg_lat
            lon = lon0 + dx / m_per_deg_lon
            heading = (math.degrees(theta) + 90.0) % 360.0

            try:
                requests.post(
                    f"{args.server}/api/drone",
                    json={"lat": lat, "lon": lon, "alt_m": args.alt_m, "heading_deg": heading},
                    timeout=0.5,
                )
            except requests.RequestException as e:
                print(f"[drone] post failed: {e}")

            if now >= next_fire_at:
                jitter_m = 40.0
                f_lat = lat + random.uniform(-jitter_m, jitter_m) / m_per_deg_lat
                f_lon = lon + random.uniform(-jitter_m, jitter_m) / m_per_deg_lon
                try:
                    r = requests.post(
                        f"{args.server}/api/fire",
                        json={
                            "lat": f_lat,
                            "lon": f_lon,
                            "size_m": round(random.uniform(2.0, 12.0), 1),
                            "area_m2": round(random.uniform(10.0, 200.0), 1),
                            "confidence": round(random.uniform(0.6, 0.95), 2),
                        },
                        timeout=0.5,
                    )
                    print(f"[fire] posted @ ({f_lat:.5f},{f_lon:.5f}) -> {r.status_code}")
                except requests.RequestException as e:
                    print(f"[fire] post failed: {e}")
                next_fire_at = now + random.expovariate(1.0 / args.fire_every_s)

            time.sleep(dt)
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
