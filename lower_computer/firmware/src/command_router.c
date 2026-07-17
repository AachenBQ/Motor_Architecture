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
    uint8_t detail[40];
    uint16_t detail_length = 0U;
    ProtocolStatus status = PROTOCOL_OK;
    MotorResult motor_result;
    MotorPid pid;
    uint8_t loop;
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
            memcpy(detail, "TC375-MCU/0.2", 13U);
            detail_length = 13U;
            break;

        case CMD_GET_DEVICE_INFO:
            detail[0] = 0U;
            detail[1] = 2U;
            detail[2] = 0U;
            detail[3] = 1U;
            detail[4] = 0U;
            WriteU32(&detail[5], 0x37500001UL);
            memset(&detail[9], 0, 24U);
            memcpy(&detail[9], "TC375-MCU", 9U);
            memcpy(&detail[25], "LOCAL", 5U);
            detail_length = 33U;
            break;

        case CMD_GET_CAPABILITIES:
            detail[0] = 1U;
            detail[1] = 0x01U;
            detail[2] = 0x07U;
            WriteU32(&detail[3], (1UL << 0) | (1UL << 2) |
                                    (1UL << 3) | (1UL << 4));
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
        case CMD_QUICK_STOP:
            if (!IsSingleMotorPayload(request, 1U))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            MotorControl_Stop(router->motor, false);
            break;

        case CMD_EMERGENCY_STOP:
            if ((request->payload_length != 1U) ||
                ((request->payload[0] != MOTOR_DEVICE_ID) &&
                 (request->payload[0] != 0xFFU)))
            {
                status = PROTOCOL_INVALID_PAYLOAD;
                break;
            }
            MotorControl_Stop(router->motor, true);
            Tc375Hal_SetGateEnabled(false);
            Tc375Hal_SetPwmEnabled(false);
            break;

        case CMD_GET_DIAGNOSTICS:
            WriteU32(detail, Tc375Hal_TimeMs());
            WriteU16(&detail[4], router->protocol_errors);
            WriteU16(&detail[6], (uint16_t)router->motor->faults);
            detail_length = 8U;
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
            detail[1] = 1U;
            detail_length = 2U;
            break;

        case CMD_GET_TELEMETRY_PROFILE:
            WriteU16(detail, router->telemetry_rate_hz);
            WriteU32(&detail[2], router->telemetry_mask);
            detail_length = 6U;
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
                    (limits.position_min_rad >= limits.position_max_rad) ||
                    (limits.bus_min_v >= limits.bus_max_v))
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
    if (router->motor->faults != 0U)
    {
        status |= 1U << 3;
    }
    if (router->motor->heartbeat_valid)
    {
        status |= 1U << 4;
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
