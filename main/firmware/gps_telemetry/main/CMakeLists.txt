idf_component_register(SRCS "read_pos_data.c" "cloud_uplink.c" "ble_provision.c"
                       INCLUDE_DIRS "."
                       REQUIRES nvs_flash esp_wifi esp_netif esp_event lwip
                                esp_driver_uart esp_http_client esp-tls
                                bt
                       EMBED_TXTFILES "render_roots.pem")
