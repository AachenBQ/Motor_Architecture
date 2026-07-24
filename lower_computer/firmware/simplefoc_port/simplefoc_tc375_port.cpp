#include "simplefoc_tc375_port.hpp"

#include "project_config.h"
#include "tc375_hal.h"

#if MOTOR_USE_SIMPLEFOC
#include "tc375_simplefoc_adapters.hpp"
#endif

/*
 * SimpleFOC is compiled behind a stable C boundary so the FreeRTOS C app does
 * not depend on a specific C++ library version. Power output is still gated by
 * MOTOR_REAL_HARDWARE_ENABLED because board pins, current polarity, dead-time
 * and protection thresholds are not frozen yet.
 */

#if MOTOR_USE_SIMPLEFOC
static BLDCMotor g_foc_motor(MOTOR_POLE_PAIRS);
static Tc375BldcDriver g_driver;
static Tc375CurrentSense g_current_sense;
static Tc375Encoder g_sensor;
static bool g_simplefoc_bound;
static bool g_simplefoc_open_loop;

static float ClampPositive(float value, float fallback)
{
    return value > 0.0F ? value : fallback;
}

static float ClampVoltageLimit(float voltage_limit_v, float bus_voltage_v)
{
    float limit = ClampPositive(voltage_limit_v, bus_voltage_v * 0.1F);

    if (limit > bus_voltage_v)
    {
        limit = bus_voltage_v;
    }

    return limit;
}

static void ConfigureSimpleFoc(const MotorControl *motor)
{
    g_driver.voltage_power_supply = motor->limits.bus_max_v;
    g_driver.voltage_limit = motor->limits.bus_max_v * 0.5F;
    g_foc_motor.voltage_limit = g_driver.voltage_limit;
    g_foc_motor.current_limit = motor->limits.current_a;
    g_foc_motor.velocity_limit = motor->limits.speed_rad_s;
    g_foc_motor.PID_current_q.P = motor->pid[MOTOR_PID_CURRENT].kp;
    g_foc_motor.PID_current_q.I = motor->pid[MOTOR_PID_CURRENT].ki;
    g_foc_motor.PID_current_q.D = motor->pid[MOTOR_PID_CURRENT].kd;
    g_foc_motor.PID_current_d = g_foc_motor.PID_current_q;
    g_foc_motor.PID_velocity.P = motor->pid[MOTOR_PID_SPEED].kp;
    g_foc_motor.PID_velocity.I = motor->pid[MOTOR_PID_SPEED].ki;
    g_foc_motor.PID_velocity.D = motor->pid[MOTOR_PID_SPEED].kd;
    g_foc_motor.P_angle.P = motor->pid[MOTOR_PID_POSITION].kp;
    g_foc_motor.P_angle.I = motor->pid[MOTOR_PID_POSITION].ki;
    g_foc_motor.P_angle.D = motor->pid[MOTOR_PID_POSITION].kd;
    g_foc_motor.torque_controller = TorqueControlType::foc_current;
}

static MotionControlType ToSimpleFocMode(MotorMode mode)
{
    switch (mode)
    {
        case MOTOR_MODE_TORQUE:
            return MotionControlType::torque;
        case MOTOR_MODE_POSITION:
            return MotionControlType::angle;
        case MOTOR_MODE_SPEED:
        default:
            return MotionControlType::velocity;
    }
}
#endif

bool SimpleFocTc375_Init(MotorControl *motor)
{
    Tc375Hal_SetGateEnabled(false);
    Tc375Hal_SetPwmEnabled(false);
    if (!Tc375Hal_MotorPeripheralsInit())
    {
        return false;
    }
#if MOTOR_USE_SIMPLEFOC
    ConfigureSimpleFoc(motor);
    g_foc_motor.linkDriver(&g_driver);
    g_foc_motor.linkSensor(&g_sensor);
    g_current_sense.linkDriver(&g_driver);
    g_foc_motor.linkCurrentSense(&g_current_sense);
    g_simplefoc_bound = true;
#if MOTOR_REAL_HARDWARE_ENABLED
    g_sensor.init();
    if (!g_driver.init() || !g_current_sense.init() || !g_sensor.isValid())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }
    if (!g_foc_motor.init() || !g_foc_motor.initFOC())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }
    g_foc_motor.disable();
#endif
#else
    (void)motor;
#endif
    return true;
}

void SimpleFocTc375_AdcPwmIsr(MotorControl *motor)
{
    Tc375PhaseCurrents currents = Tc375Hal_ReadPhaseCurrents();
    if (!currents.sample_valid || !motor->enabled)
    {
        Tc375Hal_SetPwmEnabled(false);
        return;
    }
#if MOTOR_USE_SIMPLEFOC && MOTOR_REAL_HARDWARE_ENABLED
    if (g_simplefoc_bound)
    {
        g_foc_motor.loopFOC();
    }
#else
    (void)currents;
#endif
}

