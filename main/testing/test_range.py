import socket
import json
import time

UDP_PORT = 4210
TIMEOUT_SECONDS = 3.0

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.settimeout(TIMEOUT_SECONDS)
    
    print(f"Listening for GPS telemetry on UDP port {UDP_PORT}...")
    
    expected_seq = None
    packets_received = 0
    packets_dropped = 0
    start_time = time.time()

    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                msg = json.loads(data.decode("utf-8"))
                
                current_seq = msg.get("seq")
                if current_seq is None:
                    continue
                
                if expected_seq is not None:
                    # If the current sequence is higher than expected, we dropped packets
                    if current_seq > expected_seq:
                        dropped_this_time = current_seq - expected_seq
                        packets_dropped += dropped_this_time
                        print(f"⚠️ Dropped {dropped_this_time} packet(s)!")
                
                packets_received += 1
                expected_seq = current_seq + 1
                
                # Calculate metrics
                total_expected = packets_received + packets_dropped
                drop_rate = (packets_dropped / total_expected) * 100 if total_expected > 0 else 0
                elapsed = time.time() - start_time
                
                print(f"Received: {packets_received} | Dropped: {packets_dropped} | Drop Rate: {drop_rate:.2f}% | Uptime: {elapsed:.1f}s")
                
            except socket.timeout:
                print("⏳ Timeout: No packets received for 3 seconds. Out of range?")
            except json.JSONDecodeError:
                print("❌ Received malformed JSON.")

    except KeyboardInterrupt:
        print("\n--- Final Test Results ---")
        print(f"Total Packets Received: {packets_received}")
        print(f"Total Packets Dropped:  {packets_dropped}")
        if (packets_received + packets_dropped) > 0:
            print(f"Final Drop Rate:        {(packets_dropped / (packets_received + packets_dropped)) * 100:.2f}%")

if __name__ == "__main__":
    main()