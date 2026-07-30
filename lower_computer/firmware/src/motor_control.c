#include "motor_control.h"

#include "project_config.h"

#include <math.h>
#include <string.h>

static bool IsFiniteNonnegative(float value)
{
    return isfinite(value) && value >= 0.0F;
}

static bool IsValidPowerStageOpenLoopConfig(
    const MotorOpenLoopConfig *config)
{
#if MOTOR_POWER_STAGE_ENABLED
    return
        (config->bus_voltage_v >= MOTOR_POWER_STAGE_MIN_BUS_V) &&
        (config->bus_voltage_v <= MOTOR_POWER_STAGE_MAX_BUS_V) &&
        (config->voltage_limit_v <=
         MOTOR_POWER_STAGE_MAX_OPEN_LOOP_VOLTAGE_V) &&
        (fabsf(config->target_velocity_rad_s) <=
         MOTOR_POWER_STAGE_MAX_OPEN_LOOP_SPEED_RAD_S) &&
        (config->acceleration_rad_s2 <=
         MOTOR_POWER_STAGE_MAX_OPEN_LOOP_ACCEL_RAD_S2) &&
        (config->startup_delay_ms >=
         MOTOR_POWER_STAGE_MIN_START_DELAY_MS) &&
        (config->max_runtime_ms <=
         MOTOR_POWER_STAGE_MAX_OPEN_LOOP_RUNTIME_MS)
#if MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE
        && (config->voltage_limit_v <=
            MOTOR_COMMISSIONING_MAX_OPEN_LOOP_VOLTAGE_V)
        && (fabsf(config->target_velocity_rad_s) <=
            MOTOR_COMMISSIONING_MAX_OPEN_LOOP_SPEED_RAD_S)
        && (config->acceleration_rad_s2 <=
            MOTOR_COMMISSIONING_MAX_OPEN_LOOP_ACCEL_RAD_S2)
        && (config->max_runtime_ms <=
            MOTOR_COMMISSIONING_MAX_OPEN_LOOP_RUNTIME_MS)
#endif
        ;
#else
    (void)config;
    return true;
#endif
}

static MotorOpenLoopConfig DefaultOpenLoopConfig(void)
{
    MotorOpenLoopConfig config;
    memset(&config, 0, sizeof(config));
    config.backend = MOTOR_OPEN_LOOP_DEFAULT_BACKEND;
    config.pole_pairs = MOTOR_POLE_PAIRS;
    config.bus_voltage_v = MOTOR_OPEN_LOOP_DEFAULT_BUS_V;
    config.voltage_limit_v = MOTOR_OPEN_LOOP_DEFAULT_VOLTAGE_LIMIT_V;
    config.target_velocity_rad_s =
        MOTOR_OPEN_LOOP_DEFAULT_TARGET_RAD_S;
    config.acceleration_rad_s2 =
        MOTOR_OPEN_LOOP_DEFAULT_ACCEL_RAD_S2;
    config.update_period_ms =
        MOTOR_OPEN_LOOP_DEFAULT_UPDATE_MS;
    config.startup_delay_ms =
        MOTOR_OPEN_LOOP_DEFAULT_START_DELAY_MS;
    config.max_runtime_ms =
        MOTOR_OPEN_LOOP_DEFAULT_MAX_RUNTIME_MS;
    return config;
}

static bool IsValidOpenLoopConfig(const MotorOpenLoopConfig *config)
{
    return
        (config != NULL) &&
        (config->backend <= MOTOR_OPEN_LOOP_SIMPLEFOC) &&
        (config->flags == 0U) &&
        ((config->backend != MOTOR_OPEN_LOOP_SIMPLEFOC) ||
         (config->pole_pairs == MOTOR_POLE_PAIRS)) &&
        (config->pole_pairs >= 1U) &&
        (config->pole_pairs <= 64U) &&
        isfinite(config->bus_voltage_v) &&
        isfinite(config->voltage_limit_v) &&
        isfinite(config->target_velocity_rad_s) &&
        isfinite(config->acceleration_rad_s2) &&
        (config->bus_voltage_v > 0.0F) &&
        (config->bus_voltage_v <= MOTOR_OPEN_LOOP_HARD_MAX_BUS_V) &&
        (config->voltage_limit_v > 0.0F) &&
        (config->voltage_limit_v <= config->bus_voltage_v) &&
        (config->voltage_limit_v <=
         MOTOR_OPEN_LOOP_HARD_MAX_VOLTAGE_V) &&
        (fabsf(config->target_velocity_rad_s) <=
         MOTOR_OPEN_LOOP_HARD_MAX_TARGET_RAD_S) &&
        (config->acceleration_rad_s2 >= 0.01F) &&
        (config->acceleration_rad_s2 <= 10000.0F) &&
        (config->update_period_ms >= 1U) &&
        (config->update_period_ms <= 100U) &&
        (config->startup_delay_ms <= 5000U) &&
        (config->max_runtime_ms >= 1000UL) &&
        (config->max_runtime_ms <=
         MOTOR_OPEN_LOOP_HARD_MAX_RUNTIME_MS) &&
        IsValidPowerStageOpenLoopConfig(config);
}

