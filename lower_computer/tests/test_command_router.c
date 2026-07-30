#include "command_router.h"
#include "motor_control.h"
#include "native_protocol.h"
#include "project_config.h"
#include "tc375_hal_stub.h"

#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t g_transmitted[NATIVE_PROTOCOL_MAX_FRAME];
static uint16_t g_transmitted_length;

static const uint8_t g_open_loop_payload[
    COMMAND_ROUTER_OPEN_LOOP_CONFIG_SIZE] = {
    0x01U, 0x01U, 0x07U, 0x00U,
    0x00U, 0x00U, 0x00U, 0x41U, /* bus voltage = 8.0 V */
    0x00U, 0x00U, 0x80U, 0x3EU, /* voltage limit = 0.25 V */
    0x00U, 0x00U, 0x80U, 0x40U, /* target = 4.0 rad/s */
    0x00U, 0x00U, 0x00U, 0x41U, /* acceleration = 8 rad/s^2 */
    0x0FU, 0x00U,             /* update period = 15 ms */
    0x58U, 0x02U,             /* startup delay = 600 ms */
    0xD0U, 0x07U, 0x00U, 0x00U /* max runtime = 2000 ms */
};

static bool CaptureTransmit(
    const uint8_t *data,
    uint16_t length,
    bool high_priority)
{
    assert(high_priority);
    assert(length <= sizeof(g_transmitted));
    memcpy(g_transmitted, data, length);
    g_transmitted_length = length;
    return true;
}

static NativeFrame ParseSingleFrame(
    const uint8_t *bytes,
    size_t length)
{
    NativeParser parser;
    NativeFrame frame;
    size_t index;
    bool complete = false;

    NativeParser_Init(&parser);
    memset(&frame, 0, sizeof(frame));
    for (index = 0U; index < length; ++index)
    {
        if (NativeParser_Push(&parser, bytes[index], &frame))
        {
            assert(!complete);
            complete = true;
        }
    }
    assert(complete);
    assert(parser.crc_errors == 0U);
    assert(parser.length_errors == 0U);
    return frame;
}

static void InitRequest(
    NativeFrame *request,
    uint8_t command,
    uint8_t sequence,
    const uint8_t *payload,
    uint16_t payload_length)
{
    memset(request, 0, sizeof(*request));
    request->version = NATIVE_PROTOCOL_VERSION;
    request->device = MOTOR_DEVICE_ID;
    request->command = command;
    request->sequence = sequence;
    request->payload_length = payload_length;
    if (payload_length != 0U)
    {
        assert(payload != NULL);
        memcpy(request->payload, payload, payload_length);
    }
}

static NativeFrame HandleAndParse(
    CommandRouter *router,
    const NativeFrame *request)
{
    g_transmitted_length = 0U;
    CommandRouter_Handle(router, request);
    assert(g_transmitted_length != 0U);
    return ParseSingleFrame(g_transmitted, g_transmitted_length);
}

static void AssertResponse(
    const NativeFrame *response,
    uint8_t response_command,
    uint8_t original_command,
    uint8_t sequence,
    ProtocolStatus status)
{
    assert(response->command == response_command);
    assert(response->sequence == sequence);
    assert(response->payload_length >= 2U);
    assert(response->payload[0] == original_command);
    assert(response->payload[1] == (uint8_t)status);
}

static uint16_t ReadResponseU16(
    const NativeFrame *response,
    uint16_t offset)
{
    assert((uint16_t)(offset + 1U) < response->payload_length);
    return (uint16_t)response->payload[offset] |
           ((uint16_t)response->payload[offset + 1U] << 8);
}

static uint32_t ReadResponseU32(
    const NativeFrame *response,
    uint16_t offset)
{
    assert((uint16_t)(offset + 3U) < response->payload_length);
    return (uint32_t)response->payload[offset] |
           ((uint32_t)response->payload[offset + 1U] << 8) |
           ((uint32_t)response->payload[offset + 2U] << 16) |
           ((uint32_t)response->payload[offset + 3U] << 24);
}

