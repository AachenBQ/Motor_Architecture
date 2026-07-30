#include "motor_control.h"
#include "native_protocol.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static size_t EncodeTestFrame(
    NativeFrame *frame,
    uint8_t sequence,
    const uint8_t *payload,
    uint16_t payload_length,
    uint8_t *encoded)
{
    memset(frame, 0, sizeof(*frame));
    frame->version = NATIVE_PROTOCOL_VERSION;
    frame->device = 1U;
    frame->command = CMD_PING;
    frame->sequence = sequence;
    frame->payload_length = payload_length;
    if (payload_length != 0U)
    {
        memcpy(frame->payload, payload, payload_length);
    }
    return NativeProtocol_Encode(
        frame,
        encoded,
        NATIVE_PROTOCOL_MAX_FRAME);
}

static bool PushBytes(
    NativeParser *parser,
    NativeFrame *output,
    const uint8_t *bytes,
    size_t length)
{
    size_t index;
    bool complete = false;

    for (index = 0U; index < length; ++index)
    {
        complete = NativeParser_Push(parser, bytes[index], output);
    }
    return complete;
}

static void TestProtocolRoundTrip(void)
{
    NativeFrame input;
    NativeFrame output;
    NativeParser parser;
    uint8_t encoded[NATIVE_PROTOCOL_MAX_FRAME];
    size_t length;
    size_t index;
    bool complete = false;

    memset(&input, 0, sizeof(input));
    input.version = NATIVE_PROTOCOL_VERSION;
    input.device = 1U;
    input.command = CMD_PING;
    input.sequence = 42U;
    memcpy(input.payload, "hello", 5U);
    input.payload_length = 5U;

    length = NativeProtocol_Encode(&input, encoded, sizeof(encoded));
    assert(length == 16U);
    NativeParser_Init(&parser);
    for (index = 0U; index < length; ++index)
    {
        complete = NativeParser_Push(&parser, encoded[index], &output);
    }
    assert(complete);
    assert(output.version == NATIVE_PROTOCOL_VERSION);
    assert(output.command == CMD_PING);
    assert(output.sequence == 42U);
    assert(output.payload_length == 5U);
    assert(memcmp(output.payload, "hello", 5U) == 0);
}

static void TestParserPartialTimeoutThenValidFrame(void)
{
    static const uint8_t payload[] = {0x11U, 0x22U, 0x33U};
    NativeFrame input;
    NativeFrame output;
    NativeParser parser;
    uint8_t encoded[NATIVE_PROTOCOL_MAX_FRAME];
    size_t length;

    length = EncodeTestFrame(
        &input,
        10U,
        payload,
        (uint16_t)sizeof(payload),
        encoded);
    assert(length != 0U);

    NativeParser_Init(&parser);
    assert(!PushBytes(&parser, &output, encoded, 6U));
    assert(parser.used == 6U);
    assert(NativeParser_ExpirePartial(&parser));
    assert(parser.timeout_errors == 1U);
    assert(parser.used == 0U);
    assert(parser.expected == 0U);
    assert(!NativeParser_ExpirePartial(&parser));
    assert(parser.timeout_errors == 1U);

    assert(PushBytes(&parser, &output, encoded, length));
    assert(output.sequence == 10U);
    assert(output.payload_length == sizeof(payload));
    assert(memcmp(output.payload, payload, sizeof(payload)) == 0);
}

static void TestParserBadCrcThenValidFrame(void)
{
    static const uint8_t payload[] = {0x41U, 0x42U};
    NativeFrame input;
    NativeFrame output;
    NativeParser parser;
    uint8_t encoded[NATIVE_PROTOCOL_MAX_FRAME];
    uint8_t bad[NATIVE_PROTOCOL_MAX_FRAME];
    size_t length;

    length = EncodeTestFrame(
        &input,
        20U,
        payload,
        (uint16_t)sizeof(payload),
        encoded);
    assert(length != 0U);
    memcpy(bad, encoded, length);
    bad[length - 1U] ^= 0x01U;

    NativeParser_Init(&parser);
    assert(!PushBytes(&parser, &output, bad, length));
    assert(parser.crc_errors == 1U);
    assert(parser.resync_events == 1U);
    assert(PushBytes(&parser, &output, encoded, length));
    assert(output.sequence == 20U);
    assert(output.payload_length == sizeof(payload));
}

