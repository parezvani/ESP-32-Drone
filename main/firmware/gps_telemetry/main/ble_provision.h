#pragma once

#include <stdbool.h>

#include "esp_err.h"

/**
 * Initialize BLE provisioning server.
 * - Advertises as "FireFly-C3" 
 * - Exposes service AB00 with characteristic AB01 for provisioning credentials
 * - Characteristic accepts JSON: {"ssid":"Your Network","password":"Your Password","api_key":"Your API Key"}
 * - Saves credentials to NVS namespace "wifi" and stops advertising when received
 */
esp_err_t ble_provision_init(void);

/**
 * Stop BLE advertising (called after WiFi successfully connects).
 */
void ble_provision_stop(void);

/**
 * Check if provisioning credentials were just received via BLE.
 * Returns true if new credentials were written; caller should call wifi_init_sta() again.
 */
bool ble_provision_credentials_updated(void);
