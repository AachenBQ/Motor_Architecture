#include "tc375_hal_stub.h"

#include "project_config.h"

#include <string.h>

typedef struct
{
    bool valid;
    uint8_t bytes[512];
    size_t size;
} MotorPersistentConfigStorage;

static uint64_t g_time_us;
static bool g_gate_enabled;
static bool g_pwm_enabled;
static float g_phase_duty_a;
static float g_phase_duty_b;
static float g_phase_duty_c;
static uint32_t g_active_faults;
static Tc375PhaseCurrents g_phase_currents;
static Tc375EncoderSample g_encoder_sample;
static float g_bus_voltage;
static float g_temperature;
static uint16_t g_uart_rx_isr_entries;
static uint16_t g_uart_rx_poll_drains;
static uint16_t g_uart_rx_poll_bytes;
static MotorPersistentConfigStorage g_storage;

void Tc375HalStub_Reset(void)
{
    memset(&g_storage, 0, sizeof(g_storage));
    g_time_us = 0U;
    g_gate_enabled = false;
    g_pwm_enabled = false;
    g_phase_duty_a = 0.0F;
    g_phase_duty_b = 0.0F;
    g_phase_duty_c = 0.0F;
    g_active_faults = 0U;
    g_phase_currents = (Tc375PhaseCurrents){0.0F, 0.0F, 0.0F, false};
    g_encoder_sample =
        (Tc375EncoderSample){0.0F, 0.0F, 0.0F, true};
    g_bus_voltage = 7.0F;
    g_temperature = 25.0F;
    g_uart_rx_isr_entries = 0U;
    g_uart_rx_poll_drains = 0U;
    g_uart_rx_poll_bytes = 0U;
}

void Tc375HalStub_SetTimeMs(uint64_t time_ms)
{
    g_time_us = time_ms * 1000ULL;
}

void Tc375HalStub_SetPhaseCurrentSample(
    float phase_a,
    float phase_b,
    float phase_c,
    bool valid)
{
    g_phase_currents =
        (Tc375PhaseCurrents){phase_a, phase_b, phase_c, valid};
}

void Tc375HalStub_SetEncoderSample(
    float mechanical_angle_rad,
    float multi_turn_angle_rad,
    float velocity_rad_s,
    bool valid)
{
    g_encoder_sample = (Tc375EncoderSample){
        mechanical_angle_rad,
        multi_turn_angle_rad,
        velocity_rad_s,
        valid};
}

void Tc375HalStub_SetActiveFaults(uint32_t faults)
{
    g_active_faults = faults;
}

void Tc375HalStub_SetBusVoltage(float bus_voltage_v)
{
    g_bus_voltage = bus_voltage_v;
}

void Tc375HalStub_SetPowerTemperature(float temperature_c)
{
    g_temperature = temperature_c;
}

void Tc375HalStub_SetUartRxServiceCounters(
    uint16_t isr_entries,
    uint16_t poll_drains,
    uint16_t poll_bytes)
{
    g_uart_rx_isr_entries = isr_entries;
    g_uart_rx_poll_drains = poll_drains;
    g_uart_rx_poll_bytes = poll_bytes;
}

bool Tc375HalStub_GateEnabled(void)
{
    return g_gate_enabled;
}

bool Tc375HalStub_PwmEnabled(void)
{
    return g_pwm_enabled;
}

void Tc375HalStub_GetPhaseDuty(
    float *phase_a,
    float *phase_b,
    float *phase_c)
{
    *phase_a = g_phase_duty_a;
    *phase_b = g_phase_duty_b;
    *phase_c = g_phase_duty_c;
}

bool Tc375Hal_BoardInit(void)
{
    return true;
}

uint32_t Tc375Hal_TimeMs(void)
{
    return (uint32_t)Tc375Hal_TimeMs64();
}

uint64_t Tc375Hal_TimeMs64(void)
{
    g_time_us += 100ULL;
    return g_time_us / 1000ULL;
}

