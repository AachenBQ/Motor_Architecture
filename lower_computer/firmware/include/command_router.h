#ifndef COMMAND_ROUTER_H
#define COMMAND_ROUTER_H

#include "motor_control.h"
#include "native_protocol.h"

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef bool (*CommandRouterTransmit)(
    const uint8_t *data,
    uint16_t length,
    bool high_priority);

#define COMMAND_ROUTER_OPEN_LOOP_CONFIG_SIZE       28U
#define COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_SIZE      2U
#define COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_COUNT    14U
#define COMMAND_ROUTER_OPEN_LOOP_FRAGMENT_FULL_MASK 0x3FFFU
#define COMMAND_ROUTER_OPEN_LOOP_STAGING_TIMEOUT_MS 5000U

typedef struct
{
    MotorControl *motor;
    CommandRouterTransmit transmit;
    uint16_t telemetry_rate_hz;
    uint32_t telemetry_mask;
    uint32_t commands_received;
    uint16_t protocol_errors;
    uint16_t parser_crc_errors;
    uint16_t parser_length_errors;
    uint16_t parser_timeout_errors;
    uint16_t parser_resync_events;
    uint8_t open_loop_staging[
        COMMAND_ROUTER_OPEN_LOOP_CONFIG_SIZE];
    uint16_t open_loop_staging_mask;
    uint8_t open_loop_staging_generation;
    uint32_t open_loop_staging_updated_ms;
    bool open_loop_staging_active;
    uint8_t open_loop_committed_generation;
    uint16_t open_loop_committed_crc;
    uint64_t open_loop_committed_at_ms;
    bool open_loop_committed_valid;
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

#ifdef __cplusplus
}
#endif

#endif
