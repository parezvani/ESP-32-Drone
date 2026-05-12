#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <sys/time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "lwip/sockets.h"

#include "cloud_uplink.h"
#include "ble_provision.h"

#define GPS_UART_NUM   UART_NUM_1
#define GPS_TX_PIN     5
#define GPS_RX_PIN     4
#define GPS_BAUD_RATE  9600
#define UART_BUF_SIZE  1024
#define GPS_LINE_MAX   128

static const char *TAG = "gps";

static EventGroupHandle_t s_wifi_events;
#define WIFI_CONNECTED_BIT BIT0

static int s_udp_sock = -1;
static struct sockaddr_in s_bcast_addr;

static bool s_ble_provisioning_active = false;
static bool s_wifi_connected = false;

static void wifi_event_handler(void *arg, esp_event_base_t base,
                               int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        s_wifi_connected = false;
        xEventGroupClearBits(s_wifi_events, WIFI_CONNECTED_BIT);
        wifi_event_sta_disconnected_t *evt = (wifi_event_sta_disconnected_t *)data;
        int reason = evt ? evt->reason : -1;
        ESP_LOGW(TAG, "wifi disconnected (reason=%d), retrying in 1s", reason);
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "wifi got ip: " IPSTR, IP2STR(&ev->ip_info.ip));
        s_wifi_connected = true;
        xEventGroupSetBits(s_wifi_events, WIFI_CONNECTED_BIT);
        
        /* Stop BLE provisioning once WiFi is connected */
        if (s_ble_provisioning_active) {
            ble_provision_stop();
            s_ble_provisioning_active = false;
            ESP_LOGI(TAG, "BLE provisioning stopped");
        }
    }
}

static void wifi_init_sta(void)
{
    s_wifi_events = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    esp_err_t _evt_err = esp_event_loop_create_default();
    if (_evt_err != ESP_OK && _evt_err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(_evt_err);
    }
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    /* Try to load WiFi credentials from NVS first (set via BLE provisioning) */
    char ssid[32] = {0};
    char password[64] = {0};
    size_t ssid_len = sizeof(ssid) - 1;
    size_t pwd_len = sizeof(password) - 1;

    nvs_handle_t nvs_h;
    esp_err_t err = nvs_open("wifi", NVS_READONLY, &nvs_h);
    if (err == ESP_OK) {
        esp_err_t ssid_err = nvs_get_str(nvs_h, "ssid", ssid, &ssid_len);
        esp_err_t pwd_err = nvs_get_str(nvs_h, "password", password, &pwd_len);
        ESP_LOGI(TAG, "NVS read results: ssid_err=%s pwd_err=%s (ssid_len=%d pwd_len=%d)",
                 esp_err_to_name(ssid_err), esp_err_to_name(pwd_err), (int)ssid_len, (int)pwd_len);
        nvs_close(nvs_h);

        if (ssid_err == ESP_OK && pwd_err == ESP_OK) {
            ESP_LOGI(TAG, "Loaded WiFi credentials from NVS: SSID='%s' (len=%d), password_len=%d",
                     ssid, (int)ssid_len, (int)pwd_len);
        } else {
            /* Fall back to hardcoded credentials from Kconfig */
            strncpy(ssid, CONFIG_GPS_WIFI_SSID, sizeof(ssid) - 1);
            strncpy(password, CONFIG_GPS_WIFI_PASSWORD, sizeof(password) - 1);
            ESP_LOGI(TAG, "Using hardcoded WiFi credentials: SSID='%s'", ssid);
        }
    } else {
        /* Fall back to hardcoded credentials */
        strncpy(ssid, CONFIG_GPS_WIFI_SSID, sizeof(ssid) - 1);
        strncpy(password, CONFIG_GPS_WIFI_PASSWORD, sizeof(password) - 1);
        ESP_LOGI(TAG, "Using hardcoded WiFi credentials: SSID='%s'", ssid);
    }

    wifi_config_t wc = {
        .sta = {
            .ssid     = {0},
            .password = {0},
        },
    };
    strncpy((char *)wc.sta.ssid, ssid, sizeof(wc.sta.ssid) - 1);
    strncpy((char *)wc.sta.password, password, sizeof(wc.sta.password) - 1);
    
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));

    ESP_LOGI(TAG, "connecting to SSID '%s'", ssid);
}

