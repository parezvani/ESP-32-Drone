#include "driver/uart.h"

void app_main(void) {
    uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE
    };
    uart_param_config(UART_NUM_1, &uart_config);
    uart_set_pin(UART_NUM_1, 21, 20, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE); // TX=21, RX=20
    uart_driver_install(UART_NUM_1, 1024, 0, 0, NULL, 0);

    uint8_t data[128];
    while (1) {
        int len = uart_read_bytes(UART_NUM_1, data, sizeof(data), 20 / portTICK_PERIOD_MS);
        if (len > 0) {
            printf("DATA RECEIVED: Captured %d bytes of telemetry from FC\n", len);
            // Toggle an LED here to show "Mission Link Active"
        }
    }
}