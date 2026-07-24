#ifndef TC375_BOARD_CONFIG_H
#define TC375_BOARD_CONFIG_H

/*
 * Board-level serial configuration.
 *
 * The default mapping is the common ASCLIN0 virtual-COM mapping used by many
 * TC3xx evaluation boards:
 *   MCU P14.0 (TX) -> USB-UART RX
 *   MCU P14.1 (RX) <- USB-UART TX
 *
 * Override these macros for a custom board. TX/RX must belong to the selected
 * ASCLIN instance and both sides must share a ground.
 */
#ifndef TC375_BOARD_UART_ENABLED
#define TC375_BOARD_UART_ENABLED             (1)
#endif

#ifndef TC375_BOARD_UART_MODULE
#define TC375_BOARD_UART_MODULE              MODULE_ASCLIN0
#endif

#ifndef TC375_BOARD_UART_RX_PIN
#define TC375_BOARD_UART_RX_PIN              IfxAsclin0_RXA_P14_1_IN
#endif

#ifndef TC375_BOARD_UART_TX_PIN
#define TC375_BOARD_UART_TX_PIN              IfxAsclin0_TX_P14_0_OUT
#endif

#ifndef TC375_BOARD_UART_BAUDRATE
#define TC375_BOARD_UART_BAUDRATE            (115200U)
#endif

#ifndef TC375_BOARD_UART_RX_BUFFER_SIZE
#define TC375_BOARD_UART_RX_BUFFER_SIZE      (4096U)
#endif

#ifndef TC375_BOARD_UART_TX_BUFFER_SIZE
#define TC375_BOARD_UART_TX_BUFFER_SIZE      (4096U)
#endif

/*
 * UART interrupts stay below the motor PWM interrupt (priority 20). They do
 * not call FreeRTOS APIs, so they are also valid in the cooperative runtime.
 */
#ifndef TC375_BOARD_UART_TX_ISR_PRIORITY
#define TC375_BOARD_UART_TX_ISR_PRIORITY     (8)
#endif

#ifndef TC375_BOARD_UART_RX_ISR_PRIORITY
#define TC375_BOARD_UART_RX_ISR_PRIORITY     (9)
#endif

#ifndef TC375_BOARD_UART_ERR_ISR_PRIORITY
#define TC375_BOARD_UART_ERR_ISR_PRIORITY    (10)
#endif

#endif