static NativeFrame SendOpenLoopFragmentData(
    CommandRouter *router,
    uint8_t generation,
    uint8_t fragment_index,
    uint8_t sequence,
    const uint8_t *raw_config)
{
    NativeFrame request;
    NativeFrame response;
    uint8_t payload[5];
    uint8_t encoded[NATIVE_PROTOCOL_MAX_FRAME];
    size_t encoded_length;

    payload[0] = MOTOR_DEVICE_ID;
    payload[1] = generation;
    payload[2] = fragment_index;
    memcpy(
        &payload[3],
        &raw_config[
            (uint16_t)fragment_index *
            COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_SIZE],
        COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_SIZE);
    InitRequest(
        &request,
        CMD_SET_OPEN_LOOP_CONFIG_PART,
        sequence,
        payload,
        sizeof(payload));

    encoded_length = NativeProtocol_Encode(
        &request,
        encoded,
        sizeof(encoded));
    assert(encoded_length == 16U);

    response = HandleAndParse(router, &request);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_SET_OPEN_LOOP_CONFIG_PART,
        sequence,
        PROTOCOL_OK);
    assert(response.payload_length == 4U);
    assert(response.payload[2] == generation);
    assert(response.payload[3] == fragment_index);
    return response;
}

static NativeFrame SendOpenLoopFragment(
    CommandRouter *router,
    uint8_t generation,
    uint8_t fragment_index,
    uint8_t sequence)
{
    return SendOpenLoopFragmentData(
        router,
        generation,
        fragment_index,
        sequence,
        g_open_loop_payload);
}

static NativeFrame SendOpenLoopCommit(
    CommandRouter *router,
    uint8_t generation,
    uint16_t config_crc,
    uint8_t sequence)
{
    NativeFrame request;
    uint8_t payload[4];
    uint8_t encoded[NATIVE_PROTOCOL_MAX_FRAME];
    size_t encoded_length;

    payload[0] = MOTOR_DEVICE_ID;
    payload[1] = generation;
    payload[2] = (uint8_t)(config_crc & 0xFFU);
    payload[3] = (uint8_t)(config_crc >> 8);
    InitRequest(
        &request,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        sequence,
        payload,
        sizeof(payload));

    encoded_length = NativeProtocol_Encode(
        &request,
        encoded,
        sizeof(encoded));
    assert(encoded_length == 15U);
    return HandleAndParse(router, &request);
}

static void AssertOpenLoopConfigWasCommitted(
    const MotorControl *motor)
{
    assert(motor->open_loop.backend == MOTOR_OPEN_LOOP_SIMPLEFOC);
    assert(motor->open_loop.pole_pairs == 7U);
    assert(fabsf(motor->open_loop.bus_voltage_v - 8.0F) < 0.0001F);
    assert(
        fabsf(motor->open_loop.voltage_limit_v - 0.25F) <
        0.0001F);
    assert(
        fabsf(motor->open_loop.target_velocity_rad_s - 4.0F) <
        0.0001F);
    assert(
        fabsf(motor->open_loop.acceleration_rad_s2 - 8.0F) <
        0.0001F);
    assert(motor->open_loop.update_period_ms == 15U);
    assert(motor->open_loop.startup_delay_ms == 600U);
    assert(motor->open_loop.max_runtime_ms == 2000U);
}

