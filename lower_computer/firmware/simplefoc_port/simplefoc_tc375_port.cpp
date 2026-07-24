#include "simplefoc_tc375_port.hpp"

#include "project_config.h"
#include "tc375_hal.h"

#include <math.h>
#include <string.h>

#if MOTOR_USE_SIMPLEFOC
#include "tc375_simplefoc_adapters.hpp"
#endif

/*
 * SimpleFOC is compiled behind a stable C boundary so the FreeRTOS C app does
 * not depend on a specific C++ library version. MCU PWM generation and the
 * physical power stage are separate compile-time layers: control-board-only
 * tests may emit TOUT waveforms while the DRV8313 remains disabled.
 */

#if MOTOR_USE_SIMPLEFOC
static BLDCMotor g_foc_motor(MOTOR_POLE_PAIRS);
static Tc375BldcDriver g_driver;
static Tc375CurrentSense g_current_sense;
static Tc375Encoder g_sensor;
static bool g_simplefoc_bound;
static bool g_simplefoc_open_loop;
#if MOTOR_POWER_STAGE_ENABLED
static bool g_closed_loop_initialized;
#endif

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

#if MOTOR_POWER_STAGE_ENABLED
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

static bool PrepareClosedLoop(void)
{
    if (g_closed_loop_initialized)
    {
        return true;
    }
    g_sensor.init();
    if (!g_driver.init() ||
        !g_current_sense.init() ||
        !g_sensor.isValid() ||
        !g_foc_motor.init() ||
        !g_foc_motor.initFOC())
    {
        return false;
    }
    g_foc_motor.disable();
    g_closed_loop_initialized = true;
    return true;
}
#endif
#endif

static bool g_direct_sine_open_loop;
static bool g_runtime_open_loop_started;
#if MOTOR_CONTROL_HARDWARE_ENABLED
static uint32_t g_direct_sine_last_us;
static float g_direct_sine_electrical_angle;
#endif
static MotorOpenLoopConfig g_runtime_open_loop_config;

