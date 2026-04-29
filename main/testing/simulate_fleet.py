import socket
import json
import time
import math

UDP_IP, UDP_PORT = "127.0.0.1", 4210
LAT0, LON0 = 36.995578, -122.058878
TRUE_FIRE_LAT, TRUE_FIRE_LON = 36.996278, -122.058078

# 1. WIDENED THE FOV! 10 degrees is too narrow for a 1-second tick.
CAMERA_FOV = 60.0 

def get_bearing(lat1, lon1, lat2, lon2):
    dLon = math.radians(lon2 - lon1)
    y = math.sin(dLon) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dLon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print("Fleet Simulator running. Broadcasting raw sensor data...")
    start_time = time.time()
    
    while True:
        t = time.time() - start_time
        
        # Drone 1
        theta1 = t * 0.3
        lat1, lon1 = LAT0 + (math.sin(theta1) * 0.001), LON0 + (math.cos(theta1) * 0.001)
        hdg1 = get_bearing(lat1, lon1, LAT0 + (math.sin(theta1 + 0.1) * 0.001), LON0 + (math.cos(theta1 + 0.1) * 0.001))
        
        # Drone 2
        theta2 = -t * 0.15
        lat2, lon2 = LAT0 + (math.sin(theta2) * 0.002), LON0 + (math.cos(theta2) * 0.002)
        hdg2 = get_bearing(lat2, lon2, LAT0 + (math.sin(theta2 - 0.1) * 0.002), LON0 + (math.cos(theta2 - 0.1) * 0.002))

        # Sensor logic: Are they looking at the fire?
        b1 = get_bearing(lat1, lon1, TRUE_FIRE_LAT, TRUE_FIRE_LON)
        sees_fire_1 = abs((b1 - hdg1 + 180) % 360 - 180) <= CAMERA_FOV
        
        b2 = get_bearing(lat2, lon2, TRUE_FIRE_LAT, TRUE_FIRE_LON)
        sees_fire_2 = abs((b2 - hdg2 + 180) % 360 - 180) <= CAMERA_FOV

        # 2. ADD DEBUG PRINTS SO YOU CAN SEE THE SENSORS WORKING
        if sees_fire_1:
            print(f"[Time: {int(t)}s] Drone 1 sees smoke!")
        if sees_fire_2:
            print(f"[Time: {int(t)}s] Drone 2 sees smoke!")

        # Broadcast raw data
        msg1 = {"id": "drone_1", "lat": lat1, "lon": lon1, "heading_deg": hdg1, "fire_detected": sees_fire_1}
        msg2 = {"id": "drone_2", "lat": lat2, "lon": lon2, "heading_deg": hdg2, "fire_detected": sees_fire_2}
        
        sock.sendto(json.dumps(msg1).encode("utf-8"), (UDP_IP, UDP_PORT))
        sock.sendto(json.dumps(msg2).encode("utf-8"), (UDP_IP, UDP_PORT))
        
        time.sleep(1)

if __name__ == "__main__":
    main()
#