void MotorControl_Init(MotorControl *motor, uint32_t now_ms)
{
    memset(motor, 0, sizeof(*motor));
    motor->state = MOTOR_STATE_IDLE;
    motor->mode = MOTOR_MODE_SPEED;
    motor->heartbeat_lease_ms = MOTOR_HEARTBEAT_DEFAULT_MS;
    motor->last_heartbeat_ms = now_ms;
    motor->pid[MOTOR_PID_CURRENT] = (MotorPid){0.80F, 0.12F, 0.01F};
    motor->pid[MOTOR_PID_SPEED] = (MotorPid){0.50F, 0.05F, 0.00F};
    motor->pid[MOTOR_PID_POSITION] = (MotorPid){2.00F, 0.00F, 0.02F};
    memcpy(motor->pending_pid, motor->pid, sizeof(motor->pid));
    motor->limits = (MotorLimits){
        MOTOR_DEFAULT_CURRENT_LIMIT_A,
        MOTOR_DEFAULT_TORQUE_LIMIT_NM,
        MOTOR_DEFAULT_SPEED_LIMIT_RAD_S,
        MOTOR_DEFAULT_POSITION_MIN_RAD,
        MOTOR_DEFAULT_POSITION_MAX_RAD,
        MOTOR_DEFAULT_BUS_MIN_V,
        MOTOR_DEFAULT_BUS_MAX_V,
        MOTOR_DEFAULT_TEMP_MAX_C};
    motor->open_loop = DefaultOpenLoopConfig();
}

void MotorControl_SetCalibrationValid(MotorControl *motor, bool valid)
{
    if (motor->enabled)
    {
        return;
    }
    motor->calibrated = valid;
    motor->state = valid ? MOTOR_STATE_READY : MOTOR_STATE_IDLE;
}

void MotorControl_Heartbeat(
    MotorControl *motor,
    uint32_t now_ms,
    uint16_t lease_ms)
{
    motor->last_heartbeat_ms = now_ms;
    motor->heartbeat_lease_ms = lease_ms;
    motor->heartbeat_valid = true;
}

void MotorControl_Tick(MotorControl *motor, uint32_t now_ms)
{
    uint32_t elapsed = now_ms - motor->last_heartbeat_ms;
    /*
     * A recent boot timestamp is not a heartbeat. Once a real heartbeat has
     * armed the lease, Tick may keep it valid or expire it, but must never
     * promote the initial false state to true by itself.
     */
    if (motor->heartbeat_valid)
    {
        motor->heartbeat_valid =
            elapsed <= motor->heartbeat_lease_ms;
    }
    if (!motor->heartbeat_valid &&
        (motor->enabled || motor->open_loop_active))
    {
        motor->last_stop_reason =
            MOTOR_STOP_REASON_HEARTBEAT_TIMEOUT;
        MotorControl_TripFault(motor, MOTOR_FAULT_COMM_TIMEOUT);
        return;
    }

    if (!motor->open_loop_active)
    {
        return;
    }
    if ((now_ms - motor->open_loop_started_ms) >=
        motor->open_loop.max_runtime_ms)
    {
        MotorControl_StopWithReason(
            motor,
            false,
            MOTOR_STOP_REASON_OPEN_LOOP_RUNTIME);
        return;
    }
    if (!motor->open_loop_output_ready)
    {
        motor->open_loop_output_ready =
            (now_ms - motor->open_loop_started_ms) >=
            motor->open_loop.startup_delay_ms;
        motor->open_loop_last_update_ms = now_ms;
        return;
    }
    elapsed = now_ms - motor->open_loop_last_update_ms;
    if (elapsed >= motor->open_loop.update_period_ms)
    {
        float desired = motor->target;
        float maximum_step =
            motor->open_loop.acceleration_rad_s2 *
            ((float)elapsed / 1000.0F);
        float difference = desired - motor->open_loop_velocity_rad_s;
        if (difference > maximum_step)
        {
            difference = maximum_step;
        }
        else if (difference < -maximum_step)
        {
            difference = -maximum_step;
        }
        motor->open_loop_velocity_rad_s += difference;
        motor->open_loop_last_update_ms = now_ms;
        if ((motor->state == MOTOR_STATE_STOPPING) &&
            (fabsf(motor->open_loop_velocity_rad_s) < 0.001F))
        {
            MotorControl_StopWithReason(
                motor,
                false,
                MOTOR_STOP_REASON_CONTROLLED_COMMAND);
        }
    }
}

