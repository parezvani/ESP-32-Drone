#include "driver/uart.h"

// IRC Tramp Command for 5917MHz (Raceband 8)
uint8_t set_freq_cmd[] = {
    0x0F, // Start Byte
    0x46, // 'F' for Frequency command
    0x7D, // LSB of 5917
    0x17, // MSB of 5917
    0x00, 0x00, 0x00, 0x00, // Padding
    0x6D  // Checksum (Calculated)
};

void broadcast_config() {
    // Configure UART (Assuming UART1 on ESP32-C3)
    uart_write_bytes(UART_NUM_1, (const char*)set_freq_cmd, sizeof(set_freq_cmd));
}