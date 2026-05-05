import socket
import json

UDP_PORT = 4210

def main():
    print(f"Listening for GPS UDP packets on port {UDP_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))

    try:
        # Wait for a single valid packet
        data, addr = sock.recvfrom(1024)
        print(f"Packet received from {addr[0]}")
        
        payload = json.loads(data.decode("utf-8", "ignore"))
        lat = payload.get("lat")
        lon = payload.get("lon")
        
        if lat is not None and lon is not None:
            print(f"Parsed Coordinates: {lat}, {lon}")
            
            # Validate if coordinates are within the Santa Cruz region
            is_lat_valid = 36.9 < lat < 37.1
            is_lon_valid = -122.1 < lon < -122.0
            
            if is_lat_valid and is_lon_valid:
                print("SUCCESS: Valid GPS coordinates detected within Santa Cruz range.")
            else:
                print("WARNING: Coordinates received but they are outside the expected local range.")
        else:
            print("FAILURE: Packet received but lat/lon fields are missing or null.")
            
    except json.JSONDecodeError:
        print("ERROR: Received data that was not valid JSON.")
    except Exception as e:
        print(f"ERROR: GPS test failed. {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    main()