MotorResult MotorControl_SetEnable(MotorControl *motor, bool enable)
{
    if (!enable)
    {
        MotorControl_StopWithReason(
            motor,
            false,
            MOTOR_STOP_REASON_DISABLE_COMMAND);
        return MOTOR_RESULT_OK;
    }
#if MOTOR_POWER_STAGE_ENABLED
    if (!MOTOR_CLOSED_LOOP_CONTROL_READY ||
        !MOTOR_ENCODER_SENSE_READY ||
        !MOTOR_PHASE_CURRENT_SENSE_READY)
    {
        return MOTOR_RESULT_SAFETY_INTERLOCK;
    }
#endif
    if (motor->mode == MOTOR_MODE_OPEN_LOOP_SPEED)
    {
        return MOTOR_RESULT_INVALID_STATE;
    }
    if (motor->faults != 0U)
    {
        return MOTOR_RESULT_HARDWARE_FAULT;
    }
    if (!motor->calibrated)
    {
        return MOTOR_RESULT_NOT_CALIBRATED;
    }
    if (!motor->heartbeat_valid)
    {
        return MOTOR_RESULT_HEARTBEAT_REQUIRED;
    }
    if (motor->state != MOTOR_STATE_READY)
    {
        return MOTOR_RESULT_INVALID_STATE;
    }
    motor->enabled = true;
    motor->state = MOTOR_STATE_RUNNING;
    motor->last_stop_reason = MOTOR_STOP_REASON_NONE;
    return MOTOR_RESULT_OK;
}

MotorResult MotorControl_SetMode(MotorControl *motor, MotorMode mode)
{
    if ((mode < MOTOR_MODE_TORQUE) ||
        (mode > MOTOR_MODE_OPEN_LOOP_SPEED) ||
        (mode == MOTOR_MODE_OPEN_LOOP_SPEED))
    {
        return MOTOR_RESULT_OUT_OF_RANGE;
    }
    if ((motor->state != MOTOR_STATE_READY) &&
        (motor->state != MOTOR_STATE_RUNNING))
    {
        return MOTOR_RESULT_INVALID_STATE;
    }
    if (motor->mode != mode)
    {
        motor->target = 0.0F;
        motor->mode = mode;
    }
    return MOTOR_RESULT_OK;
}

MotorResult MotorControl_SetTarget(
    MotorControl *motor,
    MotorMode mode,
    float target)
{
    if (!isfinite(target) || (mode != motor->mode))
    {
        return MOTOR_RESULT_OUT_OF_RANGE;
    }
    if ((mode == MOTOR_MODE_TORQUE) &&
        (fabsf(target) > motor->limits.torque_nm))
    {
        return MOTOR_RESULT_OUT_OF_RANGE;
    }
    if ((mode == MOTOR_MODE_SPEED) &&
        (fabsf(target) > motor->limits.speed_rad_s))
    {
        return MOTOR_RESULT_OUT_OF_RANGE;
    }
    if ((mode == MOTOR_MODE_POSITION) &&
        ((target < motor->limits.position_min_rad) ||
         (target > motor->limits.position_max_rad)))
    {
        return MOTOR_RESULT_OUT_OF_RANGE;
    }
    if (mode == MOTOR_MODE_OPEN_LOOP_SPEED)
    {
        if (!motor->open_loop_active ||
            (fabsf(target) > motor->limits.speed_rad_s) ||
            (fabsf(target) >
             MOTOR_OPEN_LOOP_HARD_MAX_TARGET_RAD_S))
        {
            return MOTOR_RESULT_OUT_OF_RANGE;
        }
        motor->open_loop.target_velocity_rad_s = target;
    }
    motor->target = target;
    return MOTOR_RESULT_OK;
}

