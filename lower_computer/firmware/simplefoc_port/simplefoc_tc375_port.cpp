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

static bool g_current_sense_ready;

#if MOTOR_USE_SIMPLEFOC
static BLDCMotor g_foc_motor(MOTOR_POLE_PAIRS);
static Tc375BldcDriver g_driver;
static Tc375CurrentSense g_current_sense;
static Tc375Encoder g_sensor;
static bool g_simplefoc_bound;
static bool g_simplefoc_core_initialized;
static bool g_simplefoc_open_loop;
#if MOTOR_POWER_STAGE_ENABLED
static bool g_closed_loop_initialized;
static bool g_closed_loop_running;
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

static bool InitializeSimpleFocCoreSafely(void)
{
    bool driver_initialized;
    bool motor_initialized = false;

    if (g_simplefoc_core_initialized)
    {
        return true;
    }
    if (!g_simplefoc_bound)
    {
        return false;
    }

    /*
     * BLDCMotor::init() calls driver->enable() before two stabilization
     * delays. Keep that internal enable call inhibited so a real inverter can
     * never sit energized while initialization blocks for roughly one second.
     */
    SimpleFocTc375_ForceSafeState();
    g_driver.setInitializationInhibit(true);
    driver_initialized = g_driver.init() != 0;
    if (driver_initialized)
    {
        motor_initialized = g_foc_motor.init() != 0;
    }

    if (motor_initialized)
    {
        g_foc_motor.disable();
    }
    else
    {
        g_driver.disable();
    }
    g_driver.setInitializationInhibit(false);

    if (!driver_initialized || !motor_initialized)
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }

    g_simplefoc_core_initialized = true;
    return true;
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
#if !MOTOR_PHASE_CURRENT_SENSE_READY || \
    !MOTOR_ENCODER_SENSE_READY || \
    !MOTOR_CLOSED_LOOP_CONTROL_READY
    /*
     * A build may use the commissioning override for open-loop bring-up, but
     * closed-loop FOC remains unavailable until every feedback path has
     * explicit implementation evidence.
     */
    return false;
#else
    bool foc_initialized;

    if (g_closed_loop_initialized)
    {
        return true;
    }
    SimpleFocTc375_ForceSafeState();
    g_sensor.init();
    if (!g_current_sense_ready)
    {
        g_current_sense_ready =
            g_current_sense.init() != 0;
    }
    if (!g_current_sense_ready ||
        !g_sensor.isValid() ||
        !InitializeSimpleFocCoreSafely())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }

    /*
     * Sensor alignment requires an energized motor. Gate validation is
     * therefore completed before PWM is admitted, and every failure returns
     * through the same fail-closed path.
     */
    g_foc_motor.enable();
    if (!g_driver.isOutputEnabled())
    {
        g_foc_motor.disable();
        SimpleFocTc375_ForceSafeState();
        return false;
    }
    foc_initialized = g_foc_motor.initFOC() != 0;
    g_foc_motor.disable();
    SimpleFocTc375_ForceSafeState();
    if (!foc_initialized)
    {
        return false;
    }
    g_closed_loop_initialized = true;
    return true;
#endif
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

#if MOTOR_CONTROL_HARDWARE_ENABLED
static bool EnableHardwareOutputSafely(void)
{
    /*
     * Start from an unambiguous safe state. On real power hardware the HAL
     * must positively confirm gate READY before PWM can be admitted.
     */
    Tc375Hal_SetPwmEnabled(false);
    Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
    (void)Tc375Hal_SetGateEnabled(false);

#if MOTOR_POWER_STAGE_ENABLED
    if ((Tc375Hal_ReadActiveFaults() != 0U) ||
        !Tc375Hal_SetGateEnabled(true) ||
        !Tc375Hal_IsGateEnabled() ||
        (Tc375Hal_ReadActiveFaults() != 0U))
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }
#else
    /*
     * Control-board commissioning intentionally leaves the physical gate
     * inhibited while allowing the three MCU TOUT signals to be observed.
     */
    if (Tc375Hal_IsGateEnabled())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }
