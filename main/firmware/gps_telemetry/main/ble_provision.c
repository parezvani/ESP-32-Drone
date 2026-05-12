#include "ble_provision.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_nimble_hci.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "host/ble_att.h"
#include "host/ble_gatt.h"
#include "host/ble_gap.h"
#include "host/ble_hs.h"
#include "host/ble_hs_id.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

static const char *TAG = "ble_prov";

#define PROV_DEVICE_NAME        "FireFly-C3"
#define PROV_SERVICE_UUID       0xAB00
#define PROV_CHAR_UUID          0xAB01
#define PROV_MAX_JSON_LEN       160

static const ble_uuid16_t s_service_uuid = BLE_UUID16_INIT(PROV_SERVICE_UUID);
static const ble_uuid16_t s_char_uuid = BLE_UUID16_INIT(PROV_CHAR_UUID);
static volatile bool s_credentials_updated = false;
static bool s_advertising = false;
static uint8_t s_own_addr_type;

static bool parse_json_string_field(const char *json, const char *key,
                                    char *out, size_t out_size)
{
    if (!json || !key || !out || out_size == 0) {
        return false;
    }

    char pattern[64];
    int n = snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    if (n < 0 || (size_t)n >= sizeof(pattern)) {
        return false;
    }

    const char *p = strstr(json, pattern);
    if (!p) {
        return false;
    }

    p += strlen(pattern);
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') {
        p++;
    }
    if (*p != ':') {
        return false;
    }
    p++;

    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') {
        p++;
    }
    if (*p != '"') {
        return false;
    }
    p++;

    const char *start = p;
    while (*p && *p != '"') {
        if (*p == '\\' && p[1] != '\0') {
            p += 2;
            continue;
        }
        p++;
    }
    if (*p != '"') {
        return false;
    }

    size_t len = (size_t)(p - start);
    if (len >= out_size) {
        len = out_size - 1;
    }
    memcpy(out, start, len);
    out[len] = '\0';
    return len > 0;
}

static bool save_wifi_credentials(const char *ssid, const char *password)
{
    nvs_handle_t nvs_h;
    esp_err_t err = nvs_open("wifi", NVS_READWRITE, &nvs_h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open failed: %s", esp_err_to_name(err));
        return false;
    }

    err = nvs_set_str(nvs_h, "ssid", ssid);
    if (err == ESP_OK) {
        err = nvs_set_str(nvs_h, "password", password);
    }
    if (err == ESP_OK) {
        err = nvs_commit(nvs_h);
    }

    nvs_close(nvs_h);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "saving WiFi credentials failed: %s", esp_err_to_name(err));
        return false;
    }

    ESP_LOGI(TAG, "WiFi credentials saved to NVS (SSID=%s)", ssid);
    /* Log masked password length for diagnostics (do not print raw password) */
    size_t pwd_len = password ? strlen(password) : 0;
    ESP_LOGI(TAG, "Saved password length=%d (masked)", (int)pwd_len);
    s_credentials_updated = true;
    return true;
}

static int prov_access_cb(uint16_t conn_handle, uint16_t attr_handle,
                          struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    (void)conn_handle;
    (void)attr_handle;
    (void)arg;

    if (ctxt->op != BLE_GATT_ACCESS_OP_WRITE_CHR) {
        return BLE_ATT_ERR_READ_NOT_PERMITTED;
    }

    int payload_len = OS_MBUF_PKTLEN(ctxt->om);
    if (payload_len <= 0 || payload_len >= PROV_MAX_JSON_LEN) {
        ESP_LOGE(TAG, "invalid provisioning payload length: %d", payload_len);
        return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
    }

    char payload[PROV_MAX_JSON_LEN];
    if (os_mbuf_copydata(ctxt->om, 0, payload_len, payload) != 0) {
        ESP_LOGE(TAG, "failed to copy provisioning payload");
        return BLE_ATT_ERR_UNLIKELY;
    }
    payload[payload_len] = '\0';

    ESP_LOGI(TAG, "received provisioning payload: %s", payload);

    char ssid[32];
    char password[64];
    if (!parse_json_string_field(payload, "ssid", ssid, sizeof(ssid)) ||
        !parse_json_string_field(payload, "password", password, sizeof(password))) {
        ESP_LOGE(TAG, "payload missing ssid or password");
        return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
    }

    if (!save_wifi_credentials(ssid, password)) {
        return BLE_ATT_ERR_UNLIKELY;
    }

    ESP_LOGI(TAG, "provisioning accepted, stopping advertising");
    ble_gap_adv_stop();
    s_advertising = false;
    return 0;
}

static const struct ble_gatt_svc_def s_gatt_svcs[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &s_service_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = &s_char_uuid.u,
                .access_cb = prov_access_cb,
                .flags = BLE_GATT_CHR_F_WRITE | BLE_GATT_CHR_F_WRITE_NO_RSP,
            },
            {
                0,
            }
        },
    },
    {
        0,
    },
};

static void start_advertising(void)
{
    struct ble_gap_adv_params adv_params = {0};
    struct ble_hs_adv_fields fields = {0};

    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (const uint8_t *)PROV_DEVICE_NAME;
    fields.name_len = (uint8_t)strlen(PROV_DEVICE_NAME);
    fields.name_is_complete = 1;
    fields.uuids16 = (ble_uuid16_t[]){ BLE_UUID16_INIT(PROV_SERVICE_UUID) };
    fields.num_uuids16 = 1;

    int rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_gap_adv_set_fields failed: %d", rc);
        return;
    }

    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    adv_params.itvl_min = 0x0020;
    adv_params.itvl_max = 0x0040;

    rc = ble_gap_adv_start(s_own_addr_type, NULL, BLE_HS_FOREVER,
                           &adv_params, NULL, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_gap_adv_start failed: %d", rc);
        return;
    }

    s_advertising = true;
    ESP_LOGI(TAG, "BLE advertising started as %s", PROV_DEVICE_NAME);
}

static void ble_app_on_reset(int reason)
{
    ESP_LOGE(TAG, "BLE reset reason=%d", reason);
    s_advertising = false;
}

static void ble_app_on_sync(void)
{
    int rc = ble_hs_id_infer_auto(0, &s_own_addr_type);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_hs_id_infer_auto failed: %d", rc);
        return;
    }

    start_advertising();
}

static void ble_host_task(void *param)
{
    (void)param;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

esp_err_t ble_provision_init(void)
{
    nimble_port_init();

    ble_hs_cfg.reset_cb = ble_app_on_reset;
    ble_hs_cfg.sync_cb = ble_app_on_sync;
    ble_hs_cfg.gatts_register_cb = NULL;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

    ble_svc_gap_init();
    ble_svc_gatt_init();

    int rc = ble_gatts_count_cfg(s_gatt_svcs);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_gatts_count_cfg failed: %d", rc);
        return ESP_FAIL;
    }

    rc = ble_gatts_add_svcs(s_gatt_svcs);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_gatts_add_svcs failed: %d", rc);
        return ESP_FAIL;
    }

    nimble_port_freertos_init(ble_host_task);
    ESP_LOGI(TAG, "BLE provisioning initialized");
    return ESP_OK;
}

void ble_provision_stop(void)
{
    if (!s_advertising) {
        return;
    }

    int rc = ble_gap_adv_stop();
    if (rc != 0) {
        ESP_LOGW(TAG, "ble_gap_adv_stop returned %d", rc);
    }
    s_advertising = false;
}

bool ble_provision_credentials_updated(void)
{
    return s_credentials_updated;
}
