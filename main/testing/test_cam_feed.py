import requests
import time

# Replace with your actual stream endpoint (usually /stream or :81/stream)
STREAM_URL = "http://10.0.0.XXX:81/stream"

def main():
    print(f"Testing Camera Feed at {STREAM_URL}...")
    try:
        # Stream=True allows reading the raw byte stream without loading into memory
        with requests.get(STREAM_URL, stream=True, timeout=10) as r:
            r.raise_for_status()
            print("Connection established. Analyzing stream data...")
            
            start_time = time.time()
            bytes_received = 0
            
            # Check the first 5 seconds of the stream
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    bytes_received += len(chunk)
                
                if time.time() - start_time > 5:
                    break
            
            if bytes_received > 0:
                print(f"SUCCESS: Received {bytes_received} bytes of video data.")
            else:
                print("FAILURE: Connection successful but 0 bytes received.")
                
    except Exception as e:
        print(f"ERROR: Feed test failed. {e}")

if __name__ == "__main__":
    main()