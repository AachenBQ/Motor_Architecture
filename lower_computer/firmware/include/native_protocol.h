#ifndef NATIVE_PROTOCOL_H
#define NATIVE_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define NATIVE_PROTOCOL_VERSION 0x02U
#define NATIVE_PROTOCOL_MAX_PAYLOAD 2048U
#define NATIVE_PROTOCOL_MAX_FRAME (9U + NATIVE_PROTOCOL_MAX_PAYLOAD + 2U)

typedef enum
{
    CMD_PING = 0x01,
    CMD_GET_DEVICE_INFO = 0x02,
    CMD_GET_CAPABILITIES = 0x03,
    CMD_HEARTBEAT = 0x04,
    CMD_SET_ENABLE = 0x10,
    CMD_SET_MODE = 0x11,
    CMD_SET_TARGET = 0x12,
    CMD_SET_PID = 0x13,
    CMD_CALIBRATE = 0x15,
    CMD_CLEAR_FAULT = 0x16,
    CMD_SET_LIMITS = 0x17,
    CMD_GET_LIMITS = 0x18,
    CMD_SAVE_CONFIG = 0x19,
    CMD_RESTORE_DEFAULTS = 0x1A,
    CMD_CONTROLLED_STOP = 0x1B,
    CMD_QUICK_STOP = 0x1C,
    CMD_EMERGENCY_STOP = 0x1F,
    CMD_GET_PID = 0x20,
    CMD_GET_DIAGNOSTICS = 0x22,
    CMD_SET_TELEMETRY_PROFILE = 0x23,
    CMD_GET_BACKEND_INFO = 0x24,
    CMD_GET_TELEMETRY_PROFILE = 0x25,
    CMD_TELEMETRY = 0x80,
    CMD_FAULT_EVENT = 0x81,
    CMD_ACK = 0xF0,
    CMD_ERROR = 0xF1
} NativeCommand;

typedef enum
{
    PROTOCOL_OK = 0,
    PROTOCOL_UNSUPPORTED_COMMAND = 1,
    PROTOCOL_INVALID_PAYLOAD = 2,
    PROTOCOL_INVALID_DEVICE = 3,
    PROTOCOL_INVALID_STATE = 4,
    PROTOCOL_OUT_OF_RANGE = 5,
    PROTOCOL_NOT_CALIBRATED = 6,
    PROTOCOL_HEARTBEAT_REQUIRED = 7,
    PROTOCOL_BUSY = 8,
    PROTOCOL_STORAGE_ERROR = 9,
    PROTOCOL_HARDWARE_FAULT = 10,
    PROTOCOL_CAPABILITY_UNAVAILABLE = 11
} ProtocolStatus;

typedef struct
{
    uint8_t version;
    uint8_t flags;
    uint8_t device;
    uint8_t command;
    uint8_t sequence;
    uint16_t payload_length;
    uint8_t payload[NATIVE_PROTOCOL_MAX_PAYLOAD];
} NativeFrame;

typedef struct
{
    uint8_t bytes[NATIVE_PROTOCOL_MAX_FRAME];
    uint16_t used;
    uint16_t expected;
    uint32_t crc_errors;
    uint32_t length_errors;
} NativeParser;

void NativeParser_Init(NativeParser *parser);
bool NativeParser_Push(NativeParser *parser, uint8_t value, NativeFrame *frame);
uint16_t NativeProtocol_Crc16(const uint8_t *data, size_t length);
size_t NativeProtocol_Encode(
    const NativeFrame *frame,
    uint8_t *destination,
    size_t capacity);

#endif