static void TestParserOversizeLengthThenValidFrame(void)
{
    static const uint8_t invalid_header[] = {
        0xAAU,
        0x55U,
        NATIVE_PROTOCOL_VERSION,
        0x00U,
        0x01U,
        CMD_PING,
        0x30U,
        (uint8_t)((NATIVE_PROTOCOL_MAX_PAYLOAD + 1U) & 0xFFU),
        (uint8_t)((NATIVE_PROTOCOL_MAX_PAYLOAD + 1U) >> 8)
    };
    static const uint8_t payload[] = {0x5AU};
    NativeFrame input;
    NativeFrame output;
    NativeParser parser;
    uint8_t encoded[NATIVE_PROTOCOL_MAX_FRAME];
    size_t length;

    length = EncodeTestFrame(
        &input,
        31U,
        payload,
        (uint16_t)sizeof(payload),
        encoded);
    assert(length != 0U);

    NativeParser_Init(&parser);
    assert(!PushBytes(
        &parser,
        &output,
        invalid_header,
        sizeof(invalid_header)));
    assert(parser.length_errors == 1U);
    assert(parser.resync_events == 1U);
    assert(PushBytes(&parser, &output, encoded, length));
    assert(output.sequence == 31U);
}

static void TestParserRecoversNestedFrameOnSamePush(void)
{
    static const uint8_t payload[] = {0xDEU, 0xADU, 0xBEU};
    NativeFrame input;
    NativeFrame output;
    NativeParser parser;
    uint8_t nested[NATIVE_PROTOCOL_MAX_FRAME];
    uint8_t stream[NATIVE_PROTOCOL_MAX_FRAME];
    size_t nested_length;
    size_t stream_length;
    uint16_t corrupt_length;
    uint16_t outer_crc;
    uint16_t nested_crc;

    nested_length = EncodeTestFrame(
        &input,
        40U,
        payload,
        (uint16_t)sizeof(payload),
        nested);
    assert(nested_length > 2U);

    /*
     * The first header claims a plausible length that ends exactly at the
     * nested frame's final byte. The final push must reject the outer CRC,
     * find the nested AA 55 header, and return that valid frame immediately.
     */
    corrupt_length = (uint16_t)(nested_length - 2U);
    stream[0] = 0xAAU;
    stream[1] = 0x55U;
    stream[2] = NATIVE_PROTOCOL_VERSION;
    stream[3] = 0U;
    stream[4] = 1U;
    stream[5] = CMD_PING;
    stream[6] = 39U;
    stream[7] = (uint8_t)(corrupt_length & 0xFFU);
    stream[8] = (uint8_t)(corrupt_length >> 8);
    memcpy(&stream[9], nested, nested_length);
    stream_length = 9U + nested_length;

    outer_crc = NativeProtocol_Crc16(&stream[2], stream_length - 4U);
    nested_crc = (uint16_t)stream[stream_length - 2U] |
        ((uint16_t)stream[stream_length - 1U] << 8);
    assert(outer_crc != nested_crc);

    NativeParser_Init(&parser);
    assert(PushBytes(&parser, &output, stream, stream_length));
    assert(parser.crc_errors == 1U);
    assert(parser.resync_events == 1U);
    assert(output.sequence == 40U);
    assert(output.payload_length == sizeof(payload));
    assert(memcmp(output.payload, payload, sizeof(payload)) == 0);
}

static void TestParserPreservesTailAaAndHeaderOverlap(void)
{
    static const uint8_t payload[] = {0x66U, 0x77U};
    NativeFrame input;
    NativeFrame output;
    NativeParser parser;
    uint8_t encoded[NATIVE_PROTOCOL_MAX_FRAME];
    uint8_t bad[NATIVE_PROTOCOL_MAX_FRAME];
    size_t length;

    length = EncodeTestFrame(
        &input,
        50U,
        payload,
        (uint16_t)sizeof(payload),
        encoded);
    assert(length != 0U);
    memcpy(bad, encoded, length);
    bad[length - 1U] = 0xAAU;
    if (encoded[length - 1U] == 0xAAU)
    {
        bad[length - 2U] ^= 0x01U;
    }

    NativeParser_Init(&parser);
    assert(!PushBytes(&parser, &output, bad, length));
    assert(parser.crc_errors == 1U);
    assert(parser.used == 1U);

    /*
     * The bad frame's tail AA and the next frame's leading AA overlap.
     * A repeated AA must keep the parser synchronized for the following 55.
     */
    assert(PushBytes(&parser, &output, encoded, length));
    assert(output.sequence == 50U);
    assert(output.payload_length == sizeof(payload));
}

static void TestKnownCrc(void)
{
    static const uint8_t vector[] = "123456789";
    assert(NativeProtocol_Crc16(vector, 9U) == 0x4B37U);
}

