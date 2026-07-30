import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from motor_control.codex_bridge import BridgeRequestError, CodexBridge
from motor_control.codex_client import (
    BridgeClient,
    ClientError,
    READ_CONFIG_ACTIONS,
    _read_config_sequentially,
    _run_communication_test,
    _transaction_result,
)


class _ImmediateRoot:
    def after(self, _delay, callback):
        callback()


class CodexBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.manifest = Path(self.temporary.name) / "bridge.json"
        self.calls = []

        def handle(action, params):
            self.calls.append((action, params))
            if action == "denied":
                raise BridgeRequestError("denied by test", 403)
            return {"action": action, "params": params}

        self.bridge = CodexBridge(
            _ImmediateRoot(),
            handle,
            manifest_path=self.manifest,
        )
        self.bridge.start()

    def tearDown(self):
        self.bridge.stop()
        self.temporary.cleanup()

    def test_manifest_client_and_dispatch(self):
        self.assertTrue(self.manifest.exists())
        client = BridgeClient(self.manifest)
        result = client.get("/status")
        self.assertEqual(result["action"], "status")
        result = client.action("ping", value=7)
        self.assertEqual(result["params"]["value"], 7)
        self.assertIn(("status", {}), self.calls)

    def test_requires_bearer_token(self):
        with self.manifest.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream)
        request = Request(
            "http://127.0.0.1:{}/v1/status".format(manifest["port"])
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2.0)
        self.assertEqual(raised.exception.code, 401)

    def test_bridge_error_status_is_preserved(self):
        client = BridgeClient(self.manifest)
        with self.assertRaises(Exception) as raised:
            client.action("denied")
        self.assertIn("denied by test", str(raised.exception))

    def test_stop_removes_own_manifest(self):
        self.bridge.stop()
        self.assertFalse(self.manifest.exists())

    def test_read_config_waits_for_each_ack_before_next_query(self):
        events = []

        class _Client:
            def action(self, name):
                events.append(("send", name))
                return {"sequence": len(events)}

            def wait_transaction(self, sequence, timeout):
                events.append(("wait", sequence, timeout))
                return {"state": "ack"}

        result = _read_config_sequentially(_Client(), False, 1.5)
        self.assertEqual(
            [item["action"] for item in result["queries"]],
            list(READ_CONFIG_ACTIONS),
        )
        for index, action in enumerate(READ_CONFIG_ACTIONS):
            send = events[index * 2]
            wait = events[index * 2 + 1]
            self.assertEqual(send, ("send", action))
            self.assertEqual(wait[0], "wait")
            self.assertEqual(wait[2], 1.5)

    def test_fragment_transfer_result_waits_for_terminal_state(self):
        calls = []

        class _Client:
            def wait_open_loop_transfer(self, token, timeout):
                calls.append((token, timeout))
                return {"token": token, "state": "ack"}

        result = _transaction_result(
            _Client(),
            {"queued": True, "transfer_token": 17},
            False,
            8.0,
        )
        self.assertEqual(calls, [(17, 8.0)])
        self.assertEqual(result["reply"]["state"], "ack")

    def test_communication_test_checks_every_readback_and_counter(self):
        class _Client:
            def __init__(self):
                self.sequence = 0
                self.token = 0
                self.last_target = 0.0
                self.transactions = {}
                self.diagnostics_reads = 0

            def action(self, name, **params):
                if name == "configure_open_loop":
                    self.token += 1
                    self.last_target = float(params["target_velocity"])
                    return {"transfer_token": self.token}
                self.sequence += 1
                self.transactions[self.sequence] = name
                return {"sequence": self.sequence}

            def wait_open_loop_transfer(self, token, timeout):
                return {
                    "token": token,
                    "state": "ack",
                    "retries": 0,
                }

            def wait_transaction(self, sequence, timeout):
                action = self.transactions[sequence]
                if action == "open_loop_config":
                    decoded = {
                        "motor_id": 1,
                        "backend": "SIMPLEFOC",
                        "pole_pairs": 7,
                        "flags": 0,
                        "bus_voltage_v": 7.0,
                        "voltage_limit_v": 0.3,
                        "target_velocity_rad_s": self.last_target,
                        "acceleration_rad_s2": 10.0,
                        "update_period_ms": 10,
                        "startup_delay_ms": 500,
                        "max_runtime_ms": 30000,
                    }
                elif action == "capabilities":
                    decoded = {"features": 1 << 6}
                elif action == "diagnostics":
                    self.diagnostics_reads += 1
                    decoded = {
                        "rx_scheduler_available": True,
                        "rx_isr_entries":
                            100 + 3 * self.diagnostics_reads,
                        "rx_poll_drains":
                            200 + 4 * self.diagnostics_reads,
                        "rx_poll_bytes":
                            300 + 50 * self.diagnostics_reads,
                    }
                else:
                    decoded = {}
                return {
                    "state": "ack",
                    "status": 0,
                    "decoded": decoded,
                }

        args = SimpleNamespace(
            iterations=3,
            timeout=2.0,
            pole_pairs=7,
            bus_voltage=7.0,
            voltage_limit=0.3,
            target_velocity=5.0,
            acceleration=10.0,
            update_period_ms=10,
            startup_delay_ms=500,
            max_runtime_ms=30000,
        )
        result = _run_communication_test(_Client(), args)
        self.assertEqual(result["state"], "pass")
        self.assertEqual(result["iterations"], 3)
        self.assertEqual(result["fragment_frames"], 42)
        self.assertEqual(
            result["rx_activity_deltas"],
            {
                "rx_isr_entries": 3,
                "rx_poll_drains": 4,
                "rx_poll_bytes": 50,
            },
        )
        self.assertTrue(
            all(
                result["counter_deltas"][name] == 0
                for name in result["counter_deltas"]
                if name not in result["rx_activity_deltas"]
            )
        )

    def test_communication_test_rejects_recovered_retry(self):
        class _RetryClient:
            def __init__(self):
                self.sequence = 0
                self.actions = {}

            def action(self, name, **params):
                if name == "configure_open_loop":
                    return {"transfer_token": 1}
                self.sequence += 1
                self.actions[self.sequence] = name
                return {"sequence": self.sequence}

            def wait_transaction(self, sequence, timeout):
                decoded = (
                    {"features": 1 << 6}
                    if self.actions[sequence] == "capabilities"
                    else (
                        {"rx_scheduler_available": True}
                        if self.actions[sequence] == "diagnostics"
                        else {}
                    )
                )
                return {
                    "state": "ack",
                    "status": 0,
                    "decoded": decoded,
                }

            def wait_open_loop_transfer(self, token, timeout):
                return {
                    "token": token,
                    "state": "ack",
                    "retries": 1,
                }

        args = SimpleNamespace(
            iterations=1,
            timeout=2.0,
            pole_pairs=7,
            bus_voltage=7.0,
            voltage_limit=0.3,
            target_velocity=5.0,
            acceleration=10.0,
            update_period_ms=10,
            startup_delay_ms=500,
            max_runtime_ms=30000,
        )
        with self.assertRaises(ClientError) as raised:
            _run_communication_test(_RetryClient(), args)
        self.assertIn("zero-fault", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