#endif

    Tc375Hal_SetPwmEnabled(true);
    if (!Tc375Hal_IsPwmEnabled())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }
    return true;
}
#endif

#if MOTOR_POWER_STAGE_ENABLED && MOTOR_PHASE_CURRENT_SENSE_READY
static bool PhaseCurrentExceedsLimit(
    const Tc375PhaseCurrents *currents,
    float limit_a)
{
    return
        (fabsf(currents->phase_a) > limit_a) ||
        (fabsf(currents->phase_b) > limit_a) ||
        (fabsf(currents->phase_c) > limit_a);
}
#endif

bool SimpleFocTc375_Init(MotorControl *motor)
{
    SimpleFocTc375_ForceSafeState();
    g_current_sense_ready = false;
    if (!Tc375Hal_MotorPeripheralsInit())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }
#if MOTOR_USE_SIMPLEFOC
    ConfigureSimpleFoc(motor);
    g_foc_motor.linkDriver(&g_driver);
    g_foc_motor.linkSensor(&g_sensor);
    g_current_sense.linkDriver(&g_driver);
    g_foc_motor.linkCurrentSense(&g_current_sense);
    g_simplefoc_bound = true;

    /*
     * Complete BLDCMotor::init() at boot with its internal driver enable
     * inhibited. The first runtime start is then non-blocking and cannot
     * consume the heartbeat lease before the gate is validated.
     */
    if (!InitializeSimpleFocCoreSafely())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }

#if MOTOR_POWER_STAGE_ENABLED && MOTOR_PHASE_CURRENT_SENSE_READY
    g_current_sense_ready =
        g_current_sense.init() != 0;
    if (!g_current_sense_ready)
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }
#endif
    g_foc_motor.disable();
#else
    (void)motor;
#endif
    SimpleFocTc375_ForceSafeState();
    return true;
}

void SimpleFocTc375_AdcPwmIsr(MotorControl *motor)
{
    Tc375PhaseCurrents currents;

    if (motor->open_loop_active)
    {
#if MOTOR_POWER_STAGE_ENABLED && MOTOR_PHASE_CURRENT_SENSE_READY
        if (g_current_sense_ready)
        {
            currents = Tc375Hal_ReadPhaseCurrents();
            if (!currents.sample_valid)
            {
                MotorControl_TripFault(
                    motor,
                    MOTOR_FAULT_CURRENT_SENSOR);
                SimpleFocTc375_ForceSafeState();
                return;
            }
            if (PhaseCurrentExceedsLimit(
                    &currents,
                    motor->limits.current_a))
            {
                MotorControl_TripFault(
                    motor,
                    MOTOR_FAULT_OVERCURRENT);
                SimpleFocTc375_ForceSafeState();
            }
        }
#endif
        return;
    }

    if (!motor->enabled)
    {
        SimpleFocTc375_ForceSafeState();
        return;
    }

#if MOTOR_POWER_STAGE_ENABLED && MOTOR_PHASE_CURRENT_SENSE_READY
    if (!g_current_sense_ready)
    {
        MotorControl_TripFault(
            motor,
            MOTOR_FAULT_CURRENT_SENSOR);
        SimpleFocTc375_ForceSafeState();
        return;
    }
    currents = Tc375Hal_ReadPhaseCurrents();
    if (!currents.sample_valid)
    {
        MotorControl_TripFault(
            motor,
            MOTOR_FAULT_CURRENT_SENSOR);
        SimpleFocTc375_ForceSafeState();
        return;
    }
    if (PhaseCurrentExceedsLimit(
            &currents,
            motor->limits.current_a))
    {
        MotorControl_TripFault(
            motor,
            MOTOR_FAULT_OVERCURRENT);
        SimpleFocTc375_ForceSafeState();
        return;
    }
#else
    currents = Tc375Hal_ReadPhaseCurrents();
    (void)currents;
#endif

#if MOTOR_USE_SIMPLEFOC && MOTOR_POWER_STAGE_ENABLED
    if (g_simplefoc_bound &&
        g_driver.isOutputEnabled())
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
            if (!g_closed_loop_running)
            {
                g_foc_motor.enable();
                if (!g_driver.isOutputEnabled())
                {
                    MotorControl_TripFault(
                        motor,
                        MOTOR_FAULT_GATE_DRIVER);
                    g_foc_motor.disable();
                    SimpleFocTc375_ForceSafeState();
                }
                else
                {
                    g_closed_loop_running = true;
                }
            }
            if (g_closed_loop_running)
            {
                g_foc_motor.move(
                    motor->mode == MOTOR_MODE_TORQUE
                        ? motor->target /
                          MOTOR_TORQUE_CONSTANT_NM_PER_A
                        : motor->target);
                g_foc_motor.loopFOC();
            }
        }
    }
    else if (g_closed_loop_running)
    {
        g_foc_motor.disable();
        g_closed_loop_running = false;
        SimpleFocTc375_ForceSafeState();
    }
