# FireFly setup — installs Python dependencies into a local virtual environment.
# Windows PowerShell counterpart to setup.sh.
#
# Usage (from PowerShell, in the repo root):
#   .\setup.ps1
#
# If you get a "running scripts is disabled" error, run this first (one-time):
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# ---------- find Python ----------
$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) {
    Write-Host "[setup] Python not found on PATH."
    Write-Host "        Install Python 3.10+ from https://www.python.org/downloads/ and re-run."
    exit 1
}

# ---------- check Python version ----------
$check = & $python -c "import sys; print('ok' if sys.version_info >= (3, 10) else 'old')"
if ($check.Trim() -ne "ok") {
    Write-Host "[setup] Python 3.10+ required. Found:"
    & $python --version
    exit 1
}
Write-Host "[setup] using $((& $python --version)) at $python"

# ---------- create venv ----------
if (-not (Test-Path ".venv")) {
    Write-Host "[setup] creating virtual environment in .venv\"
    & $python -m venv .venv
} else {
    Write-Host "[setup] reusing existing .venv\"
}

# ---------- activate venv ----------
$activate = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Host "[setup] could not find $activate — bailing"
    exit 1
}
. $activate

# ---------- install dependencies ----------
Write-Host "[setup] upgrading pip"
& python -m pip install --upgrade pip | Out-Null

Write-Host "[setup] installing Python dependencies (~250 MB, takes 2-5 minutes)"
& pip install -r requirements.txt

# ---------- done ----------
Write-Host ""
Write-Host "[setup] done."
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "  1. Activate the virtual environment in your terminal:"
Write-Host "       .\.venv\Scripts\Activate.ps1     (Windows PowerShell)"
Write-Host "       source .venv/bin/activate        (macOS / Linux / Git Bash)"
Write-Host ""
Write-Host "  2. Run the launcher:"
Write-Host "       python run.py"
Write-Host ""
Write-Host "     Optional flags:"
Write-Host "       --no-sim       skip the fake drone fleet (use real GPS only)"
Write-Host "       --no-cam       skip camera discovery and YOLO"
Write-Host "       --no-yolo      register the camera but skip fire detection"
Write-Host "       --no-browser   don't auto-open the browser"
Write-Host ""
Write-Host "  3. Browser opens at http://127.0.0.1:5050"
Write-Host ""
Write-Host "Notes:"
Write-Host "  - For real ESP32 hardware (GPS firmware, ESP32-CAM), see the README."
Write-Host "    ESP-IDF and Arduino IDE installers are not handled by this script."
