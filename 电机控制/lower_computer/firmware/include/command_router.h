#ifndef COMMAND_ROUTER_H
#define COMMAND_ROUTER_H

#include "motor_control.h"
#include "native_protocol.h"

#include <stdbool.h>
#include <stdint.h>

typedef bool (*CommandRouterTransmit)(
    const uint8_t *data,
    uint16_t length,
    bool high_priority);

typedef struct
{
    MotorControl *motor;
    CommandRouterTransmit transmit;
    uint16_t telemetry_rate_hz;
    uint32_t telemetry_mask;
    uint32_t commands_received;
    uint16_t protocol_errors;
    NativeFrame response_frame;
    uint8_t encoded_frame[NATIVE_PROTOCOL_MAX_FRAME];
    NativeFrame telemetry_frame;
    uint8_t encoded_telemetry[NATIVE_PROTOCOL_MAX_FRAME];
} CommandRouter;

void CommandRouter_Init(
    CommandRouter *router,
    MotorControl *motor,
    CommandRouterTransmit transmit);
void CommandRouter_Handle(CommandRouter *router, const NativeFrame *request);
void CommandRouter_SendTelemetry(CommandRouter *router, uint8_t sequence);

#endif
