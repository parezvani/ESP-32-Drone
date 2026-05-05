#pragma once

#include <stddef.h>

/* Initialize the HTTPS client. Call once after WiFi is connected. */
void cloud_uplink_init(void);

/* POST a JSON payload to the configured cloud endpoint with the X-API-Key
 * header. Non-blocking-ish (TLS handshake on first call may take 1-2 sec).
 * Returns 0 on success, negative on error. Safe to call when CONFIG_GPS_CLOUD_ENABLED
 * is disabled — becomes a no-op. */
int cloud_uplink_post(const char *json, size_t json_len);
