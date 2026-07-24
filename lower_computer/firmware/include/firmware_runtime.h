#ifndef FIRMWARE_RUNTIME_H
#define FIRMWARE_RUNTIME_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Cooperative runtime used by the TASKING ADS project until a verified
 * TASKING TriCore FreeRTOS port is available. It uses the same protocol,
 * command router, motor state machine, protection and telemetry as the
 * FreeRTOS application.
 */
bool Firmware_CooperativeInit(void);
void Firmware_CooperativePoll(void);
void Firmware_CooperativeFocAdcIsr(void);

#ifdef __cplusplus
}
#endif

#endif
