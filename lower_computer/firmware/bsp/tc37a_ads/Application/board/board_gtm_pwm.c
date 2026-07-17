#include "board_gtm_pwm.h"

#include "board_gtm_pwm_pins.h"
#include "project_config.h"

#include "Gtm/Pwm/IfxGtm_Pwm.h"
#include "Gtm/Std/IfxGtm.h"

#ifndef BOARD_GTM_PWM_CLUSTER
#define BOARD_GTM_PWM_CLUSTER IfxGtm_Cluster_1
#endif

#ifndef BOARD_GTM_PWM_CLOCK_SOURCE
#define BOARD_GTM_PWM_CLOCK_SOURCE IfxGtm_Cmu_Clk_0
#endif

#ifndef BOARD_GTM_PWM_DTM_CLOCK_SOURCE
#define BOARD_GTM_PWM_DTM_CLOCK_SOURCE IfxGtm_Dtm_ClockSource_cmuClock0
#endif

#ifndef BOARD_GTM_PWM_RISING_DEAD_TIME_S
#define BOARD_GTM_PWM_RISING_DEAD_TIME_S 1.0e-6f
#endif

#ifndef BOARD_GTM_PWM_FALLING_DEAD_TIME_S
#define BOARD_GTM_PWM_FALLING_DEAD_TIME_S 1.0e-6f
#endif

typedef struct
{
    IfxGtm_Pwm pwm;
    IfxGtm_Pwm_Channel channels[BOARD_GTM_PWM_PHASE_COUNT];
    float32 duty[BOARD_GTM_PWM_PHASE_COUNT];
    IfxGtm_Pwm_DeadTime deadTime[BOARD_GTM_PWM_PHASE_COUNT];
    BoardGtmPwmSettings settings;
    boolean initialized;
    boolean running;
} BoardGtmPwmState;

static BoardGtmPwmState g_boardGtmPwm;

static float32 BoardGtmPwm_clampDuty(float32 duty)
{
    if (duty < 0.0f)
    {
        return 0.0f;
    }

    if (duty > 100.0f)
    {
        return 100.0f;
    }

    return duty;
}

static void BoardGtmPwm_enableGtmClock(void)
{
    if (IfxGtm_isEnabled(&MODULE_GTM) == FALSE)
    {
        IfxGtm_enable(&MODULE_GTM);
    }

    float32 moduleFrequency = IfxGtm_Cmu_getModuleFrequency(&MODULE_GTM);
    IfxGtm_Cmu_setGclkFrequency(&MODULE_GTM, moduleFrequency);
    IfxGtm_Cmu_setClkFrequency(&MODULE_GTM, BOARD_GTM_PWM_CLOCK_SOURCE, moduleFrequency);
    IfxGtm_Cmu_enableClocks(&MODULE_GTM, IFXGTM_CMU_CLKEN_CLK0);
}

#if BOARD_GTM_PWM_ENABLE_OUTPUT_PINS
static void BoardGtmPwm_fillOutput(IfxGtm_Pwm_OutputConfig *output,
                                   IfxGtm_Pwm_ToutMap *highSide,
                                   IfxGtm_Pwm_ToutMap *lowSide)
{
    output->pin = highSide;
    output->complementaryPin = lowSide;
    output->polarity = Ifx_ActiveState_high;
    output->complementaryPolarity = Ifx_ActiveState_low;
    output->outputMode = IfxPort_OutputMode_pushPull;
    output->padDriver = IfxPort_PadDriver_cmosAutomotiveSpeed1;
}
#endif

static void BoardGtmPwm_initChannel(IfxGtm_Pwm_ChannelConfig *channel,
                                    IfxGtm_Pwm_SubModule_Ch timerChannel,
                                    float32 duty,
                                    IfxGtm_Pwm_DtmConfig *deadTime,
                                    IfxGtm_Pwm_OutputConfig *output,
                                    IfxGtm_Pwm_InterruptConfig *interrupt)
{
    IfxGtm_Pwm_initChannelConfig(channel);
    channel->timerCh = timerChannel;
    channel->phase = 0.0f;
    channel->duty = duty;
    channel->dtm = deadTime;
    channel->output = output;
#ifndef DEVICE_TC33X
    channel->mscOut = NULL_PTR;
#endif
    channel->interrupt = interrupt;
}

