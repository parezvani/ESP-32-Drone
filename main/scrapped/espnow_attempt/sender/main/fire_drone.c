#include <stdio.h>
#include <string.h>
#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "driver/i2c.h"

static const char *TAG = "ESP_NOW_DRONE";

// CHANGE THIS to match the bridge log
static uint8_t BRIDGE_MAC[ESP_NOW_ETH_ALEN] = { 0xA0, 0x85, 0xE3, 0x06, 0x38, 0xE8 };

// Onboard SHTC3 temp/humidity sensor on the ESP32-C3-DevKit-RUST-1
// I2C address and pins from board docs:
#define I2C_PORT_NUM       I2C_NUM_0
#define I2C_SCL_IO         GPIO_NUM_8    // SCL
#define I2C_SDA_IO         GPIO_NUM_10   // SDA
#define I2C_FREQ_HZ        100000
#define SHTC3_ADDR         0x70

// SHTC3 commands (no clock stretching, single-shot, high precision)
#define SHTC3_CMD_WAKEUP           0x3517
#define SHTC3_CMD_SLEEP            0xB098
#define SHTC3_CMD_MEASURE_TFIRST   0x7866  // measure T first, then RH (no clock stretching)

static esp_err_t i2c_master_init(void)
{
    i2c_config_t conf = {
        .mode = I2C_MODE_MASTER,
        .sda_io_num = I2C_SDA_IO,
        .scl_io_num = I2C_SCL_IO,
        .sda_pullup_en = GPIO_PULLUP_ENABLE,
        .scl_pullup_en = GPIO_PULLUP_ENABLE,
        .master.clk_speed = I2C_FREQ_HZ,
    };
    ESP_ERROR_CHECK(i2c_param_config(I2C_PORT_NUM, &conf));
    ESP_ERROR_CHECK(i2c_driver_install(I2C_PORT_NUM, conf.mode, 0, 0, 0));
    return ESP_OK;
}

static esp_err_t shtc3_write_cmd(uint16_t cmd)
{
    uint8_t buf[2] = { (uint8_t)(cmd >> 8), (uint8_t)(cmd & 0xFF) };

    i2c_cmd_handle_t handle = i2c_cmd_link_create();
    i2c_master_start(handle);
    i2c_master_write_byte(handle, (SHTC3_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write(handle, buf, 2, true);
    i2c_master_stop(handle);
    esp_err_t ret = i2c_master_cmd_begin(I2C_PORT_NUM, handle, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(handle);
    return ret;
}

// Read temperature (°C) and humidity (%RH) from SHTC3
static esp_err_t shtc3_read_temp_humidity(float *temperature_c, float *humidity_rh)
{
    esp_err_t ret;

    // Wake up sensor
    ret = shtc3_write_cmd(SHTC3_CMD_WAKEUP);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "SHTC3 wakeup failed: %s", esp_err_to_name(ret));
        return ret;
    }
    vTaskDelay(pdMS_TO_TICKS(5));

    // Trigger measurement (temperature first, then humidity)
    ret = shtc3_write_cmd(SHTC3_CMD_MEASURE_TFIRST);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "SHTC3 measure command failed: %s", esp_err_to_name(ret));
        return ret;
    }

    // Measurement time: ~12ms typical; use 30ms to be safe
    vTaskDelay(pdMS_TO_TICKS(30));

    // Read 6 bytes: T_MSB, T_LSB, T_CRC, RH_MSB, RH_LSB, RH_CRC
    uint8_t data[6] = {0};
    i2c_cmd_handle_t handle = i2c_cmd_link_create();
    i2c_master_start(handle);
    i2c_master_write_byte(handle, (SHTC3_ADDR << 1) | I2C_MASTER_READ, true);
    i2c_master_read(handle, data, 6, I2C_MASTER_LAST_NACK);
    i2c_master_stop(handle);
    ret = i2c_master_cmd_begin(I2C_PORT_NUM, handle, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(handle);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "SHTC3 read failed: %s", esp_err_to_name(ret));
        return ret;
    }

    uint16_t raw_t = ((uint16_t)data[0] << 8) | data[1];
    uint16_t raw_rh = ((uint16_t)data[3] << 8) | data[4];

    // Convert raw values to physical units (from SHTC3 datasheet)
    *temperature_c = -45.0f + 175.0f * ((float)raw_t / 65535.0f);
    *humidity_rh = 100.0f * ((float)raw_rh / 65535.0f);

    return ESP_OK;
}