MotorResult MotorControl_SetOpenLoopConfig(
    MotorControl *motor,
    const MotorOpenLoopConfig *config)
{
    if (motor->enabled || motor->open_loop_active)
    {
        return MOTOR_RESULT_INVALID_STATE;
    }
    if (!IsValidOpenLoopConfig(config) ||
        (fabsf(config->target_velocity_rad_s) >
         motor->limits.speed_rad_s) ||
        (config->bus_voltage_v < motor->limits.bus_min_v) ||
        (config->bus_voltage_v > motor->limits.bus_max_v))
    {
        return MOTOR_RESULT_OUT_OF_RANGE;
    }
    motor->open_loop = *config;
    motor->open_loop.reserved = 0U;
    return MOTOR_RESULT_OK;
}

MotorResult MotorControl_StartOpenLoop(
    MotorControl *motor,
    uint32_t now_ms)
{
    if (motor->faults != 0U)
    {
        return MOTOR_RESULT_HARDWARE_FAULT;
    }
    if (!motor->heartbeat_valid)
    {
        return MOTOR_RESULT_HEARTBEAT_REQUIRED;
    }
    if (motor->enabled ||
        motor->open_loop_active ||
        ((motor->state != MOTOR_STATE_IDLE) &&
         (motor->state != MOTOR_STATE_READY)))
    {
        return MOTOR_RESULT_INVALID_STATE;
    }
    if (!IsValidOpenLoopConfig(&motor->open_loop))
    {
        return MOTOR_RESULT_OUT_OF_RANGE;
    }
    motor->mode = MOTOR_MODE_OPEN_LOOP_SPEED;
    motor->target = motor->open_loop.target_velocity_rad_s;
    motor->open_loop_velocity_rad_s = 0.0F;
    motor->open_loop_started_ms = now_ms;
    motor->open_loop_last_update_ms = now_ms;
    motor->open_loop_output_ready =
        motor->open_loop.startup_delay_ms == 0U;
    motor->open_loop_active = true;
    motor->enabled = true;
    motor->state = MOTOR_STATE_RUNNING;
    motor->last_stop_reason = MOTOR_STOP_REASON_NONE;
    return MOTOR_RESULT_OK;
}

void MotorControl_RequestControlledStop(MotorControl *motor)
{
    if (motor->open_loop_active && motor->enabled)
    {
        motor->target = 0.0F;
        motor->state = MOTOR_STATE_STOPPING;
        motor->last_stop_reason =
            MOTOR_STOP_REASON_CONTROLLED_COMMAND;
        return;
    }
    MotorControl_StopWithReason(
        motor,
        false,
        MOTOR_STOP_REASON_CONTROLLED_COMMAND);
}

MotorResult MotorControl_SetPid(
    MotorControl *motor,
    MotorPidLoop loop,
    const MotorPid *pid)
{
    if ((loop >= MOTOR_PID_COUNT) ||
        !IsFiniteNonnegative(pid->kp) ||
        !IsFiniteNonnegative(pid->ki) ||
        !IsFiniteNonnegative(pid->kd))
    {
        return MOTOR_RESULT_OUT_OF_RANGE;
    }
    motor->pending_pid[loop] = *pid;
    motor->pending_pid_mask |= (uint8_t)(1U << loop);
    return MOTOR_RESULT_OK;
}

void MotorControl_ApplyPendingPid(MotorControl *motor)
{
    uint8_t loop;
    for (loop = 0U; loop < MOTOR_PID_COUNT; ++loop)
    {
        if ((motor->pending_pid_mask & (1U << loop)) != 0U)
        {
            motor->pid[loop] = motor->pending_pid[loop];
        }
    }
    motor->pending_pid_mask = 0U;
}

