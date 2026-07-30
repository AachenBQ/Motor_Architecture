#include "firmware_runtime.h"

#include "command_router.h"
#include "motor_control.h"
#include "native_protocol.h"
#include "project_config.h"
#include "simplefoc_tc375_port.hpp"
#include "tc375_hal.h"

#include <stddef.h>
#include <stdint.h>

#define COOPERATIVE_UART_CHUNK_SIZE       128U
#define COOPERATIVE_MAX_RX_CHUNKS         16U
#define COOPERATIVE_UART_INTERBYTE_TIMEOUT_MS 100U
#define COOPERATIVE_HEALTH_PERIOD_MS      10U

static MotorControl g_motor;
static CommandRouter g_router;
static NativeParser g_parser;
/*
 * NativeFrame contains a 2048-byte payload. Keeping it out of
 * ServiceCommands() prevents the cooperative task from overflowing CPU0's
 * user stack while command handlers add their own call frames.
 */
static NativeFrame g_rx_frame;
static uint8_t g_telemetry_sequence;
static uint32_t g_last_outer_loop_ms;
static uint32_t g_last_telemetry_ms;
static uint32_t g_last_health_ms;
static uint32_t g_last_rx_byte_ms;
static bool g_rx_byte_seen;
static bool g_initialized;

static bool ProtocolTransmit(
    const uint8_t *data,
    uint16_t length,
    bool high_priority)
{
    return Tc375Hal_UartQueueTx(data, length, high_priority);
}

static uint32_t PeriodFromRate(uint16_t rate_hz)
{
    uint32_t period_ms;

    if (rate_hz == 0U)
    {
        rate_hz = MOTOR_TELEMETRY_HZ;
    }
    period_ms = (1000U + (uint32_t)rate_hz - 1U) /
                (uint32_t)rate_hz;
    return period_ms == 0U ? 1U : period_ms;
}

static void UpdateProtocolErrorCount(void)
{
    uint32_t total =
        g_parser.crc_errors +
        g_parser.length_errors +
        g_parser.timeout_errors;
    g_router.protocol_errors =
        total > 0xFFFFU ? 0xFFFFU : (uint16_t)total;
    g_router.parser_crc_errors =
        g_parser.crc_errors > 0xFFFFU
            ? 0xFFFFU
            : (uint16_t)g_parser.crc_errors;
    g_router.parser_length_errors =
        g_parser.length_errors > 0xFFFFU
            ? 0xFFFFU
            : (uint16_t)g_parser.length_errors;
    g_router.parser_timeout_errors =
        g_parser.timeout_errors > 0xFFFFU
            ? 0xFFFFU
            : (uint16_t)g_parser.timeout_errors;
    g_router.parser_resync_events =
        g_parser.resync_events > 0xFFFFU
            ? 0xFFFFU
            : (uint16_t)g_parser.resync_events;
}

static void ServiceCommands(void)
{
    uint8_t bytes[COOPERATIVE_UART_CHUNK_SIZE];
    size_t count;
    size_t index;
    uint8_t chunk;
    bool received_bytes = false;

    /*
     * Drain bytes that are already waiting before applying the inter-byte
     * timeout. The ASCLIN ISR/USB-UART path may split a longer frame into
     * several chunks. Expiring the old prefix before reading an already
     * queued suffix makes valid commands such as the 39-byte open-loop
     * configuration frame impossible to complete.
     */
    for (chunk = 0U;
         chunk < COOPERATIVE_MAX_RX_CHUNKS;
         ++chunk)
    {
        count = Tc375Hal_UartRead(bytes, sizeof(bytes));
        if (count == 0U)
        {
            break;
        }
        received_bytes = true;
        g_last_rx_byte_ms = Tc375Hal_TimeMs();
        g_rx_byte_seen = true;
        for (index = 0U; index < count; ++index)
        {
            if (NativeParser_Push(
                    &g_parser,
                    bytes[index],
                    &g_rx_frame))
            {
                UpdateProtocolErrorCount();
                CommandRouter_Handle(&g_router, &g_rx_frame);
            }
        }
    }
    if (g_parser.used == 0U)
    {
        g_rx_byte_seen = false;
    }
    else if (!received_bytes &&
             g_rx_byte_seen &&
             ((uint32_t)(
                  Tc375Hal_TimeMs() - g_last_rx_byte_ms) >=
              COOPERATIVE_UART_INTERBYTE_TIMEOUT_MS))
    {
        (void)NativeParser_ExpirePartial(&g_parser);
        g_rx_byte_seen = false;
    }
    UpdateProtocolErrorCount();
}

