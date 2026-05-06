import argparse
import json
import socket
import time

def test_gps_stream(port, timeout_seconds):
    print(f"Testing GPS UDP stream on port {port} for up to {timeout_seconds} seconds...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    
    # Set a 1-second timeout on the socket so the while loop can evaluate the time limit
    sock.settimeout(1.0) 

    start_time = time.time()
    packets_received = 0

    while time.time() - start_time < timeout_seconds:
        try:
            data, addr = sock.recvfrom(1024)
            packets_received += 1
            
            payload = json.loads(data.decode("utf-8", "ignore"))
            lat = payload.get("lat")
            lon = payload.get("lon")
            sats = payload.get("sats", 0)
            alt = payload.get("alt_m")
            hdop = payload.get("hdop")
            drone_id = payload.get("id", "unknown")
            
            # Check for a valid coordinate fix (not None and not default 0.0)
            if lat is not None and lon is not None and lat != 0.0 and lon != 0.0:
                print("\n\n--- GPS Lock Established ---")
                print(f"Source ID:   {drone_id} (IP: {addr[0]})")
                print(f"Coordinates: {lat:.6f}, {lon:.6f}")
                print(f"Satellites:  {sats}")
                print(f"Altitude:    {alt} m" if alt is not None else "Altitude:    N/A")
                print(f"HDOP:        {hdop}" if hdop is not None else "HDOP:        N/A")
                
                # Validate Santa Cruz region bounding box
                if 36.9 < lat < 37.1 and -122.1 < lon < -122.0:
                    print("STATUS:      SUCCESS (Valid coordinates within Santa Cruz region)")
                else:
                    print("STATUS:      WARNING (Coordinates are valid but outside Santa Cruz region)")
                
                return True
            else:
                # Print status on the same line to avoid flooding the terminal
                print(f"\rPacket received, but no GPS fix yet (Sats: {sats}). Waiting...", end="", flush=True)
                
        except socket.timeout:
            # Re-evaluate the while loop condition
            continue 
        except json.JSONDecodeError:
            print(f"\nERROR: Received malformed JSON from {addr[0]}")
        except Exception as e:
            print(f"\nERROR: Unexpected error: {e}")

    # If the loop exits, the timeout was reached
    print(f"\n\nFAILURE: Test timed out after {timeout_seconds} seconds.")
    if packets_received > 0:
        print("Packets were received, but none contained a valid GPS lock (lat/lon).")
        print("Ensure the GPS antenna has a clear, unobstructed view of the sky.")
    else:
        print("No UDP packets were received. Verify the ESP32 Wi-Fi connection and target IP address.")
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test incoming GPS UDP packets.")
    parser.add_argument("--port", type=int, default=4210, help="UDP port to listen on.")
    parser.add_argument("--timeout", type=int, default=45, help="Seconds to wait for a valid fix.")
    args = parser.parse_args()
    
    test_gps_stream(args.port, args.timeout)