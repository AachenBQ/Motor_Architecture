#include "motor_control.h"

#include "project_config.h"

#include <math.h>
#include <string.h>

static bool IsFiniteNonnegative(float value)
{
    return isfinite(value) && value >= 0.0F;
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
    motor->heartbeat_valid = elapsed <= motor->heartbeat_lease_ms;
    if (!motor->heartbeat_valid && motor->enabled)
    {
        motor->target = 0.0F;
        motor->enabled = false;
        motor->faults |= MOTOR_FAULT_COMM_TIMEOUT;
        motor->state = MOTOR_STATE_FAULT;
    }
}

MotorResult MotorControl_SetEnable(MotorControl *motor, bool enable)
{
    if (!enable)
    {
        motor->enabled = false;
        motor->target = 0.0F;
        if (motor->state == MOTOR_STATE_RUNNING)
        {
            motor->state = MOTOR_STATE_READY;
        }
        return MOTOR_RESULT_OK;
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
    return MOTOR_RESULT_OK;
}

MotorResult MotorControl_SetMode(MotorControl *motor, MotorMode mode)
{
    if ((mode < MOTOR_MODE_TORQUE) || (mode > MOTOR_MODE_POSITION))
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
    motor->target = target;
    return MOTOR_RESULT_OK;
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
    motor->target = 0.0F;
    motor->enabled = false;
    motor->state = emergency
        ? MOTOR_STATE_ESTOP
        : (motor->calibrated ? MOTOR_STATE_READY : MOTOR_STATE_IDLE);
}

void MotorControl_TripFault(MotorControl *motor, uint32_t fault)
{
    motor->target = 0.0F;
    motor->enabled = false;
    motor->faults |= fault;
    motor->state = MOTOR_STATE_FAULT;
}

void MotorControl_UpdateTelemetry(
    MotorControl *motor,
    const MotorTelemetry *telemetry)
{
    motor->telemetry = *telemetry;
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
    MotorControl_SetCalibrationValid(
        motor,
        config->calibration_valid != 0U);
    return true;
}