MotorResult MotorControl_StartCalibration(
    MotorControl *motor,
    uint8_t calibration_type)
{
#if MOTOR_POWER_STAGE_ENABLED
    /*
     * Sensor/current alignment may move the rotor. Until calibration has its
     * own one-shot power confirmation and bounded alignment profile, it must
     * not be an alternate route around the open-loop commissioning interlock.
     */
    (void)motor;
    (void)calibration_type;
    return MOTOR_RESULT_SAFETY_INTERLOCK;
#else
    if (motor->enabled ||
        ((motor->state != MOTOR_STATE_IDLE) &&
         (motor->state != MOTOR_STATE_READY)))
    {
        return MOTOR_RESULT_INVALID_STATE;
    }
    motor->calibrated = false;
    motor->calibration_type = calibration_type;
    motor->state = MOTOR_STATE_CALIBRATING;
    return MOTOR_RESULT_OK;
#endif
}

void MotorControl_FinishCalibration(MotorControl *motor, bool success)
{
    motor->calibrated = success;
    motor->state = success ? MOTOR_STATE_READY : MOTOR_STATE_FAULT;
    if (!success)
    {
        motor->faults |= MOTOR_FAULT_ENCODER;
    }
}

MotorResult MotorControl_ClearFault(MotorControl *motor, uint32_t active_faults)
{
    if (motor->state == MOTOR_STATE_ESTOP)
    {
        return MOTOR_RESULT_INVALID_STATE;
    }
    if (active_faults != 0U)
    {
        motor->faults = active_faults;
        return MOTOR_RESULT_HARDWARE_FAULT;
    }
    motor->faults = 0U;
    motor->state = motor->calibrated ? MOTOR_STATE_READY : MOTOR_STATE_IDLE;
    return MOTOR_RESULT_OK;
}

void MotorControl_Stop(MotorControl *motor, bool emergency)
{
    MotorControl_StopWithReason(
        motor,
        emergency,
        emergency
            ? MOTOR_STOP_REASON_EMERGENCY_COMMAND
            : MOTOR_STOP_REASON_DISABLE_COMMAND);
}

void MotorControl_StopWithReason(
    MotorControl *motor,
    bool emergency,
    MotorStopReason reason)
{
    motor->target = 0.0F;
    motor->enabled = false;
    motor->open_loop_active = false;
    motor->open_loop_output_ready = false;
    motor->open_loop_velocity_rad_s = 0.0F;
    motor->last_stop_reason = reason;
    motor->state = emergency
        ? MOTOR_STATE_ESTOP
        : (motor->calibrated ? MOTOR_STATE_READY : MOTOR_STATE_IDLE);
}

void MotorControl_TripFault(MotorControl *motor, uint32_t fault)
{
    motor->target = 0.0F;
    motor->enabled = false;
    motor->open_loop_active = false;
    motor->open_loop_output_ready = false;
    motor->open_loop_velocity_rad_s = 0.0F;
    motor->faults |= fault;
    if ((fault & MOTOR_FAULT_COMM_TIMEOUT) != 0U)
    {
        motor->last_stop_reason =
            MOTOR_STOP_REASON_HEARTBEAT_TIMEOUT;
    }
    else
    {
        motor->last_stop_reason = MOTOR_STOP_REASON_FAULT;
    }
    motor->state = MOTOR_STATE_FAULT;
}

void MotorControl_UpdateTelemetry(
    MotorControl *motor,
    const MotorTelemetry *telemetry)
{
    motor->telemetry = *telemetry;
    if (fabsf(telemetry->iq_current_a) > motor->limits.current_a)
    {
        MotorControl_TripFault(motor, MOTOR_FAULT_OVERCURRENT);
    }
    if (telemetry->bus_voltage_v > 0.0F)
    {
        if (telemetry->bus_voltage_v > motor->limits.bus_max_v)
        {
            MotorControl_TripFault(motor, MOTOR_FAULT_OVERVOLTAGE);
        }
        else if (telemetry->bus_voltage_v < motor->limits.bus_min_v)
        {
            MotorControl_TripFault(motor, MOTOR_FAULT_UNDERVOLTAGE);
        }
    }
    if (telemetry->temperature_c > motor->limits.temperature_max_c)
    {
        MotorControl_TripFault(motor, MOTOR_FAULT_OVERTEMPERATURE);
    }
}

