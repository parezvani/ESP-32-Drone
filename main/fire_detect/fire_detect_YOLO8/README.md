model.pt taken from [YOLO8](https://github.com/thilak-r/Forest-fire-detection-using-YOLOv8.git)


To run in WSL / Ubuntu:

python3 -m venv .venv
source .venv/bin/activate

pip install ultralytics opencv-python
pip install opencv-python numpy

python3 fire_detect.py
