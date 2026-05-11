# FireFLY iOS Provisioning App

This SwiftUI app is the phone-side prototype for sending WiFi credentials to the FireFLY Arduino/ESP32 controller over BLE.

## Demo Flow

1. Enter the WiFi SSID and password.
2. Tap **Restore Saved Credentials** if the credentials were saved during a previous run.
3. Tap **Scan for Arduino**.
4. Select the advertised Arduino/ESP32 device.
5. Tap **Send Credentials**.

## BLE Contract

The app currently matches the prototype BLE service already present in `main/scrapped/nrf.c`:

- Provisioning service: `AB00`
- Combined credential characteristic: `AB01`

For `AB01`, the app writes a UTF-8 JSON payload followed by a newline:

```json
{"ssid":"Network Name","password":"Network Password"}
```

The app also supports a split-characteristic firmware variant:

- SSID characteristic: `AB02`
- Password characteristic: `AB03`
- Optional command characteristic: `AB04`, written with `CONNECT`

If the professor's Arduino implementation uses different UUIDs, update the constants in `FireFLY/ProvisioningBLEManager.swift`.
