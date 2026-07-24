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
    initialized = Tc375Hal_MotorPeripheralsInit();
    disable();
    return initialized ? 1 : 0;
}

void Tc375BldcDriver::enable()
{
#if MOTOR_CONTROL_HARDWARE_ENABLED
    Tc375Hal_SetPwmEnabled(true);
#if MOTOR_POWER_STAGE_ENABLED
    Tc375Hal_SetGateEnabled(true);
#else
    Tc375Hal_SetGateEnabled(false);
#endif
#endif
}

void Tc375BldcDriver::disable()
{
    Tc375Hal_SetPhaseDuty(0.0F, 0.0F, 0.0F);
    Tc375Hal_SetPwmEnabled(false);
    Tc375Hal_SetGateEnabled(false);
}

void Tc375BldcDriver::setPwm(float ua, float ub, float uc)
{
    dc_a = ClampDuty(ua, voltage_power_supply, voltage_limit);
    dc_b = ClampDuty(ub, voltage_power_supply, voltage_limit);
    dc_c = ClampDuty(uc, voltage_power_supply, voltage_limit);
#if MOTOR_CONTROL_HARDWARE_ENABLED
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
    Tc375Hal_SetPwmEnabled(all_on);
#else
    (void)all_on;
    Tc375Hal_SetPwmEnabled(false);
#endif
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