void SimpleFocTc375_OuterLoop(MotorControl *motor)
{
    Tc375EncoderSample encoder = Tc375Hal_ReadEncoder();
    MotorTelemetry telemetry;

    MotorControl_ApplyPendingPid(motor);
    if (!motor->enabled)
    {
        SimpleFocTc375_ForceSafeState();
    }
#if MOTOR_USE_SIMPLEFOC && MOTOR_REAL_HARDWARE_ENABLED
    else
    {
        ConfigureSimpleFoc(motor);
        g_foc_motor.updateMotionControlType(ToSimpleFocMode(motor->mode));
        g_foc_motor.enable();
        g_foc_motor.move(
            motor->mode == MOTOR_MODE_TORQUE
                ? motor->target / MOTOR_TORQUE_CONSTANT_NM_PER_A
                : motor->target);
    }
#endif
    if (!encoder.valid)
    {
        MotorControl_TripFault(motor, MOTOR_FAULT_ENCODER);
        SimpleFocTc375_ForceSafeState();
    }

#if MOTOR_USE_SIMPLEFOC && MOTOR_REAL_HARDWARE_ENABLED
    telemetry.iq_current_a = g_foc_motor.current.q;
#else
    telemetry.iq_current_a = 0.0F;
#endif

    telemetry.speed_rad_s = encoder.velocity_rad_s;
    telemetry.bus_voltage_v = Tc375Hal_ReadBusVoltage();
    telemetry.temperature_c = Tc375Hal_ReadPowerTemperature();
    telemetry.position_rad = encoder.multi_turn_angle_rad;
    telemetry.status = encoder.valid ? (uint16_t)(1U << 7) : 0U;
    MotorControl_UpdateTelemetry(motor, &telemetry);
}

bool SimpleFocTc375_RunCalibration(unsigned int calibration_type)
{
    (void)calibration_type;
#if MOTOR_USE_SIMPLEFOC && MOTOR_REAL_HARDWARE_ENABLED
    if (!g_simplefoc_bound)
    {
        return false;
    }
    return g_foc_motor.initFOC() != 0;
#else
    return false;
#endif
}

void SimpleFocTc375_ForceSafeState(void)
{
    Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
    Tc375Hal_SetPwmEnabled(false);
    Tc375Hal_SetGateEnabled(false);
}

bool SimpleFocTc375_OpenLoopInit(float bus_voltage_v, float voltage_limit_v)
{
#if MOTOR_USE_SIMPLEFOC
    float bus_voltage = ClampPositive(bus_voltage_v, MOTOR_DEFAULT_BUS_MAX_V);
    float voltage_limit = ClampVoltageLimit(voltage_limit_v, bus_voltage);

    SimpleFocTc375_ForceSafeState();

    if (!Tc375Hal_MotorPeripheralsInit())
    {
        return false;
    }

    g_driver.voltage_power_supply = bus_voltage;
    g_driver.voltage_limit = voltage_limit;

    g_foc_motor.controller = MotionControlType::velocity_openloop;
    g_foc_motor.torque_controller = TorqueControlType::voltage;
    g_foc_motor.foc_modulation = FOCModulationType::SinePWM;
    g_foc_motor.voltage_limit = voltage_limit;
    g_foc_motor.current_limit = MOTOR_DEFAULT_CURRENT_LIMIT_A;
    g_foc_motor.velocity_limit = MOTOR_DEFAULT_SPEED_LIMIT_RAD_S;
    g_foc_motor.linkDriver(&g_driver);

    g_simplefoc_bound = true;
    g_simplefoc_open_loop = false;

    if (!g_driver.init() || !g_foc_motor.init())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }

    g_simplefoc_open_loop = true;
    return true;
#else
    (void)bus_voltage_v;
    (void)voltage_limit_v;
    SimpleFocTc375_ForceSafeState();
    return false;
#endif
}

void SimpleFocTc375_OpenLoopStep(float target_velocity_rad_s)
{
#if MOTOR_USE_SIMPLEFOC
    if (!g_simplefoc_open_loop || !g_simplefoc_bound)
    {
        return;
    }

    if (Tc375Hal_ReadActiveFaults() != 0U)
    {
        SimpleFocTc375_OpenLoopStop();
        return;
    }

    g_foc_motor.move(target_velocity_rad_s);
#else
    (void)target_velocity_rad_s;
#endif
}

void SimpleFocTc375_OpenLoopStop(void)
{
#if MOTOR_USE_SIMPLEFOC
    if (g_simplefoc_bound)
    {
        g_foc_motor.disable();
    }
    g_simplefoc_open_loop = false;
#endif
    SimpleFocTc375_ForceSafeState();
}
