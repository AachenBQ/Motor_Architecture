#include "native_protocol.h"

#include <string.h>

static uint16_t ReadU16Le(const uint8_t *data)
{
    return (uint16_t)data[0] | ((uint16_t)data[1] << 8);
}

static void ResetForNextByte(NativeParser *parser, uint8_t value)
{
    parser->used = 0U;
    parser->expected = 0U;
    if (value == 0xAAU)
    {
        parser->bytes[0] = value;
        parser->used = 1U;
    }
}

void NativeParser_Init(NativeParser *parser)
{
    memset(parser, 0, sizeof(*parser));
}

uint16_t NativeProtocol_Crc16(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFFU;
    size_t index;
    uint8_t bit;
    for (index = 0U; index < length; ++index)
    {
        crc ^= data[index];
        for (bit = 0U; bit < 8U; ++bit)
        {
            crc = (crc & 1U) != 0U
                ? (uint16_t)((crc >> 1) ^ 0xA001U)
                : (uint16_t)(crc >> 1);
        }
    }
    return crc;
}

bool NativeParser_Push(NativeParser *parser, uint8_t value, NativeFrame *frame)
{
    uint16_t payload_length;
    uint16_t received_crc;
    uint16_t actual_crc;

    if (parser->used == 0U)
    {
        if (value == 0xAAU)
        {
            parser->bytes[0] = value;
            parser->used = 1U;
        }
        return false;
    }
    if (parser->used == 1U)
    {
        if (value != 0x55U)
        {
            ResetForNextByte(parser, value);
            return false;
        }
        parser->bytes[parser->used++] = value;
        return false;
    }

    parser->bytes[parser->used++] = value;
    if (parser->used == 9U)
    {
        payload_length = ReadU16Le(&parser->bytes[7]);
        if (payload_length > NATIVE_PROTOCOL_MAX_PAYLOAD)
        {
            parser->length_errors++;
            ResetForNextByte(parser, value);
            return false;
        }
        parser->expected = (uint16_t)(11U + payload_length);
    }
    if ((parser->expected == 0U) || (parser->used < parser->expected))
    {
        return false;
    }

    received_crc = ReadU16Le(&parser->bytes[parser->expected - 2U]);
    actual_crc = NativeProtocol_Crc16(
        &parser->bytes[2],
        (size_t)parser->expected - 4U);
    if (received_crc != actual_crc)
    {
        parser->crc_errors++;
        ResetForNextByte(parser, value);
        return false;
    }

    frame->version = parser->bytes[2];
    frame->flags = parser->bytes[3];
    frame->device = parser->bytes[4];
    frame->command = parser->bytes[5];
    frame->sequence = parser->bytes[6];
    frame->payload_length = ReadU16Le(&parser->bytes[7]);
    if (frame->payload_length != 0U)
    {
        memcpy(frame->payload, &parser->bytes[9], frame->payload_length);
    }
    parser->used = 0U;
    parser->expected = 0U;
    return true;
}

size_t NativeProtocol_Encode(
    const NativeFrame *frame,
    uint8_t *destination,
    size_t capacity)
{
    size_t frame_length;
    uint16_t crc;
    if (frame->payload_length > NATIVE_PROTOCOL_MAX_PAYLOAD)
    {
        return 0U;
    }
    frame_length = 11U + frame->payload_length;
    if (capacity < frame_length)
    {
        return 0U;
    }

    destination[0] = 0xAAU;
    destination[1] = 0x55U;
    destination[2] = frame->version;
    destination[3] = frame->flags;
    destination[4] = frame->device;
    destination[5] = frame->command;
    destination[6] = frame->sequence;
    destination[7] = (uint8_t)(frame->payload_length & 0xFFU);
    destination[8] = (uint8_t)(frame->payload_length >> 8);
    if (frame->payload_length != 0U)
    {
        memcpy(&destination[9], frame->payload, frame->payload_length);
    }
    crc = NativeProtocol_Crc16(&destination[2], 7U + frame->payload_length);
    destination[9U + frame->payload_length] = (uint8_t)(crc & 0xFFU);
    destination[10U + frame->payload_length] = (uint8_t)(crc >> 8);
    return frame_length;
}