#endif
    if (!encoder.valid &&
        motor->enabled &&
        !motor->open_loop_active)
    {
        MotorControl_TripFault(motor, MOTOR_FAULT_ENCODER);
        SimpleFocTc375_ForceSafeState();
    }

#if MOTOR_USE_SIMPLEFOC && \
    MOTOR_POWER_STAGE_ENABLED && \
    MOTOR_PHASE_CURRENT_SENSE_READY
    telemetry.iq_current_a = g_foc_motor.current.q;
#else
    telemetry.iq_current_a = 0.0F;
#endif

    telemetry.speed_rad_s = encoder.velocity_rad_s;
#if MOTOR_BUS_VOLTAGE_SENSE_READY
    telemetry.bus_voltage_v = Tc375Hal_ReadBusVoltage();
#else
    /*
     * Zero means "not available" to MotorControl_UpdateTelemetry(), avoiding
     * false voltage trips from placeholder HAL constants.
     */
    telemetry.bus_voltage_v = 0.0F;
#endif
#if MOTOR_POWER_TEMPERATURE_SENSE_READY
    telemetry.temperature_c = Tc375Hal_ReadPowerTemperature();
#else
    telemetry.temperature_c = 0.0F;
#endif
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
    if (g_closed_loop_running)
    {
        g_foc_motor.disable();
        g_closed_loop_running = false;
    }
    SimpleFocTc375_ForceSafeState();
    g_closed_loop_initialized = false;
    return PrepareClosedLoop();
#else
    return false;
#endif
}

void SimpleFocTc375_ForceSafeState(void)
{
    Tc375Hal_SetPwmEnabled(false);
    Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
    (void)Tc375Hal_SetGateEnabled(false);
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
    /*
     * The driver converts absolute phase voltages to duty cycle using the
     * full DC bus. Keep the requested open-loop voltage limit on the motor;
     * applying it to the driver as well moves the SinePWM common mode close
     * to 0% duty instead of centering it around 50%.
     */
    g_driver.voltage_limit = bus_voltage;

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

    if (!InitializeSimpleFocCoreSafely())
    {
        SimpleFocTc375_ForceSafeState();
        return false;
    }

    g_foc_motor.enable();
    if (!g_driver.isOutputEnabled() ||
        (Tc375Hal_ReadActiveFaults() != 0U))
    {
        g_foc_motor.disable();
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
        if (!EnableHardwareOutputSafely() ||
            (Tc375Hal_ReadActiveFaults() != 0U))
        {
            SimpleFocTc375_OpenLoopStop();
            return false;
        }
        g_direct_sine_open_loop = true;
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
        if (!Tc375Hal_IsPwmEnabled()
#if MOTOR_POWER_STAGE_ENABLED
            || !Tc375Hal_IsGateEnabled()
#else
            || Tc375Hal_IsGateEnabled()
#endif
            )
        {
            SimpleFocTc375_OpenLoopStop();
            return;
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
    if (!g_simplefoc_open_loop ||
        !g_simplefoc_bound ||
        !g_driver.isOutputEnabled())
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
