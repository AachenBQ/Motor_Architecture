import struct
import unittest

from motor_control.protocol import (
    Command,
    Frame,
    FrameParser,
    Telemetry,
    encode_frame,
    pack_telemetry,
)
from motor_control.raw_serial_probe import (
    READ_ONLY_REQUESTS,
    ProbeError,
    RawSerialProbe,
    decode_read_only_detail,
)


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def monotonic(self):
        return self.value

    def sleep(self, duration):
        self.value += max(0.0, float(duration))


def diagnostics_payload(
    commands_received=1,
    protocol_errors=0,
    telemetry_drops=0,
    rx_sw_fifo_overflows=0,
):
    base = struct.pack(
        "<IHHIHHBBBBHH",
        12345,
        protocol_errors,
        0,
        commands_received,
        0xFFFF,
        0,
        1,
        0,
        0,
        0,
        0,
        telemetry_drops,
    )
    extension = struct.pack(
        "<HHHHHHHHHHH",
        rx_sw_fifo_overflows,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        10,
        20,
        30,
    )
    return base + extension


def detail_for(command, commands_received=1, protocol_errors=0):
    if command == Command.PING:
        return b"TC375-Test"
    if command == Command.GET_DEVICE_INFO:
        return struct.pack(
            "<BBBBBI16s8s",
            0,
            3,
            6,
            1,
            0,
            0x37500001,
            b"TC375-MCU",
            b"FRG2",
        )
    if command == Command.GET_CAPABILITIES:
        return struct.pack("<BBBIH", 1, 1, 15, 1 << 6, 1000)
    if command == Command.GET_DIAGNOSTICS:
        return diagnostics_payload(
            commands_received=commands_received,
            protocol_errors=protocol_errors,
        )
    raise AssertionError("unexpected command")


class FakeSerial:
    def __init__(self, responder):
        self.responder = responder
        self.rx = bytearray()
        self.writes = []
        self.request_parser = FrameParser()
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.rx)

    def write(self, packet):
        self.writes.append(bytes(packet))
        frames = self.request_parser.feed(packet)
        if len(frames) != 1:
            raise AssertionError("expected one request frame")
        response = self.responder(frames[0], len(self.writes))
        if response:
            self.rx.extend(response)
        return len(packet)

    def read(self, size):
        if not self.rx:
            return b""
        count = min(int(size), len(self.rx))
        result = bytes(self.rx[:count])
        del self.rx[:count]
        return result

    def close(self):
        self.closed = True


def ack_for(frame, detail=None, command=Command.ACK, status=0):
    if detail is None:
        detail = detail_for(frame.command)
    return encode_frame(
        Frame(
            frame.device_id,
            command,
            frame.sequence,
            bytes((frame.command, status)) + detail,
        )
    )


