#include "tc375_hal.h"

#include "DRV8313_handle.h"
#include "GTM_ATOM_3_Phase_Inverter_PWM.h"

#include "Bsp.h"
#include "IfxStm.h"

#ifndef TC375_HAL_ADS_BUS_VOLTAGE_V
#define TC375_HAL_ADS_BUS_VOLTAGE_V (24.0f)
#endif

#ifndef TC375_HAL_ADS_TEMPERATURE_C
#define TC375_HAL_ADS_TEMPERATURE_C (25.0f)
#endif

#define TC375_HAL_FAULT_GATE_DRIVER (1UL << 5)

static boolean g_motor_peripherals_initialized = FALSE;
static boolean g_pwm_enabled = FALSE;
static boolean g_gate_enabled = FALSE;

static float Tc375Hal_ClampUnitDuty(float duty)
{
    if (duty < 0.0f)
    {
        return 0.0f;
    }

    if (duty > 1.0f)
    {
        return 1.0f;
    }

    return duty;
}

bool Tc375Hal_BoardInit(void)
{
    return true;
}

uint32_t Tc375Hal_TimeMs(void)
{
    return Tc375Hal_TimeUs() / 1000U;
}

uint32_t Tc375Hal_TimeUs(void)
{
    uint32 ticks;
    uint32 frequency_hz;

    ticks = IfxStm_getLower(BSP_DEFAULT_TIMER);
    frequency_hz = (uint32)IfxStm_getFrequency(BSP_DEFAULT_TIMER);

    if (frequency_hz == 0U)
    {
        return 0U;
    }

    return (uint32_t)(((uint64)ticks * 1000000ULL) / (uint64)frequency_hz);
}

void Tc375Hal_ServiceWatchdogs(void)
{
}

size_t Tc375Hal_UartRead(uint8_t *destination, size_t capacity)
{
    (void)destination;
    (void)capacity;
    return 0U;
}

bool Tc375Hal_UartQueueTx(
    const uint8_t *data,
    size_t length,
    bool high_priority)
{
    (void)data;
    (void)length;
    (void)high_priority;
    return true;
}

bool Tc375Hal_MotorPeripheralsInit(void)
{
    if (g_motor_peripherals_initialized == FALSE)
    {
        Drv8313_init();
        initGtmAtom3phInv();
        GtmAtom3phInv_setSafeDuty();
        g_motor_peripherals_initialized = TRUE;
    }

    return true;
}

Tc375PhaseCurrents Tc375Hal_ReadPhaseCurrents(void)
{
    Tc375PhaseCurrents currents;

    currents.phase_a = 0.0f;
    currents.phase_b = 0.0f;
    currents.phase_c = 0.0f;
    currents.sample_valid = false;

    return currents;
}

Tc375EncoderSample Tc375Hal_ReadEncoder(void)
{
    Tc375EncoderSample sample;

    sample.mechanical_angle_rad = 0.0f;
    sample.multi_turn_angle_rad = 0.0f;
    sample.velocity_rad_s = 0.0f;
    sample.valid = false;

    return sample;
}

float Tc375Hal_ReadBusVoltage(void)
{
    return TC375_HAL_ADS_BUS_VOLTAGE_V;
}

float Tc375Hal_ReadPowerTemperature(void)
{
    return TC375_HAL_ADS_TEMPERATURE_C;
}

void Tc375Hal_SetPhaseDuty(float phase_a, float phase_b, float phase_c)
{
    float duty_u;
    float duty_v;
    float duty_w;

    if ((g_pwm_enabled == FALSE) || (g_gate_enabled == FALSE))
    {
        GtmAtom3phInv_setSafeDuty();
        return;
    }

    duty_u = Tc375Hal_ClampUnitDuty(phase_a) * 100.0f;
    duty_v = Tc375Hal_ClampUnitDuty(phase_b) * 100.0f;
    duty_w = Tc375Hal_ClampUnitDuty(phase_c) * 100.0f;

    GtmAtom3phInv_setDuty(duty_u, duty_v, duty_w);
}

void Tc375Hal_SetPwmEnabled(bool enabled)
{
    g_pwm_enabled = enabled ? TRUE : FALSE;

    if (g_pwm_enabled == FALSE)
    {
        GtmAtom3phInv_setSafeDuty();
    }
}

void Tc375Hal_SetGateEnabled(bool enabled)
{
    if (enabled)
    {
        if (Tc375Hal_MotorPeripheralsInit() == true)
        {
            Drv8313_enable();
            g_gate_enabled = (Drv8313_getStatus() == DRV8313_STATUS_READY) ? TRUE : FALSE;
        }
    }
    else
    {
        GtmAtom3phInv_setSafeDuty();
        Drv8313_disable();
        g_gate_enabled = FALSE;
    }
}

uint32_t Tc375Hal_ReadActiveFaults(void)
{
    if (Drv8313_hasFault() == TRUE)
    {
        return TC375_HAL_FAULT_GATE_DRIVER;
    }

    return 0U;
}

bool Tc375Hal_LoadCalibration(void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}

bool Tc375Hal_LoadConfiguration(void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}

bool Tc375Hal_SaveConfiguration(const void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}
