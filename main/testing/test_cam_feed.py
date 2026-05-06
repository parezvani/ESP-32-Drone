import requests
import time
import argparse

def test_mjpeg_stream(stream_url, duration):
    print(f"Testing Camera Feed at {stream_url} for {duration} seconds...")
    try:
        # stream=True allows reading the raw byte stream without loading into memory
        with requests.get(stream_url, stream=True, timeout=10) as r:
            r.raise_for_status()
            print("Connection established. Analyzing stream data...\n")
            
            start_time = time.time()
            bytes_received = 0
            frames_received = 0
            buffer = b""
            
            # Read in larger chunks for efficiency
            for chunk in r.iter_content(chunk_size=4096):
                if chunk:
                    bytes_received += len(chunk)
                    buffer += chunk
                    
                    # Search the buffer for JPEG Start of Image (SOI) and End of Image (EOI) markers
                    # SOI is \xff\xd8, EOI is \xff\xd9
                    while b'\xff\xd8' in buffer and b'\xff\xd9' in buffer:
                        start_idx = buffer.find(b'\xff\xd8')
                        end_idx = buffer.find(b'\xff\xd9', start_idx)
                        
                        if start_idx != -1 and end_idx != -1:
                            frames_received += 1
                            # Remove the processed frame from the buffer
                            buffer = buffer[end_idx + 2:]
                        else:
                            break
                
                elapsed_time = time.time() - start_time
                if elapsed_time > duration:
                    break
            
            # Calculate and display metrics
            if bytes_received > 0:
                kbps = (bytes_received / 1024) / elapsed_time
                fps = frames_received / elapsed_time
                print("--- Stream Metrics ---")
                print("STATUS: SUCCESS")
                print(f"Total Data: {bytes_received / 1024:.2f} KB")
                print(f"Frames Detected: {frames_received}")
                print(f"Bandwidth: {kbps:.2f} KB/s")
                print(f"Estimated Framerate: {fps:.2f} FPS")
                
                if frames_received == 0:
                    print("\nWARNING: Received data, but no complete JPEG frames were detected.")
                    print("The stream might be corrupt, or not a standard MJPEG feed.")
            else:
                print("\nFAILURE: Connection successful but 0 bytes received.")
                
    except requests.exceptions.Timeout:
        print("\nERROR: Connection timed out.")
    except Exception as e:
        print(f"\nERROR: Feed test failed. {e}")

if __name__ == "__main__":
    # Use argparse so the IP can be passed via command line instead of hardcoding
    parser = argparse.ArgumentParser(description="Test an MJPEG camera stream.")
    parser.add_argument("--url", default="http://10.0.0.251:81/stream", help="The full stream URL to test.")
    parser.add_argument("--duration", type=int, default=5, help="Seconds to run the test.")
    args = parser.parse_args()
    
    test_mjpeg_stream(args.url, args.duration)