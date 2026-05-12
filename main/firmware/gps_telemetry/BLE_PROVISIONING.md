# ESP32-C3 GPS Firmware with BLE WiFi Provisioning

## Overview

This GPS telemetry firmware now supports **BLE (Bluetooth Low Energy) WiFi provisioning**, allowing you to configure WiFi credentials directly from an iOS app without needing to hardcode them during compilation.

## How It Works

### Boot Flow

1. **Firmware boots** and checks NVS flash for saved WiFi credentials
2. **If credentials found**: Uses saved credentials to connect to WiFi (skips BLE)
3. **If NO credentials found**: Starts BLE advertising as "FireFly-C3" and waits for iOS app to send credentials
4. **iOS app connects** via BLE and sends WiFi SSID + password as JSON
5. **Firmware saves** credentials to NVS flash
6. **Firmware connects** to WiFi using the new credentials
7. **BLE advertising stops** once WiFi connects successfully
8. **Future boots** use the saved credentials automatically

## Building the Firmware

### Prerequisites

Ensure your `esp-idf` environment is set up:

```bash
source $ESP_IDF_PATH/export.sh
cd /path/to/FireFly/main/firmware/gps_telemetry
```

### Build Steps

```bash
# Configure (optional, if you want to customize WiFi or other settings)
idf.py menuconfig

# Build
idf.py build

# Flash to board
idf.py -p /dev/ttyUSB0 flash monitor
```

### Serial Monitor Output

After flashing, you should see:

```
[gps] BLE provisioning initialized
[gps] Open iOS app and select 'FireFly-C3' to configure WiFi
```

If credentials were already saved:

```
[gps] Loaded WiFi credentials from NVS: SSID='MyNetwork'
[gps] connecting to SSID 'MyNetwork'
[gps] wifi got ip: 192.168.1.100
[ble_prov] BLE advertising stopped
```

## Using the iOS App

1. **Open the FireFly provisioning app** on your iPhone
2. **Tap "Scan for Arduino"** (it discovers BLE devices)
3. **Select "FireFly-C3"** from the list
4. **Enter WiFi SSID and password**
5. **Tap "Send Credentials"**
6. **Wait** for the serial monitor to show: `wifi got ip: X.X.X.X`

The credentials are now saved permanently. On next boot, the firmware connects automatically without BLE.

## Resetting Credentials

To force BLE provisioning again (forget saved credentials):

### Option 1: Erase NVS Flash

```bash
idf.py erase_flash  # Erases entire flash (includes NVS)
idf.py flash         # Reflash firmware
```

### Option 2: Selective NVS Erase

Use the following in your code (requires a special build):

```bash
# Via serial monitor command (if implemented):
# Send 'RESET_WIFI' over UART to trigger NVS clear
```

### Option 3: Edit `read_pos_data.c`

Temporarily add at the start of `app_main()`:

```c
nvs_handle_t h;
nvs_open("wifi", NVS_READWRITE, &h);
nvs_erase_all(h);
nvs_commit(h);
nvs_close(h);
```

Then recompile and flash.

## Firmware Structure

### New Files

- **`ble_provision.h`** — Header with BLE provisioning API
- **`ble_provision.c`** — BLE GATT server implementation
  - Advertises service `AB00` with characteristic `AB01`
  - Receives JSON: `{"ssid":"Network","password":"Pass"}`
  - Saves to NVS under namespace `"wifi"` with keys `"ssid"` and `"password"`

### Modified Files

- **`read_pos_data.c`** — Main application
  - Added NVS credential loading before WiFi init
  - Added BLE provisioning check on boot
  - Added periodic check for new BLE-received credentials
  - Stops BLE advertising once WiFi connects

- **`CMakeLists.txt`** — Build configuration
  - Added `ble_provision.c` to sources
  - Added `bt` component (Bluetooth stack)
  - Added `cjson` component (for JSON parsing)

## NVS Storage Format

Credentials are stored in NVS under:

- **Namespace**: `"wifi"`
- **Keys**:
  - `"ssid"` → WiFi network name (string, max 31 chars)
  - `"password"` → WiFi password (string, max 63 chars)

## JSON Payload Format

The iOS app sends credentials as:

```json
{
  "ssid": "Your WiFi Network",
  "password": "Your WiFi Password"
}
```

The payload is sent as a write operation to BLE characteristic `AB01`.

## Troubleshooting

### "BLE provisioning initialized" but iOS app doesn't see the device

- [ ] Ensure Bluetooth is enabled on your iPhone
- [ ] Restart the iOS app
- [ ] Power cycle the ESP32 and retry
- [ ] Check that the firmware compiled with BLE support (`bt` component)

### "No WiFi credentials found, starting BLE provisioning" but WiFi never connects

- [ ] Verify the SSID and password are correct in the iOS app
- [ ] Check the serial monitor for errors in credential parsing
- [ ] Try manually setting hardcoded credentials in `Kconfig` and compare

### Firmware keeps asking for BLE credentials

- [ ] Check that NVS is not full: `idf.py erase_flash && idf.py flash`
- [ ] Verify the iOS app shows `"OK"` response after sending credentials
- [ ] Check serial monitor for `"WiFi credentials saved to NVS"` message

### "esp_ble_gap_register_callback failed" during build

- [ ] Ensure you're using an ESP-IDF version that supports BLE (v4.4+)
- [ ] Run `idf.py menuconfig` and enable: **Component Config → Bluetooth → Bluetooth LE (BLE)**

## Configuration Options

Edit `Kconfig.projbuild` to customize:

```
CONFIG_GPS_DRONE_ID       # Drone identifier for broadcasts
CONFIG_GPS_UDP_PORT       # UDP port for local network broadcasts (default 4210)
CONFIG_GPS_CLOUD_ENABLED  # Enable HTTPS cloud uplink (optional)
```

## Performance Notes

- BLE advertising uses ~30 mA while waiting for credentials
- WiFi connection is established within ~5 seconds of credential receipt
- NVS write takes ~100 ms (non-blocking)
- BLE stops once WiFi connects, reducing power draw

## Security Considerations

⚠️ **This is a development/lab feature**. For production:

- [ ] Add BLE authentication (passkey or OOB pairing)
- [ ] Encrypt WiFi credentials in transit (use BLE secure connections)
- [ ] Implement rate limiting on credential attempts
- [ ] Add certificate pinning for HTTPS cloud uplink

Currently, any iOS app can provision WiFi credentials to any "FireFly-C3" device.