#if MOTOR_CONTROL_HARDWARE_ENABLED
static float ClampUnit(float value)
{
    if (value < 0.0F)
    {
        return 0.0F;
    }
    if (value > 1.0F)
    {
        return 1.0F;
    }
    return value;
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
#if MOTOR_POWER_STAGE_ENABLED
    if (!g_driver.init() || !g_current_sense.init())
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
    if (motor->open_loop_active)
    {
        return;
    }
    if (!currents.sample_valid || !motor->enabled)
    {
        Tc375Hal_SetPwmEnabled(false);
        return;
    }
#if MOTOR_USE_SIMPLEFOC && MOTOR_POWER_STAGE_ENABLED
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
    if (motor->open_loop_active)
    {
        if (!motor->open_loop_output_ready)
        {
            SimpleFocTc375_ForceSafeState();
            g_runtime_open_loop_started = false;
        }
        else if (!g_runtime_open_loop_started)
        {
            if (!SimpleFocTc375_OpenLoopStart(&motor->open_loop))
            {
                MotorControl_TripFault(
                    motor,
                    MOTOR_FAULT_GATE_DRIVER);
                SimpleFocTc375_ForceSafeState();
            }
            else
            {
                g_runtime_open_loop_started = true;
            }
        }
        else
        {
            SimpleFocTc375_OpenLoopStep(
                motor->open_loop_velocity_rad_s);
        }
    }
    else
    {
        if (g_runtime_open_loop_started)
        {
            SimpleFocTc375_OpenLoopStop();
            g_runtime_open_loop_started = false;
        }
        SimpleFocTc375_ForceSafeState();
    }
#if MOTOR_USE_SIMPLEFOC && MOTOR_POWER_STAGE_ENABLED
    if (motor->enabled && !motor->open_loop_active)
    {
        if (!PrepareClosedLoop())
        {
            MotorControl_TripFault(motor, MOTOR_FAULT_ENCODER);
            SimpleFocTc375_ForceSafeState();
        }
        else
        {
            ConfigureSimpleFoc(motor);
            g_foc_motor.updateMotionControlType(
                ToSimpleFocMode(motor->mode));
            g_foc_motor.enable();
            g_foc_motor.move(
                motor->mode == MOTOR_MODE_TORQUE
                    ? motor->target /
                      MOTOR_TORQUE_CONSTANT_NM_PER_A
                    : motor->target);
            g_foc_motor.loopFOC();
        }
    }
#endif
    if (!encoder.valid &&
        motor->enabled &&
        !motor->open_loop_active)
    {
        MotorControl_TripFault(motor, MOTOR_FAULT_ENCODER);
        SimpleFocTc375_ForceSafeState();
    }

#if MOTOR_USE_SIMPLEFOC && MOTOR_POWER_STAGE_ENABLED
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
#if MOTOR_USE_SIMPLEFOC && MOTOR_POWER_STAGE_ENABLED
    if (!g_simplefoc_bound)
    {
        return false;
    }
    g_closed_loop_initialized = false;
    return PrepareClosedLoop();
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
    g_direct_sine_open_loop = false;

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

bool SimpleFocTc375_OpenLoopStart(
    const MotorOpenLoopConfig *config)
{
    if (config == NULL)
    {
        return false;
    }
    memcpy(
        &g_runtime_open_loop_config,
        config,
        sizeof(g_runtime_open_loop_config));
    if (config->backend == MOTOR_OPEN_LOOP_DIRECT_SINE)
    {
#if MOTOR_CONTROL_HARDWARE_ENABLED
        SimpleFocTc375_ForceSafeState();
        if (!Tc375Hal_MotorPeripheralsInit())
        {
            return false;
        }
        g_direct_sine_electrical_angle = 0.0F;
        g_direct_sine_last_us = Tc375Hal_TimeUs();
        g_direct_sine_open_loop = true;
        Tc375Hal_SetPwmEnabled(true);
        Tc375Hal_SetGateEnabled(true);
        if (Tc375Hal_ReadActiveFaults() != 0U)
        {
            SimpleFocTc375_OpenLoopStop();
            return false;
        }
        return true;
#else
        return false;
#endif
    }
    return SimpleFocTc375_OpenLoopInit(
        config->bus_voltage_v,
        config->voltage_limit_v);
}

void SimpleFocTc375_OpenLoopStep(float target_velocity_rad_s)
{
#if MOTOR_CONTROL_HARDWARE_ENABLED
    if (g_direct_sine_open_loop)
    {
        const float two_pi = 6.2831853071795864769F;
        const float phase_shift = 2.0943951023931954923F;
        uint32_t now_us = Tc375Hal_TimeUs();
        uint32_t elapsed_us = now_us - g_direct_sine_last_us;
        float elapsed_s = (float)elapsed_us * 0.000001F;
        float amplitude =
            g_runtime_open_loop_config.voltage_limit_v /
            g_runtime_open_loop_config.bus_voltage_v;
        if (elapsed_s > 0.1F)
        {
            elapsed_s = 0.1F;
        }
        if (amplitude > 0.45F)
        {
            amplitude = 0.45F;
        }
        g_direct_sine_electrical_angle +=
            target_velocity_rad_s *
            (float)g_runtime_open_loop_config.pole_pairs *
            elapsed_s;
        g_direct_sine_electrical_angle =
            fmodf(g_direct_sine_electrical_angle, two_pi);
        if (g_direct_sine_electrical_angle < 0.0F)
        {
            g_direct_sine_electrical_angle += two_pi;
        }
        Tc375Hal_SetPhaseDuty(
            ClampUnit(
                0.5F + amplitude *
                sinf(g_direct_sine_electrical_angle)),
            ClampUnit(
                0.5F + amplitude *
                sinf(g_direct_sine_electrical_angle - phase_shift)),
            ClampUnit(
                0.5F + amplitude *
                sinf(g_direct_sine_electrical_angle + phase_shift)));
        g_direct_sine_last_us = now_us;
        if (Tc375Hal_ReadActiveFaults() != 0U)
        {
            SimpleFocTc375_OpenLoopStop();
        }
        return;
    }
#endif
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
    g_foc_motor.loopFOC();
#else
    (void)target_velocity_rad_s;
#endif
}

void SimpleFocTc375_OpenLoopStop(void)
{
    g_direct_sine_open_loop = false;
#if MOTOR_USE_SIMPLEFOC
    if (g_simplefoc_bound)
    {
        g_foc_motor.disable();
    }
    g_simplefoc_open_loop = false;
#endif
    SimpleFocTc375_ForceSafeState();
}
