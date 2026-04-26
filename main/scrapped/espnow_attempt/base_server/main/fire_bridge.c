// ESP-IDF bridge for ESP32-C3:
// Receives LiteWing ESP-NOW telemetry and sends safe test commands.

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "nvs_flash.h"

#include "driver/uart.h"

static const char *TAG = "ESP_NOW_BRIDGE";

#define ESPNOW_CHANNEL 6
#define LITEWING_ESPNOW_VERSION 1
#define LITEWING_COMMAND_MAGIC "LWCM"
#define LITEWING_COMMAND_FLAG_DISARM (1u << 1)

static const uint8_t BROADCAST_MAC[ESP_NOW_ETH_ALEN] = {
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff
};

typedef struct __attribute__((packed)) {
    char magic[4];
    uint8_t version;
    uint8_t flags;
    uint16_t sequence;
    int16_t roll_cdeg;
    int16_t pitch_cdeg;
    int16_t yaw_rate_cdeg_s;
    uint16_t thrust;
} litewing_command_packet_t;

static volatile bool telemetry_seen = false;

static void espnow_recv_cb(const esp_now_recv_info_t *recv_info,
    const uint8_t *data, int len)
{
    char buf[300];
    int copy_len = (len < (int)sizeof(buf) - 1) ? len : (int)sizeof(buf) - 1;
    memcpy(buf, data, copy_len);
    buf[copy_len] = '\0';

    telemetry_seen = true;

    const uint8_t *src = recv_info->src_addr;
    int rssi = recv_info->rx_ctrl ? recv_info->rx_ctrl->rssi : 0;

    ESP_LOGI(TAG, "RX %d bytes from %02X:%02X:%02X:%02X:%02X:%02X RSSI=%d",
             len, src[0], src[1], src[2], src[3], src[4], src[5], rssi);

    if (copy_len > 0 && buf[0] == '{') {
        ESP_LOGI(TAG, "%s", buf);
        return;
    }

    ESP_LOGI(TAG, "-----------------------------");

    char *req_line = buf;
    char *telemetry_line = strchr(buf, '\n');
    if (telemetry_line) {
        *telemetry_line = '\0';
        telemetry_line++;
    }

    if (!telemetry_line || *telemetry_line == '\0') {
        telemetry_line = req_line;
        req_line = NULL;
    }

    if (req_line) {
        ESP_LOGI(TAG, "%s", req_line);
    }

    char *saveptr = NULL;
    char *field = strtok_r(telemetry_line, ";", &saveptr);
    while (field) {
        while (*field == ' ') field++;
        if (*field != '\0') {
            ESP_LOGI(TAG, "%s", field);
        }
        field = strtok_r(NULL, ";", &saveptr);
    }

    ESP_LOGI(TAG, "");
}

static void espnow_send_cb(const uint8_t *mac_addr, esp_now_send_status_t status)
{
    ESP_LOGD(TAG, "TX to %02X:%02X:%02X:%02X:%02X:%02X -> %s",
             mac_addr[0], mac_addr[1], mac_addr[2],
             mac_addr[3], mac_addr[4], mac_addr[5],
             status == ESP_NOW_SEND_SUCCESS ? "OK" : "FAIL");
}

static void add_broadcast_peer(void)
{
    if (esp_now_is_peer_exist(BROADCAST_MAC)) {
        return;
    }

    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, BROADCAST_MAC, sizeof(peer.peer_addr));
    peer.channel = ESPNOW_CHANNEL;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;

    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
}

static void command_tx_task(void *arg)
{
    (void)arg;
    uint16_t sequence = 0;

    while (true) {
        litewing_command_packet_t command = {
            .magic = LITEWING_COMMAND_MAGIC,
            .version = LITEWING_ESPNOW_VERSION,
            .flags = LITEWING_COMMAND_FLAG_DISARM,
            .sequence = sequence++,
            .roll_cdeg = 0,
            .pitch_cdeg = 0,
            .yaw_rate_cdeg_s = 0,
            .thrust = 0,
        };

        esp_err_t err = esp_now_send(BROADCAST_MAC, (const uint8_t *)&command, sizeof(command));
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Command send failed: %s", esp_err_to_name(err));
        } else if (telemetry_seen && (sequence % 20) == 0) {
            ESP_LOGI(TAG, "Safe command stream active: disarm + zero thrust");
        }

        vTaskDelay(pdMS_TO_TICKS(250));
    }
}

static void init_uart(void)
{
    const uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &uart_config));
    // On ESP32-C3 devkits, UART0 is already mapped to USB serial, no pins to set
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0));
}

static void init_wifi_espnow(void)
{
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    // Initialize the underlying TCP/IP stack & event loop
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    // Wi-Fi init
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE));

    // Print MAC address (STA interface)
    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, mac));
    ESP_LOGI(TAG, "Bridge STA MAC: %02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    // Initialize ESP-NOW
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_recv_cb(espnow_recv_cb));
    ESP_ERROR_CHECK(esp_now_register_send_cb(espnow_send_cb));
    add_broadcast_peer();
    ESP_LOGI(TAG, "ESP-NOW initialized on channel %d", ESPNOW_CHANNEL);
}

void app_main(void)
{
    init_uart();
    init_wifi_espnow();

    ESP_LOGI(TAG, "ESP-NOW bridge running...");
    xTaskCreate(command_tx_task, "command_tx", 3072, NULL, 4, NULL);

    // Nothing else to do; ESP-NOW callbacks handle traffic
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
