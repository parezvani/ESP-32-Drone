#!/usr/bin/env bash
# FireFly setup — installs Python dependencies into a local virtual environment.
# Works on macOS, Linux, and Git Bash on Windows.
#
# Usage:
#   ./setup.sh
# or
#   bash setup.sh
set -euo pipefail

cd "$(dirname "$0")"

# ---------- find Python ----------
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[setup] Python not found on PATH."
    echo "        Install Python 3.10+ from https://www.python.org/downloads/ and re-run."
    exit 1
fi

# ---------- check Python version ----------
if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo "[setup] Python 3.10+ required. Found:"
    "$PY" --version
    exit 1
fi
echo "[setup] using $($PY --version) at $(command -v "$PY")"

# ---------- create venv ----------
if [ ! -d ".venv" ]; then
    echo "[setup] creating virtual environment in .venv/"
    "$PY" -m venv .venv
else
    echo "[setup] reusing existing .venv/"
fi

# ---------- activate venv ----------
# Linux/macOS layout vs Windows layout
if [ -f ".venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    # shellcheck disable=SC1091
    source .venv/Scripts/activate
else
    echo "[setup] could not find venv activate script — bailing"
    exit 1
fi

# ---------- install dependencies ----------
echo "[setup] upgrading pip"
python -m pip install --upgrade pip >/dev/null

echo "[setup] installing Python dependencies (~250 MB, takes 2-5 minutes)"
pip install -r requirements.txt

# ---------- done ----------
cat <<EOF

[setup] done.

Next steps:

  1. Activate the virtual environment in your terminal:
       source .venv/bin/activate           (macOS / Linux / Git Bash)
       .venv\\Scripts\\Activate.ps1        (Windows PowerShell)

  2. Run the launcher:
       python run.py

     Optional flags:
       --no-sim       skip the fake drone fleet (use real GPS only)
       --no-cam       skip camera discovery and YOLO
       --no-yolo      register the camera but skip fire detection
       --no-browser   don't auto-open the browser

  3. Browser opens at http://127.0.0.1:5050

Notes:
  - For real ESP32 hardware (GPS firmware, ESP32-CAM), see the README. ESP-IDF
    and Arduino IDE installers are not handled by this script.
  - On macOS/Linux, set permission first if needed:  chmod +x setup.sh
EOF
