#include "cloud_uplink.h"

#include "esp_log.h"
#include "sdkconfig.h"

#if CONFIG_GPS_CLOUD_ENABLED
#include "esp_http_client.h"
#endif

static const char *TAG = "cloud";

#if CONFIG_GPS_CLOUD_ENABLED
extern const char render_roots_pem_start[] asm("_binary_render_roots_pem_start");

static esp_http_client_handle_t s_client = NULL;

static esp_err_t _http_event_handler(esp_http_client_event_t *evt)
{
    switch (evt->event_id) {
    case HTTP_EVENT_ERROR:
        ESP_LOGW(TAG, "HTTP_EVENT_ERROR");
        break;
    case HTTP_EVENT_ON_CONNECTED:
        break;
    case HTTP_EVENT_ON_FINISH:
        break;
    case HTTP_EVENT_DISCONNECTED:
        break;
    default:
        break;
    }
    return ESP_OK;
}
#endif


void cloud_uplink_init(void)
{
#if CONFIG_GPS_CLOUD_ENABLED
    esp_http_client_config_t cfg = {
        .url = CONFIG_GPS_CLOUD_URL,
        .method = HTTP_METHOD_POST,
        .event_handler = _http_event_handler,
        .cert_pem = render_roots_pem_start,
        .timeout_ms = 5000,
        .keep_alive_enable = true,
    };
    s_client = esp_http_client_init(&cfg);
    if (!s_client) {
        ESP_LOGE(TAG, "esp_http_client_init failed");
        return;
    }
    esp_http_client_set_header(s_client, "Content-Type", "application/json");
    esp_http_client_set_header(s_client, "X-API-Key", CONFIG_GPS_API_KEY);
    ESP_LOGI(TAG, "cloud uplink ready -> %s", CONFIG_GPS_CLOUD_URL);
#else
    ESP_LOGI(TAG, "cloud uplink disabled at build time (CONFIG_GPS_CLOUD_ENABLED=n)");
#endif
}


int cloud_uplink_post(const char *json, size_t json_len)
{
#if CONFIG_GPS_CLOUD_ENABLED
    if (!s_client) return -1;

    esp_http_client_set_post_field(s_client, json, json_len);
    esp_err_t err = esp_http_client_perform(s_client);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "POST failed: %s", esp_err_to_name(err));
        return -2;
    }

    int status = esp_http_client_get_status_code(s_client);
    if (status < 200 || status >= 300) {
        ESP_LOGW(TAG, "cloud returned HTTP %d", status);
        return -3;
    }
    return 0;
#else
    (void)json;
    (void)json_len;
    return 0;
#endif
}
