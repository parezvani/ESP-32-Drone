"""FireFly launcher — starts server, registers camera, runs simulator + YOLO, opens browser.

Usage:
    python run.py                       # full stack with auto-discovered camera
    python run.py --no-cam              # skip camera + YOLO (sim-only demo)
    python run.py --no-yolo             # camera in UI but no fire detection
    FIREFLY_CAM_URL=http://X:81/stream python run.py    # skip scan, use explicit URL

The launcher sets a per-run FIREFLY_CAMERA_TOKEN for camera registration.
Ctrl+C kills everything.
"""
import argparse
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor

import requests

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER = "http://127.0.0.1:5050"
CAMERA_API_TOKEN = os.environ.get("FIREFLY_CAMERA_TOKEN") or secrets.token_urlsafe(32)

processes: list[tuple[str, subprocess.Popen]] = []


def start(name: str, cmd: list[str], cwd: str, env_extra: dict | None = None) -> subprocess.Popen:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    print(f"[run] starting {name}")
    p = subprocess.Popen(cmd, cwd=cwd, env=env)
    processes.append((name, p))
    return p


def wait_for_server(timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{SERVER}/api/state", timeout=0.5)
            if r.ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.3)
    return False


def local_subnet() -> str:
    """Return the /24 subnet prefix the host is on (e.g. '192.168.1')."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ".".join(ip.split(".")[:3])


def probe_cam(ip: str, timeout: float = 1.5) -> str | None:
    """Return ip if the host has an ESP32-CAM control panel on port 80."""
    try:
        r = requests.get(f"http://{ip}/", timeout=timeout)
        if r.status_code == 200 and ("ESP32" in r.text or "OV2640" in r.text or "stream" in r.text.lower()):
            return ip
    except requests.RequestException:
        pass
    return None


def discover_cam() -> str | None:
    """Find the ESP32-CAM by scanning the local subnet. Returns full stream URL or None."""
    explicit = os.environ.get("FIREFLY_CAM_URL")
    if explicit:
        print(f"[run] using FIREFLY_CAM_URL={explicit}")
        return explicit

    subnet = local_subnet()
    print(f"[run] scanning {subnet}.1-254 for ESP32-CAM...")

    for attempt in range(2):
        with ThreadPoolExecutor(max_workers=64) as ex:
            for ip in ex.map(probe_cam, (f"{subnet}.{i}" for i in range(1, 255))):
                if ip:
                    url = f"http://{ip}:81/stream"
                    print(f"[run] found camera at {url}")
                    return url
        if attempt == 0:
            print("[run] first scan came up empty, retrying...")
            time.sleep(1.5)

    print("[run] no camera found on local subnet")
    return None


def register_cam(url: str) -> bool:
    try:
        headers = {"X-Camera-Token": CAMERA_API_TOKEN}
        r = requests.post(f"{SERVER}/api/camera", json={"url": url}, headers=headers, timeout=2)
        if r.ok:
            print(f"[run] registered camera: {url}")
            return True
        print(f"[run] /api/camera returned {r.status_code}")
    except requests.RequestException as e:
        print(f"[run] failed to register cam: {e}")
    return False


def cleanup(signum=None, frame=None):
    print("\n[run] shutting down...")
    for name, p in reversed(processes):
        if p.poll() is None:
            print(f"[run] terminating {name}")
            p.terminate()
    deadline = time.time() + 3
    for name, p in processes:
        remaining = max(0, deadline - time.time())
        try:
            p.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            print(f"[run] force killing {name}")
            p.kill()
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Launch the FireFly stack")
    parser.add_argument("--no-cam", action="store_true", help="skip camera discovery and YOLO")
    parser.add_argument("--no-yolo", action="store_true", help="register camera but skip YOLO")
    parser.add_argument("--no-sim", action="store_true", help="skip the fake drone fleet")
    parser.add_argument("--no-browser", action="store_true", help="don't auto-open browser")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    start("server",
          [sys.executable, "server.py"],
          cwd=os.path.join(REPO_ROOT, "main", "groundstation"),
          env_extra={"FIREFLY_CAMERA_TOKEN": CAMERA_API_TOKEN})

    if not wait_for_server():
        print("[run] server failed to start within 10s")
        cleanup()
    print("[run] server ready at http://127.0.0.1:5050")

    cam_url = None
    if not args.no_cam:
        cam_url = discover_cam()
        if cam_url:
            register_cam(cam_url)

    if not args.no_sim:
        start("simulate_fleet",
              [sys.executable, "simulate_fleet.py"],
              cwd=os.path.join(REPO_ROOT, "main", "testing"))

    if cam_url and not args.no_yolo and not args.no_cam:
        start("fire_detect",
              [sys.executable, "fire_detect.py"],
              cwd=os.path.join(REPO_ROOT, "main", "fire_detect", "fire_detect_YOLO8"),
              env_extra={"FIREFLY_VIDEO": cam_url, "PYTHONUNBUFFERED": "1"})

    if not args.no_browser:
        time.sleep(0.5)
        webbrowser.open("http://127.0.0.1:5050")

    print("[run] all services running — Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
            for name, p in processes:
                if p.poll() is not None:
                    code = p.returncode
                    print(f"[run] {name} exited (code {code}) — shutting everything down")
                    cleanup()
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