#if !MOTOR_POWER_STAGE_ENABLED
static void TestSetOpenLoopConfigAck(void)
{
    static const uint8_t request_bytes[] = {
        0xAAU, 0x55U, 0x02U, 0x00U, 0x01U, 0x26U, 0xE2U,
        0x1CU, 0x00U, 0x01U, 0x01U, 0x07U, 0x00U, 0x00U,
        0x00U, 0xE0U, 0x40U, 0x9AU, 0x99U, 0x99U, 0x3EU,
        0x00U, 0x00U, 0xA0U, 0x40U, 0x00U, 0x00U, 0x20U,
        0x41U, 0x0AU, 0x00U, 0xF4U, 0x01U, 0x30U, 0x75U,
        0x00U, 0x00U, 0xB3U, 0x99U};
    MotorControl motor;
    CommandRouter router;
    NativeFrame request;
    NativeFrame response;

    request = ParseSingleFrame(
        request_bytes,
        sizeof(request_bytes));
    assert(request.command == CMD_SET_OPEN_LOOP_CONFIG);
    assert(request.payload_length == 28U);

    MotorControl_Init(&motor, 0U);
    CommandRouter_Init(&router, &motor, CaptureTransmit);
    g_transmitted_length = 0U;

    CommandRouter_Handle(&router, &request);

    assert(g_transmitted_length != 0U);
    response = ParseSingleFrame(
        g_transmitted,
        g_transmitted_length);
    assert(response.command == CMD_ACK);
    assert(response.sequence == 0xE2U);
    assert(response.payload_length == 2U);
    assert(response.payload[0] == CMD_SET_OPEN_LOOP_CONFIG);
    assert(response.payload[1] == PROTOCOL_OK);
    assert(motor.open_loop.backend == MOTOR_OPEN_LOOP_SIMPLEFOC);
    assert(motor.open_loop.pole_pairs == 7U);
    assert(fabsf(motor.open_loop.bus_voltage_v - 7.0F) < 0.0001F);
    assert(fabsf(motor.open_loop.voltage_limit_v - 0.3F) < 0.0001F);
    assert(
        fabsf(motor.open_loop.target_velocity_rad_s - 5.0F) <
        0.0001F);
    assert(motor.open_loop.update_period_ms == 10U);
    assert(motor.open_loop.startup_delay_ms == 500U);
    assert(motor.open_loop.max_runtime_ms == 30000U);
}
#endif

static void TestFragmentedOpenLoopConfigCommit(void)
{
    MotorControl motor;
    MotorOpenLoopConfig before;
    CommandRouter router;
    NativeFrame response;
    uint8_t index;
    uint16_t crc;

    MotorControl_Init(&motor, 0U);
    before = motor.open_loop;
    CommandRouter_Init(&router, &motor, CaptureTransmit);
    crc = NativeProtocol_Crc16(
        g_open_loop_payload,
        sizeof(g_open_loop_payload));

    for (index = 0U;
         index < COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_COUNT;
         ++index)
    {
        (void)SendOpenLoopFragment(
            &router,
            0x42U,
            index,
            (uint8_t)(0x20U + index));
        assert(
            memcmp(
                &motor.open_loop,
                &before,
                sizeof(before)) == 0);

        /* A timeout retry may overwrite the same part safely. */
        if (index == 5U)
        {
            (void)SendOpenLoopFragment(
                &router,
                0x42U,
                index,
                0x60U);
        }
    }

    response = SendOpenLoopCommit(
        &router,
        0x42U,
        crc,
        0x70U);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0x70U,
        PROTOCOL_OK);
    assert(response.payload_length == 3U);
    assert(response.payload[2] == 0x42U);
    assert(!router.open_loop_staging_active);
    assert(router.open_loop_staging_mask == 0U);
    AssertOpenLoopConfigWasCommitted(&motor);

    /* A lost commit ACK must not turn a successful write into failure. */
    response = SendOpenLoopCommit(
        &router,
        0x42U,
        crc,
        0x71U);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0x71U,
        PROTOCOL_OK);
    assert(response.payload_length == 3U);
    assert(response.payload[2] == 0x42U);
    AssertOpenLoopConfigWasCommitted(&motor);

    Tc375HalStub_SetTimeMs(
        (uint64_t)UINT32_MAX +
        COMMAND_ROUTER_OPEN_LOOP_STAGING_TIMEOUT_MS +
        100ULL);
    response = SendOpenLoopCommit(
        &router,
        0x42U,
        crc,
        0x72U);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0x72U,
        PROTOCOL_INVALID_STATE);
    assert(!router.open_loop_committed_valid);
    AssertOpenLoopConfigWasCommitted(&motor);
}

