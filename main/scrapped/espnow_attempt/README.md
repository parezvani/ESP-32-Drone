FIRE_SERVER:
------------------------------------------------------------------------------------------------------------------------------------------
Sends message using cargo/rust. 
If you want to test this out on your own you can download the "fire_server" directory. 

Open two instances of Ubuntu:
- On one run "cargo run --bin fire_server", 
- On the other run "cargo run --bin fire_server"

Send message from drone to server in the following format:
- Request Line: FIRE /telemetry DRONE/1.0\n
- Telemetry Line: Fire-Detected: yes; Fire-Distance: 120; Fire-Range: 45; Temperature: 63.4; Humidity: 21.5; Drone-ID: DRONE-01\n

Full Payload:
FIRE /telemetry DRONE/1.0\nFire-Detected: yes; Fire-Distance: 120; Fire-Range: 45; Temperature: 63.4; Humidity: 21.5; Drone-ID: DRONE-01\n

------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------




ESPNOW DIRECTORIES:
------------------------------------------------------------------------------------------------------------------------------------------
Sends messages between two ESP32c3-devkit-Rust-1 microcontrollers
Uses ESP-IDF

Build and flash fire_bridge on base station esp

Build and flash fire_drone on drone esp

Currently takes temperature and humidity readings from onboard drone ESP IMU and sends them to the base server ESP through ESP-NOW

Same payload construction as fire_server:
FIRE /telemetry DRONE/1.0\nFire-Detected: yes; Fire-Distance: 120; Fire-Range: 45; Temperature: 63.4; Humidity: 21.5; Drone-ID: DRONE-01\n



LITEWING ESPNOW TELEMETRY/COMMAND TEST:
------------------------------------------------------------------------------------------------------------------------------------------
The LiteWing firmware now broadcasts compact JSON telemetry over native ESP-NOW on the configured Wi-Fi channel, default channel 6.
It also receives compact LiteWing command packets and legacy 7-byte "now" joystick packets. Command packets are converted into the
existing CRTP RPYT commander path.

Base-station test app:
- `main/base-server/espnow_drone_base_server/` receives telemetry and prints it over USB serial.
- The same app broadcasts a safe command stream every 250 ms: disarm + zero thrust.
- This bridge is for communication testing, not flight, because it intentionally keeps the drone disarmed.
- Keep `ESPNOW_CHANNEL` in `fire_bridge.c` matched to LiteWing `CONFIG_WIFI_CHANNEL`.

Build/flash LiteWing drone firmware:
- `. ./esp/esp-idf/export.sh`
- `cd litewing/LiteWing`
- `idf.py set-target esp32s3`
- `idf.py build flash monitor`

Build/flash the base-station ESP32-C3:
- `. ./esp/esp-idf/export.sh`
- `cd main/base-server/espnow_drone_base_server`
- `idf.py set-target esp32c3`
- `idf.py build flash monitor`

Expected result:
- The base station logs JSON lines beginning with `{"type":"telemetry",...}`.
- The LiteWing monitor logs ESP-NOW initialization on the same channel.
- The base station periodically logs `Safe command stream active: disarm + zero thrust` after telemetry is seen.
