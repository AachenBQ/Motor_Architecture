#include "motor_control.h"
#include "native_protocol.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

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

int main(void)
{
    TestKnownCrc();
    TestProtocolRoundTrip();
    TestHeartbeatSafetyStop();
    TestPidLoopsRemainIndependent();
    puts("lower_computer core tests: OK");
    return 0;
}