uint32_t Tc375Hal_TimeUs(void)
{
    g_time_us += 100ULL;
    return (uint32_t)g_time_us;
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

uint16_t Tc375Hal_UartHighPriorityFailures(void)
{
    return 0U;
}

uint16_t Tc375Hal_UartTelemetryDrops(void)
{
    return 0U;
}

uint16_t Tc375Hal_UartRxSwFifoOverflows(void)
{
    return 0U;
}

uint16_t Tc375Hal_UartRxHwFifoOverflows(void)
{
    return 0U;
}

uint16_t Tc375Hal_UartRxFrameErrors(void)
{
    return 0U;
}

uint16_t Tc375Hal_UartRxParityErrors(void)
{
    return 0U;
}

uint16_t Tc375Hal_UartRxIsrEntries(void)
{
    return g_uart_rx_isr_entries;
}

uint16_t Tc375Hal_UartRxPollDrains(void)
{
    return g_uart_rx_poll_drains;
}

uint16_t Tc375Hal_UartRxPollBytes(void)
{
    return g_uart_rx_poll_bytes;
}

bool Tc375Hal_MotorPeripheralsInit(void)
{
    return true;
}

Tc375PhaseCurrents Tc375Hal_ReadPhaseCurrents(void)
{
    return g_phase_currents;
}

Tc375EncoderSample Tc375Hal_ReadEncoder(void)
{
    return g_encoder_sample;
}

float Tc375Hal_ReadBusVoltage(void)
{
    return g_bus_voltage;
}

float Tc375Hal_ReadPowerTemperature(void)
{
    return g_temperature;
}

void Tc375Hal_SetPhaseDuty(float phase_a, float phase_b, float phase_c)
{
    if (!g_pwm_enabled)
    {
        g_phase_duty_a = 0.0F;
        g_phase_duty_b = 0.0F;
        g_phase_duty_c = 0.0F;
        return;
    }
    g_phase_duty_a = phase_a;
    g_phase_duty_b = phase_b;
    g_phase_duty_c = phase_c;
}

void Tc375Hal_SetPwmEnabled(bool enabled)
{
#if MOTOR_CONTROL_HARDWARE_ENABLED
#if MOTOR_POWER_STAGE_ENABLED
    g_pwm_enabled = enabled && g_gate_enabled;
#else
    g_pwm_enabled = enabled;
#endif
#else
    (void)enabled;
    g_pwm_enabled = false;
#endif
    if (!g_pwm_enabled)
    {
        g_phase_duty_a = 0.0F;
        g_phase_duty_b = 0.0F;
        g_phase_duty_c = 0.0F;
    }
}

bool Tc375Hal_SetGateEnabled(bool enabled)
{
#if MOTOR_POWER_STAGE_ENABLED
    if (!enabled)
    {
        Tc375Hal_SetPwmEnabled(false);
        g_gate_enabled = false;
        return true;
    }
    if (g_active_faults != 0U)
    {
        Tc375Hal_SetPwmEnabled(false);
        g_gate_enabled = false;
        return false;
    }
    g_gate_enabled = true;
    return true;
#else
    (void)enabled;
    g_gate_enabled = false;
    return !enabled;
#endif
}

bool Tc375Hal_IsPwmEnabled(void)
{
    return g_pwm_enabled;
}

bool Tc375Hal_IsGateEnabled(void)
{
    return g_gate_enabled;
}

uint32_t Tc375Hal_ReadActiveFaults(void)
{
    return g_active_faults;
}

bool Tc375Hal_LoadCalibration(void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}

bool Tc375Hal_LoadConfiguration(void *data, size_t size)
{
    if (!g_storage.valid || (size > g_storage.size))
    {
        return false;
    }
    memcpy(data, g_storage.bytes, size);
    return true;
}

bool Tc375Hal_SaveConfiguration(const void *data, size_t size)
{
    if (size > sizeof(g_storage.bytes))
    {
        return false;
    }
    memcpy(g_storage.bytes, data, size);
    g_storage.size = size;
    g_storage.valid = true;
    return true;
}