void MotorControl_RestoreDefaults(MotorControl *motor)
{
    motor->pending_pid[MOTOR_PID_CURRENT] =
        (MotorPid){0.80F, 0.12F, 0.01F};
    motor->pending_pid[MOTOR_PID_SPEED] =
        (MotorPid){0.50F, 0.05F, 0.00F};
    motor->pending_pid[MOTOR_PID_POSITION] =
        (MotorPid){2.00F, 0.00F, 0.02F};
    motor->pending_pid_mask = 0x07U;
    motor->limits = (MotorLimits){
        MOTOR_DEFAULT_CURRENT_LIMIT_A,
        MOTOR_DEFAULT_TORQUE_LIMIT_NM,
        MOTOR_DEFAULT_SPEED_LIMIT_RAD_S,
        MOTOR_DEFAULT_POSITION_MIN_RAD,
        MOTOR_DEFAULT_POSITION_MAX_RAD,
        MOTOR_DEFAULT_BUS_MIN_V,
        MOTOR_DEFAULT_BUS_MAX_V,
        MOTOR_DEFAULT_TEMP_MAX_C};
    motor->open_loop = DefaultOpenLoopConfig();
}

void MotorControl_ExportPersistentConfig(
    const MotorControl *motor,
    MotorPersistentConfig *config)
{
    memset(config, 0, sizeof(*config));
    config->magic = MOTOR_PERSISTENT_MAGIC;
    config->version = MOTOR_PERSISTENT_VERSION;
    config->calibration_valid = motor->calibrated ? 1U : 0U;
    config->telemetry_rate_hz = MOTOR_TELEMETRY_HZ;
    config->telemetry_mask = 0xFFFFFFFFUL;
    memcpy(config->pid, motor->pid, sizeof(config->pid));
    config->limits = motor->limits;
    config->open_loop = motor->open_loop;
    config->open_loop.flags = 0U;
}

bool MotorControl_ImportPersistentConfig(
    MotorControl *motor,
    const MotorPersistentConfig *config)
{
    uint8_t loop;
    if ((config->magic != MOTOR_PERSISTENT_MAGIC) ||
        (config->version != MOTOR_PERSISTENT_VERSION) ||
        (config->telemetry_rate_hz == 0U) ||
        (config->telemetry_rate_hz > 1000U) ||
        !isfinite(config->limits.current_a) ||
        !isfinite(config->limits.torque_nm) ||
        !isfinite(config->limits.speed_rad_s) ||
        !isfinite(config->limits.position_min_rad) ||
        !isfinite(config->limits.position_max_rad) ||
        !isfinite(config->limits.bus_min_v) ||
        !isfinite(config->limits.bus_max_v) ||
        !isfinite(config->limits.temperature_max_c) ||
        (config->limits.current_a <= 0.0F) ||
        (config->limits.torque_nm <= 0.0F) ||
        (config->limits.speed_rad_s <= 0.0F) ||
        (config->limits.position_min_rad >=
         config->limits.position_max_rad) ||
        (config->limits.bus_min_v >= config->limits.bus_max_v))
    {
        return false;
    }
    if (!IsValidOpenLoopConfig(&config->open_loop) ||
        (fabsf(config->open_loop.target_velocity_rad_s) >
         config->limits.speed_rad_s) ||
        (config->open_loop.bus_voltage_v <
         config->limits.bus_min_v) ||
        (config->open_loop.bus_voltage_v >
         config->limits.bus_max_v))
    {
        return false;
    }
    for (loop = 0U; loop < MOTOR_PID_COUNT; ++loop)
    {
        if (!IsFiniteNonnegative(config->pid[loop].kp) ||
            !IsFiniteNonnegative(config->pid[loop].ki) ||
            !IsFiniteNonnegative(config->pid[loop].kd))
        {
            return false;
        }
    }
    memcpy(motor->pid, config->pid, sizeof(motor->pid));
    memcpy(motor->pending_pid, config->pid, sizeof(motor->pending_pid));
    motor->pending_pid_mask = 0U;
    motor->limits = config->limits;
    motor->open_loop = config->open_loop;
    motor->open_loop.flags = 0U;
    MotorControl_SetCalibrationValid(
        motor,
        config->calibration_valid != 0U);
    return true;
}