static void TestFragmentedOpenLoopConfigRejectsMissingPart(void)
{
    MotorControl motor;
    MotorOpenLoopConfig before;
    CommandRouter router;
    NativeFrame response;
    uint8_t index;
    uint16_t crc;

    MotorControl_Init(&motor, 0U);
    before = motor.open_loop;
    CommandRouter_Init(&router, &motor, CaptureTransmit);
    crc = NativeProtocol_Crc16(
        g_open_loop_payload,
        sizeof(g_open_loop_payload));

    for (index = 0U;
         index < COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_COUNT;
         ++index)
    {
        if (index != 6U)
        {
            (void)SendOpenLoopFragment(
                &router,
                0x51U,
                index,
                (uint8_t)(0x80U + index));
        }
    }

    response = SendOpenLoopCommit(
        &router,
        0x51U,
        crc,
        0x90U);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0x90U,
        PROTOCOL_INVALID_STATE);
    assert(response.payload_length == 2U);
    assert(router.open_loop_staging_active);
    assert(
        memcmp(
            &motor.open_loop,
            &before,
            sizeof(before)) == 0);

    (void)SendOpenLoopFragment(&router, 0x51U, 6U, 0x91U);
    response = SendOpenLoopCommit(
        &router,
        0x51U,
        crc,
        0x92U);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0x92U,
        PROTOCOL_OK);
    AssertOpenLoopConfigWasCommitted(&motor);
}

static void TestFragmentedOpenLoopConfigRejectsBadCrc(void)
{
    MotorControl motor;
    MotorOpenLoopConfig before;
    CommandRouter router;
    NativeFrame response;
    uint8_t index;
    uint16_t crc;

    MotorControl_Init(&motor, 0U);
    before = motor.open_loop;
    CommandRouter_Init(&router, &motor, CaptureTransmit);
    crc = NativeProtocol_Crc16(
        g_open_loop_payload,
        sizeof(g_open_loop_payload));

    for (index = 0U;
         index < COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_COUNT;
         ++index)
    {
        (void)SendOpenLoopFragment(
            &router,
            0x63U,
            index,
            (uint8_t)(0xA0U + index));
    }

    response = SendOpenLoopCommit(
        &router,
        0x63U,
        (uint16_t)(crc ^ 0x0001U),
        0xB0U);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0xB0U,
        PROTOCOL_INVALID_PAYLOAD);
    assert(response.payload_length == 2U);
    assert(router.open_loop_staging_active);
    assert(
        memcmp(
            &motor.open_loop,
            &before,
            sizeof(before)) == 0);

    /* A corrected commit can reuse the fully staged generation. */
    response = SendOpenLoopCommit(
        &router,
        0x63U,
        crc,
        0xB1U);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0xB1U,
        PROTOCOL_OK);
    AssertOpenLoopConfigWasCommitted(&motor);
}

static void TestFragmentedOpenLoopConfigRejectsInnerMotor(void)
{
    MotorControl motor;
    MotorOpenLoopConfig before;
    CommandRouter router;
    NativeFrame response;
    uint8_t invalid_payload[
        COMMAND_ROUTER_OPEN_LOOP_CONFIG_SIZE];
    uint8_t index;
    uint16_t crc;

    memcpy(
        invalid_payload,
        g_open_loop_payload,
        sizeof(invalid_payload));
    invalid_payload[0] = 2U;
    crc = NativeProtocol_Crc16(
        invalid_payload,
        sizeof(invalid_payload));
    Tc375HalStub_Reset();
    MotorControl_Init(&motor, 0U);
    before = motor.open_loop;
    CommandRouter_Init(&router, &motor, CaptureTransmit);

    for (index = 0U;
         index < COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_COUNT;
         ++index)
    {
        (void)SendOpenLoopFragmentData(
            &router,
            0x74U,
            index,
            (uint8_t)(0x20U + index),
            invalid_payload);
    }
    response = SendOpenLoopCommit(
        &router,
        0x74U,
        crc,
        0x40U);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0x40U,
        PROTOCOL_INVALID_PAYLOAD);
    assert(
        memcmp(
            &motor.open_loop,
            &before,
            sizeof(before)) == 0);
}

