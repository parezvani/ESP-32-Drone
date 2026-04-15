#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/gpio.h"

// Define your UART pins based on our wiring
#define TXD_PIN (GPIO_NUM_21)
#define RXD_PIN (GPIO_NUM_20)
#define UART_PORT_NUM UART_NUM_1

// Neutral RC Channels: Roll, Pitch, Yaw at 1500; Throttle at 1000
uint16_t rc_channels[8] = {1500, 1500, 1500, 1000, 1000, 1000, 1000, 1000};

void init_uart() {
    const uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    uart_driver_install(UART_PORT_NUM, 1024 * 2, 0, 0, NULL, 0);
    uart_param_config(UART_PORT_NUM, &uart_config);
    uart_set_pin(UART_PORT_NUM, TXD_PIN, RXD_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
}

void send_msp_rc_command() {
    uint8_t msp_packet[22];
    uint8_t checksum = 0;
    
    // MSP Header
    msp_packet[0] = '$'; msp_packet[1] = 'M'; msp_packet[2] = '<';
    msp_packet[3] = 16;  // Payload size (8 channels * 2 bytes)
    msp_packet[4] = 200; // Command ID (MSP_SET_RAW_RC)
    
    checksum ^= msp_packet[3];
    checksum ^= msp_packet[4];

    // Payload
    int index = 5;
    for (int i = 0; i < 8; i++) {
        msp_packet[index] = rc_channels[i] & 0xFF;
        checksum ^= msp_packet[index++];
        msp_packet[index] = (rc_channels[i] >> 8) & 0xFF;
        checksum ^= msp_packet[index++];
    }

    // Checksum
    msp_packet[index] = checksum;

    // Send packet
    uart_write_bytes(UART_PORT_NUM, (const char*)msp_packet, sizeof(msp_packet));
}

void app_main(void) {
    init_uart();
    
    while (1) {
        send_msp_rc_command();
        // Send command ~50 times a second (20ms delay)
        vTaskDelay(20 / portTICK_PERIOD_MS); 
    }
}