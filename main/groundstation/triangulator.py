import time
import math
import requests

SERVER_STATE_URL = "http://10.0.0.251:5000/api/state"
SERVER_FIRE_URL = "http://10.0.0.251:5000/api/fire"

LAT0, LON0 = 36.995578, -122.058878

def triangulate(lat1, lon1, hdg1, lat2, lon2, hdg2):
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(LAT0))
    
    x1 = (lon1 - LON0) * m_per_deg_lon
    y1 = (lat1 - LAT0) * m_per_deg_lat
    x2 = (lon2 - LON0) * m_per_deg_lon
    y2 = (lat2 - LAT0) * m_per_deg_lat
    
    dx1, dy1 = math.sin(math.radians(hdg1)), math.cos(math.radians(hdg1))
    dx2, dy2 = math.sin(math.radians(hdg2)), math.cos(math.radians(hdg2))
    
    det = dx1 * dy2 - dy1 * dx2
    if abs(det) < 1e-6:
        return None 
        
    t1 = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / det
    if t1 < 0:
        return None 
        
    est_lat = LAT0 + ((y1 + t1 * dy1) / m_per_deg_lat)
    est_lon = LON0 + ((x1 + t1 * dx1) / m_per_deg_lon)
    return est_lat, est_lon

def main():
    print("Triangulation Engine Started. Awaiting detection:")
    last_fire_report = 0
    memory_bank = {}
    
    while True:
        now = time.time()
        try:
            r = requests.get(SERVER_STATE_URL, timeout=1)
            state = r.json()
            drones = state.get("drones", {})
            
            for d_id, data in drones.items():
                if data.get("fire_detected") is True and data.get("heading_deg") is not None:
                    memory_bank[d_id] = {
                        "lat": data["lat"],
                        "lon": data["lon"],
                        "heading_deg": data["heading_deg"],
                        "ts": now
                    }
            
            stale_keys = [k for k, v in memory_bank.items() if now - v["ts"] > 10.0]
            for k in stale_keys:
                del memory_bank[k]
            
            if len(memory_bank) >= 2 and (now - last_fire_report > 5.0):
                d1_id, d2_id = list(memory_bank.keys())[:2]
                d1, d2 = memory_bank[d1_id], memory_bank[d2_id]
                
                print(f"\nDetected: {d1_id} and {d2_id}")
                print(f"Calculating intersection...")
                
                coords = triangulate(
                    d1["lat"], d1["lon"], d1["heading_deg"],
                    d2["lat"], d2["lon"], d2["heading_deg"]
                )
                
                if coords:
                    print(f"Intersection found at: {coords[0]:.5f}, {coords[1]:.5f}")
                    
                    # Post to server and check response
                    post_req = requests.post(SERVER_FIRE_URL, json={
                        "lat": coords[0], "lon": coords[1],
                        "size_m": 12.0, "area_m2": 75.0, "confidence": 0.88
                    })
                    
                    if post_req.status_code == 200:
                        print("Successfully pushed coordinates to map server.")
                    else:
                        print(f"Error: Server rejected coordinates. HTTP Status: {post_req.status_code}")
                        
                    last_fire_report = now
                    memory_bank.clear()
                    
        except requests.RequestException:
            pass # Fails silently if server is down, keeps terminal clean
            
        time.sleep(1)

if __name__ == "__main__":
    main()