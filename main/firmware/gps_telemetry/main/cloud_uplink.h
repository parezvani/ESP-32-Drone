#pragma once

#include <stddef.h>

#define GPS_API_KEY_MAX_LEN 192

/* Initialize the HTTPS client with the BLE-provisioned API key. */
void cloud_uplink_init(const char *api_key);

/* POST a JSON payload to the configured cloud endpoint with the provisioned
 * X-API-Key header. Non-blocking-ish (TLS handshake on first call may take 1-2 sec).
 * Returns 0 on success, negative on error. Safe to call when CONFIG_GPS_CLOUD_ENABLED
 * is disabled — becomes a no-op. */
int cloud_uplink_post(const char *json, size_t json_len);
