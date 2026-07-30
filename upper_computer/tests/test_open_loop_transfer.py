import unittest

from motor_control.protocol import (
    Command,
    FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG,
    FrameParser,
    OpenLoopBackend,
    OpenLoopConfig,
)
from motor_control.ui import MotorStudioApp


class _Value:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _Status:
    def __init__(self):
        self.text = ""

    def configure(self, **values):
        self.text = values.get("text", self.text)


class _Root:
    def __init__(self):
        self.callbacks = []

    def after(self, delay, callback):
        self.callbacks.append((delay, callback))

    def run_next(self, delay):
        for index, item in enumerate(self.callbacks):
            if item[0] == delay:
                self.callbacks.pop(index)
                item[1]()
                return
        raise AssertionError("no callback scheduled for {} ms".format(delay))


class _Link:
    def __init__(self):
        self.connected = True
        self.packets = []

    def send(self, packet):
        self.packets.append(packet)


class OpenLoopTransferTests(unittest.TestCase):
    def setUp(self):
        app = MotorStudioApp.__new__(MotorStudioApp)
        app.root = _Root()
        app.link = _Link()
        app.sequence = 0
        app.status_message = _Status()
        app.config_status_var = _Value()
        app._pending_open_loop_start = None
        app._open_loop_transfer = None
        app._open_loop_transfer_result = None
        app._open_loop_transfer_token = 0
        app._device_features = FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG
        app._append_log = lambda message, tag: None
        self.app = app
        self.config = OpenLoopConfig(
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

    @staticmethod
    def _decode(packet):
        frames = FrameParser().feed(packet)
        if len(frames) != 1:
            raise AssertionError("expected one encoded frame")
        return frames[0]

    def test_lost_fragment_ack_retries_same_payload_then_recovers(self):
        transfer = self.app._begin_open_loop_config_transfer(
            self.config,
            False,
        )
        self.assertIsNotNone(transfer)
        first = self._decode(self.app.link.packets[-1])
        self.assertEqual(first.command, Command.SET_OPEN_LOOP_CONFIG_PART)
        self.assertEqual(len(self.app.link.packets[-1]), 16)

        self.app._on_open_loop_transfer_timeout(
            transfer["token"],
            first.sequence,
        )
        retry = self._decode(self.app.link.packets[-1])
        self.assertNotEqual(retry.sequence, first.sequence)
        self.assertEqual(retry.payload, first.payload)
        self.assertEqual(transfer["result"]["retries"], 1)

        self.assertFalse(
            self.app._handle_open_loop_transfer_reply(
                Command.SET_OPEN_LOOP_CONFIG_PART,
                0,
                first.sequence,
                bytes((transfer["generation"], 0)),
            )
        )
        self.assertTrue(
            self.app._handle_open_loop_transfer_reply(
                Command.SET_OPEN_LOOP_CONFIG_PART,
                0,
                retry.sequence,
                bytes((transfer["generation"], 0)),
            )
        )
        self.app.root.run_next(10)
        second = self._decode(self.app.link.packets[-1])
        self.assertEqual(second.payload[2], 1)

    def test_full_transfer_reaches_atomic_commit(self):
        transfer = self.app._begin_open_loop_config_transfer(
            self.config,
            False,
        )
        self.assertIsNotNone(transfer)
        generation = transfer["generation"]

        for index in range(14):
            current = self._decode(self.app.link.packets[-1])
            self.assertEqual(
                current.command,
                Command.SET_OPEN_LOOP_CONFIG_PART,
            )
            self.assertEqual(current.payload[2], index)
            self.app._handle_open_loop_transfer_reply(
                Command.SET_OPEN_LOOP_CONFIG_PART,
                0,
                current.sequence,
                bytes((generation, index)),
            )
            self.app.root.run_next(10)

        commit = self._decode(self.app.link.packets[-1])
        self.assertEqual(commit.command, Command.COMMIT_OPEN_LOOP_CONFIG)
        self.assertEqual(len(self.app.link.packets[-1]), 15)
        self.app._handle_open_loop_transfer_reply(
            Command.COMMIT_OPEN_LOOP_CONFIG,
            0,
            commit.sequence,
            bytes((generation,)),
        )
        self.assertIsNone(self.app._open_loop_transfer)
        self.assertEqual(
            self.app._open_loop_transfer_result["state"],
            "ack",
        )

    def test_malformed_ack_aborts_instead_of_advancing(self):
        transfer = self.app._begin_open_loop_config_transfer(
            self.config,
            False,
        )
        current = self._decode(self.app.link.packets[-1])
        handled = self.app._handle_open_loop_transfer_reply(
            Command.SET_OPEN_LOOP_CONFIG_PART,
            0,
            current.sequence,
            b"",
        )
        self.assertTrue(handled)
        self.assertIsNone(self.app._open_loop_transfer)
        self.assertEqual(transfer["result"]["state"], "error")


if __name__ == "__main__":
    unittest.main()