static void udp_init(void)
{
    s_udp_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s_udp_sock < 0) {
        ESP_LOGE(TAG, "socket failed: errno %d", errno);
        return;
    }

    int one = 1;
    setsockopt(s_udp_sock, SOL_SOCKET, SO_BROADCAST, &one, sizeof(one));

    memset(&s_bcast_addr, 0, sizeof(s_bcast_addr));
    s_bcast_addr.sin_family = AF_INET;
    s_bcast_addr.sin_port = htons(CONFIG_GPS_UDP_PORT);
    s_bcast_addr.sin_addr.s_addr = htonl(INADDR_BROADCAST);
}

static double nmea_to_deg(const char *nmea, const char *hemi)
{
    const char *dot = strchr(nmea, '.');
    if (!dot || dot - nmea < 3) return 0.0;
    int whole = atoi(nmea);
    double minutes = atof(dot - 2);
    double deg = (whole / 100) + (minutes / 60.0);
    if (hemi[0] == 'S' || hemi[0] == 'W') deg = -deg;
    return deg;
}

#define DRONE_ID CONFIG_GPS_DRONE_ID

#define HEADING_MIN_MOVEMENT_M 1.0  // ignore GPS jitter when stationary

static uint32_t seq_num = 0;
static double prev_lat = 0.0, prev_lon = 0.0;
static double last_heading_deg = 0.0;
static bool has_prev = false;

static double compute_heading(double lat, double lon)
{
    if (!has_prev) {
        prev_lat = lat;
        prev_lon = lon;
        has_prev = true;
        return last_heading_deg;
    }

    double lat_rad = prev_lat * M_PI / 180.0;
    double dy_m = (lat - prev_lat) * 111320.0;
    double dx_m = (lon - prev_lon) * 111320.0 * cos(lat_rad);
    double moved_m = sqrt(dx_m * dx_m + dy_m * dy_m);

    if (moved_m < HEADING_MIN_MOVEMENT_M) {
        return last_heading_deg;
    }

    double heading = atan2(dx_m, dy_m) * 180.0 / M_PI;
    if (heading < 0) heading += 360.0;

    prev_lat = lat;
    prev_lon = lon;
    last_heading_deg = heading;
    return heading;
}

static void broadcast_fix(double lat, double lon, double alt,
                          int sats, double hdop)
{
    if (s_udp_sock < 0) return;
    if (!(xEventGroupGetBits(s_wifi_events) & WIFI_CONNECTED_BIT)) return;

    struct timeval tv;
    gettimeofday(&tv, NULL);
    long long ms = (long long)tv.tv_sec * 1000LL + tv.tv_usec / 1000;

    seq_num++;

    double heading = compute_heading(lat, lon);

    char json[256];

    int len = snprintf(json, sizeof(json),
        "{\"id\":\"%s\",\"seq\":%lu,\"lat\":%.7f,\"lon\":%.7f,\"alt_m\":%.1f,\"heading_deg\":%.1f,\"fire_detected\":false,\"sats\":%d,\"hdop\":%.2f,\"ts_ms\":%lld}",
        DRONE_ID, seq_num, lat, lon, alt, heading, sats, hdop, ms);

    int sent = sendto(s_udp_sock, json, len, 0,
                      (struct sockaddr *)&s_bcast_addr, sizeof(s_bcast_addr));
    if (sent < 0) {
        ESP_LOGW(TAG, "sendto failed: errno %d", errno);
    }

    cloud_uplink_post(json, (size_t)len);
}

static void parse_gga(const char *line)
{
    char copy[GPS_LINE_MAX];
    strncpy(copy, line, sizeof(copy) - 1);
    copy[sizeof(copy) - 1] = '\0';

    char *f[16] = {0};
    int n = 0;
    char *p = copy;
    f[n++] = p;
    while (*p && n < 16) {
        if (*p == ',') { *p = '\0'; f[n++] = p + 1; }
        p++;
    }
    if (n < 10) return;

    const char *fix = f[6];
    if (fix[0] == '0' || fix[0] == '\0') {
        ESP_LOGW(TAG, "no fix (sats=%s)", f[7][0] ? f[7] : "0");
        return;
    }

    double lat  = nmea_to_deg(f[2], f[3]);
    double lon  = nmea_to_deg(f[4], f[5]);
    int    sats = atoi(f[7]);
    double hdop = atof(f[8]);
    double alt  = atof(f[9]);

    ESP_LOGI(TAG, "FIX lat=%.7f lon=%.7f alt=%.1fm sats=%d hdop=%.2f",
             lat, lon, alt, sats, hdop);

    broadcast_fix(lat, lon, alt, sats, hdop);
}

