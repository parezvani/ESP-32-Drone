# FireFLY iOS Provisioning App

This SwiftUI app is the phone-side prototype for sending WiFi credentials and the drone API key to the FireFLY ESP32 controller over BLE.

## Demo Flow

1. Enter the WiFi SSID, password, and drone API key.
2. Tap **Restore Saved Credentials** if the credentials were saved during a previous run.
3. Tap **Scan for Arduino**.
4. Select the advertised ESP32 device.
5. Tap **Send Credentials**.

## BLE Contract

The app currently matches the prototype BLE service already present in `main/scrapped/nrf.c`:

- Provisioning service: `AB00`
- Combined credential characteristic: `AB01`

For `AB01`, the app writes a UTF-8 JSON payload followed by a newline:

```json
{"ssid":"Network Name","password":"Network Password","api_key":"Drone API Key"}
```

The current firmware requires the combined `AB01` payload so the API key can be provisioned with the WiFi credentials. Older split-characteristic firmware variants only support WiFi fields:

- SSID characteristic: `AB02`
- Password characteristic: `AB03`
- Optional command characteristic: `AB04`, written with `CONNECT`

If the professor's implementation uses different UUIDs, update the constants in `FireFLY/ProvisioningBLEManager.swift`.
