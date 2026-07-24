import time
import struct
import unittest
from typing import List

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
    pack_pid,
    pack_target,
    pack_telemetry_profile,
    unpack_build_config,
    unpack_limits,
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

    def test_simulator_produces_telemetry(self) -> None:
        frames = self._collect_frames()
        telemetry_frames = [
            frame for frame in frames if frame.command == Command.TELEMETRY
        ]
        self.assertGreaterEqual(len(telemetry_frames), 2)
        values = [unpack_telemetry(frame.payload) for frame in telemetry_frames]
        self.assertEqual({value.motor_id for value in values}, {1})

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
        self.assertEqual(struct.unpack("<BBBIH", replies[30].payload[2:])[0], 1)

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
        frames = self._collect_frames(0.1)
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
            20.0,
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
        self.assertAlmostEqual(default_limits[2], 2.0, places=5)

    def test_open_loop_configuration_start_and_quick_stop(self) -> None:
        config = OpenLoopConfig(
            1,
            OpenLoopBackend.DIRECT_SINE,
            7,
            0,
            24.0,
            2.0,
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
        stopped_frames = self._collect_frames(0.12)
        stopped = [
            unpack_telemetry(frame.payload)
            for frame in stopped_frames
            if frame.command == Command.TELEMETRY
        ]
        self.assertTrue(stopped)
        self.assertEqual(stopped[-1].status & (1 << 0), 0)
        self.assertEqual(stopped[-1].status & (1 << 5), 0)


if __name__ == "__main__":
    unittest.main()
