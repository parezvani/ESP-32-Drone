"""cam_relay.py — pull MJPEG from an ESP32-CAM, push frames to FireFly cloud.

The ESP32-CAM's stock firmware only serves a local MJPEG stream on port 81.
This worker runs on the laptop (which is on the same WiFi as the cam), pulls
frames from that local stream, and POSTs each one to the FireFly cloud server
authenticated with the drone's API key — the same key the GPS firmware uses.

Usage:
    python cam_relay.py \\
        --cam-url http://<cam-ip>:81/stream \\
        --server  https://your-firefly.onrender.com \\
        --api-key JFjQoTWebvkz823ayIaHxwqhEMfm7phPamLE1r8--XkGgSxYHNvT74rYxWrFDVpu \\
        --fps 5
"""

import argparse
import time

import requests


def _parse_boundary(content_type: str) -> str | None:
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            return part.split("=", 1)[1].strip().strip('"')
    return None


def _frames_from(url: str, timeout: float):
    """Yield JPEG bytes from a multipart/x-mixed-replace MJPEG endpoint."""
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        boundary = _parse_boundary(r.headers.get("Content-Type", ""))
        if not boundary:
            raise RuntimeError(
                f"no multipart boundary in Content-Type: {r.headers.get('Content-Type')!r}"
            )
        boundary_bytes = ("--" + boundary).encode()
        buffer = b""
        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                continue
            buffer += chunk
            while True:
                idx = buffer.find(boundary_bytes)
                if idx < 0:
                    break
                hdr_end = buffer.find(b"\r\n\r\n", idx)
                if hdr_end < 0:
                    break
                hdr_block = buffer[idx + len(boundary_bytes):hdr_end]
                clen = None
                for line in hdr_block.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        try:
                            clen = int(line.split(b":", 1)[1].strip())
                        except ValueError:
                            pass
                        break
                payload_start = hdr_end + 4
                if clen is None:
                    # Fallback for cams that omit Content-Length: scan for next boundary.
                    next_idx = buffer.find(boundary_bytes, payload_start)
                    if next_idx < 0:
                        break  # need more bytes
                    jpeg = buffer[payload_start:next_idx].rstrip(b"\r\n")
                    buffer = buffer[next_idx:]
                else:
                    payload_end = payload_start + clen
                    if len(buffer) < payload_end:
                        break  # need more bytes
                    jpeg = buffer[payload_start:payload_end]
                    buffer = buffer[payload_end:]
                if jpeg:
                    yield jpeg


def main():
    ap = argparse.ArgumentParser(description="ESP32-CAM -> FireFly cloud frame relay")
    ap.add_argument("--cam-url", required=True,
                    help="MJPEG stream URL, e.g. http://192.168.1.47:81/stream")
    ap.add_argument("--server", required=True,
                    help="FireFly server base URL, e.g. https://firefly.onrender.com")
    ap.add_argument("--api-key", required=True,
                    help="API key for the drone (from the FireFly dashboard)")
    ap.add_argument("--fps", type=float, default=5.0,
                    help="Maximum frames per second to upload (default: 5)")
    ap.add_argument("--reconnect-delay", type=float, default=3.0,
                    help="Seconds to wait before retrying after a stream/POST error")
    ap.add_argument("--timeout", type=float, default=5.0,
                    help="HTTP timeout for each frame POST (seconds)")
    args = ap.parse_args()

    target = args.server.rstrip("/") + "/api/camera/frame"
    headers = {"X-API-Key": args.api_key, "Content-Type": "image/jpeg"}
    interval = 1.0 / args.fps if args.fps > 0 else 0.0

    sent = 0
    skipped = 0
    last_log = time.time()
    last_post = 0.0

    print(f"[relay] cam:    {args.cam_url}")
    print(f"[relay] server: {target}")
    print(f"[relay] fps:    {args.fps}")

    while True:
        try:
            for jpeg in _frames_from(args.cam_url, args.timeout):
                now = time.time()
                if interval and (now - last_post) < interval:
                    skipped += 1
                else:
                    try:
                        r = requests.post(target, data=jpeg, headers=headers,
                                          timeout=args.timeout)
                        if r.ok:
                            sent += 1
                            last_post = now
                        else:
                            print(f"[relay] POST {r.status_code}: {r.text.strip()[:200]}")
                    except requests.RequestException as e:
                        print(f"[relay] POST error: {e}")

                if now - last_log > 5.0:
                    print(f"[relay] sent={sent} skipped={skipped} "
                          f"last_frame_bytes={len(jpeg)}")
                    last_log = now
        except KeyboardInterrupt:
            print("\n[relay] stopped by user")
            return
        except (requests.RequestException, RuntimeError) as e:
            print(f"[relay] stream error: {e}; reconnecting in {args.reconnect_delay}s")

        time.sleep(args.reconnect_delay)


if __name__ == "__main__":
    main()