static void TestFragmentValidationAndStagingExpiry(void)
{
    MotorControl motor;
    MotorOpenLoopConfig before;
    CommandRouter router;
    NativeFrame request;
    NativeFrame response;
    uint8_t payload[5] = {
        MOTOR_DEVICE_ID, 0x75U,
        COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_COUNT,
        0U, 0U};
    uint8_t index;
    uint16_t crc;

    Tc375HalStub_Reset();
    MotorControl_Init(&motor, 0U);
    before = motor.open_loop;
    CommandRouter_Init(&router, &motor, CaptureTransmit);
    crc = NativeProtocol_Crc16(
        g_open_loop_payload,
        sizeof(g_open_loop_payload));

    InitRequest(
        &request,
        CMD_SET_OPEN_LOOP_CONFIG_PART,
        0x50U,
        payload,
        sizeof(payload));
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_SET_OPEN_LOOP_CONFIG_PART,
        0x50U,
        PROTOCOL_INVALID_PAYLOAD);

    (void)SendOpenLoopFragment(
        &router,
        0x75U,
        0U,
        0x51U);
    Tc375HalStub_SetTimeMs(
        COMMAND_ROUTER_OPEN_LOOP_STAGING_TIMEOUT_MS + 100U);
    for (index = 1U;
         index < COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_COUNT;
         ++index)
    {
        (void)SendOpenLoopFragment(
            &router,
            0x75U,
            index,
            (uint8_t)(0x51U + index));
    }
    response = SendOpenLoopCommit(
        &router,
        0x75U,
        crc,
        0x70U);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_COMMIT_OPEN_LOOP_CONFIG,
        0x70U,
        PROTOCOL_INVALID_STATE);
    assert(
        memcmp(
            &motor.open_loop,
            &before,
            sizeof(before)) == 0);

    motor.enabled = true;
    payload[1] = 0x76U;
    payload[2] = 0U;
    memcpy(
        &payload[3],
        g_open_loop_payload,
        COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_SIZE);
    InitRequest(
        &request,
        CMD_SET_OPEN_LOOP_CONFIG_PART,
        0x71U,
        payload,
        sizeof(payload));
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_SET_OPEN_LOOP_CONFIG_PART,
        0x71U,
        PROTOCOL_INVALID_STATE);
}

static void TestExtendedRxServiceDiagnostics(void)
{
    MotorControl motor;
    CommandRouter router;
    NativeFrame request;
    NativeFrame response;
    uint8_t sections;

    Tc375HalStub_Reset();
    Tc375HalStub_SetUartRxServiceCounters(
        0x1234U,
        0x4567U,
        0x89ABU);
    MotorControl_Init(&motor, 0U);
    CommandRouter_Init(&router, &motor, CaptureTransmit);

    /*
     * The pre-RXF1 request stays byte-for-byte compatible: two ACK prefix
     * bytes followed by the existing 40-byte diagnostics detail.
     */
    sections = 0x03U;
    InitRequest(
        &request,
        CMD_GET_DIAGNOSTICS,
        0xD0U,
        &sections,
        sizeof(sections));
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_GET_DIAGNOSTICS,
        0xD0U,
        PROTOCOL_OK);
    assert(response.payload_length == 42U);

    /*
     * Section bit 2 appends three saturated u16 counters. Offsets include
     * the two-byte ACK prefix, hence detail[40] starts at payload[42].
     */
    sections = 0x07U;
    InitRequest(
        &request,
        CMD_GET_DIAGNOSTICS,
        0xD1U,
        &sections,
        sizeof(sections));
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_GET_DIAGNOSTICS,
        0xD1U,
        PROTOCOL_OK);
    assert(response.payload_length == 48U);
    assert(ReadResponseU16(&response, 42U) == 0x1234U);
    assert(ReadResponseU16(&response, 44U) == 0x4567U);
    assert(ReadResponseU16(&response, 46U) == 0x89ABU);
}

static uint8_t ExpectedHardwareFlags(void)
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

