#ifndef TC375_HAL_STUB_H
#define TC375_HAL_STUB_H

#include "tc375_hal.h"

#ifdef __cplusplus
extern "C" {
#endif

void Tc375HalStub_Reset(void);
void Tc375HalStub_SetPhaseCurrentSample(
    float phase_a,
    float phase_b,
    float phase_c,
    bool valid);
void Tc375HalStub_SetEncoderSample(
    float mechanical_angle_rad,
    float multi_turn_angle_rad,
    float velocity_rad_s,
    bool valid);
void Tc375HalStub_SetActiveFaults(uint32_t faults);
bool Tc375HalStub_GateEnabled(void);
bool Tc375HalStub_PwmEnabled(void);

#ifdef __cplusplus
}
#endif

#endif
