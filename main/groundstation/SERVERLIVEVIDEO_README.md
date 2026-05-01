The live server implementation uses a similar setup as the regular server.

First, host a camera using an IP camera setup (e.g., Android App called "IP Camera")

3 Terminals

T1: python3 server_live_video.py
T2: python3 simulate_fleet.py
T3: run the following command replacing "<camera_ip" with the camera's IP address:

#curl -s -X POST http://localhost:5050/api/camera      -H "Content-Type: application/json"      -d '{"url": "http://<camera_ip>/video", "drone_id": "drone_1"}' | python -m json.tool


Go to http://127.0.0.1:5050 on a browser and click open camera to see the feed.
You can also see the smoke / fire alerts in the terminal where you ran "simulate_fleet.py"
