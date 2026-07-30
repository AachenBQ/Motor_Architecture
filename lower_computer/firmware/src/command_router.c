#include "command_router.h"

#include "project_config.h"
#include "tc375_hal.h"

#include <math.h>
#include <string.h>

static float ReadF32(const uint8_t *data)
{
    float value;
    memcpy(&value, data, sizeof(value));
    return value;
}

static uint16_t ReadU16(const uint8_t *data)
{
    return (uint16_t)data[0] | ((uint16_t)data[1] << 8);
}

static uint32_t ReadU32(const uint8_t *data)
{
    return (uint32_t)data[0] |
           ((uint32_t)data[1] << 8) |
           ((uint32_t)data[2] << 16) |
           ((uint32_t)data[3] << 24);
}

static void WriteU16(uint8_t *data, uint16_t value)
{
    data[0] = (uint8_t)(value & 0xFFU);
    data[1] = (uint8_t)(value >> 8);
}

static void WriteU32(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)(value & 0xFFU);
    data[1] = (uint8_t)((value >> 8) & 0xFFU);
    data[2] = (uint8_t)((value >> 16) & 0xFFU);
    data[3] = (uint8_t)(value >> 24);
}

static void WriteF32(uint8_t *data, float value)
{
    memcpy(data, &value, sizeof(value));
}

static ProtocolStatus FromMotorResult(MotorResult result)
{
    switch (result)
    {
        case MOTOR_RESULT_OK:
            return PROTOCOL_OK;
        case MOTOR_RESULT_OUT_OF_RANGE:
            return PROTOCOL_OUT_OF_RANGE;
        case MOTOR_RESULT_NOT_CALIBRATED:
            return PROTOCOL_NOT_CALIBRATED;
        case MOTOR_RESULT_HEARTBEAT_REQUIRED:
            return PROTOCOL_HEARTBEAT_REQUIRED;
        case MOTOR_RESULT_HARDWARE_FAULT:
            return PROTOCOL_HARDWARE_FAULT;
        case MOTOR_RESULT_CAPABILITY_UNAVAILABLE:
            return PROTOCOL_CAPABILITY_UNAVAILABLE;
        case MOTOR_RESULT_SAFETY_INTERLOCK:
            return PROTOCOL_SAFETY_INTERLOCK;
        default:
            return PROTOCOL_INVALID_STATE;
    }
}

static void SendResponse(
    CommandRouter *router,
    const NativeFrame *request,
    ProtocolStatus status,
    const uint8_t *detail,
    uint16_t detail_length)
{
    NativeFrame *response = &router->response_frame;
    size_t length;
    memset(response, 0, sizeof(*response));
    response->version = NATIVE_PROTOCOL_VERSION;
    response->flags = 1U;
    response->device = request->device;
    response->command = status == PROTOCOL_OK ? CMD_ACK : CMD_ERROR;
    response->sequence = request->sequence;
    response->payload[0] = request->command;
    response->payload[1] = (uint8_t)status;
    if ((detail != NULL) && (detail_length != 0U))
    {
        memcpy(&response->payload[2], detail, detail_length);
    }
    response->payload_length = (uint16_t)(2U + detail_length);
    length = NativeProtocol_Encode(
        response,
        router->encoded_frame,
        sizeof(router->encoded_frame));
    if (length != 0U)
    {
        router->transmit(
            router->encoded_frame,
            (uint16_t)length,
            true);
    }
}

static bool IsSingleMotorPayload(const NativeFrame *request, uint16_t minimum)
{
    return (request->payload_length >= minimum) &&
           (request->payload[0] == MOTOR_DEVICE_ID);
}

static void ResetOpenLoopStaging(CommandRouter *router)
{
    router->open_loop_staging_active = false;
    router->open_loop_staging_mask = 0U;
    router->open_loop_staging_updated_ms = 0U;
}

static void InvalidateOpenLoopTransferState(CommandRouter *router)
{
    ResetOpenLoopStaging(router);
    router->open_loop_committed_valid = false;
    router->open_loop_committed_at_ms = 0U;
}

static void ExpireOpenLoopStaging(
    CommandRouter *router,
    uint32_t now_ms)
{
    if (router->open_loop_staging_active &&
        ((uint32_t)(
             now_ms - router->open_loop_staging_updated_ms) >=
         COMMAND_ROUTER_OPEN_LOOP_STAGING_TIMEOUT_MS))
    {
        ResetOpenLoopStaging(router);
    }
}

