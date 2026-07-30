#include "tc375_simplefoc_adapters.hpp"

#if MOTOR_USE_SIMPLEFOC

#include "tc375_hal.h"

static float ClampDuty(float voltage, float supply, float voltage_limit)
{
    if (supply <= 0.0F)
    {
        return 0.0F;
    }

    if (voltage_limit < 0.0F)
    {
        voltage_limit = 0.0F;
    }

    if (voltage_limit > supply)
    {
        voltage_limit = supply;
    }

    if (voltage < 0.0F)
    {
        voltage = 0.0F;
    }

    if (voltage > voltage_limit)
    {
        voltage = voltage_limit;
    }

    float duty = voltage / supply;
    if (duty < 0.0F)
    {
        return 0.0F;
    }
    if (duty > 1.0F)
    {
        return 1.0F;
    }
    return duty;
}

Tc375BldcDriver::Tc375BldcDriver()
{
    pwm_frequency = MOTOR_PWM_FREQUENCY_HZ;
    voltage_power_supply = MOTOR_DEFAULT_BUS_MAX_V;
    voltage_limit = MOTOR_DEFAULT_BUS_MAX_V * 0.5F;
}

int Tc375BldcDriver::init()
{
    /*
     * Initialization is always fail-closed. BLDCMotor::init() calls enable()
     * internally before its stabilization delays; initialization_inhibit_
     * prevents that call from releasing the real gate driver.
     */
    Tc375Hal_SetPwmEnabled(false);
    Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
    (void)Tc375Hal_SetGateEnabled(false);
    output_enabled_ = false;
    initialized = Tc375Hal_MotorPeripheralsInit();
    if (!initialized)
    {
        disable();
    }
    return initialized ? 1 : 0;
}

void Tc375BldcDriver::enable()
{
    /*
     * Never expose stale compare values while changing gate state. A real
     * inverter is enabled in the strict order gate-ready -> PWM; the
     * control-board-only build deliberately keeps the gate inhibited while
     * allowing the MCU TOUT pins to run.
     */
    output_enabled_ = false;
    Tc375Hal_SetPwmEnabled(false);
    Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
    (void)Tc375Hal_SetGateEnabled(false);

#if MOTOR_CONTROL_HARDWARE_ENABLED
    if (initialization_inhibit_ || !initialized)
    {
        return;
    }

#if MOTOR_POWER_STAGE_ENABLED
    if ((Tc375Hal_ReadActiveFaults() != 0U) ||
        !Tc375Hal_SetGateEnabled(true) ||
        !Tc375Hal_IsGateEnabled() ||
        (Tc375Hal_ReadActiveFaults() != 0U))
    {
        disable();
        return;
    }
#else
    /* Compile-time gate lock: SetGateEnabled(true) must never be requested. */
    if (Tc375Hal_IsGateEnabled())
    {
        disable();
        return;
    }
#endif

    Tc375Hal_SetPwmEnabled(true);
    if (!Tc375Hal_IsPwmEnabled())
    {
        disable();
        return;
    }
    output_enabled_ = true;
#endif
}

void Tc375BldcDriver::disable()
{
    output_enabled_ = false;
    Tc375Hal_SetPwmEnabled(false);
    Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
    (void)Tc375Hal_SetGateEnabled(false);
}

void Tc375BldcDriver::setPwm(float ua, float ub, float uc)
{
    dc_a = ClampDuty(ua, voltage_power_supply, voltage_limit);
    dc_b = ClampDuty(ub, voltage_power_supply, voltage_limit);
    dc_c = ClampDuty(uc, voltage_power_supply, voltage_limit);
#if MOTOR_CONTROL_HARDWARE_ENABLED
    if (!output_enabled_)
    {
        Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
        return;
    }
    Tc375Hal_SetPhaseDuty(dc_a, dc_b, dc_c);
#else
    Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
#endif
}

void Tc375BldcDriver::setPhaseState(
    PhaseState sa,
    PhaseState sb,
    PhaseState sc)
{
    bool all_on =
        (sa == PhaseState::PHASE_ON) &&
        (sb == PhaseState::PHASE_ON) &&
        (sc == PhaseState::PHASE_ON);
#if MOTOR_CONTROL_HARDWARE_ENABLED
    Tc375Hal_SetPwmEnabled(all_on && output_enabled_);
#else
    (void)all_on;
    Tc375Hal_SetPwmEnabled(false);
#endif
}

void Tc375BldcDriver::setInitializationInhibit(bool inhibited)
{
    initialization_inhibit_ = inhibited;
    if (inhibited)
    {
        disable();
    }
}

bool Tc375BldcDriver::isOutputEnabled() const
{
    return
        output_enabled_ &&
        Tc375Hal_IsPwmEnabled()
#if MOTOR_POWER_STAGE_ENABLED
        && Tc375Hal_IsGateEnabled()
#else
        && !Tc375Hal_IsGateEnabled()
#endif
        ;
}

void Tc375Encoder::init()
{
    update();
    if (!valid_)
    {
        return;
    }
    Sensor::init();
}

bool Tc375Encoder::isValid() const
{
    return valid_;
}

void Tc375Encoder::update()
{
    Tc375EncoderSample sample = Tc375Hal_ReadEncoder();
    valid_ = sample.valid;
    if (!valid_)
    {
        return;
    }
    mechanical_angle_rad_ = sample.mechanical_angle_rad;
    multi_turn_angle_rad_ = sample.multi_turn_angle_rad;
    velocity_rad_s_ = sample.velocity_rad_s;
}

float Tc375Encoder::getMechanicalAngle()
{
    return mechanical_angle_rad_;
}

float Tc375Encoder::getAngle()
{
    return multi_turn_angle_rad_;
}

double Tc375Encoder::getPreciseAngle()
{
    return (double)multi_turn_angle_rad_;
}

float Tc375Encoder::getVelocity()
{
    return velocity_rad_s_;
}

int32_t Tc375Encoder::getFullRotations()
{
    return (int32_t)(multi_turn_angle_rad_ / _2PI);
}

int Tc375Encoder::needsSearch()
{
    return 0;
}

float Tc375Encoder::getSensorAngle()
{
    return mechanical_angle_rad_;
}

Tc375CurrentSense::Tc375CurrentSense()
{
    pinA = 0;
    pinB = 1;
    pinC = 2;
    gain_a = 1.0F;
    gain_b = 1.0F;
    gain_c = 1.0F;
    offset_ia = 0.0F;
    offset_ib = 0.0F;
    offset_ic = 0.0F;
    skip_align = true;
}

int Tc375CurrentSense::init()
{
    initialized = true;
    return 1;
}

PhaseCurrent_s Tc375CurrentSense::getPhaseCurrents()
{
    Tc375PhaseCurrents currents = Tc375Hal_ReadPhaseCurrents();
    if (!currents.sample_valid)
    {
        return {0.0F, 0.0F, 0.0F};
    }
    return {currents.phase_a, currents.phase_b, currents.phase_c};
}

int Tc375CurrentSense::driverAlign(
    float align_voltage,
    bool modulation_centered)
{
    (void)align_voltage;
    (void)modulation_centered;
    return 1;
}

#endif
