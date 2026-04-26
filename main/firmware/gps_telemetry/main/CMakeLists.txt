idf_component_register(SRCS "read_pos_data.c"
                       INCLUDE_DIRS "."
                       REQUIRES nvs_flash esp_wifi esp_netif esp_event lwip esp_driver_uart)