void BoardGtmPwm_init(void)
{
    if (g_boardGtmPwm.initialized == TRUE)
    {
        return;
    }

    IfxGtm_Pwm_Config config;
    IfxGtm_Pwm_ChannelConfig channelConfig[BOARD_GTM_PWM_PHASE_COUNT];
    IfxGtm_Pwm_DtmConfig dtmConfig[BOARD_GTM_PWM_PHASE_COUNT];
    IfxGtm_Pwm_OutputConfig *outputs[BOARD_GTM_PWM_PHASE_COUNT] = {NULL_PTR, NULL_PTR, NULL_PTR};
#if BOARD_GTM_PWM_ENABLE_OUTPUT_PINS
    IfxGtm_Pwm_OutputConfig outputConfig[BOARD_GTM_PWM_PHASE_COUNT];

    BoardGtmPwm_fillOutput(&outputConfig[BoardGtmPwmPhase_U],
                           BOARD_GTM_PWM_PHASE_U_HS_PIN,
                           BOARD_GTM_PWM_PHASE_U_LS_PIN);
    BoardGtmPwm_fillOutput(&outputConfig[BoardGtmPwmPhase_V],
                           BOARD_GTM_PWM_PHASE_V_HS_PIN,
                           BOARD_GTM_PWM_PHASE_V_LS_PIN);
    BoardGtmPwm_fillOutput(&outputConfig[BoardGtmPwmPhase_W],
                           BOARD_GTM_PWM_PHASE_W_HS_PIN,
                           BOARD_GTM_PWM_PHASE_W_LS_PIN);

    outputs[BoardGtmPwmPhase_U] = &outputConfig[BoardGtmPwmPhase_U];
    outputs[BoardGtmPwmPhase_V] = &outputConfig[BoardGtmPwmPhase_V];
    outputs[BoardGtmPwmPhase_W] = &outputConfig[BoardGtmPwmPhase_W];
#endif

    IfxGtm_Pwm_initConfig(&config, &MODULE_GTM);

    for (uint8 channel = 0u; channel < BOARD_GTM_PWM_PHASE_COUNT; ++channel)
    {
        dtmConfig[channel].deadTime.rising = BOARD_GTM_PWM_RISING_DEAD_TIME_S;
        dtmConfig[channel].deadTime.falling = BOARD_GTM_PWM_FALLING_DEAD_TIME_S;
        g_boardGtmPwm.deadTime[channel] = dtmConfig[channel].deadTime;
        g_boardGtmPwm.duty[channel] = 0.0f;
    }

    BoardGtmPwm_initChannel(&channelConfig[BoardGtmPwmPhase_U],
                            IfxGtm_Pwm_SubModule_Ch_0,
                            g_boardGtmPwm.duty[BoardGtmPwmPhase_U],
                            &dtmConfig[BoardGtmPwmPhase_U],
                            outputs[BoardGtmPwmPhase_U],
                            NULL_PTR);
    BoardGtmPwm_initChannel(&channelConfig[BoardGtmPwmPhase_V],
                            IfxGtm_Pwm_SubModule_Ch_1,
                            g_boardGtmPwm.duty[BoardGtmPwmPhase_V],
                            &dtmConfig[BoardGtmPwmPhase_V],
                            outputs[BoardGtmPwmPhase_V],
                            NULL_PTR);
    BoardGtmPwm_initChannel(&channelConfig[BoardGtmPwmPhase_W],
                            IfxGtm_Pwm_SubModule_Ch_2,
                            g_boardGtmPwm.duty[BoardGtmPwmPhase_W],
                            &dtmConfig[BoardGtmPwmPhase_W],
                            outputs[BoardGtmPwmPhase_W],
                            NULL_PTR);

    config.cluster = BOARD_GTM_PWM_CLUSTER;
    config.subModule = IfxGtm_Pwm_SubModule_atom;
    config.alignment = IfxGtm_Pwm_Alignment_center;
    config.numChannels = BOARD_GTM_PWM_PHASE_COUNT;
    config.channels = channelConfig;
    config.frequency = (float32)MOTOR_PWM_FREQUENCY_HZ;
    config.clockSource.atom = BOARD_GTM_PWM_CLOCK_SOURCE;
    config.dtmClockSource = BOARD_GTM_PWM_DTM_CLOCK_SOURCE;
    config.syncUpdateEnabled = TRUE;
    config.syncStart = FALSE;

    BoardGtmPwm_enableGtmClock();
    IfxGtm_Pwm_init(&g_boardGtmPwm.pwm, &g_boardGtmPwm.channels[0], &config);

    g_boardGtmPwm.settings.frequencyHz = (uint32)MOTOR_PWM_FREQUENCY_HZ;
    g_boardGtmPwm.settings.risingDeadTimeS = BOARD_GTM_PWM_RISING_DEAD_TIME_S;
    g_boardGtmPwm.settings.fallingDeadTimeS = BOARD_GTM_PWM_FALLING_DEAD_TIME_S;
    g_boardGtmPwm.initialized = TRUE;
    g_boardGtmPwm.running = FALSE;
}