static void TestBuildConfigAndHardwareDiagnostics(void)
{
    MotorControl motor;
    CommandRouter router;
    NativeFrame request;
    NativeFrame response;
    uint8_t expected_flags;

    Tc375HalStub_Reset();
    MotorControl_Init(&motor, 0U);
    CommandRouter_Init(&router, &motor, CaptureTransmit);

    InitRequest(
        &request,
        CMD_GET_CAPABILITIES,
        0xE0U,
        NULL,
        0U);
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_GET_CAPABILITIES,
        0xE0U,
        PROTOCOL_OK);
    assert(response.payload_length == 11U);
    assert(
        (ReadResponseU32(&response, 5U) &
         NATIVE_FEATURE_POWER_STAGE_CONFIRMED_START) != 0U);

    InitRequest(
        &request,
        CMD_GET_BUILD_CONFIG,
        0xE1U,
        NULL,
        0U);
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_GET_BUILD_CONFIG,
        0xE1U,
        PROTOCOL_OK);
    assert(response.payload_length == 39U);
    assert(response.payload[2] == MOTOR_DEVICE_ID);
    assert(
        response.payload[3] ==
        (MOTOR_CONTROL_HARDWARE_ENABLED ? 1U : 0U));
    assert(
        response.payload[4] ==
        (MOTOR_POWER_STAGE_ENABLED ? 1U : 0U));
    assert(
        ReadResponseU32(&response, 35U) ==
        MOTOR_POWER_STAGE_REPORTED_SAFETY_MASK);

    assert(
        Tc375Hal_SetGateEnabled(true) ==
        (MOTOR_POWER_STAGE_ENABLED ? true : false));
    Tc375Hal_SetPwmEnabled(true);
    expected_flags = ExpectedHardwareFlags();
    InitRequest(
        &request,
        CMD_GET_DIAGNOSTICS,
        0xE2U,
        NULL,
        0U);
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_GET_DIAGNOSTICS,
        0xE2U,
        PROTOCOL_OK);
    assert(response.payload_length == 26U);
    assert(response.payload[21] == expected_flags);

    Tc375HalStub_SetActiveFaults(MOTOR_FAULT_GATE_DRIVER);
    expected_flags = ExpectedHardwareFlags();
    response = HandleAndParse(&router, &request);
    assert(response.payload[21] == expected_flags);
    assert(
        (response.payload[21] &
         NATIVE_DIAGNOSTIC_HW_NFAULT_CLEAR) == 0U);
}

static void TestOpenLoopStartFlags(void)
{
    MotorControl motor;
    MotorOpenLoopConfig config;
    CommandRouter router;
    NativeFrame request;
    NativeFrame response;
    uint8_t legacy_payload[1] = {MOTOR_DEVICE_ID};
    uint8_t flagged_payload[2] = {
        MOTOR_DEVICE_ID,
        NATIVE_START_FLAG_POWER_STAGE_CONFIRMED};

    Tc375HalStub_Reset();
    MotorControl_Init(&motor, 0U);
    config = motor.open_loop;
#if MOTOR_POWER_STAGE_ENABLED
    /*
     * Keep the power-stage variant conservative even when the build uses
     * the explicit commissioning override.
     */
    config.bus_voltage_v = 9.0F;
    config.voltage_limit_v = 0.10F;
    config.target_velocity_rad_s = 1.0F;
    config.acceleration_rad_s2 = 1.0F;
    config.startup_delay_ms = 500U;
    config.max_runtime_ms = 1000U;
#endif
    assert(
        MotorControl_SetOpenLoopConfig(&motor, &config) ==
        MOTOR_RESULT_OK);
    MotorControl_Heartbeat(&motor, 0U, 5000U);
    CommandRouter_Init(&router, &motor, CaptureTransmit);

    InitRequest(
        &request,
        CMD_START_OPEN_LOOP,
        0xF0U,
        legacy_payload,
        sizeof(legacy_payload));
    response = HandleAndParse(&router, &request);
#if MOTOR_POWER_STAGE_ENABLED
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_START_OPEN_LOOP,
        0xF0U,
        PROTOCOL_SAFETY_INTERLOCK);
    assert(!motor.enabled);
