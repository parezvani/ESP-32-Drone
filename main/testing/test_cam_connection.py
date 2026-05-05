import requests
import sys

# Replace with your actual camera IP
CAMERA_URL = "http://10.0.0.XXX" 

def main():
    print("Testing Camera Connection...")
    try:
        response = requests.get(CAMERA_URL, timeout=5)
        if response.status_code == 200:
            print(f"SUCCESS: Camera at {CAMERA_URL} is reachable.")
            print(f"Server Header: {response.headers.get('Server', 'Unknown')}")
        else:
            print(f"FAILURE: Camera responded with status code {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not connect to camera. {e}")

if __name__ == "__main__":
    main()