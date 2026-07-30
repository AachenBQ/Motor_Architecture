#ifndef PROJECT_CONFIG_H
#define PROJECT_CONFIG_H

/*
 * Keep this identity visible through PING/GET_DEVICE_INFO so a host log can
 * prove which binary is actually executing on the MCU after a download.
 */
#define MOTOR_FIRMWARE_VERSION_MAJOR       0U
#define MOTOR_FIRMWARE_VERSION_MINOR       3U
#define MOTOR_FIRMWARE_VERSION_PATCH       8U
#define MOTOR_FIRMWARE_PING_TEXT           "TC375-MCU/0.3"
#define MOTOR_FIRMWARE_BUILD_TAG           "PSF1"
#define MOTOR_FIRMWARE_BUILD_TAG_LENGTH    4U

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
 * A real-power build must explicitly describe which safety layers have been
 * implemented and verified on the actual board. These switches are evidence
 * gates, not TODO suppression: set one to 1 only after its implementation and
 * hardware test are complete.
 */
#ifndef MOTOR_PHASE_CURRENT_SENSE_READY
#define MOTOR_PHASE_CURRENT_SENSE_READY 0
#endif
#ifndef MOTOR_BUS_VOLTAGE_SENSE_READY
#define MOTOR_BUS_VOLTAGE_SENSE_READY 0
#endif
#ifndef MOTOR_POWER_TEMPERATURE_SENSE_READY
#define MOTOR_POWER_TEMPERATURE_SENSE_READY 0
#endif
#ifndef MOTOR_CPU_WATCHDOG_READY
#define MOTOR_CPU_WATCHDOG_READY 0
#endif
#ifndef MOTOR_PHYSICAL_ESTOP_READY
#define MOTOR_PHYSICAL_ESTOP_READY 0
#endif
#ifndef MOTOR_EXTERNAL_CURRENT_LIMIT_READY
#define MOTOR_EXTERNAL_CURRENT_LIMIT_READY 0
#endif
#ifndef MOTOR_GATE_FAULT_MONITOR_READY
#define MOTOR_GATE_FAULT_MONITOR_READY 0
#endif
#ifndef MOTOR_HEARTBEAT_INTERLOCK_READY
#define MOTOR_HEARTBEAT_INTERLOCK_READY 1
#endif
#ifndef MOTOR_SAFE_OUTPUT_PATH_READY
#define MOTOR_SAFE_OUTPUT_PATH_READY 1
#endif
#ifndef MOTOR_ENCODER_SENSE_READY
#define MOTOR_ENCODER_SENSE_READY 0
#endif
#ifndef MOTOR_CLOSED_LOOP_CONTROL_READY
#define MOTOR_CLOSED_LOOP_CONTROL_READY 0
#endif

/*
 * Bench commissioning override:
 *   0 = production-style build; every required safety bit must be ready.
 *   1 = short, externally current-limited commissioning only. The firmware
 *       and host still require an explicit confirmation on every start.
 */
#ifndef MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE
#define MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE 0
#endif

#define MOTOR_POWER_SAFETY_CURRENT_SENSE          (1UL << 0)
#define MOTOR_POWER_SAFETY_BUS_VOLTAGE_SENSE      (1UL << 1)
#define MOTOR_POWER_SAFETY_TEMPERATURE_SENSE      (1UL << 2)
#define MOTOR_POWER_SAFETY_CPU_WATCHDOG           (1UL << 3)
#define MOTOR_POWER_SAFETY_PHYSICAL_ESTOP         (1UL << 4)
#define MOTOR_POWER_SAFETY_EXTERNAL_CURRENT_LIMIT (1UL << 5)
#define MOTOR_POWER_SAFETY_GATE_FAULT_MONITOR     (1UL << 6)
#define MOTOR_POWER_SAFETY_HEARTBEAT              (1UL << 7)
#define MOTOR_POWER_SAFETY_SAFE_OUTPUT             (1UL << 8)
#define MOTOR_POWER_SAFETY_OVERRIDE_ACTIVE        (1UL << 31)

