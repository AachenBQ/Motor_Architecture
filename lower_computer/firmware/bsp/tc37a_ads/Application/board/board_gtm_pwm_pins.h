#ifndef BOARD_GTM_PWM_PINS_H
#define BOARD_GTM_PWM_PINS_H

#include "project_config.h"
#include "Ifx_Types.h"
#include "Gtm/Pwm/IfxGtm_Pwm.h"

#ifndef BOARD_GTM_PWM_ENABLE_OUTPUT_PINS
#define BOARD_GTM_PWM_ENABLE_OUTPUT_PINS MOTOR_REAL_HARDWARE_ENABLED
#endif

#ifndef BOARD_GTM_PWM_USE_TC387_APPKIT_P02_PINMAP
#define BOARD_GTM_PWM_USE_TC387_APPKIT_P02_PINMAP 0
#endif

#if BOARD_GTM_PWM_ENABLE_OUTPUT_PINS
#if BOARD_GTM_PWM_USE_TC387_APPKIT_P02_PINMAP
#include "IfxGtm_PinMap.h"
#define BOARD_GTM_PWM_PHASE_U_HS_PIN ((IfxGtm_Pwm_ToutMap *)&IfxGtm_ATOM1_0_TOUT0_P02_0_OUT)
#define BOARD_GTM_PWM_PHASE_U_LS_PIN ((IfxGtm_Pwm_ToutMap *)&IfxGtm_ATOM1_0N_TOUT7_P02_7_OUT)
#define BOARD_GTM_PWM_PHASE_V_HS_PIN ((IfxGtm_Pwm_ToutMap *)&IfxGtm_ATOM1_1_TOUT1_P02_1_OUT)
#define BOARD_GTM_PWM_PHASE_V_LS_PIN ((IfxGtm_Pwm_ToutMap *)&IfxGtm_ATOM1_1N_TOUT4_P02_4_OUT)
#define BOARD_GTM_PWM_PHASE_W_HS_PIN ((IfxGtm_Pwm_ToutMap *)&IfxGtm_ATOM1_2_TOUT2_P02_2_OUT)
#define BOARD_GTM_PWM_PHASE_W_LS_PIN ((IfxGtm_Pwm_ToutMap *)&IfxGtm_ATOM1_2N_TOUT5_P02_5_OUT)
#else
#error "BOARD_GTM_PWM_ENABLE_OUTPUT_PINS requires a confirmed board pin map. Define one here before enabling power outputs."
#endif
#else
#define BOARD_GTM_PWM_PHASE_U_HS_PIN NULL_PTR
#define BOARD_GTM_PWM_PHASE_U_LS_PIN NULL_PTR
#define BOARD_GTM_PWM_PHASE_V_HS_PIN NULL_PTR
#define BOARD_GTM_PWM_PHASE_V_LS_PIN NULL_PTR
#define BOARD_GTM_PWM_PHASE_W_HS_PIN NULL_PTR
#define BOARD_GTM_PWM_PHASE_W_LS_PIN NULL_PTR
#endif

#endif