void BoardGtmPwm_startTiming(void)
{
    if (g_boardGtmPwm.initialized == FALSE)
    {
        BoardGtmPwm_init();
    }

    if (g_boardGtmPwm.running == FALSE)
    {
        IfxGtm_Pwm_startSyncedChannels(&g_boardGtmPwm.pwm);
        g_boardGtmPwm.running = TRUE;
    }
}

void BoardGtmPwm_stopTiming(void)
{
    if ((g_boardGtmPwm.initialized == TRUE) && (g_boardGtmPwm.running == TRUE))
    {
        IfxGtm_Pwm_stopSyncedChannels(&g_boardGtmPwm.pwm);
        g_boardGtmPwm.running = FALSE;
    }
}

void BoardGtmPwm_setDutyPercent(float32 phaseU, float32 phaseV, float32 phaseW)
{
    if (g_boardGtmPwm.initialized == FALSE)
    {
        BoardGtmPwm_init();
    }

    g_boardGtmPwm.duty[BoardGtmPwmPhase_U] = BoardGtmPwm_clampDuty(phaseU);
    g_boardGtmPwm.duty[BoardGtmPwmPhase_V] = BoardGtmPwm_clampDuty(phaseV);
    g_boardGtmPwm.duty[BoardGtmPwmPhase_W] = BoardGtmPwm_clampDuty(phaseW);

    IfxGtm_Pwm_updateChannelsDuty(&g_boardGtmPwm.pwm, &g_boardGtmPwm.duty[0]);
}

void BoardGtmPwm_setDutyFrame(const BoardGtmPwmDutyPercent *duty)
{
    if (duty == NULL_PTR)
    {
        return;
    }

    BoardGtmPwm_setDutyPercent(duty->u, duty->v, duty->w);
}

void BoardGtmPwm_setSafeState(void)
{
    if (g_boardGtmPwm.initialized == FALSE)
    {
        return;
    }

    g_boardGtmPwm.duty[BoardGtmPwmPhase_U] = 0.0f;
    g_boardGtmPwm.duty[BoardGtmPwmPhase_V] = 0.0f;
    g_boardGtmPwm.duty[BoardGtmPwmPhase_W] = 0.0f;

    IfxGtm_Pwm_updateChannelsDutyImmediate(&g_boardGtmPwm.pwm, &g_boardGtmPwm.duty[0]);
    BoardGtmPwm_stopTiming();
}

boolean BoardGtmPwm_isInitialized(void)
{
    return g_boardGtmPwm.initialized;
}

boolean BoardGtmPwm_isRunning(void)
{
    return g_boardGtmPwm.running;
}

IfxGtm_Pwm *BoardGtmPwm_getHandle(void)
{
    return &g_boardGtmPwm.pwm;
}

const BoardGtmPwmSettings *BoardGtmPwm_getSettings(void)
{
    return &g_boardGtmPwm.settings;
}