static ProtocolStatus ApplyOpenLoopConfigPayload(
    CommandRouter *router,
    const uint8_t *payload)
{
    MotorOpenLoopConfig config;

    if (payload[0] != MOTOR_DEVICE_ID)
    {
        return PROTOCOL_INVALID_PAYLOAD;
    }
    memset(&config, 0, sizeof(config));
    config.backend = payload[1];
    config.pole_pairs = payload[2];
    config.flags = payload[3];
    config.bus_voltage_v = ReadF32(&payload[4]);
    config.voltage_limit_v = ReadF32(&payload[8]);
    config.target_velocity_rad_s = ReadF32(&payload[12]);
    config.acceleration_rad_s2 = ReadF32(&payload[16]);
    config.update_period_ms = ReadU16(&payload[20]);
    config.startup_delay_ms = ReadU16(&payload[22]);
    config.max_runtime_ms = ReadU32(&payload[24]);
    return FromMotorResult(
        MotorControl_SetOpenLoopConfig(
            router->motor,
            &config));
}

static uint8_t GetHardwareDiagnosticFlags(void)
{
    uint8_t flags = 0U;

    if (Tc375Hal_IsPwmEnabled())
    {
        flags |= NATIVE_DIAGNOSTIC_HW_PWM_ENABLED;
    }
    if (Tc375Hal_IsGateEnabled())
    {
        flags |= NATIVE_DIAGNOSTIC_HW_GATE_ENABLED;
    }
    if (Tc375Hal_ReadActiveFaults() == 0U)
    {
        flags |= NATIVE_DIAGNOSTIC_HW_NFAULT_CLEAR;
    }
    if ((MOTOR_POWER_STAGE_SAFETY_READY_MASK &
         MOTOR_POWER_STAGE_REQUIRED_SAFETY_MASK) ==
        MOTOR_POWER_STAGE_REQUIRED_SAFETY_MASK)
    {
        flags |= NATIVE_DIAGNOSTIC_HW_SAFETY_READY;
    }
#if MOTOR_POWER_STAGE_ENABLED
    flags |= NATIVE_DIAGNOSTIC_HW_POWER_STAGE_BUILD;
#endif
#if MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE
    flags |= NATIVE_DIAGNOSTIC_HW_OVERRIDE_ACTIVE;
#endif
    return flags;
}

static ProtocolStatus PowerStageRuntimePreflight(CommandRouter *router)
{
#if MOTOR_POWER_STAGE_ENABLED
    MotorControl *motor = router->motor;
    uint32_t active_faults;

    /*
     * A start command is accepted only from an electrically quiet state.
     * This also detects a stale software state left behind by a previous
     * aborted run before any new gate transition is attempted.
     */
    if (Tc375Hal_IsPwmEnabled() || Tc375Hal_IsGateEnabled())
    {
        Tc375Hal_SetPwmEnabled(false);
        (void)Tc375Hal_SetGateEnabled(false);
        return PROTOCOL_SAFETY_INTERLOCK;
    }

    active_faults = Tc375Hal_ReadActiveFaults();
    if (active_faults != 0U)
    {
        MotorControl_TripFault(motor, active_faults);
        return PROTOCOL_HARDWARE_FAULT;
    }

#if MOTOR_PHASE_CURRENT_SENSE_READY
    {
        Tc375PhaseCurrents currents =
            Tc375Hal_ReadPhaseCurrents();
        float peak_current;

        if (!currents.sample_valid ||
            !isfinite(currents.phase_a) ||
            !isfinite(currents.phase_b) ||
            !isfinite(currents.phase_c))
        {
            MotorControl_TripFault(
                motor,
                MOTOR_FAULT_CURRENT_SENSOR);
            return PROTOCOL_HARDWARE_FAULT;
        }
        peak_current = fabsf(currents.phase_a);
        if (fabsf(currents.phase_b) > peak_current)
        {
            peak_current = fabsf(currents.phase_b);
        }
        if (fabsf(currents.phase_c) > peak_current)
        {
            peak_current = fabsf(currents.phase_c);
        }
        if (peak_current > motor->limits.current_a)
        {
            MotorControl_TripFault(
                motor,
                MOTOR_FAULT_OVERCURRENT);
            return PROTOCOL_HARDWARE_FAULT;
        }
    }
#endif

#if MOTOR_BUS_VOLTAGE_SENSE_READY
    {
        float bus_voltage = Tc375Hal_ReadBusVoltage();

        if (!isfinite(bus_voltage) || (bus_voltage <= 0.0F))
        {
            MotorControl_TripFault(
                motor,
                MOTOR_FAULT_BUS_VOLTAGE_SENSOR);
            return PROTOCOL_HARDWARE_FAULT;
        }
        if (bus_voltage < motor->limits.bus_min_v)
        {
            MotorControl_TripFault(
                motor,
                MOTOR_FAULT_UNDERVOLTAGE);
            return PROTOCOL_HARDWARE_FAULT;
        }
        if (bus_voltage > motor->limits.bus_max_v)
        {
            MotorControl_TripFault(
                motor,
                MOTOR_FAULT_OVERVOLTAGE);
            return PROTOCOL_HARDWARE_FAULT;
        }
        if (fabsf(
                bus_voltage -
                motor->open_loop.bus_voltage_v) >
            MOTOR_POWER_STAGE_BUS_TOLERANCE_V)
        {
            return PROTOCOL_SAFETY_INTERLOCK;
        }
    }
#endif

#if MOTOR_POWER_TEMPERATURE_SENSE_READY
    {
        float temperature =
            Tc375Hal_ReadPowerTemperature();

        if (!isfinite(temperature))
        {
            MotorControl_TripFault(
                motor,
                MOTOR_FAULT_TEMPERATURE_SENSOR);
            return PROTOCOL_HARDWARE_FAULT;
        }
        if (temperature > motor->limits.temperature_max_c)
        {
            MotorControl_TripFault(
                motor,
                MOTOR_FAULT_OVERTEMPERATURE);
            return PROTOCOL_HARDWARE_FAULT;
        }
    }
#endif

    return PROTOCOL_OK;
#else
    (void)router;
    return PROTOCOL_OK;
#endif
}

