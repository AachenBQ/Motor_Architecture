import struct
import unittest
from typing import List

from motor_control.protocol import (
    CalibrationType,
    Command,
    ControlMode,
    Frame,
    FrameParser,
    OpenLoopBackend,
    OpenLoopConfig,
    PidLoop,
    Telemetry,
    crc16_modbus,
    encode_frame,
    hex_to_bytes,
    pack_calibrate,
    pack_heartbeat,
    pack_limits,
    pack_open_loop_config_commit,
    pack_open_loop_config_fragments,
    pack_open_loop_config,
    pack_telemetry_profile,
    pack_target,
    pack_telemetry,
    pack_pid,
    unpack_pid,
    unpack_build_config,
    unpack_diagnostics,
    unpack_limits,
    unpack_open_loop_config_commit,
    unpack_open_loop_config_fragment,
    unpack_open_loop_config,
    unpack_telemetry_profile,
    unpack_target,
    unpack_telemetry,
)


class CrcTests(unittest.TestCase):
    def test_known_modbus_vector(self) -> None:
        self.assertEqual(crc16_modbus(b"123456789"), 0x4B37)


class FrameTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        original = Frame(
            device_id=3,
            command=Command.SET_TARGET,
            sequence=27,
            payload=pack_target(3, ControlMode.SPEED, 1250.5),
            flags=1,
        )
        parser = FrameParser()
        decoded = parser.feed(encode_frame(original))
        self.assertEqual(decoded, [original])
        motor_id, mode, target = unpack_target(decoded[0].payload)
        self.assertEqual(motor_id, 3)
        self.assertEqual(mode, ControlMode.SPEED)
        self.assertAlmostEqual(target, 1250.5, places=3)

    def test_split_packet(self) -> None:
        frame = Frame(1, Command.PING, 8, b"hello")
        packet = encode_frame(frame)
        parser = FrameParser()
        result = []  # type: List[Frame]
        for value in packet:
            result.extend(parser.feed(bytes((value,))))
        self.assertEqual(result, [frame])

    def test_joined_packets_and_leading_noise(self) -> None:
        first = Frame(1, Command.PING, 1, b"a")
        second = Frame(1, Command.GET_PID, 2, b"b")
        parser = FrameParser()
        decoded = parser.feed(b"\x00\xFFnoise" + encode_frame(first) + encode_frame(second))
        self.assertEqual(decoded, [first, second])
        self.assertGreater(parser.discarded_bytes, 0)

    def test_crc_failure_resynchronizes(self) -> None:
        bad = bytearray(encode_frame(Frame(1, Command.PING, 1, b"bad")))
        bad[-1] ^= 0xFF
        good = Frame(2, Command.PING, 2, b"good")
        parser = FrameParser()
        decoded = parser.feed(bytes(bad) + encode_frame(good))
        self.assertEqual(decoded, [good])
        self.assertEqual(parser.crc_errors, 1)

    def test_invalid_length_resynchronizes(self) -> None:
        invalid_header = b"\xAA\x55\x01\x00\x01\x80\x01\xFF\x7F"
        good = Frame(1, Command.PING, 3)
        parser = FrameParser()
        decoded = parser.feed(invalid_header + encode_frame(good))
        self.assertEqual(decoded, [good])
        self.assertEqual(parser.length_errors, 1)