class RawSerialProbeTests(unittest.TestCase):
    def make_probe(self, responder, iterations_interval=0.0):
        clock = FakeClock()
        serial_port = FakeSerial(responder)
        probe = RawSerialProbe(
            serial_port,
            timeout=0.05,
            interval=iterations_interval,
            clock=clock.monotonic,
            sleep=clock.sleep,
        )
        return probe, serial_port

    def test_runs_only_four_allow_list_queries_and_decodes_telemetry(self):
        seen_commands = []

        def responder(frame, request_number):
            seen_commands.append(Command(frame.command))
            telemetry = encode_frame(
                Frame(
                    1,
                    Command.TELEMETRY,
                    request_number,
                    pack_telemetry(
                        Telemetry(1, 0.0, 0.0, 7.0, 25.0, 0.0, 0)
                    ),
                )
            )
            return telemetry + ack_for(
                frame,
                detail_for(frame.command, request_number),
            )

        probe, serial_port = self.make_probe(responder)
        summary = probe.run(2)
        self.assertEqual(
            seen_commands,
            [item[0] for item in READ_ONLY_REQUESTS] * 2,
        )
        self.assertTrue(summary["success"])
        self.assertEqual(summary["requests"], 8)
        self.assertEqual(summary["matched_responses"], 8)
        self.assertEqual(summary["telemetry_frames"], 8)
        self.assertEqual(summary["host_parser"]["crc_errors"], 0)
        self.assertEqual(summary["diagnostics"]["delta"]["protocol_errors"], 0)
        self.assertEqual(
            summary["diagnostics"]["last"]["rx_isr_entries"],
            10,
        )
        self.assertEqual(
            summary["diagnostics"]["last"]["rx_poll_drains"],
            20,
        )
        self.assertEqual(
            summary["diagnostics"]["last"]["rx_poll_bytes"],
            30,
        )

        decoded_requests = []
        parser = FrameParser()
        for packet in serial_port.writes:
            decoded_requests.extend(parser.feed(packet))
        self.assertTrue(decoded_requests)
        self.assertTrue(
            all(
                Command(frame.command)
                in [item[0] for item in READ_ONLY_REQUESTS]
                for frame in decoded_requests
            )
        )
        self.assertTrue(
            all(
                frame.payload == b"\x07"
                for frame in decoded_requests
                if frame.command == Command.GET_DIAGNOSTICS
            )
        )

    def test_strict_sequence_and_original_command_matching(self):
        def responder(frame, _request_number):
            wrong_sequence = encode_frame(
                Frame(
                    frame.device_id,
                    Command.ACK,
                    (frame.sequence + 1) & 0xFF,
                    bytes((frame.command, 0)) + detail_for(frame.command),
                )
            )
            wrong_original = encode_frame(
                Frame(
                    frame.device_id,
                    Command.ACK,
                    frame.sequence,
                    bytes((Command.SET_ENABLE, 0)),
                )
            )
            return wrong_sequence + wrong_original + ack_for(frame)

        probe, _ = self.make_probe(responder)
        result = probe.query(Command.PING)
        self.assertEqual(result["state"], "ack")
        self.assertEqual(probe.stats.mismatched_responses, 2)
        self.assertFalse(probe.stats.successful(probe.parser))

    def test_wrong_original_never_completes_request(self):
        def responder(frame, _request_number):
            return encode_frame(
                Frame(
                    frame.device_id,
                    Command.ACK,
                    frame.sequence,
                    bytes((Command.GET_CAPABILITIES, 0)),
                )
            )

        probe, _ = self.make_probe(responder)
        result = probe.query(Command.PING)
        self.assertEqual(result["state"], "timeout")
        self.assertEqual(probe.stats.timeouts, 1)
        self.assertEqual(probe.stats.mismatched_responses, 1)

    def test_crc_error_is_counted_without_losing_following_ack(self):
        def responder(frame, _request_number):
            bad = bytearray(ack_for(frame))
            bad[-1] ^= 0xFF
            return bytes(bad) + ack_for(frame)

        probe, _ = self.make_probe(responder)
        result = probe.query(Command.PING)
        self.assertEqual(result["state"], "ack")
        self.assertEqual(probe.parser.crc_errors, 1)
        self.assertFalse(probe.stats.successful(probe.parser))

    def test_diagnostic_counter_increase_fails_clean_result(self):
        diagnostic_request = [0]

        def responder(frame, request_number):
            if frame.command == Command.GET_DIAGNOSTICS:
                diagnostic_request[0] += 1
                detail = detail_for(
                    frame.command,
                    request_number,
                    protocol_errors=diagnostic_request[0] - 1,
                )
            else:
                detail = detail_for(frame.command, request_number)
            return ack_for(frame, detail)

        probe, _ = self.make_probe(responder)
        summary = probe.run(2)
        self.assertEqual(
            summary["diagnostics"]["delta"]["protocol_errors"],
            1,
        )
        self.assertFalse(summary["success"])

    def test_non_read_only_command_and_modified_payload_are_refused(self):
        def responder(_frame, _request_number):
            raise AssertionError("safety rejection must happen before write")

        probe, serial_port = self.make_probe(responder)
        with self.assertRaises(ProbeError):
            probe.query(Command.SET_ENABLE, b"\x01\x01")
        with self.assertRaises(ProbeError):
            probe.query(Command.GET_DIAGNOSTICS, b"")
        self.assertEqual(serial_port.writes, [])

    def test_error_response_is_matched_and_reported(self):
        def responder(frame, _request_number):
            return ack_for(
                frame,
                detail=b"",
                command=Command.ERROR,
                status=4,
            )

        probe, _ = self.make_probe(responder)
        result = probe.query(Command.GET_DIAGNOSTICS, b"\x07")
        self.assertEqual(result["state"], "error")
        self.assertEqual(result["status"], 4)
        self.assertEqual(probe.stats.error_responses, 1)

    def test_read_only_detail_rejects_bad_fixed_lengths(self):
        with self.assertRaises(ValueError):
            decode_read_only_detail(Command.GET_DEVICE_INFO, b"\x00")
        with self.assertRaises(ValueError):
            decode_read_only_detail(Command.GET_CAPABILITIES, b"\x00")


if __name__ == "__main__":
    unittest.main()