static void espnow_send_cb(const esp_now_send_info_t *tx_info, esp_now_send_status_t status)
{
    const uint8_t *mac_addr = tx_info->des_addr;
    ESP_LOGI(TAG, "Send status to %02X:%02X:%02X:%02X:%02X:%02X -> %s",
             mac_addr[0], mac_addr[1], mac_addr[2],
             mac_addr[3], mac_addr[4], mac_addr[5],
             status == ESP_NOW_SEND_SUCCESS ? "SUCCESS" : "FAIL");
}

static void init_wifi_espnow_and_i2c(void)
{
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    // Initialize TCP/IP and event loop
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    // Initialize Wi-Fi in STA mode
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, mac));
    ESP_LOGI(TAG, "Drone STA MAC: %02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    // Initialize I2C for SHTC3
    ESP_ERROR_CHECK(i2c_master_init());
    ESP_LOGI(TAG, "I2C initialized for SHTC3");

    // Initialize ESP-NOW
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_send_cb(espnow_send_cb));
    ESP_LOGI(TAG, "ESP-NOW initialized");

    // Add bridge as peer
    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, BRIDGE_MAC, ESP_NOW_ETH_ALEN);
    peer.channel = 0;      // use current Wi-Fi channel
    peer.encrypt = false;  // no encryption for now

    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
    ESP_LOGI(TAG, "Bridge peer added");
}

void app_main(void)
{
    init_wifi_espnow_and_i2c();

    ESP_LOGI(TAG, "ESP-NOW drone sender running...");

    while (true) {
        // Example fire-related fields (replace with real logic later)
        bool fire_detected = true;
        float fire_distance = 120.0f;
        float fire_range = 45.0f;
        const char *drone_id = "DRONE-01";

        // Read temperature and humidity from SHTC3
        float temperature_c = 0.0f;
        float humidity_pct = 0.0f;
        esp_err_t ret = shtc3_read_temp_humidity(&temperature_c, &humidity_pct);
        if (ret == ESP_OK) {
            ESP_LOGI(TAG, "SHTC3: T=%.2f C, RH=%.2f %%", temperature_c, humidity_pct);
        } else {
            ESP_LOGW(TAG, "Using default T/RH due to read error");
            temperature_c = 25.0f;
            humidity_pct = 50.0f;
        }

        char msg[256];
        int len = snprintf(
            msg, sizeof(msg),
            "FIRE /telemetry DRONE/1.0\n"
            "Fire-Detected: %s; Fire-Distance: %.2f; Fire-Range: %.2f; "
            "Temperature: %.2f; Humidity: %.2f; Drone-ID: %s\n",
            fire_detected ? "yes" : "no",
            fire_distance,
            fire_range,
            temperature_c,
            humidity_pct,
            drone_id
        );

        if (len < 0 || len >= (int)sizeof(msg)) {
            ESP_LOGE(TAG, "Telemetry message truncated or error");
        } else {
            esp_err_t err = esp_now_send(BRIDGE_MAC, (const uint8_t *)msg, len);
            if (err == ESP_OK) {
                ESP_LOGI(TAG, "Telemetry sent: \"%.*s\"", len, msg);
            } else {
                ESP_LOGE(TAG, "Error sending telemetry: %s", esp_err_to_name(err));
            }
        }

        vTaskDelay(pdMS_TO_TICKS(5000));  // send every 5 seconds
    }
}
