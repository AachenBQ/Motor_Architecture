import time
import struct
import sys
import unittest
from types import SimpleNamespace
from typing import List
from unittest.mock import patch

from motor_control.protocol import (
    Command,
    ControlMode,
    Frame,
    FrameParser,
    OpenLoopBackend,
    OpenLoopConfig,
    PidLoop,
    encode_frame,
    pack_enable,
    pack_heartbeat,
    pack_limits,
    pack_open_loop_config,
    pack_open_loop_config_commit,
    pack_open_loop_config_fragments,
    pack_pid,
    pack_target,
    pack_telemetry_profile,
    unpack_build_config,
    unpack_diagnostics,
    unpack_limits,
    unpack_open_loop_config,
    unpack_telemetry,
)
from motor_control.transport import ControllerLink


class SimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.link = ControllerLink()
        self.link.connect_simulator(motor_count=1)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not self.link.connected:
            time.sleep(0.01)
        self.assertTrue(self.link.connected)

    def tearDown(self) -> None:
        self.link.close()

    def _collect_frames(self, duration: float = 0.2) -> List[Frame]:
        parser = FrameParser()
        frames = []  # type: List[Frame]
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            for event in self.link.poll():
                if event.kind == "rx":
                    frames.extend(parser.feed(event.data))
            time.sleep(0.005)
        return frames

    def _read_open_loop_config(self, sequence: int) -> OpenLoopConfig:
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.GET_OPEN_LOOP_CONFIG,
                    sequence,
                    b"\x01",
                )
            )
        )
        replies = [
            frame
            for frame in self._collect_frames(0.12)
            if frame.command == Command.ACK
            and frame.sequence == sequence
            and frame.payload[:2]
            == bytes((Command.GET_OPEN_LOOP_CONFIG, 0))
        ]
        self.assertEqual(len(replies), 1)
        return unpack_open_loop_config(replies[0].payload[2:])

    def _assert_open_loop_config_equal(
        self,
        actual: OpenLoopConfig,
        expected: OpenLoopConfig,
    ) -> None:
        self.assertEqual(actual.motor_id, expected.motor_id)
        self.assertEqual(actual.backend, expected.backend)
        self.assertEqual(actual.pole_pairs, expected.pole_pairs)
        self.assertEqual(actual.flags, expected.flags)
        self.assertAlmostEqual(actual.bus_voltage_v, expected.bus_voltage_v, places=5)
        self.assertAlmostEqual(
            actual.voltage_limit_v,
            expected.voltage_limit_v,
            places=5,
        )
        self.assertAlmostEqual(
            actual.target_velocity_rad_s,
            expected.target_velocity_rad_s,
            places=5,
        )
        self.assertAlmostEqual(
            actual.acceleration_rad_s2,
            expected.acceleration_rad_s2,
            places=5,
        )
        self.assertEqual(actual.update_period_ms, expected.update_period_ms)
        self.assertEqual(actual.startup_delay_ms, expected.startup_delay_ms)
        self.assertEqual(actual.max_runtime_ms, expected.max_runtime_ms)

    def test_simulator_produces_telemetry(self) -> None:
        frames = self._collect_frames()
        telemetry_frames = [
            frame for frame in frames if frame.command == Command.TELEMETRY
        ]
        self.assertGreaterEqual(len(telemetry_frames), 2)
        values = [unpack_telemetry(frame.payload) for frame in telemetry_frames]
        self.assertEqual({value.motor_id for value in values}, {1})
        self.assertTrue(
            all(5.0 <= value.voltage_v <= 8.0 for value in values)
        )

    def test_extended_diagnostics_query(self) -> None:
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.GET_DIAGNOSTICS,
                    9,
                    b"\x07",
                )
            )
        )
        frames = self._collect_frames()
        replies = [
            frame
            for frame in frames
            if frame.command == Command.ACK and frame.sequence == 9
        ]
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0].payload[:2], b"\x22\x00")
        self.assertEqual(len(replies[0].payload[2:]), 46)
        diagnostics = unpack_diagnostics(replies[0].payload[2:])
        self.assertEqual(diagnostics.rx_sw_fifo_overflows, 0)
        self.assertEqual(diagnostics.parser_timeout_errors, 0)
        self.assertEqual(diagnostics.rx_isr_entries, 0)
        self.assertGreaterEqual(diagnostics.rx_poll_drains, 1)
        self.assertGreaterEqual(diagnostics.rx_poll_bytes, 1)

    def test_simulator_accepts_enable_and_target(self) -> None:
        self.link.send(
            encode_frame(
                Frame(1, Command.SET_ENABLE, 10, pack_enable(1, True))
            )
        )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.SET_TARGET,
                    11,
                    pack_target(1, ControlMode.SPEED, 120.0),
                )
            )
        )
        frames = self._collect_frames(0.5)
        ack_sequences = {
            frame.sequence for frame in frames if frame.command == Command.ACK
        }
        self.assertTrue({10, 11}.issubset(ack_sequences))
        speeds = [
            unpack_telemetry(frame.payload).speed_rpm
            for frame in frames
            if frame.command == Command.TELEMETRY and frame.device_id == 1
        ]
        self.assertTrue(speeds)
        self.assertGreater(max(speeds), 500.0)

    def test_simulator_keeps_pid_loops_separate(self) -> None:
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.SET_PID,
                    20,
                    pack_pid(1, PidLoop.CURRENT, 1.1, 0.2, 0.03),
                )
            )
        )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.SET_PID,
                    21,
                    pack_pid(1, PidLoop.POSITION, 3.3, 0.4, 0.05),
                )
            )
        )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.GET_PID,
                    22,
                    bytes((1, int(PidLoop.CURRENT))),
                )
            )
        )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.GET_PID,
                    23,
                    bytes((1, int(PidLoop.POSITION))),
                )
            )
        )
        frames = self._collect_frames(0.25)
        replies = {
            frame.sequence: frame
            for frame in frames
            if frame.command == Command.ACK and frame.sequence in (22, 23)
        }
        self.assertEqual(set(replies), {22, 23})
        current = struct.unpack("<Bfff", replies[22].payload[2:])
        position = struct.unpack("<Bfff", replies[23].payload[2:])
        self.assertEqual(current[0], PidLoop.CURRENT)
        self.assertEqual(position[0], PidLoop.POSITION)
        self.assertAlmostEqual(current[1], 1.1, places=5)
        self.assertAlmostEqual(position[1], 3.3, places=5)

    def test_capabilities_and_heartbeat(self) -> None:
        self.link.send(
            encode_frame(Frame(1, Command.GET_CAPABILITIES, 30))
        )
        self.link.send(
            encode_frame(
                Frame(1, Command.HEARTBEAT, 31, pack_heartbeat(5000, 750))
            )
        )
        frames = self._collect_frames(0.15)
        replies = {
            frame.sequence: frame
            for frame in frames
            if frame.command == Command.ACK and frame.sequence in (30, 31)
        }
        self.assertEqual(set(replies), {30, 31})
        capabilities = struct.unpack(
            "<BBBIH",
            replies[30].payload[2:],
        )
        self.assertEqual(capabilities[0], 1)
        self.assertNotEqual(capabilities[3] & (1 << 6), 0)

    def test_build_config_query_returns_ack(self) -> None:
        self.link.send(
            encode_frame(Frame(1, Command.GET_BUILD_CONFIG, 32))
        )
        frames = self._collect_frames(0.15)
        replies = [
            frame
            for frame in frames
            if frame.command == Command.ACK and frame.sequence == 32
        ]
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0].payload[:2], bytes((Command.GET_BUILD_CONFIG, 0)))
        build_config = unpack_build_config(replies[0].payload[2:])
        self.assertEqual(build_config[0:4], (1, 1, 0, 1))
        self.assertEqual(build_config[6], 20000)

    def test_rejects_protocol_v1(self) -> None:
        self.link.send(
            encode_frame(Frame(1, Command.PING, 40, version=1))
        )
        frames = self._collect_frames(0.2)
        errors = [
            frame
            for frame in frames
            if frame.command == Command.ERROR and frame.sequence == 40
        ]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].payload[:2], bytes((Command.PING, 2)))

    def test_heartbeat_timeout_stops_motor_and_latches_fault(self) -> None:
        self.link.send(
            encode_frame(
                Frame(1, Command.SET_ENABLE, 50, pack_enable(1, True))
            )
        )
        frames = self._collect_frames(0.95)
        telemetry = [
            unpack_telemetry(frame.payload)
            for frame in frames
            if frame.command == Command.TELEMETRY
        ]
        self.assertTrue(telemetry)
        self.assertEqual(telemetry[-1].status & (1 << 0), 0)
        self.assertNotEqual(telemetry[-1].status & (1 << 3), 0)

    def test_device_configuration_round_trip(self) -> None:
        configured = pack_limits(
            1,
            18.0,
            3.0,
            90.0,
            -12.0,
            12.0,
            5.0,
            56.0,
            75.0,
        )
        requests = (
            Frame(1, Command.SET_LIMITS, 60, configured),
            Frame(1, Command.GET_LIMITS, 61, b"\x01"),
            Frame(
                1,
                Command.SET_TELEMETRY_PROFILE,
                62,
                pack_telemetry_profile(100, 0x1F),
            ),
            Frame(1, Command.GET_TELEMETRY_PROFILE, 63),
            Frame(1, Command.SAVE_CONFIG, 64),
        )
        for request in requests:
            self.link.send(encode_frame(request))
        frames = self._collect_frames(0.2)
        replies = {
            frame.sequence: frame
            for frame in frames
            if frame.command == Command.ACK
            and frame.sequence in (60, 61, 62, 63, 64)
        }
        self.assertEqual(set(replies), {60, 61, 62, 63, 64})
        limits = unpack_limits(replies[61].payload[2:])
        self.assertAlmostEqual(limits[2], 3.0, places=5)
        self.assertAlmostEqual(limits[8], 75.0, places=5)
        self.assertEqual(
            struct.unpack("<HI", replies[63].payload[2:]),
            (100, 0x1F),
        )

        self.link.send(
            encode_frame(Frame(1, Command.RESTORE_DEFAULTS, 65))
        )
        self.link.send(
            encode_frame(Frame(1, Command.GET_LIMITS, 66, b"\x01"))
        )
        restored_frames = self._collect_frames(0.15)
        restored = [
            frame
            for frame in restored_frames
            if frame.command == Command.ACK and frame.sequence == 66
        ]
        self.assertEqual(len(restored), 1)
        default_limits = unpack_limits(restored[0].payload[2:])
        self.assertAlmostEqual(default_limits[1], 0.3, places=5)
        self.assertAlmostEqual(default_limits[2], 0.03, places=5)
        self.assertAlmostEqual(default_limits[6], 5.0, places=5)
        self.assertAlmostEqual(default_limits[7], 8.0, places=5)

    def test_open_loop_configuration_start_and_quick_stop(self) -> None:
        config = OpenLoopConfig(
            1,
            OpenLoopBackend.DIRECT_SINE,
            7,
            0,
            7.0,
            0.3,
            5.0,
            20.0,
            10,
            50,
            30000,
        )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.SET_OPEN_LOOP_CONFIG,
                    70,
                    pack_open_loop_config(config),
                )
            )
        )
        self.link.send(
            encode_frame(
                Frame(1, Command.START_OPEN_LOOP, 71, b"\x01")
            )
        )
        frames = self._collect_frames(0.35)
        replies = {
            frame.sequence: frame
            for frame in frames
            if frame.command == Command.ACK
            and frame.sequence in (70, 71)
        }
        self.assertEqual(set(replies), {70, 71})
        telemetry = [
            unpack_telemetry(frame.payload)
            for frame in frames
            if frame.command == Command.TELEMETRY
        ]
        self.assertTrue(telemetry)
        self.assertNotEqual(telemetry[-1].status & (1 << 5), 0)
        self.assertGreater(max(value.speed_rpm for value in telemetry), 5.0)

        self.link.send(
            encode_frame(
                Frame(1, Command.QUICK_STOP, 72, b"\x01")
            )
        )
        # The simulator publishes telemetry on a background timer.  Leave more
        # than one telemetry period here so a busy CI host cannot turn this
        # state assertion into a scheduling race.
        stopped_frames = self._collect_frames(0.30)
        stopped = [
            unpack_telemetry(frame.payload)
            for frame in stopped_frames
            if frame.command == Command.TELEMETRY
        ]
        self.assertTrue(stopped)
        self.assertEqual(stopped[-1].status & (1 << 0), 0)
        self.assertEqual(stopped[-1].status & (1 << 5), 0)

    def test_fragmented_open_loop_config_commit_and_readback(self) -> None:
        config = OpenLoopConfig(
            1,
            OpenLoopBackend.SIMPLEFOC,
            7,
            0,
            7.0,
            0.25,
            6.0,
            12.0,
            15,
            60,
            20000,
        )
        generation = 7
        fragment_payloads = pack_open_loop_config_fragments(config, generation)
        for index, payload in enumerate(fragment_payloads):
            self.link.send(
                encode_frame(
                    Frame(
                        1,
                        Command.SET_OPEN_LOOP_CONFIG_PART,
                        80 + index,
                        payload,
                    )
                )
            )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    94,
                    pack_open_loop_config_commit(config, generation),
                )
            )
        )

        frames = self._collect_frames(0.25)
        replies = {
            frame.sequence: frame
            for frame in frames
            if frame.command == Command.ACK
            and 80 <= frame.sequence <= 94
        }
        self.assertEqual(set(replies), set(range(80, 95)))
        for index in range(len(fragment_payloads)):
            self.assertEqual(
                replies[80 + index].payload,
                bytes(
                    (
                        Command.SET_OPEN_LOOP_CONFIG_PART,
                        0,
                        generation,
                        index,
                    )
                ),
            )
        self.assertEqual(
            replies[94].payload,
            bytes((Command.COMMIT_OPEN_LOOP_CONFIG, 0, generation)),
        )
        self._assert_open_loop_config_equal(
            self._read_open_loop_config(95),
            config,
        )
        # If the first commit ACK was lost, retrying the same commit remains
        # successful even though staging has already been retired.
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    96,
                    pack_open_loop_config_commit(
                        config,
                        generation,
                    ),
                )
            )
        )
        duplicate_commit = [
            frame
            for frame in self._collect_frames(0.12)
            if frame.command == Command.ACK
            and frame.sequence == 96
        ]
        self.assertEqual(len(duplicate_commit), 1)
        self.assertEqual(
            duplicate_commit[0].payload,
            bytes(
                (
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    0,
                    generation,
                )
            ),
        )

    def test_fragmented_open_loop_config_rejects_missing_part(self) -> None:
        original = self._read_open_loop_config(100)
        config = OpenLoopConfig(
            1,
            OpenLoopBackend.DIRECT_SINE,
            7,
            0,
            7.0,
            0.2,
            4.0,
            9.0,
            20,
            70,
            18000,
        )
        generation = 8
        fragment_payloads = pack_open_loop_config_fragments(config, generation)
        for index, payload in enumerate(fragment_payloads):
            if index == 5:
                continue
            self.link.send(
                encode_frame(
                    Frame(
                        1,
                        Command.SET_OPEN_LOOP_CONFIG_PART,
                        101 + index,
                        payload,
                    )
                )
            )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    115,
                    pack_open_loop_config_commit(config, generation),
                )
            )
        )

        frames = self._collect_frames(0.25)
        errors = [
            frame
            for frame in frames
            if frame.command == Command.ERROR and frame.sequence == 115
        ]
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].payload[:2],
            bytes((Command.COMMIT_OPEN_LOOP_CONFIG, 4)),
        )
        self._assert_open_loop_config_equal(
            self._read_open_loop_config(116),
            original,
        )

    def test_fragmented_open_loop_config_rejects_bad_crc(self) -> None:
        original = self._read_open_loop_config(120)
        config = OpenLoopConfig(
            1,
            OpenLoopBackend.SIMPLEFOC,
            7,
            0,
            7.0,
            0.2,
            5.5,
            11.0,
            10,
            80,
            19000,
        )
        generation = 9
        for index, payload in enumerate(
            pack_open_loop_config_fragments(config, generation)
        ):
            self.link.send(
                encode_frame(
                    Frame(
                        1,
                        Command.SET_OPEN_LOOP_CONFIG_PART,
                        121 + index,
                        payload,
                    )
                )
            )
        bad_commit = bytearray(
            pack_open_loop_config_commit(config, generation)
        )
        bad_commit[-1] ^= 0x80
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    135,
                    bytes(bad_commit),
                )
            )
        )

        frames = self._collect_frames(0.25)
        errors = [
            frame
            for frame in frames
            if frame.command == Command.ERROR and frame.sequence == 135
        ]
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].payload[:2],
            bytes((Command.COMMIT_OPEN_LOOP_CONFIG, 2)),
        )
        self._assert_open_loop_config_equal(
            self._read_open_loop_config(136),
            original,
        )

    def test_fragmented_open_loop_config_matches_firmware_validation(self) -> None:
        original = self._read_open_loop_config(137)
        invalid = OpenLoopConfig(
            1,
            OpenLoopBackend.SIMPLEFOC,
            6,
            0,
            7.0,
            0.2,
            5.0,
            10.0,
            10,
            100,
            15000,
        )
        generation = 11
        for index, payload in enumerate(
            pack_open_loop_config_fragments(invalid, generation)
        ):
            self.link.send(
                encode_frame(
                    Frame(
                        1,
                        Command.SET_OPEN_LOOP_CONFIG_PART,
                        180 + index,
                        payload,
                    )
                )
            )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    194,
                    pack_open_loop_config_commit(
                        invalid,
                        generation,
                    ),
                )
            )
        )
        errors = [
            frame
            for frame in self._collect_frames(0.25)
            if frame.command == Command.ERROR
            and frame.sequence == 194
        ]
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].payload[:2],
            bytes((Command.COMMIT_OPEN_LOOP_CONFIG, 5)),
        )
        self._assert_open_loop_config_equal(
            self._read_open_loop_config(195),
            original,
        )

    def test_fragmented_open_loop_config_duplicate_part_is_idempotent(self) -> None:
        config = OpenLoopConfig(
            1,
            OpenLoopBackend.DIRECT_SINE,
            7,
            0,
            7.0,
            0.18,
            3.5,
            8.0,
            25,
            90,
            17000,
        )
        generation = 10
        fragments = pack_open_loop_config_fragments(config, generation)
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.SET_OPEN_LOOP_CONFIG_PART,
                    140,
                    fragments[0],
                )
            )
        )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.SET_OPEN_LOOP_CONFIG_PART,
                    141,
                    fragments[0],
                )
            )
        )
        for index, payload in enumerate(fragments[1:], 1):
            self.link.send(
                encode_frame(
                    Frame(
                        1,
                        Command.SET_OPEN_LOOP_CONFIG_PART,
                        141 + index,
                        payload,
                    )
                )
            )
        self.link.send(
            encode_frame(
                Frame(
                    1,
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    155,
                    pack_open_loop_config_commit(config, generation),
                )
            )
        )

        frames = self._collect_frames(0.25)
        duplicate_replies = [
            frame
            for frame in frames
            if frame.command == Command.ACK
            and frame.sequence in (140, 141)
        ]
        self.assertEqual(len(duplicate_replies), 2)
        self.assertTrue(
            all(
                frame.payload
                == bytes(
                    (
                        Command.SET_OPEN_LOOP_CONFIG_PART,
                        0,
                        generation,
                        0,
                    )
                )
                for frame in duplicate_replies
            )
        )
        commit_replies = [
            frame
            for frame in frames
            if frame.command == Command.ACK and frame.sequence == 155
        ]
        self.assertEqual(len(commit_replies), 1)
        self._assert_open_loop_config_equal(
            self._read_open_loop_config(156),
            config,
        )

    def test_fragmented_open_loop_config_stress(self) -> None:
        iterations = 12
        expected_replies = iterations * 15
        last_config = None
        sequence = 160
        for iteration in range(iterations):
            config = OpenLoopConfig(
                1,
                OpenLoopBackend.SIMPLEFOC
                if iteration % 2
                else OpenLoopBackend.DIRECT_SINE,
                7,
                0,
                7.0,
                0.10 + iteration * 0.01,
                2.0 + iteration * 0.2,
                6.0 + iteration * 0.3,
                10 + iteration,
                100 + iteration,
                15000 + iteration * 100,
            )
            generation = 20 + iteration
            for payload in pack_open_loop_config_fragments(
                config,
                generation,
            ):
                self.link.send(
                    encode_frame(
                        Frame(
                            1,
                            Command.SET_OPEN_LOOP_CONFIG_PART,
                            sequence & 0xFF,
                            payload,
                        )
                    )
                )
                sequence += 1
            self.link.send(
                encode_frame(
                    Frame(
                        1,
                        Command.COMMIT_OPEN_LOOP_CONFIG,
                        sequence & 0xFF,
                        pack_open_loop_config_commit(config, generation),
                    )
                )
            )
            sequence += 1
            last_config = config

        frames = self._collect_frames(0.8)
        transfer_replies = [
            frame
            for frame in frames
            if frame.command == Command.ACK
            and frame.payload
            and frame.payload[0]
            in (
                Command.SET_OPEN_LOOP_CONFIG_PART,
                Command.COMMIT_OPEN_LOOP_CONFIG,
            )
        ]
        transfer_errors = [
            frame
            for frame in frames
            if frame.command == Command.ERROR
            and frame.payload
            and frame.payload[0]
            in (
                Command.SET_OPEN_LOOP_CONFIG_PART,
                Command.COMMIT_OPEN_LOOP_CONFIG,
            )
        ]
        self.assertEqual(transfer_errors, [])
        self.assertEqual(len(transfer_replies), expected_replies)
        self.assertIsNotNone(last_config)
        self._assert_open_loop_config_equal(
            self._read_open_loop_config(sequence & 0xFF),
            last_config,
        )


