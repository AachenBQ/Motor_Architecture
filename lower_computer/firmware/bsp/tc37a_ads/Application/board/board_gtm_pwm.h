#ifndef BOARD_GTM_PWM_H
#define BOARD_GTM_PWM_H

#include "Ifx_Types.h"
#include "Gtm/Pwm/IfxGtm_Pwm.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BOARD_GTM_PWM_PHASE_COUNT 3u

typedef enum
{
    BoardGtmPwmPhase_U = 0,
    BoardGtmPwmPhase_V = 1,
    BoardGtmPwmPhase_W = 2
} BoardGtmPwmPhase;

typedef struct
{
    float32 u;
    float32 v;
    float32 w;
} BoardGtmPwmDutyPercent;

typedef struct
{
    uint32 frequencyHz;
    float32 risingDeadTimeS;
    float32 fallingDeadTimeS;
} BoardGtmPwmSettings;

void BoardGtmPwm_init(void);
void BoardGtmPwm_startTiming(void);
void BoardGtmPwm_stopTiming(void);
void BoardGtmPwm_setDutyPercent(float32 phaseU, float32 phaseV, float32 phaseW);
void BoardGtmPwm_setDutyFrame(const BoardGtmPwmDutyPercent *duty);
void BoardGtmPwm_setSafeState(void);

boolean BoardGtmPwm_isInitialized(void);
boolean BoardGtmPwm_isRunning(void);
IfxGtm_Pwm *BoardGtmPwm_getHandle(void);
const BoardGtmPwmSettings *BoardGtmPwm_getSettings(void);

#ifdef __cplusplus
}
#endif

#endif