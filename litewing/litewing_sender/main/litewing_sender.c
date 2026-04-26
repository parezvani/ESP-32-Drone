// Simple sender to test litewing communication

#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "esp_log.h"

static const char *TAG = "ESPNOW_SENDER";

static uint8_t broadcast_mac[] = {
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff
};

void send_task(void *pvParameter)
{
    while (1) {
        uint8_t data[7] = {
            'n','o','w',
            50, // yaw
            50, // thrust
            0, // pitch
            0 // roll
        };

        esp_err_t result = esp_now_send(broadcast_mac, data, sizeof(data));

        if (result == ESP_OK) {
            ESP_LOGI(TAG, "Sent command");
        } else {
            ESP_LOGE(TAG, "Send error: %s", esp_err_to_name(result));
        }

        vTaskDelay(pdMS_TO_TICKS(200));
    }
}

void app_main(void)
{
    // 1. NVS (required for WiFi)
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES ||
        ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    // 2. Network
    esp_netif_init();
    esp_event_loop_create_default();

    // 3. WiFi init
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);

    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_start();

    // MUST BE THE SAME AS RECEIVER CHANNEL
    esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);

    // 4. ESP-NOW init
    esp_now_init();

    // 5. Broadcast
    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, broadcast_mac, 6);
    peer.channel = 1;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;

    esp_now_add_peer(&peer);

    // 6. Start sender loop
    xTaskCreate(send_task, "send_task", 2048, NULL, 1, NULL);
}