class _FakeWorkerSerial:
    def __init__(self, write_count=None):
        self.write_count = write_count
        self.writes = []
        self.opened = False
        self.closed = False
        self.in_waiting = 0

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def read(self, _size):
        time.sleep(0.001)
        return b""

    def write(self, packet):
        packet = bytes(packet)
        self.writes.append(packet)
        if self.write_count is None:
            return len(packet)
        return int(self.write_count)


class ControllerLinkSerialWriteTests(unittest.TestCase):
    @staticmethod
    def _serial_module(serial_port):
        return SimpleNamespace(
            Serial=lambda: serial_port,
            EIGHTBITS=8,
            PARITY_NONE="N",
            STOPBITS_ONE=1,
        )

    @staticmethod
    def _wait_connected(link):
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not link.connected:
            time.sleep(0.005)
        if not link.connected:
            raise AssertionError("fake serial worker did not connect")

    def test_send_only_queues_until_worker_writes(self):
        link = ControllerLink()
        link._connected = True
        link.send(b"\x10\x20", quiet=True)
        self.assertEqual(link.poll(), [])
        self.assertEqual(link.tx_queued_packets, 1)
        self.assertEqual(link.tx_queued_bytes, 2)
        self.assertEqual(link.tx_written_packets, 0)
        self.assertEqual(
            link._tx.get_nowait(),
            (b"\x10\x20", True),
        )

    def test_full_serial_write_emits_tx_written_and_counts_bytes(self):
        serial_port = _FakeWorkerSerial()
        link = ControllerLink()
        events = []
        with patch.dict(
            sys.modules,
            {"serial": self._serial_module(serial_port)},
        ):
            link.connect_serial("TEST", 115200)
            self._wait_connected(link)
            events.extend(link.poll())
            link.send(b"\xAA\x55\x01")
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                events.extend(link.poll())
                if any(event.kind == "tx_written" for event in events):
                    break
                time.sleep(0.005)
            link.close()

        written_events = [
            event for event in events if event.kind == "tx_written"
        ]
        self.assertEqual(len(written_events), 1)
        self.assertEqual(written_events[0].data["written"], 3)
        self.assertEqual(
            written_events[0].data["packet"],
            b"\xAA\x55\x01",
        )
        self.assertEqual(link.tx_written_packets, 1)
        self.assertEqual(link.tx_written_bytes, 3)
        self.assertEqual(link.tx_write_failures, 0)
        self.assertEqual(serial_port.writes, [b"\xAA\x55\x01"])

    def test_short_serial_write_is_failure_not_tx_written(self):
        serial_port = _FakeWorkerSerial(write_count=2)
        link = ControllerLink()
        events = []
        with patch.dict(
            sys.modules,
            {"serial": self._serial_module(serial_port)},
        ):
            link.connect_serial("TEST", 115200)
            self._wait_connected(link)
            events.extend(link.poll())
            link.send(b"\x01\x02\x03")
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                events.extend(link.poll())
                if any(
                    event.kind == "tx_write_error"
                    for event in events
                ):
                    break
                time.sleep(0.005)
            link.close()
            events.extend(link.poll())

        self.assertFalse(
            any(event.kind == "tx_written" for event in events)
        )
        failures = [
            event for event in events
            if event.kind == "tx_write_error"
        ]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].data["requested"], 3)
        self.assertEqual(failures[0].data["written"], 2)
        self.assertEqual(link.tx_written_packets, 0)
        self.assertEqual(link.tx_write_failures, 1)


if __name__ == "__main__":
    unittest.main()