class PayloadTests(unittest.TestCase):
    def test_telemetry_round_trip(self) -> None:
        telemetry = Telemetry(
            motor_id=7,
            speed_rpm=-1234.5,
            current_a=4.25,
            voltage_v=47.8,
            temperature_c=56.75,
            position_deg=182.0,
            status=0x0201,
        )
        decoded = unpack_telemetry(pack_telemetry(telemetry))
        self.assertEqual(decoded.motor_id, telemetry.motor_id)
        self.assertAlmostEqual(decoded.speed_rpm, telemetry.speed_rpm, places=3)
        self.assertAlmostEqual(decoded.current_a, telemetry.current_a, places=3)
        self.assertEqual(decoded.status, telemetry.status)

    def test_three_pid_loops_round_trip(self) -> None:
        for loop in (PidLoop.CURRENT, PidLoop.SPEED, PidLoop.POSITION):
            decoded = unpack_pid(pack_pid(4, loop, 1.2, 0.3, 0.04))
            self.assertEqual(decoded[0], 4)
            self.assertEqual(decoded[1], loop)
            self.assertAlmostEqual(decoded[2], 1.2, places=5)
            self.assertAlmostEqual(decoded[3], 0.3, places=5)
            self.assertAlmostEqual(decoded[4], 0.04, places=5)

    def test_invalid_telemetry_length(self) -> None:
        with self.assertRaises(ValueError):
            unpack_telemetry(b"\x00")

    def test_hex_input(self) -> None:
        self.assertEqual(hex_to_bytes("AA 55,01 0f"), b"\xAA\x55\x01\x0F")
        with self.assertRaises(ValueError):
            hex_to_bytes("ABC")

    def test_v2_heartbeat_and_calibration_payloads(self) -> None:
        self.assertEqual(struct.unpack("<IH", pack_heartbeat(1234)), (1234, 750))
        self.assertEqual(
            struct.unpack("<BB", pack_calibrate(1, CalibrationType.ALL)),
            (1, 0),
        )
        with self.assertRaises(ValueError):
            pack_heartbeat(1234, 100)

    def test_device_configuration_payloads(self) -> None:
        limits = pack_limits(
            1,
            18.0,
            3.0,
            90.0,
            -12.0,
            12.0,
            20.0,
            56.0,
            75.0,
        )
        decoded = unpack_limits(limits)
        self.assertEqual(decoded[0], 1)
        self.assertAlmostEqual(decoded[2], 3.0, places=5)
        self.assertAlmostEqual(decoded[8], 75.0, places=5)
        profile = pack_telemetry_profile(100, 0x1F)
        self.assertEqual(unpack_telemetry_profile(profile), (100, 0x1F))
        with self.assertRaises(ValueError):
            pack_telemetry_profile(0)

    def test_build_config_hardware_layers_and_legacy_compatibility(self) -> None:
        layered = struct.pack(
            "<BBBBBIIIIHHHHf",
            1,
            1,
            0,
            1,
            7,
            10000,
            20000,
            10000,
            1000,
            100,
            750,
            300,
            5000,
            0.1,
        )
        values = unpack_build_config(layered)
        self.assertEqual(values[:5], (1, 1, 0, 1, 7))
        self.assertEqual(values[6], 20000)

        legacy = struct.pack(
            "<BBBBIIIIHHHHf",
            1,
            1,
            1,
            7,
            10000,
            10000,
            10000,
            1000,
            100,
            750,
            300,
            5000,
            0.1,
        )
        legacy_values = unpack_build_config(legacy)
        self.assertEqual(legacy_values[:5], (1, 1, 1, 1, 7))

    def test_diagnostics_extension_and_legacy_compatibility(self) -> None:
        extended = struct.pack(
            "<IHHIHHBBBBHH",
            12345,
            2,
            0x0100,
            77,
            280,
            750,
            6,
            5,
            0x01,
            0,
            1,
            9,
        )
        values = unpack_diagnostics(extended)
        self.assertEqual(values.uptime_ms, 12345)
        self.assertEqual(values.commands_received, 77)
        self.assertEqual(values.last_stop_reason, 5)
        self.assertEqual(values.tx_high_priority_failures, 1)
        self.assertEqual(values.telemetry_drops, 9)
        self.assertEqual(values.rx_sw_fifo_overflows, 0)

        uart = extended + struct.pack("<HHHH", 10, 11, 12, 13)
        uart_values = unpack_diagnostics(uart)
        self.assertEqual(uart_values.rx_sw_fifo_overflows, 10)
        self.assertEqual(uart_values.rx_hw_fifo_overflows, 11)
        self.assertEqual(uart_values.parser_crc_errors, 0)

        full = extended + struct.pack(
            "<HHHHHHHH",
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
        )
        full_values = unpack_diagnostics(full)
        self.assertEqual(full_values.rx_sw_fifo_overflows, 10)
        self.assertEqual(full_values.rx_hw_fifo_overflows, 11)
        self.assertEqual(full_values.rx_frame_errors, 12)
        self.assertEqual(full_values.rx_parity_errors, 13)
        self.assertEqual(full_values.parser_crc_errors, 14)
        self.assertEqual(full_values.parser_length_errors, 15)
        self.assertEqual(full_values.parser_timeout_errors, 16)
        self.assertEqual(full_values.parser_resync_events, 17)
        self.assertEqual(full_values.rx_isr_entries, 0)

        scheduler = full + struct.pack("<HHH", 18, 19, 20)
        scheduler_values = unpack_diagnostics(scheduler)
        self.assertEqual(scheduler_values.rx_isr_entries, 18)
        self.assertEqual(scheduler_values.rx_poll_drains, 19)
        self.assertEqual(scheduler_values.rx_poll_bytes, 20)

        legacy = unpack_diagnostics(struct.pack("<IHH", 42, 3, 4))
        self.assertEqual(legacy.uptime_ms, 42)
        self.assertEqual(legacy.protocol_errors, 3)
        self.assertEqual(legacy.fault_bits, 4)
        self.assertEqual(legacy.commands_received, 0)
        self.assertEqual(legacy.rx_poll_drains, 0)

    def test_open_loop_configuration_round_trip(self) -> None:
        config = OpenLoopConfig(
            1,
            OpenLoopBackend.DIRECT_SINE,
            7,
            0,
            24.0,
            2.0,
            -5.0,
            10.0,
            10,
            500,
            30000,
        )
        decoded = unpack_open_loop_config(
            pack_open_loop_config(config)
        )
        self.assertEqual(decoded.motor_id, 1)
        self.assertEqual(decoded.backend, OpenLoopBackend.DIRECT_SINE)
        self.assertEqual(decoded.pole_pairs, 7)
        self.assertAlmostEqual(decoded.target_velocity_rad_s, -5.0)
        with self.assertRaises(ValueError):
            pack_open_loop_config(
                OpenLoopConfig(
                    1,
                    OpenLoopBackend.DIRECT_SINE,
                    7,
                    0,
                    24.0,
                    25.0,
                    5.0,
                    10.0,
                    10,
                    500,
                    30000,
                )
            )

    def test_open_loop_fragmented_transfer_stays_within_16_bytes(self) -> None:
        config = OpenLoopConfig(
            1,
            OpenLoopBackend.SIMPLEFOC,
            7,
            0,
            7.0,
            0.3,
            5.0,
            10.0,
            10,
            500,
            30000,
        )
        generation = 23
        fragments = pack_open_loop_config_fragments(
            config,
            generation,
        )
        self.assertEqual(len(fragments), 14)

        rebuilt = bytearray()
        for sequence, payload in enumerate(fragments):
            motor_id, decoded_generation, index, data = (
                unpack_open_loop_config_fragment(payload)
            )
            self.assertEqual(motor_id, 1)
            self.assertEqual(decoded_generation, generation)
            self.assertEqual(index, sequence)
            rebuilt.extend(data)
            packet = encode_frame(
                Frame(
                    1,
                    Command.SET_OPEN_LOOP_CONFIG_PART,
                    sequence,
                    payload,
                )
            )
            self.assertEqual(len(packet), 16)

        self.assertEqual(
            bytes(rebuilt),
            pack_open_loop_config(config),
        )
        commit = pack_open_loop_config_commit(
            config,
            generation,
        )
        motor_id, decoded_generation, expected_crc = (
            unpack_open_loop_config_commit(commit)
        )
        self.assertEqual((motor_id, decoded_generation), (1, generation))
        self.assertEqual(
            expected_crc,
            crc16_modbus(bytes(rebuilt)),
        )
        self.assertEqual(
            len(
                encode_frame(
                    Frame(
                        1,
                        Command.COMMIT_OPEN_LOOP_CONFIG,
                        99,
                        commit,
                    )
                )
            ),
            15,
        )


if __name__ == "__main__":
    unittest.main()