void app_main(void)
{
    /* TEST ACTION: erase NVS on boot to clear stored WiFi credentials */
    ESP_LOGW(TAG, "TEST: erasing NVS partition to clear credentials");
    esp_err_t _erase_ret = nvs_flash_erase();
    if (_erase_ret != ESP_OK) {
        ESP_LOGW(TAG, "nvs_flash_erase returned %s", esp_err_to_name(_erase_ret));
    }

    esp_err_t nvs = nvs_flash_init();
    if (nvs == ESP_ERR_NVS_NO_FREE_PAGES || nvs == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    /* Check if WiFi credentials exist; if not, start BLE provisioning */
    char ssid[32] = {0};
    size_t ssid_len = sizeof(ssid) - 1;
    nvs_handle_t nvs_h;
    esp_err_t err = nvs_open("wifi", NVS_READONLY, &nvs_h);
    bool has_credentials = false;
    if (err == ESP_OK) {
        if (nvs_get_str(nvs_h, "ssid", ssid, &ssid_len) == ESP_OK && ssid_len > 0) {
            has_credentials = true;
        }
        nvs_close(nvs_h);
    }

    if (!has_credentials) {
        ESP_LOGI(TAG, "No WiFi credentials found, starting BLE provisioning");
        ESP_ERROR_CHECK(ble_provision_init());
        s_ble_provisioning_active = true;
        ESP_LOGI(TAG, "Open iOS app and select 'FireFly-C3' to configure WiFi");

        while (!ble_provision_credentials_updated()) {
            vTaskDelay(pdMS_TO_TICKS(250));
        }

        ESP_LOGI(TAG, "BLE provisioning complete, starting WiFi");
    }

    wifi_init_sta();
    udp_init();
    cloud_uplink_init();

    uart_config_t cfg = {
        .baud_rate  = GPS_BAUD_RATE,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(GPS_UART_NUM, UART_BUF_SIZE * 2, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(GPS_UART_NUM, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(GPS_UART_NUM, GPS_TX_PIN, GPS_RX_PIN,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    ESP_LOGI(TAG, "started on UART%d, RX=GPIO%d TX=GPIO%d @ %d baud",
             GPS_UART_NUM, GPS_RX_PIN, GPS_TX_PIN, GPS_BAUD_RATE);

    char line[GPS_LINE_MAX];
    int line_len = 0;
    uint8_t buf[128];

    int bytes_since_log = 0;
    TickType_t last_log = xTaskGetTickCount();
    TickType_t last_ble_check = xTaskGetTickCount();

    while (1) {
        int n = uart_read_bytes(GPS_UART_NUM, buf, sizeof(buf), pdMS_TO_TICKS(200));
        bytes_since_log += n;

        /* Periodically check if new BLE credentials were received */
        TickType_t now = xTaskGetTickCount();
        if (s_ble_provisioning_active && (now - last_ble_check) * portTICK_PERIOD_MS >= 1000) {
            if (ble_provision_credentials_updated()) {
                ESP_LOGI(TAG, "New WiFi credentials received via BLE, reconnecting WiFi");
                esp_wifi_disconnect();
                s_ble_provisioning_active = false;
                vTaskDelay(pdMS_TO_TICKS(500));
                /* Re-read credentials and reconnect */
                wifi_init_sta();
            }
            last_ble_check = now;
        }

        if ((now - last_log) * portTICK_PERIOD_MS >= 3000) {
            if (bytes_since_log == 0) {
                ESP_LOGW(TAG, "no UART data in 3s — check GPS power / GND / RX wiring (ESP RX=GPIO%d must connect to GPS TX)", GPS_RX_PIN);
            } else {
                ESP_LOGI(TAG, "heartbeat: %d bytes in last 3s", bytes_since_log);
            }
            bytes_since_log = 0;
            last_log = now;
        }

        for (int i = 0; i < n; i++) {
            char c = (char)buf[i];
            if (c == '\n' || c == '\r') {
                if (line_len > 0) {
                    line[line_len] = '\0';
                    printf("%s\n", line);
                    if (strncmp(line, "$GPGGA", 6) == 0 ||
                        strncmp(line, "$GNGGA", 6) == 0) {
                        parse_gga(line);
                    }
                    line_len = 0;
                }
            } else if (line_len < GPS_LINE_MAX - 1) {
                line[line_len++] = c;
            } else {
                line_len = 0;
            }
        }
    }
}