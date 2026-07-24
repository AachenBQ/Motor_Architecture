#ifndef PROJECT_CONFIG_H
#define PROJECT_CONFIG_H

/*
 * Keep this identity visible through PING/GET_DEVICE_INFO so a host log can
 * prove which binary is actually executing on the MCU after a download.
 */
#define MOTOR_FIRMWARE_VERSION_MAJOR       0U
#define MOTOR_FIRMWARE_VERSION_MINOR       3U
#define MOTOR_FIRMWARE_VERSION_PATCH       0U
#define MOTOR_FIRMWARE_PING_TEXT           "TC375-MCU/0.3"
#define MOTOR_FIRMWARE_BUILD_TAG           "CFG29"
#define MOTOR_FIRMWARE_BUILD_TAG_LENGTH    5U

/*
 * Hardware output is split into two independent compile-time safety layers:
 *
 * CONTROL_HARDWARE:
 *   Initializes GTM and allows PWM waveforms on the MCU TOUT pins. This is the
 *   bench/oscilloscope mode and does not energize the inverter by itself.
 *
 * POWER_STAGE:
 *   Allows the DRV8313 nSLEEP/nRESET signals to be released. Keep this at 0
 *   until the complete power board, current limiting and physical emergency
 *   stop have been verified.
 *
 * The default build intentionally supports a control-board-only SimpleFOC
 * open-loop waveform test while the power stage remains compile-time locked.
 */
#ifndef MOTOR_CONTROL_HARDWARE_ENABLED
#ifdef MOTOR_REAL_HARDWARE_ENABLED
#define MOTOR_CONTROL_HARDWARE_ENABLED MOTOR_REAL_HARDWARE_ENABLED
#else
#define MOTOR_CONTROL_HARDWARE_ENABLED 1
#endif
#endif

#ifndef MOTOR_POWER_STAGE_ENABLED
#ifdef MOTOR_REAL_HARDWARE_ENABLED
#define MOTOR_POWER_STAGE_ENABLED MOTOR_REAL_HARDWARE_ENABLED
#else
#define MOTOR_POWER_STAGE_ENABLED 0
#endif
#endif

#if MOTOR_POWER_STAGE_ENABLED && !MOTOR_CONTROL_HARDWARE_ENABLED
#error "MOTOR_POWER_STAGE_ENABLED requires MOTOR_CONTROL_HARDWARE_ENABLED"
#endif

/*
 * Backward-compatible read-only alias. New code must use the two explicit
 * layer macros above.
 */
#ifndef MOTOR_REAL_HARDWARE_ENABLED
#define MOTOR_REAL_HARDWARE_ENABLED MOTOR_POWER_STAGE_ENABLED
#endif

/* Build and link the SimpleFOC core plus the TC375 adapter classes. */
#ifndef MOTOR_USE_SIMPLEFOC
#define MOTOR_USE_SIMPLEFOC 1
#endif

#define MOTOR_DEVICE_ID                 1U
#define MOTOR_ADC_TRIGGER_HZ            10000U
#define MOTOR_PWM_FREQUENCY_HZ          20000U
#define MOTOR_CONTROL_ISR_HZ            MOTOR_ADC_TRIGGER_HZ
#define MOTOR_OUTER_LOOP_HZ             1000U
#define MOTOR_TELEMETRY_HZ              100U
#define MOTOR_HEARTBEAT_DEFAULT_MS      750U
#define MOTOR_HEARTBEAT_MIN_MS          300U
#define MOTOR_HEARTBEAT_MAX_MS          5000U

#define MOTOR_POLE_PAIRS                 7U
#define MOTOR_TORQUE_CONSTANT_NM_PER_A   0.10F

#define MOTOR_DEFAULT_CURRENT_LIMIT_A    20.0F
#define MOTOR_DEFAULT_TORQUE_LIMIT_NM    2.0F
#define MOTOR_DEFAULT_SPEED_LIMIT_RAD_S  100.0F
#define MOTOR_DEFAULT_POSITION_MIN_RAD  -1000.0F
#define MOTOR_DEFAULT_POSITION_MAX_RAD   1000.0F
#define MOTOR_DEFAULT_BUS_MIN_V          18.0F
#define MOTOR_DEFAULT_BUS_MAX_V          60.0F
#define MOTOR_DEFAULT_TEMP_MAX_C         80.0F

/*
 * Open-loop commissioning defaults. These values are exposed through the
 * native protocol as runtime settings. The HARD_MAX values remain compile-time
 * safety ceilings and cannot be raised by the host.
 */
#define MOTOR_OPEN_LOOP_DEFAULT_BACKEND          1U
#define MOTOR_OPEN_LOOP_DEFAULT_BUS_V             24.0F
#define MOTOR_OPEN_LOOP_DEFAULT_VOLTAGE_LIMIT_V    2.0F
#define MOTOR_OPEN_LOOP_DEFAULT_TARGET_RAD_S       5.0F
#define MOTOR_OPEN_LOOP_DEFAULT_ACCEL_RAD_S2       10.0F
#define MOTOR_OPEN_LOOP_DEFAULT_UPDATE_MS          10U
#define MOTOR_OPEN_LOOP_DEFAULT_START_DELAY_MS     500U
#define MOTOR_OPEN_LOOP_DEFAULT_MAX_RUNTIME_MS     30000UL
#define MOTOR_OPEN_LOOP_HARD_MAX_BUS_V             60.0F
#define MOTOR_OPEN_LOOP_HARD_MAX_VOLTAGE_V          6.0F
#define MOTOR_OPEN_LOOP_HARD_MAX_TARGET_RAD_S     100.0F
#define MOTOR_OPEN_LOOP_HARD_MAX_RUNTIME_MS    600000UL

#endif

