#include "command_router.h"
#include "motor_control.h"
#include "native_protocol.h"
#include "project_config.h"
#include "simplefoc_tc375_port.hpp"
#include "tc375_hal.h"

#include "FreeRTOS.h"
#include "task.h"

static MotorControl g_motor;
static CommandRouter g_router;
static NativeParser g_parser;
static uint8_t g_telemetry_sequence;

static StaticTask_t g_command_task_tcb;
static StaticTask_t g_outer_task_tcb;
static StaticTask_t g_telemetry_task_tcb;
static StaticTask_t g_health_task_tcb;
static StaticTask_t g_calibration_task_tcb;
static StackType_t g_command_stack[768];
static StackType_t g_outer_stack[768];
static StackType_t g_telemetry_stack[512];
static StackType_t g_health_stack[384];
static StackType_t g_calibration_stack[512];

static bool ProtocolTransmit(
    const uint8_t *data,
    uint16_t length,
    bool high_priority)
{
    return Tc375Hal_UartQueueTx(data, length, high_priority);
}

static void CommandTask(void *argument)
{
    uint8_t bytes[128];
    NativeFrame frame;
    size_t count;
    size_t index;
    (void)argument;
    for (;;)
    {
        count = Tc375Hal_UartRead(bytes, sizeof(bytes));
        for (index = 0U; index < count; ++index)
        {
            if (NativeParser_Push(&g_parser, bytes[index], &frame))
            {
                CommandRouter_Handle(&g_router, &frame);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
}

static void MotorOuterTask(void *argument)
{
    TickType_t last_wake = xTaskGetTickCount();
    (void)argument;
    for (;;)
    {
        MotorControl_Tick(&g_motor, Tc375Hal_TimeMs());
        if (Tc375Hal_ReadActiveFaults() != 0U)
        {
            MotorControl_TripFault(
                &g_motor,
                Tc375Hal_ReadActiveFaults());
            SimpleFocTc375_ForceSafeState();
        }
        SimpleFocTc375_OuterLoop(&g_motor);
        vTaskDelayUntil(
            &last_wake,
            pdMS_TO_TICKS(1000U / MOTOR_OUTER_LOOP_HZ));
    }
}

static void TelemetryTask(void *argument)
{
    TickType_t last_wake = xTaskGetTickCount();
    TickType_t period;
    uint16_t rate_hz;
    (void)argument;
    for (;;)
    {
        CommandRouter_SendTelemetry(&g_router, g_telemetry_sequence++);
        rate_hz = g_router.telemetry_rate_hz;
        if (rate_hz == 0U)
        {
            rate_hz = MOTOR_TELEMETRY_HZ;
        }
        period = pdMS_TO_TICKS((1000U + rate_hz - 1U) / rate_hz);
        if (period == 0U)
        {
            period = 1U;
        }
        vTaskDelayUntil(&last_wake, period);
    }
}

static void CalibrationTask(void *argument)
{
    bool success;
    (void)argument;
    for (;;)
    {
        if (g_motor.state == MOTOR_STATE_CALIBRATING)
        {
            SimpleFocTc375_ForceSafeState();
            success = SimpleFocTc375_RunCalibration(
                g_motor.calibration_type);
            MotorControl_FinishCalibration(&g_motor, success);
        }
        vTaskDelay(pdMS_TO_TICKS(10U));
    }
}

static void HealthTask(void *argument)
{
    (void)argument;
    for (;;)
    {
        Tc375Hal_ServiceWatchdogs();
        vTaskDelay(pdMS_TO_TICKS(10U));
    }
}

bool Firmware_CreateStaticTasks(void)
{
    MotorPersistentConfig stored_config;
    bool stored_config_valid = false;
    if (!Tc375Hal_BoardInit())
    {
        return false;
    }
    MotorControl_Init(&g_motor, Tc375Hal_TimeMs());
    if (Tc375Hal_LoadConfiguration(
            &stored_config,
            sizeof(stored_config)))
    {
        stored_config_valid = MotorControl_ImportPersistentConfig(
            &g_motor,
            &stored_config);
    }
    NativeParser_Init(&g_parser);
    CommandRouter_Init(&g_router, &g_motor, ProtocolTransmit);
    if (stored_config_valid)
    {
        g_router.telemetry_rate_hz = stored_config.telemetry_rate_hz;
        g_router.telemetry_mask = stored_config.telemetry_mask;
    }
    if (!SimpleFocTc375_Init(&g_motor))
    {
        MotorControl_TripFault(&g_motor, MOTOR_FAULT_GATE_DRIVER);
    }

    (void)xTaskCreateStatic(
        CommandTask, "command", 768U, NULL, 4U,
        g_command_stack, &g_command_task_tcb);
    (void)xTaskCreateStatic(
        MotorOuterTask, "motor-outer", 768U, NULL, 5U,
        g_outer_stack, &g_outer_task_tcb);
    (void)xTaskCreateStatic(
        TelemetryTask, "telemetry", 512U, NULL, 2U,
        g_telemetry_stack, &g_telemetry_task_tcb);
    (void)xTaskCreateStatic(
        HealthTask, "health", 384U, NULL, 3U,
        g_health_stack, &g_health_task_tcb);
    (void)xTaskCreateStatic(
        CalibrationTask, "calibration", 512U, NULL, 1U,
        g_calibration_stack, &g_calibration_task_tcb);
    return true;
}

/*
 * 由 GTM PWM 触发的 EVADC ISR 调用。ISR 不调用任何 FreeRTOS API，
 * 不分配内存，不发送 UART。
 */
void Firmware_FocAdcIsr(void)
{
    SimpleFocTc375_AdcPwmIsr(&g_motor);
}