#define MOTOR_POWER_STAGE_REQUIRED_SAFETY_MASK ( \
    MOTOR_POWER_SAFETY_CURRENT_SENSE | \
    MOTOR_POWER_SAFETY_BUS_VOLTAGE_SENSE | \
    MOTOR_POWER_SAFETY_TEMPERATURE_SENSE | \
    MOTOR_POWER_SAFETY_CPU_WATCHDOG | \
    MOTOR_POWER_SAFETY_PHYSICAL_ESTOP | \
    MOTOR_POWER_SAFETY_EXTERNAL_CURRENT_LIMIT | \
    MOTOR_POWER_SAFETY_GATE_FAULT_MONITOR | \
    MOTOR_POWER_SAFETY_HEARTBEAT | \
    MOTOR_POWER_SAFETY_SAFE_OUTPUT)

#define MOTOR_POWER_STAGE_SAFETY_READY_MASK ( \
    (MOTOR_PHASE_CURRENT_SENSE_READY \
        ? MOTOR_POWER_SAFETY_CURRENT_SENSE : 0UL) | \
    (MOTOR_BUS_VOLTAGE_SENSE_READY \
        ? MOTOR_POWER_SAFETY_BUS_VOLTAGE_SENSE : 0UL) | \
    (MOTOR_POWER_TEMPERATURE_SENSE_READY \
        ? MOTOR_POWER_SAFETY_TEMPERATURE_SENSE : 0UL) | \
    (MOTOR_CPU_WATCHDOG_READY \
        ? MOTOR_POWER_SAFETY_CPU_WATCHDOG : 0UL) | \
    (MOTOR_PHYSICAL_ESTOP_READY \
        ? MOTOR_POWER_SAFETY_PHYSICAL_ESTOP : 0UL) | \
    (MOTOR_EXTERNAL_CURRENT_LIMIT_READY \
        ? MOTOR_POWER_SAFETY_EXTERNAL_CURRENT_LIMIT : 0UL) | \
    (MOTOR_GATE_FAULT_MONITOR_READY \
        ? MOTOR_POWER_SAFETY_GATE_FAULT_MONITOR : 0UL) | \
    (MOTOR_HEARTBEAT_INTERLOCK_READY \
        ? MOTOR_POWER_SAFETY_HEARTBEAT : 0UL) | \
    (MOTOR_SAFE_OUTPUT_PATH_READY \
        ? MOTOR_POWER_SAFETY_SAFE_OUTPUT : 0UL))

#define MOTOR_POWER_STAGE_REPORTED_SAFETY_MASK ( \
    MOTOR_POWER_STAGE_SAFETY_READY_MASK | \
    (MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE \
        ? MOTOR_POWER_SAFETY_OVERRIDE_ACTIVE : 0UL))

#if MOTOR_POWER_STAGE_ENABLED && \
    !MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE && \
    ((MOTOR_POWER_STAGE_SAFETY_READY_MASK & \
      MOTOR_POWER_STAGE_REQUIRED_SAFETY_MASK) != \
     MOTOR_POWER_STAGE_REQUIRED_SAFETY_MASK)
#error "Power-stage build blocked: complete every safety layer or use the explicit bench commissioning override"
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

#define MOTOR_DEFAULT_CURRENT_LIMIT_A     0.3F
#define MOTOR_DEFAULT_TORQUE_LIMIT_NM     0.03F
#define MOTOR_DEFAULT_SPEED_LIMIT_RAD_S  100.0F
#define MOTOR_DEFAULT_POSITION_MIN_RAD  -1000.0F
#define MOTOR_DEFAULT_POSITION_MAX_RAD   1000.0F
#if MOTOR_POWER_STAGE_ENABLED
#define MOTOR_DEFAULT_BUS_MIN_V           8.0F
#define MOTOR_DEFAULT_BUS_MAX_V          10.0F
#else
#define MOTOR_DEFAULT_BUS_MIN_V           5.0F
#define MOTOR_DEFAULT_BUS_MAX_V           8.0F
#endif
#define MOTOR_DEFAULT_TEMP_MAX_C         80.0F

