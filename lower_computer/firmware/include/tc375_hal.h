#ifndef TC375_HAL_H
#define TC375_HAL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct
{
    float phase_a;
    float phase_b;
    float phase_c;
    bool sample_valid;
} Tc375PhaseCurrents;

typedef struct
{
    float mechanical_angle_rad;
    float multi_turn_angle_rad;
    float velocity_rad_s;
    bool valid;
} Tc375EncoderSample;

/* BSP / time */
bool Tc375Hal_BoardInit(void);
uint32_t Tc375Hal_TimeMs(void);
uint64_t Tc375Hal_TimeMs64(void);
uint32_t Tc375Hal_TimeUs(void);
void Tc375Hal_ServiceWatchdogs(void);

/* UART must be non-blocking. */
size_t Tc375Hal_UartRead(uint8_t *destination, size_t capacity);
bool Tc375Hal_UartQueueTx(const uint8_t *data, size_t length, bool high_priority);
uint16_t Tc375Hal_UartHighPriorityFailures(void);
uint16_t Tc375Hal_UartTelemetryDrops(void);
uint16_t Tc375Hal_UartRxSwFifoOverflows(void);
uint16_t Tc375Hal_UartRxHwFifoOverflows(void);
uint16_t Tc375Hal_UartRxFrameErrors(void);
uint16_t Tc375Hal_UartRxParityErrors(void);
uint16_t Tc375Hal_UartRxIsrEntries(void);
uint16_t Tc375Hal_UartRxPollDrains(void);
uint16_t Tc375Hal_UartRxPollBytes(void);

/* Motor peripherals. */
bool Tc375Hal_MotorPeripheralsInit(void);
Tc375PhaseCurrents Tc375Hal_ReadPhaseCurrents(void);
Tc375EncoderSample Tc375Hal_ReadEncoder(void);
float Tc375Hal_ReadBusVoltage(void);
float Tc375Hal_ReadPowerTemperature(void);
void Tc375Hal_SetPhaseDuty(float phase_a, float phase_b, float phase_c);
void Tc375Hal_SetPwmEnabled(bool enabled);
bool Tc375Hal_SetGateEnabled(bool enabled);
bool Tc375Hal_IsPwmEnabled(void);
bool Tc375Hal_IsGateEnabled(void);
uint32_t Tc375Hal_ReadActiveFaults(void);

/* Flash operations are allowed only while the motor is disabled. */
bool Tc375Hal_LoadCalibration(void *data, size_t size);
bool Tc375Hal_LoadConfiguration(void *data, size_t size);
bool Tc375Hal_SaveConfiguration(const void *data, size_t size);

#ifdef __cplusplus
}
#endif

#endif