static void ServiceMotor(uint32_t now_ms)
{
    uint32_t active_faults;

    MotorControl_Tick(&g_motor, now_ms);
    active_faults = Tc375Hal_ReadActiveFaults();
    if (active_faults != 0U)
    {
        MotorControl_TripFault(&g_motor, active_faults);
        SimpleFocTc375_ForceSafeState();
    }
    SimpleFocTc375_OuterLoop(&g_motor);
}

static void ServiceCalibration(void)
{
    bool success;

    if (g_motor.state != MOTOR_STATE_CALIBRATING)
    {
        return;
    }

    SimpleFocTc375_ForceSafeState();
    success = SimpleFocTc375_RunCalibration(
        g_motor.calibration_type);
    MotorControl_FinishCalibration(&g_motor, success);
}

bool Firmware_CooperativeInit(void)
{
    MotorPersistentConfig stored_config;
    bool stored_config_valid = false;
    uint32_t now_ms;

    if (g_initialized)
    {
        return true;
    }
    if (!Tc375Hal_BoardInit())
    {
        return false;
    }

    now_ms = Tc375Hal_TimeMs();
    MotorControl_Init(&g_motor, now_ms);
    if (Tc375Hal_LoadConfiguration(
            &stored_config,
            sizeof(stored_config)))
    {
        stored_config_valid =
            MotorControl_ImportPersistentConfig(
                &g_motor,
                &stored_config);
    }

    NativeParser_Init(&g_parser);
    g_last_rx_byte_ms = now_ms;
    g_rx_byte_seen = false;
    CommandRouter_Init(
        &g_router,
        &g_motor,
        ProtocolTransmit);
    if (stored_config_valid)
    {
        g_router.telemetry_rate_hz =
            stored_config.telemetry_rate_hz;
        g_router.telemetry_mask =
            stored_config.telemetry_mask;
    }

    /*
     * Keep the communication channel alive even if the motor peripherals
     * fail to initialize. The host can then read diagnostics and faults.
     */
    if (!SimpleFocTc375_Init(&g_motor))
    {
        MotorControl_TripFault(
            &g_motor,
            MOTOR_FAULT_GATE_DRIVER);
        SimpleFocTc375_ForceSafeState();
    }

    /*
     * Populate bus voltage, temperature and the initial status before the
     * first telemetry frame. Sending the zero-initialized structure could
     * otherwise look like a real undervoltage event to the host.
     */
    ServiceMotor(now_ms);

    g_telemetry_sequence = 0U;
    g_last_outer_loop_ms = now_ms;
    g_last_telemetry_ms =
        now_ms - PeriodFromRate(g_router.telemetry_rate_hz);
    g_last_health_ms = now_ms;
    g_initialized = true;
    return true;
}

void Firmware_CooperativePoll(void)
{
    uint32_t now_ms;
    uint32_t outer_period_ms;
    uint32_t telemetry_period_ms;

    if (!g_initialized)
    {
        return;
    }

    ServiceCommands();
    ServiceCalibration();
    now_ms = Tc375Hal_TimeMs();

    outer_period_ms =
        (1000U + MOTOR_OUTER_LOOP_HZ - 1U) /
        MOTOR_OUTER_LOOP_HZ;
    if (outer_period_ms == 0U)
    {
        outer_period_ms = 1U;
    }
    if ((uint32_t)(now_ms - g_last_outer_loop_ms) >=
        outer_period_ms)
    {
        g_last_outer_loop_ms = now_ms;
        ServiceMotor(now_ms);
        /*
         * Bytes can arrive while SimpleFOC executes. Service them again
         * before queuing telemetry so heartbeats and command responses keep
         * priority during an open-loop run.
         */
        ServiceCommands();
    }

    telemetry_period_ms =
        PeriodFromRate(g_router.telemetry_rate_hz);
    if ((uint32_t)(now_ms - g_last_telemetry_ms) >=
        telemetry_period_ms)
    {
        g_last_telemetry_ms = now_ms;
        CommandRouter_SendTelemetry(
            &g_router,
            g_telemetry_sequence++);
    }

    if ((uint32_t)(now_ms - g_last_health_ms) >=
        COOPERATIVE_HEALTH_PERIOD_MS)
    {
        g_last_health_ms = now_ms;
        Tc375Hal_ServiceWatchdogs();
    }
}

void Firmware_CooperativeFocAdcIsr(void)
{
    if (g_initialized)
    {
        SimpleFocTc375_AdcPwmIsr(&g_motor);
    }
}