static void TestHeartbeatSafetyStop(void)
{
    MotorControl motor;
    MotorControl_Init(&motor, 0U);
    MotorControl_SetCalibrationValid(&motor, true);
    MotorControl_Heartbeat(&motor, 0U, 750U);
    assert(MotorControl_SetEnable(&motor, true) == MOTOR_RESULT_OK);
    assert(motor.enabled);

    MotorControl_Tick(&motor, 751U);
    assert(!motor.enabled);
    assert(motor.state == MOTOR_STATE_FAULT);
    assert((motor.faults & MOTOR_FAULT_COMM_TIMEOUT) != 0U);
    assert(
        motor.last_stop_reason ==
        MOTOR_STOP_REASON_HEARTBEAT_TIMEOUT);
}

static void TestHeartbeatMustBeReceivedBeforeEnable(void)
{
    MotorControl motor;

    MotorControl_Init(&motor, 100U);
    MotorControl_SetCalibrationValid(&motor, true);
    MotorControl_Tick(&motor, 101U);
    assert(!motor.heartbeat_valid);
    assert(
        MotorControl_SetEnable(&motor, true) ==
        MOTOR_RESULT_HEARTBEAT_REQUIRED);
    assert(
        MotorControl_StartOpenLoop(&motor, 101U) ==
        MOTOR_RESULT_HEARTBEAT_REQUIRED);
}

static void TestPidLoopsRemainIndependent(void)
{
    MotorControl motor;
    MotorPid current = {1.1F, 0.2F, 0.03F};
    MotorPid position = {3.3F, 0.4F, 0.05F};
    MotorControl_Init(&motor, 0U);
    assert(MotorControl_SetPid(
               &motor,
               MOTOR_PID_CURRENT,
               &current) == MOTOR_RESULT_OK);
    assert(MotorControl_SetPid(
               &motor,
               MOTOR_PID_POSITION,
               &position) == MOTOR_RESULT_OK);
    MotorControl_ApplyPendingPid(&motor);
    assert(motor.pid[MOTOR_PID_CURRENT].kp == 1.1F);
    assert(motor.pid[MOTOR_PID_SPEED].kp == 0.5F);
    assert(motor.pid[MOTOR_PID_POSITION].kp == 3.3F);
}

static void TestOpenLoopRuntimeAndControlledStop(void)
{
    MotorControl motor;
    uint32_t now_ms;
    MotorControl_Init(&motor, 0U);
    MotorControl_Heartbeat(&motor, 0U, 5000U);
    assert(MotorControl_StartOpenLoop(&motor, 0U) == MOTOR_RESULT_OK);
    assert(motor.open_loop_active);
    assert(motor.mode == MOTOR_MODE_OPEN_LOOP_SPEED);

    MotorControl_Tick(&motor, 500U);
    MotorControl_Tick(&motor, 510U);
    assert(motor.open_loop_output_ready);
    assert(motor.open_loop_velocity_rad_s > 0.0F);
    assert(MotorControl_SetTarget(
               &motor,
               MOTOR_MODE_OPEN_LOOP_SPEED,
               2.0F) == MOTOR_RESULT_OK);

    MotorControl_RequestControlledStop(&motor);
    assert(motor.state == MOTOR_STATE_STOPPING);
    for (now_ms = 520U; now_ms < 2000U; now_ms += 10U)
    {
        MotorControl_Heartbeat(&motor, now_ms, 5000U);
        MotorControl_Tick(&motor, now_ms);
    }
    assert(!motor.open_loop_active);
    assert(!motor.enabled);
    assert(
        motor.last_stop_reason ==
        MOTOR_STOP_REASON_CONTROLLED_COMMAND);
}

static void TestTelemetryTripsSafetyLimits(void)
{
    MotorControl motor;
    MotorTelemetry telemetry;
    memset(&telemetry, 0, sizeof(telemetry));
    MotorControl_Init(&motor, 0U);
    telemetry.bus_voltage_v = 7.0F;
    telemetry.temperature_c = 25.0F;
    telemetry.iq_current_a = motor.limits.current_a + 1.0F;
    MotorControl_UpdateTelemetry(&motor, &telemetry);
    assert((motor.faults & MOTOR_FAULT_OVERCURRENT) != 0U);
    assert(motor.state == MOTOR_STATE_FAULT);
}

int main(void)
{
    TestKnownCrc();
    TestProtocolRoundTrip();
    TestParserPartialTimeoutThenValidFrame();
    TestParserBadCrcThenValidFrame();
    TestParserOversizeLengthThenValidFrame();
    TestParserRecoversNestedFrameOnSamePush();
    TestParserPreservesTailAaAndHeaderOverlap();
    TestHeartbeatSafetyStop();
    TestHeartbeatMustBeReceivedBeforeEnable();
    TestPidLoopsRemainIndependent();
    TestOpenLoopRuntimeAndControlledStop();
    TestTelemetryTripsSafetyLimits();
    puts("lower_computer core tests: OK");
    return 0;
}