void CommandRouter_Init(
    CommandRouter *router,
    MotorControl *motor,
    CommandRouterTransmit transmit)
{
    memset(router, 0, sizeof(*router));
    router->motor = motor;
    router->transmit = transmit;
    router->telemetry_rate_hz = MOTOR_TELEMETRY_HZ;
    router->telemetry_mask = 0xFFFFFFFFUL;
}

void CommandRouter_Handle(CommandRouter *router, const NativeFrame *request)
{
    uint8_t detail[46];
    uint16_t detail_length = 0U;
    uint32_t now_ms;
    uint64_t now_ms64;
    uint32_t heartbeat_age_ms;
    uint8_t runtime_flags;
    ProtocolStatus status = PROTOCOL_OK;
    MotorResult motor_result;
    MotorPid pid;
    uint16_t config_crc;
    uint8_t loop;
    uint8_t start_flags;
    bool broadcast_disable;

    router->commands_received++;
    if (request->version != NATIVE_PROTOCOL_VERSION)
    {
        SendResponse(router, request, PROTOCOL_INVALID_PAYLOAD, NULL, 0U);
        return;
    }
    broadcast_disable =
        (request->device == 0xFFU) &&
        (request->command == CMD_SET_ENABLE) &&
        (request->payload_length == 2U) &&
        ((request->payload[0] == MOTOR_DEVICE_ID) ||
         (request->payload[0] == 0xFFU)) &&
        (request->payload[1] == 0U);
    if ((request->device != MOTOR_DEVICE_ID) &&
        !((request->device == 0xFFU) &&
          (request->command == CMD_EMERGENCY_STOP)) &&
        !broadcast_disable)
    {
        SendResponse(router, request, PROTOCOL_INVALID_DEVICE, NULL, 0U);
        return;
    }

    switch (request->command)
    {
        case CMD_PING:
            memcpy(detail, MOTOR_FIRMWARE_PING_TEXT, 13U);
            detail_length = 13U;
            break;

        case CMD_GET_DEVICE_INFO:
            detail[0] = MOTOR_FIRMWARE_VERSION_MAJOR;
            detail[1] = MOTOR_FIRMWARE_VERSION_MINOR;
            detail[2] = MOTOR_FIRMWARE_VERSION_PATCH;
            detail[3] = 1U;
            detail[4] = 0U;
            WriteU32(&detail[5], 0x37500001UL);
            memset(&detail[9], 0, 24U);
            memcpy(&detail[9], "TC375-MCU", 9U);
            memcpy(
                &detail[25],
                MOTOR_FIRMWARE_BUILD_TAG,
                MOTOR_FIRMWARE_BUILD_TAG_LENGTH);
            detail_length = 33U;
            break;

        case CMD_GET_CAPABILITIES:
            detail[0] = 1U;
            detail[1] = 0x01U;
            detail[2] = 0x0FU;
            WriteU32(&detail[3], (1UL << 0) | (1UL << 2) |
                                    (1UL << 3) | (1UL << 4) |
                                    (1UL << 5) | (1UL << 6) |
                                    NATIVE_FEATURE_POWER_STAGE_CONFIRMED_START);
            WriteU16(&detail[7], 1000U);
            detail_length = 9U;
            break;

        case CMD_HEARTBEAT:
            if (request->payload_length != 6U)
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            (void)ReadU32(request->payload);
            {
                uint16_t lease = ReadU16(&request->payload[4]);
                if ((lease < MOTOR_HEARTBEAT_MIN_MS) ||
                    (lease > MOTOR_HEARTBEAT_MAX_MS))
                {
                    status = PROTOCOL_OUT_OF_RANGE;
                }
                else
                {
                    MotorControl_Heartbeat(
                        router->motor,
                        Tc375Hal_TimeMs(),
                        lease);
                }
            }
            break;

        case CMD_SET_ENABLE:
            if ((!IsSingleMotorPayload(request, 2U) &&
                 !broadcast_disable) ||
                (request->payload_length != 2U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            motor_result = MotorControl_SetEnable(
                router->motor,
                request->payload[1] != 0U);
            status = FromMotorResult(motor_result);
            if ((status == PROTOCOL_OK) &&
                (request->payload[1] != 0U))
            {
                ResetOpenLoopStaging(router);
            }
            break;

        case CMD_SET_MODE:
            if (!IsSingleMotorPayload(request, 2U) ||
                (request->payload_length != 2U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            motor_result = MotorControl_SetMode(
                router->motor,
                (MotorMode)request->payload[1]);
            status = FromMotorResult(motor_result);
            break;

        case CMD_SET_TARGET:
            if (!IsSingleMotorPayload(request, 6U) ||
                (request->payload_length != 6U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            motor_result = MotorControl_SetTarget(
                router->motor,
                (MotorMode)request->payload[1],
                ReadF32(&request->payload[2]));
            status = FromMotorResult(motor_result);
            break;

        case CMD_SET_PID:
            if (!IsSingleMotorPayload(request, 14U) ||
                (request->payload_length != 14U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            loop = request->payload[1];
            pid.kp = ReadF32(&request->payload[2]);
            pid.ki = ReadF32(&request->payload[6]);
            pid.kd = ReadF32(&request->payload[10]);
            status = FromMotorResult(MotorControl_SetPid(
                router->motor,
                (MotorPidLoop)loop,
                &pid));
            break;

        case CMD_GET_PID:
            if (!IsSingleMotorPayload(request, 2U) ||
                (request->payload_length != 2U) ||
                (request->payload[1] >= MOTOR_PID_COUNT))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            loop = request->payload[1];
            detail[0] = loop;
            WriteF32(&detail[1], router->motor->pid[loop].kp);
            WriteF32(&detail[5], router->motor->pid[loop].ki);
            WriteF32(&detail[9], router->motor->pid[loop].kd);
            detail_length = 13U;
            break;

        case CMD_CALIBRATE:
            if (!IsSingleMotorPayload(request, 2U) ||
                (request->payload_length != 2U) ||
                (request->payload[1] > 4U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            status = FromMotorResult(MotorControl_StartCalibration(
                router->motor,
                request->payload[1]));
            break;

        case CMD_CLEAR_FAULT:
            if (!IsSingleMotorPayload(request, 1U) ||
                (request->payload_length != 1U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            status = FromMotorResult(MotorControl_ClearFault(
                router->motor,
                Tc375Hal_ReadActiveFaults()));
            break;

        case CMD_CONTROLLED_STOP:
            if (!IsSingleMotorPayload(request, 1U) ||
                (request->payload_length != 1U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            MotorControl_RequestControlledStop(router->motor);
            break;

        case CMD_QUICK_STOP:
            if (!IsSingleMotorPayload(request, 1U) ||
                (request->payload_length != 1U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            MotorControl_StopWithReason(
                router->motor,
                false,
                MOTOR_STOP_REASON_QUICK_STOP_COMMAND);
            Tc375Hal_SetPwmEnabled(false);
            (void)Tc375Hal_SetGateEnabled(false);
            break;

        case CMD_EMERGENCY_STOP:
            if ((request->payload_length != 1U) ||
                ((request->payload[0] != MOTOR_DEVICE_ID) &&
                 (request->payload[0] != 0xFFU)))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            MotorControl_StopWithReason(
                router->motor,
                true,
                MOTOR_STOP_REASON_EMERGENCY_COMMAND);
            Tc375Hal_SetPwmEnabled(false);
            (void)Tc375Hal_SetGateEnabled(false);
            break;

        case CMD_GET_DIAGNOSTICS:
            if (request->payload_length > 1U)
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            now_ms = Tc375Hal_TimeMs();
            heartbeat_age_ms =
                now_ms - router->motor->last_heartbeat_ms;
            if (heartbeat_age_ms > 0xFFFFU)
            {
                heartbeat_age_ms = 0xFFFFU;
            }
            runtime_flags = 0U;
            if (router->motor->heartbeat_valid)
            {
                runtime_flags |= 1U << 0;
            }
            if (router->motor->enabled)
            {
                runtime_flags |= 1U << 1;
            }
            if (router->motor->open_loop_active)
            {
                runtime_flags |= 1U << 2;
            }
            if (router->motor->open_loop_output_ready)
            {
                runtime_flags |= 1U << 3;
            }
            WriteU32(detail, now_ms);
            WriteU16(&detail[4], router->protocol_errors);
            WriteU16(&detail[6], (uint16_t)router->motor->faults);
            WriteU32(&detail[8], router->commands_received);
            WriteU16(&detail[12], (uint16_t)heartbeat_age_ms);
            WriteU16(
                &detail[14],
                router->motor->heartbeat_lease_ms);
            detail[16] = (uint8_t)router->motor->state;
            detail[17] =
                (uint8_t)router->motor->last_stop_reason;
            detail[18] = runtime_flags;
            detail[19] = GetHardwareDiagnosticFlags();
            WriteU16(
                &detail[20],
                Tc375Hal_UartHighPriorityFailures());
            WriteU16(
                &detail[22],
                Tc375Hal_UartTelemetryDrops());
            detail_length = 24U;
            if ((request->payload_length == 1U) &&
                ((request->payload[0] & 0x07U) != 0U))
            {
                WriteU16(
                    &detail[24],
                    Tc375Hal_UartRxSwFifoOverflows());
                WriteU16(
                    &detail[26],
                    Tc375Hal_UartRxHwFifoOverflows());
                WriteU16(
                    &detail[28],
                    Tc375Hal_UartRxFrameErrors());
                WriteU16(
                    &detail[30],
                    Tc375Hal_UartRxParityErrors());
                detail_length = 32U;
            }
            if ((request->payload_length == 1U) &&
                ((request->payload[0] & 0x06U) != 0U))
            {
                /*
                 * Parser counters follow the UART error counters so the
                 * 40-byte response has a stable layout. Legacy hosts request
                 * both sections with 0x03.
                 */
                WriteU16(
                    &detail[32],
                    router->parser_crc_errors);
                WriteU16(
                    &detail[34],
                    router->parser_length_errors);
                WriteU16(
                    &detail[36],
                    router->parser_timeout_errors);
                WriteU16(
                    &detail[38],
                    router->parser_resync_events);
                detail_length = 40U;
            }
            if ((request->payload_length == 1U) &&
                ((request->payload[0] & 0x04U) != 0U))
            {
                WriteU16(
                    &detail[40],
                    Tc375Hal_UartRxIsrEntries());
                WriteU16(
                    &detail[42],
                    Tc375Hal_UartRxPollDrains());
                WriteU16(
                    &detail[44],
                    Tc375Hal_UartRxPollBytes());
                detail_length = 46U;
            }
            break;

        case CMD_SET_TELEMETRY_PROFILE:
            if (request->payload_length != 6U)
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            {
                uint16_t rate_hz = ReadU16(request->payload);
                uint32_t signal_mask = ReadU32(&request->payload[2]);
                if ((rate_hz == 0U) || (rate_hz > 1000U))
                {
                    status = PROTOCOL_OUT_OF_RANGE;
                }
                else
                {
                    router->telemetry_rate_hz = rate_hz;
                    router->telemetry_mask = signal_mask;
                }
            }
            break;

        case CMD_GET_BACKEND_INFO:
            detail[0] = 0U;
            detail[1] =
                MOTOR_CONTROL_HARDWARE_ENABLED ? 1U : 0U;
            detail_length = 2U;
            break;

        case CMD_GET_TELEMETRY_PROFILE:
            WriteU16(detail, router->telemetry_rate_hz);
            WriteU32(&detail[2], router->telemetry_mask);
            detail_length = 6U;
            break;

        case CMD_SET_OPEN_LOOP_CONFIG:
            if (!IsSingleMotorPayload(
                    request,
                    COMMAND_ROUTER_OPEN_LOOP_CONFIG_SIZE) ||
                (request->payload_length !=
                 COMMAND_ROUTER_OPEN_LOOP_CONFIG_SIZE))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            status = ApplyOpenLoopConfigPayload(
                router,
                request->payload);
            if (status == PROTOCOL_OK)
            {
                InvalidateOpenLoopTransferState(router);
            }
            break;

        case CMD_SET_OPEN_LOOP_CONFIG_PART:
            if (!IsSingleMotorPayload(request, 5U) ||
                (request->payload_length != 5U) ||
                (request->payload[2] >=
                 COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_COUNT))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            if (router->motor->enabled ||
                router->motor->open_loop_active)
            {
                status = PROTOCOL_INVALID_STATE;
                break;
            }
            now_ms = Tc375Hal_TimeMs();
            ExpireOpenLoopStaging(router, now_ms);
            if (!router->open_loop_staging_active ||
                (router->open_loop_staging_generation !=
                 request->payload[1]))
            {
                memset(
                    router->open_loop_staging,
                    0,
                    sizeof(router->open_loop_staging));
                router->open_loop_staging_mask = 0U;
                router->open_loop_staging_generation =
                    request->payload[1];
                router->open_loop_staging_active = true;
            }
            memcpy(
                &router->open_loop_staging[
                    (uint16_t)request->payload[2] *
                    COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_SIZE],
                &request->payload[3],
                COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_SIZE);
            router->open_loop_staging_mask |=
                (uint16_t)(1U << request->payload[2]);
            router->open_loop_staging_updated_ms = now_ms;
            detail[0] = request->payload[1];
            detail[1] = request->payload[2];
            detail_length = 2U;
            break;

        case CMD_COMMIT_OPEN_LOOP_CONFIG:
            if (!IsSingleMotorPayload(request, 4U) ||
                (request->payload_length != 4U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            config_crc = ReadU16(&request->payload[2]);
            now_ms = Tc375Hal_TimeMs();
            now_ms64 = Tc375Hal_TimeMs64();
            ExpireOpenLoopStaging(router, now_ms);
            if (router->open_loop_committed_valid &&
                ((now_ms64 -
                  router->open_loop_committed_at_ms) >=
                 COMMAND_ROUTER_OPEN_LOOP_STAGING_TIMEOUT_MS))
            {
                router->open_loop_committed_valid = false;
                router->open_loop_committed_at_ms = 0ULL;
            }
            /*
             * A successful commit is idempotent. If its ACK was lost, the
             * host can safely retry the same generation/CRC even though the
             * staging buffer has already been retired.
             */
            if (!router->open_loop_staging_active &&
                router->open_loop_committed_valid &&
                (router->open_loop_committed_generation ==
                 request->payload[1]) &&
                (router->open_loop_committed_crc == config_crc))
            {
                detail[0] = request->payload[1];
                detail_length = 1U;
                break;
            }
            if (router->motor->enabled ||
                router->motor->open_loop_active)
            {
                status = PROTOCOL_INVALID_STATE;
                break;
            }
            if (!router->open_loop_staging_active ||
                (router->open_loop_staging_generation !=
                 request->payload[1]) ||
                (router->open_loop_staging_mask !=
                 COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_FULL_MASK))
            {
                status = PROTOCOL_INVALID_STATE;
                break;
            }
            if (router->open_loop_staging[0] !=
                request->payload[0])
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            if (NativeProtocol_Crc16(
                    router->open_loop_staging,
                    sizeof(router->open_loop_staging)) !=
                config_crc)
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            status = ApplyOpenLoopConfigPayload(
                router,
                router->open_loop_staging);
            if (status == PROTOCOL_OK)
            {
                ResetOpenLoopStaging(router);
                router->open_loop_committed_generation =
                    request->payload[1];
                router->open_loop_committed_crc = config_crc;
                router->open_loop_committed_at_ms = now_ms64;
                router->open_loop_committed_valid = true;
                detail[0] = request->payload[1];
                detail_length = 1U;
            }
            break;

        case CMD_GET_OPEN_LOOP_CONFIG:
            if (!IsSingleMotorPayload(request, 1U) ||
                (request->payload_length != 1U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            detail[0] = MOTOR_DEVICE_ID;
            detail[1] = router->motor->open_loop.backend;
            detail[2] = router->motor->open_loop.pole_pairs;
            detail[3] = router->motor->open_loop.flags;
            WriteF32(
                &detail[4],
                router->motor->open_loop.bus_voltage_v);
            WriteF32(
                &detail[8],
                router->motor->open_loop.voltage_limit_v);
            WriteF32(
                &detail[12],
                router->motor->open_loop.target_velocity_rad_s);
            WriteF32(
                &detail[16],
                router->motor->open_loop.acceleration_rad_s2);
            WriteU16(
                &detail[20],
                router->motor->open_loop.update_period_ms);
            WriteU16(
                &detail[22],
                router->motor->open_loop.startup_delay_ms);
            WriteU32(
                &detail[24],
                router->motor->open_loop.max_runtime_ms);
            detail_length = 28U;
            break;

        case CMD_START_OPEN_LOOP:
            if (!IsSingleMotorPayload(request, 1U) ||
                ((request->payload_length != 1U) &&
                 (request->payload_length != 2U)))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            start_flags =
                request->payload_length == 2U
                    ? request->payload[1]
                    : 0U;
            if ((start_flags &
                 (uint8_t)~NATIVE_START_FLAG_SUPPORTED_MASK) != 0U)
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
#if MOTOR_POWER_STAGE_ENABLED
            if ((request->payload_length != 2U) ||
                ((start_flags &
                  NATIVE_START_FLAG_POWER_STAGE_CONFIRMED) == 0U))
            {
                status = PROTOCOL_SAFETY_INTERLOCK;
                break;
            }
#endif
            status = PowerStageRuntimePreflight(router);
            if (status != PROTOCOL_OK)
            {
                break;
            }
#if MOTOR_CONTROL_HARDWARE_ENABLED
#if MOTOR_USE_SIMPLEFOC
            status = FromMotorResult(MotorControl_StartOpenLoop(
                router->motor,
                Tc375Hal_TimeMs()));
#else
            if (router->motor->open_loop.backend ==
                MOTOR_OPEN_LOOP_SIMPLEFOC)
            {
                status = PROTOCOL_CAPABILITY_UNAVAILABLE;
            }
            else
            {
                status = FromMotorResult(MotorControl_StartOpenLoop(
                    router->motor,
                    Tc375Hal_TimeMs()));
            }
#endif
#else
            status = PROTOCOL_CAPABILITY_UNAVAILABLE;
#endif
            if (status == PROTOCOL_OK)
            {
                ResetOpenLoopStaging(router);
            }
            break;

        case CMD_GET_BUILD_CONFIG:
            if (request->payload_length != 0U)
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            detail[0] = MOTOR_DEVICE_ID;
            detail[1] =
                MOTOR_CONTROL_HARDWARE_ENABLED ? 1U : 0U;
            detail[2] = MOTOR_POWER_STAGE_ENABLED ? 1U : 0U;
            detail[3] = MOTOR_USE_SIMPLEFOC ? 1U : 0U;
            detail[4] = MOTOR_POLE_PAIRS;
            WriteU32(&detail[5], MOTOR_ADC_TRIGGER_HZ);
            WriteU32(&detail[9], MOTOR_PWM_FREQUENCY_HZ);
            WriteU32(&detail[13], MOTOR_CONTROL_ISR_HZ);
            WriteU32(&detail[17], MOTOR_OUTER_LOOP_HZ);
            WriteU16(&detail[21], MOTOR_TELEMETRY_HZ);
            WriteU16(&detail[23], MOTOR_HEARTBEAT_DEFAULT_MS);
            WriteU16(&detail[25], MOTOR_HEARTBEAT_MIN_MS);
            WriteU16(&detail[27], MOTOR_HEARTBEAT_MAX_MS);
            WriteF32(&detail[29], MOTOR_TORQUE_CONSTANT_NM_PER_A);
            WriteU32(
                &detail[33],
                MOTOR_POWER_STAGE_REPORTED_SAFETY_MASK);
            detail_length = 37U;
            break;

        case CMD_SET_LIMITS:
            if (!IsSingleMotorPayload(request, 33U) ||
                (request->payload_length != 33U) ||
                router->motor->enabled)
            {
                status = router->motor->enabled
                    ? PROTOCOL_INVALID_STATE
                    : PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            {
                MotorLimits limits;
                limits.current_a = ReadF32(&request->payload[1]);
                limits.torque_nm = ReadF32(&request->payload[5]);
                limits.speed_rad_s = ReadF32(&request->payload[9]);
                limits.position_min_rad = ReadF32(&request->payload[13]);
                limits.position_max_rad = ReadF32(&request->payload[17]);
                limits.bus_min_v = ReadF32(&request->payload[21]);
                limits.bus_max_v = ReadF32(&request->payload[25]);
                limits.temperature_max_c = ReadF32(&request->payload[29]);
                if (!isfinite(limits.current_a) ||
                    !isfinite(limits.torque_nm) ||
                    !isfinite(limits.speed_rad_s) ||
                    !isfinite(limits.position_min_rad) ||
                    !isfinite(limits.position_max_rad) ||
                    !isfinite(limits.bus_min_v) ||
                    !isfinite(limits.bus_max_v) ||
                    !isfinite(limits.temperature_max_c) ||
                    (limits.current_a <= 0.0F) ||
                    (limits.torque_nm <= 0.0F) ||
                    (limits.speed_rad_s <= 0.0F) ||
                    (fabsf(
                         router->motor->open_loop
                             .target_velocity_rad_s) >
                     limits.speed_rad_s) ||
                    (limits.position_min_rad >= limits.position_max_rad) ||
                    (limits.bus_min_v >= limits.bus_max_v) ||
                    (router->motor->open_loop.bus_voltage_v <
                     limits.bus_min_v) ||
                    (router->motor->open_loop.bus_voltage_v >
                     limits.bus_max_v))
                {
                    status = PROTOCOL_OUT_OF_RANGE;
                }
                else
                {
                    router->motor->limits = limits;
                }
            }
            break;

        case CMD_GET_LIMITS:
            if (!IsSingleMotorPayload(request, 1U) ||
                (request->payload_length != 1U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            detail[0] = MOTOR_DEVICE_ID;
            WriteF32(&detail[1], router->motor->limits.current_a);
            WriteF32(&detail[5], router->motor->limits.torque_nm);
            WriteF32(&detail[9], router->motor->limits.speed_rad_s);
            WriteF32(&detail[13], router->motor->limits.position_min_rad);
            WriteF32(&detail[17], router->motor->limits.position_max_rad);
            WriteF32(&detail[21], router->motor->limits.bus_min_v);
            WriteF32(&detail[25], router->motor->limits.bus_max_v);
            WriteF32(&detail[29], router->motor->limits.temperature_max_c);
            detail_length = 33U;
            break;

        case CMD_SAVE_CONFIG:
            if (router->motor->enabled)
            {
                status = PROTOCOL_INVALID_STATE;
            }
            else
            {
                MotorPersistentConfig config;
                MotorControl_ApplyPendingPid(router->motor);
                MotorControl_ExportPersistentConfig(
                    router->motor,
                    &config);
                config.telemetry_rate_hz = router->telemetry_rate_hz;
                config.telemetry_mask = router->telemetry_mask;
                if (!Tc375Hal_SaveConfiguration(
                         &config,
                         sizeof(config)))
                {
                    status = PROTOCOL_STORAGE_ERROR;
                }
            }
            break;

        case CMD_RESTORE_DEFAULTS:
            if (router->motor->enabled)
            {
                status = PROTOCOL_INVALID_STATE;
            }
            else
            {
                MotorControl_RestoreDefaults(router->motor);
                router->telemetry_rate_hz = MOTOR_TELEMETRY_HZ;
                router->telemetry_mask = 0xFFFFFFFFUL;
                InvalidateOpenLoopTransferState(router);
            }
            break;

        default:
            status = PROTOCOL_UNSUPPORTED_COMMAND;
            break;
    }
    SendResponse(router, request, status, detail, detail_length);
}

void CommandRouter_SendTelemetry(CommandRouter *router, uint8_t sequence)
{
    NativeFrame *frame = &router->telemetry_frame;
    size_t length;
    const MotorTelemetry *value = &router->motor->telemetry;
    uint16_t status = value->status;

    memset(frame, 0, sizeof(*frame));
    frame->version = NATIVE_PROTOCOL_VERSION;
    frame->device = MOTOR_DEVICE_ID;
    frame->command = CMD_TELEMETRY;
    frame->sequence = sequence;
    frame->payload[0] = MOTOR_DEVICE_ID;
    WriteF32(&frame->payload[1], value->speed_rad_s * 9.549296586F);
    WriteF32(&frame->payload[5], value->iq_current_a);
    WriteF32(&frame->payload[9], value->bus_voltage_v);
    WriteF32(&frame->payload[13], value->temperature_c);
    WriteF32(&frame->payload[17], value->position_rad * 57.295779513F);
    if (router->motor->enabled)
    {
        status |= 1U << 0;
    }
    if (router->motor->calibrated)
    {
        status |= 1U << 1;
    }
    if (router->motor->state == MOTOR_STATE_ESTOP)
    {
        status |= 1U << 2;
    }
    if (router->motor->faults != 0U)
    {
        status |= 1U << 3;
    }
    if (router->motor->heartbeat_valid)
    {
        status |= 1U << 4;
    }
    if (router->motor->open_loop_active)
    {
        status |= 1U << 5;
    }
    if (router->motor->state == MOTOR_STATE_STOPPING)
    {
        status |= 1U << 6;
    }
    frame->payload[21] = (uint8_t)(status & 0xFFU);
    frame->payload[22] = (uint8_t)(status >> 8);
    frame->payload_length = 23U;
    length = NativeProtocol_Encode(
        frame,
        router->encoded_telemetry,
        sizeof(router->encoded_telemetry));
    if (length != 0U)
    {
        router->transmit(
            router->encoded_telemetry,
            (uint16_t)length,
            false);
    }
}