/*
 * Open-loop commissioning defaults. These values are exposed through the
 * native protocol as runtime settings. The HARD_MAX values remain compile-time
 * safety ceilings and cannot be raised by the host.
 */
#define MOTOR_OPEN_LOOP_DEFAULT_BACKEND          1U
#if MOTOR_POWER_STAGE_ENABLED
#define MOTOR_OPEN_LOOP_DEFAULT_BUS_V              9.0F
#if MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE
#define MOTOR_OPEN_LOOP_DEFAULT_VOLTAGE_LIMIT_V    0.1F
#define MOTOR_OPEN_LOOP_DEFAULT_TARGET_RAD_S       1.0F
#define MOTOR_OPEN_LOOP_DEFAULT_ACCEL_RAD_S2       1.0F
#define MOTOR_OPEN_LOOP_DEFAULT_MAX_RUNTIME_MS  1000UL
#else
#define MOTOR_OPEN_LOOP_DEFAULT_VOLTAGE_LIMIT_V    0.3F
#define MOTOR_OPEN_LOOP_DEFAULT_TARGET_RAD_S       5.0F
#define MOTOR_OPEN_LOOP_DEFAULT_ACCEL_RAD_S2      10.0F
#define MOTOR_OPEN_LOOP_DEFAULT_MAX_RUNTIME_MS  3000UL
#endif
#else
#define MOTOR_OPEN_LOOP_DEFAULT_BUS_V              7.0F
#define MOTOR_OPEN_LOOP_DEFAULT_VOLTAGE_LIMIT_V    0.3F
#define MOTOR_OPEN_LOOP_DEFAULT_TARGET_RAD_S       5.0F
#define MOTOR_OPEN_LOOP_DEFAULT_ACCEL_RAD_S2      10.0F
#define MOTOR_OPEN_LOOP_DEFAULT_MAX_RUNTIME_MS 30000UL
#endif
#define MOTOR_OPEN_LOOP_DEFAULT_UPDATE_MS          10U
#define MOTOR_OPEN_LOOP_DEFAULT_START_DELAY_MS     500U
#define MOTOR_OPEN_LOOP_HARD_MAX_BUS_V             10.0F
#define MOTOR_OPEN_LOOP_HARD_MAX_VOLTAGE_V          2.0F
#define MOTOR_OPEN_LOOP_HARD_MAX_TARGET_RAD_S     100.0F
#define MOTOR_OPEN_LOOP_HARD_MAX_RUNTIME_MS    600000UL

/* Additional hard ceilings whenever a real power-stage build is selected. */
#define MOTOR_POWER_STAGE_MIN_BUS_V                  8.0F
#define MOTOR_POWER_STAGE_MAX_BUS_V                 10.0F
#define MOTOR_POWER_STAGE_MAX_OPEN_LOOP_VOLTAGE_V    0.3F
#define MOTOR_POWER_STAGE_MAX_OPEN_LOOP_SPEED_RAD_S  5.0F
#define MOTOR_POWER_STAGE_MAX_OPEN_LOOP_ACCEL_RAD_S2 10.0F
#define MOTOR_POWER_STAGE_MIN_START_DELAY_MS        500U
#define MOTOR_POWER_STAGE_MAX_OPEN_LOOP_RUNTIME_MS 3000UL
#define MOTOR_POWER_STAGE_BUS_TOLERANCE_V             0.5F

/*
 * The override is deliberately stricter than a completed power-stage build.
 * These ceilings are enforced in firmware and cannot be raised by the host.
 */
#define MOTOR_COMMISSIONING_MAX_OPEN_LOOP_VOLTAGE_V    0.1F
#define MOTOR_COMMISSIONING_MAX_OPEN_LOOP_SPEED_RAD_S  1.0F
#define MOTOR_COMMISSIONING_MAX_OPEN_LOOP_ACCEL_RAD_S2 1.0F
#define MOTOR_COMMISSIONING_MAX_OPEN_LOOP_RUNTIME_MS 1000UL

#endif

