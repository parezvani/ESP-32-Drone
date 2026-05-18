"""FireFly indoor demo launcher.

  python demo.py                              # discovers camera, opens browser
  python demo.py --no-browser                 # skip browser
  $env:FIREFLY_CAM_URL="http://x:81/stream"   # skip LAN scan, use this URL
"""
import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor

import requests

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
CLOUD_URL = os.environ.get("FIREFLY_SERVER", "https://firefly-j68i.onrender.com").rstrip("/")


def wake_cloud(timeout: float = 60.0) -> bool:
    print(f"[1/3] waking cloud {CLOUD_URL} (Render free tier sleeps after 15min)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{CLOUD_URL}/api/state", timeout=10).ok:
                print("      cloud is awake")
                return True
        except requests.RequestException:
            pass
        time.sleep(3)
    print("      WARNING: no response — continuing anyway")
    return False


def local_subnet() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ".".join(ip.split(".")[:3])


def probe_cam(ip: str, timeout: float = 1.5):
    try:
        r = requests.get(f"http://{ip}/", timeout=timeout)
        if r.ok and ("ESP32" in r.text or "OV2640" in r.text
                     or "stream" in r.text.lower()):
            return ip
    except requests.RequestException:
        pass
    return None


def discover_cam():
    explicit = os.environ.get("FIREFLY_CAM_URL", "").strip()
    if explicit:
        print(f"[2/3] using FIREFLY_CAM_URL={explicit}")
        return explicit

    subnet = local_subnet()
    print(f"[2/3] scanning {subnet}.1-254 for ESP-CAM...")
    for attempt in range(2):
        with ThreadPoolExecutor(max_workers=64) as ex:
            for ip in ex.map(probe_cam, (f"{subnet}.{i}" for i in range(1, 255))):
                if ip:
                    url = f"http://{ip}:81/stream"
                    print(f"      found camera at {url}")
                    return url
        if attempt == 0:
            print("      first scan empty, retrying...")
            time.sleep(1.5)
    return None


def main():
    parser = argparse.ArgumentParser(description="FireFly indoor demo launcher")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-wake", action="store_true",
                        help="skip cloud warm-up GET (use for fast local restart)")
    args = parser.parse_args()

    api_key = os.environ.get("FIREFLY_API_KEY", "").strip()
    if not api_key:
        print("ERROR: FIREFLY_API_KEY not set.")
        print()
        print("  1. open the cloud dashboard and register one drone")
        print("  2. copy the API key it shows you (one-time display)")
        print('  3. PowerShell:   $env:FIREFLY_API_KEY = "<paste>"')
        print()
        sys.exit(1)

    if not args.no_wake:
        wake_cloud()

    camera_url = discover_cam()
    if not camera_url:
        print()
        print("ERROR: no ESP-CAM found on the local subnet.")
        print("  - confirm cam is powered (wall charger, not laptop USB)")
        print("  - confirm cam is on the same WiFi as this laptop")
        print("  - open http://<cam-ip>/ in a browser to verify it's alive")
        print('  - or set explicitly:  $env:FIREFLY_CAM_URL = "http://<ip>:81/stream"')
        sys.exit(1)

    print("[3/3] launching worker (this opens an OpenCV window)")
    env = os.environ.copy()
    env.update({
        "FIREFLY_API_KEY": api_key,
        "FIREFLY_SERVER": CLOUD_URL,
        "FIREFLY_VIDEO": camera_url,
        "PYTHONUNBUFFERED": "1",
    })
    worker = subprocess.Popen(
        [sys.executable, "demo_worker.py"],
        cwd=os.path.join(REPO_ROOT, "main", "demo"),
        env=env,
    )

    def cleanup(*_):
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=3)
            except subprocess.TimeoutExpired:
                worker.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if not args.no_browser:
        time.sleep(1.5)
        webbrowser.open(CLOUD_URL)

    print(f"      cloud open at {CLOUD_URL}")
    print("      Ctrl+C in this window stops everything")
    try:
        worker.wait()
    except KeyboardInterrupt:
        pass
    cleanup()


if __name__ == "__main__":
    main()