#else
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_START_OPEN_LOOP,
        0xF0U,
        PROTOCOL_OK);
    assert(motor.open_loop_active);
    MotorControl_StopWithReason(
        &motor,
        false,
        MOTOR_STOP_REASON_QUICK_STOP_COMMAND);
#endif

#if MOTOR_POWER_STAGE_ENABLED
    flagged_payload[1] = 0U;
    InitRequest(
        &request,
        CMD_START_OPEN_LOOP,
        0xF1U,
        flagged_payload,
        sizeof(flagged_payload));
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_START_OPEN_LOOP,
        0xF1U,
        PROTOCOL_SAFETY_INTERLOCK);
    assert(!motor.enabled);
#endif

    flagged_payload[1] = 0x80U;
    InitRequest(
        &request,
        CMD_START_OPEN_LOOP,
        0xF2U,
        flagged_payload,
        sizeof(flagged_payload));
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ERROR,
        CMD_START_OPEN_LOOP,
        0xF2U,
        PROTOCOL_INVALID_PAYLOAD);
    assert(!motor.enabled);

    flagged_payload[1] =
        NATIVE_START_FLAG_POWER_STAGE_CONFIRMED;
    InitRequest(
        &request,
        CMD_START_OPEN_LOOP,
        0xF3U,
        flagged_payload,
        sizeof(flagged_payload));
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_START_OPEN_LOOP,
        0xF3U,
        PROTOCOL_OK);
    assert(motor.enabled);
    assert(motor.open_loop_active);
}

static void TestQuickStopImmediatelyDisablesHardware(void)
{
    MotorControl motor;
    CommandRouter router;
    NativeFrame request;
    NativeFrame response;
    uint8_t payload[1] = {MOTOR_DEVICE_ID};
    float phase_a;
    float phase_b;
    float phase_c;

    Tc375HalStub_Reset();
    MotorControl_Init(&motor, 0U);
    CommandRouter_Init(&router, &motor, CaptureTransmit);
    (void)Tc375Hal_SetGateEnabled(true);
    Tc375Hal_SetPwmEnabled(true);
    Tc375Hal_SetPhaseDuty(0.2F, 0.4F, 0.6F);
    assert(Tc375Hal_IsPwmEnabled());

    motor.enabled = true;
    motor.open_loop_active = true;
    motor.open_loop_output_ready = true;
    motor.state = MOTOR_STATE_RUNNING;
    motor.target = 2.0F;

    InitRequest(
        &request,
        CMD_QUICK_STOP,
        0xF4U,
        payload,
        sizeof(payload));
    response = HandleAndParse(&router, &request);
    AssertResponse(
        &response,
        CMD_ACK,
        CMD_QUICK_STOP,
        0xF4U,
        PROTOCOL_OK);
    assert(!motor.enabled);
    assert(!motor.open_loop_active);
    assert(
        motor.last_stop_reason ==
        MOTOR_STOP_REASON_QUICK_STOP_COMMAND);
    assert(!Tc375Hal_IsPwmEnabled());
    assert(!Tc375Hal_IsGateEnabled());
    Tc375HalStub_GetPhaseDuty(
        &phase_a,
        &phase_b,
        &phase_c);
    assert(phase_a == 0.0F);
    assert(phase_b == 0.0F);
    assert(phase_c == 0.0F);
}

int main(void)
{
    Tc375HalStub_Reset();
#if !MOTOR_POWER_STAGE_ENABLED
    TestSetOpenLoopConfigAck();
#endif
    Tc375HalStub_Reset();
    TestFragmentedOpenLoopConfigCommit();
    Tc375HalStub_Reset();
    TestFragmentedOpenLoopConfigRejectsMissingPart();
    Tc375HalStub_Reset();
    TestFragmentedOpenLoopConfigRejectsBadCrc();
    TestFragmentedOpenLoopConfigRejectsInnerMotor();
    TestFragmentValidationAndStagingExpiry();
    TestExtendedRxServiceDiagnostics();
    TestBuildConfigAndHardwareDiagnostics();
    TestOpenLoopStartFlags();
    TestQuickStopImmediatelyDisablesHardware();
    puts("lower_computer command router: OK");
    return 0;
}
