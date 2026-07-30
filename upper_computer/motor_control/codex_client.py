"""Command-line client for a running Motor Studio Codex bridge."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .protocol import FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG


DEFAULT_MANIFEST = Path(tempfile.gettempdir()) / "motor-studio-codex-bridge.json"
READ_CONFIG_ACTIONS = (
    "device_info",
    "capabilities",
    "build_config",
    "limits",
    "telemetry_profile",
    "open_loop_config",
    "backend",
    "diagnostics",
)


class ClientError(Exception):
    pass


class BridgeClient:
    def __init__(self, manifest_path: Optional[Path] = None) -> None:
        configured = os.environ.get("MOTOR_STUDIO_BRIDGE_FILE")
        self.manifest_path = Path(
            manifest_path or configured or DEFAULT_MANIFEST
        )
        try:
            with self.manifest_path.open("r", encoding="utf-8") as stream:
                manifest = json.load(stream)
        except (OSError, ValueError) as exc:
            raise ClientError(
                "Motor Studio bridge is not running; start the GUI first."
            ) from exc
        self.base_url = "http://{}:{}/v1".format(
            manifest["host"],
            manifest["port"],
        )
        self.token = str(manifest["token"])

    def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        timeout: float = 5.0,
    ) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urlencode(query)
        body = None
        headers = {
            "Authorization": "Bearer {}".format(self.token),
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                value = json.loads(exc.read().decode("utf-8"))
                detail = value.get("error", str(exc))
            except Exception:
                detail = str(exc)
            raise ClientError(detail)
        except (URLError, OSError, ValueError) as exc:
            raise ClientError(
                "Cannot reach the Motor Studio bridge: {}".format(exc)
            )
        if not value.get("ok"):
            raise ClientError(value.get("error", "unknown bridge error"))
        return value.get("result")

    def get(self, path: str, **query: Any) -> Any:
        return self.request("GET", path, query=query or None)

    def action(self, name: str, **payload: Any) -> Any:
        return self.request("POST", "/actions/" + name, payload=payload)

    def wait_transaction(
        self,
        sequence: int,
        timeout: float = 2.0,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        latest = {}  # type: Dict[str, Any]
        while time.monotonic() < deadline:
            latest = self.get("/transactions/{}".format(sequence))
            if latest.get("state") != "pending":
                return latest
            time.sleep(0.05)
        return latest

    def wait_open_loop_transfer(
        self,
        token: int,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        latest = {
            "token": int(token),
            "state": "pending",
        }  # type: Dict[str, Any]
        while time.monotonic() < deadline:
            status = self.get("/status")
            transfer = status.get("open_loop_transfer")
            if (
                isinstance(transfer, dict)
                and int(transfer.get("token", -1)) == int(token)
            ):
                latest = transfer
                if latest.get("state") != "pending":
                    return latest
            time.sleep(0.05)
        return latest


def _add_wait_options(
    parser: argparse.ArgumentParser,
    default_timeout: float = 2.0,
) -> None:
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="queue the command without waiting for the device ACK",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=default_timeout,
        help="ACK wait timeout in seconds (default: {})".format(
            default_timeout
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connect Codex to a running Motor Studio instance"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="bridge manifest path (normally auto-discovered)",
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    sub.add_parser("status", help="show connection, safety and telemetry state")
    logs = sub.add_parser("logs", help="read the Motor Studio communication log")
    logs.add_argument("--limit", type=int, default=100)
    history = sub.add_parser("history", help="read recent decoded telemetry")
    history.add_argument("--seconds", type=float, default=5.0)
    history.add_argument("--limit", type=int, default=500)
    sub.add_parser("ports", help="list serial ports")
    sub.add_parser("arm-status", help="show Codex control authorization")

    connect = sub.add_parser("connect", help="connect the control hardware")
    connect.add_argument("--port", required=True)
    connect.add_argument("--baud", type=int, default=115200)
    sub.add_parser("simulator", help="start the single-motor simulator")
    sub.add_parser("disconnect", help="quick-stop and disconnect")

    for name, help_text in (
        ("ping", "send PING"),
        ("device-info", "read device information"),
        ("capabilities", "read device capabilities"),
        ("diagnostics", "read diagnostics"),
        ("build-config", "read firmware build macros"),
        ("read-config", "read all device configuration"),
        ("quick-stop", "remove motor output immediately"),
        ("emergency-stop", "broadcast emergency stop"),
        ("clear-fault", "clear device and software protection locks"),
        ("enable", "enable the motor (GUI authorization required)"),
        ("disable", "disable the motor"),
        ("start-open-loop", "start configured open loop (authorization required)"),
    ):
        item = sub.add_parser(name, help=help_text)
        if name not in ("disconnect",):
            _add_wait_options(item)
        if name in ("enable", "start-open-loop"):
            item.add_argument(
                "--power-stage-confirmed",
                action="store_true",
                help="explicitly confirm that the real power stage may move",
            )

    target = sub.add_parser(
        "set-target",
        help="set a target (GUI authorization required)",
    )
    target.add_argument(
        "--mode",
        choices=("torque", "speed", "position", "open-loop-speed"),
        required=True,
    )
    target.add_argument("--value", type=float, required=True)
    _add_wait_options(target)

    pid = sub.add_parser(
        "set-pid",
        help="set one PID loop (GUI authorization required)",
    )
    pid.add_argument(
        "--loop",
        choices=("current", "speed", "position"),
        required=True,
    )
    pid.add_argument("--kp", type=float, required=True)
    pid.add_argument("--ki", type=float, required=True)
    pid.add_argument("--kd", type=float, required=True)
    _add_wait_options(pid)

    config = sub.add_parser(
        "configure-open-loop",
        help="configure SimpleFOC open loop (GUI authorization required)",
    )
    config.add_argument("--pole-pairs", type=int, default=7)
    config.add_argument("--bus-voltage", type=float, default=7.0)
    config.add_argument("--voltage-limit", type=float, default=0.3)
    config.add_argument("--target-velocity", type=float, default=5.0)
    config.add_argument("--acceleration", type=float, default=10.0)
    config.add_argument("--update-period-ms", type=int, default=10)
    config.add_argument("--startup-delay-ms", type=int, default=500)
    config.add_argument("--max-runtime-ms", type=int, default=30000)
    _add_wait_options(config, 10.0)

    communication_test = sub.add_parser(
        "communication-test",
        help="repeat fragmented configuration and readback without starting PWM",
    )
    communication_test.add_argument("--iterations", type=int, default=20)
    communication_test.add_argument("--pole-pairs", type=int, default=7)
    communication_test.add_argument("--bus-voltage", type=float, default=7.0)
    communication_test.add_argument(
        "--voltage-limit",
        type=float,
        default=0.3,
    )
    communication_test.add_argument(
        "--target-velocity",
        type=float,
        default=5.0,
    )
    communication_test.add_argument(
        "--acceleration",
        type=float,
        default=10.0,
    )
    communication_test.add_argument(
        "--update-period-ms",
        type=int,
        default=10,
    )
    communication_test.add_argument(
        "--startup-delay-ms",
        type=int,
        default=500,
    )
    communication_test.add_argument(
        "--max-runtime-ms",
        type=int,
        default=30000,
    )
    communication_test.add_argument("--timeout", type=float, default=10.0)
    return parser


def _action_name(command: str) -> str:
    return command.replace("-", "_")


def _transaction_result(
    client: BridgeClient,
    result: Any,
    no_wait: bool,
    timeout: float,
) -> Any:
    if no_wait or not isinstance(result, dict):
        return result
    if "transactions" in result:
        return {
            "queued": result,
            "replies": [
                client.wait_transaction(item["sequence"], timeout)
                for item in result["transactions"]
            ],
        }
    if "transfer_token" in result:
        return {
            "queued": result,
            "reply": client.wait_open_loop_transfer(
                result["transfer_token"],
                timeout,
            ),
        }
    if "sequence" not in result:
        return result
    return {
        "queued": result,
        "reply": client.wait_transaction(result["sequence"], timeout),
    }


def _read_config_sequentially(
    client: BridgeClient,
    no_wait: bool,
    timeout: float,
) -> Dict[str, Any]:
    queries = []
    for action in READ_CONFIG_ACTIONS:
        queued = client.action(action)
        item = {"action": action, "queued": queued}
        if no_wait:
            # Keep --no-wait non-blocking without recreating an RX burst.
            time.sleep(0.12)
        elif isinstance(queued, dict) and "sequence" in queued:
            item["reply"] = client.wait_transaction(
                queued["sequence"],
                timeout,
            )
        queries.append(item)
    return {"queries": queries}


def _wait_action_ack(
    client: BridgeClient,
    action: str,
    timeout: float,
) -> Dict[str, Any]:
    queued = client.action(action)
    if not isinstance(queued, dict) or "sequence" not in queued:
        raise ClientError("{} did not create a transaction".format(action))
    reply = client.wait_transaction(queued["sequence"], timeout)
    if reply.get("state") != "ack" or reply.get("status") != 0:
        raise ClientError(
            "{} failed: {}".format(action, reply)
        )
    return reply


def _diagnostic_error_counters(
    reply: Dict[str, Any],
) -> Dict[str, int]:
    decoded = reply.get("decoded") or {}
    names = (
        "protocol_errors",
        "tx_high_priority_failures",
        "telemetry_drops",
        "rx_sw_fifo_overflows",
        "rx_hw_fifo_overflows",
        "rx_frame_errors",
        "rx_parity_errors",
        "parser_crc_errors",
        "parser_length_errors",
        "parser_timeout_errors",
        "parser_resync_events",
        "rx_isr_entries",
        "rx_poll_drains",
        "rx_poll_bytes",
    )
    return {
        name: int(decoded.get(name, 0))
        for name in names
    }


def _run_communication_test(
    client: BridgeClient,
    args: Any,
) -> Dict[str, Any]:
    iterations = int(args.iterations)
    if not 1 <= iterations <= 200:
        raise ClientError("iterations must be in 1..200")
    timeout = max(0.5, float(args.timeout))
    capabilities = _wait_action_ack(
        client,
        "capabilities",
        timeout,
    )
    features = int(
        (capabilities.get("decoded") or {}).get("features", 0)
    )
    if not features & FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG:
        raise ClientError(
            "device does not advertise fragmented open-loop configuration"
        )
    before_reply = _wait_action_ack(client, "diagnostics", timeout)
    before_decoded = before_reply.get("decoded") or {}
    if not before_decoded.get("rx_scheduler_available", False):
        raise ClientError(
            "device did not return the 46-byte RX scheduler diagnostics "
            "requested with section mask 0x07"
        )
    before = _diagnostic_error_counters(before_reply)
    total_retries = 0
    last_config_readback = None

    for iteration in range(iterations):
        target_velocity = float(args.target_velocity)
        if iteration & 1:
            target_velocity += 0.01
        queued = client.action(
            "configure_open_loop",
            pole_pairs=int(args.pole_pairs),
            bus_voltage=float(args.bus_voltage),
            voltage_limit=float(args.voltage_limit),
            target_velocity=target_velocity,
            acceleration=float(args.acceleration),
            update_period_ms=int(args.update_period_ms),
            startup_delay_ms=int(args.startup_delay_ms),
            max_runtime_ms=int(args.max_runtime_ms),
        )
        if (
            not isinstance(queued, dict)
            or "transfer_token" not in queued
        ):
            raise ClientError(
                "iteration {} did not start a transfer".format(
                    iteration + 1
                )
            )
        transfer = client.wait_open_loop_transfer(
            queued["transfer_token"],
            timeout,
        )
        if transfer.get("state") != "ack":
            raise ClientError(
                "fragmented transfer {} failed: {}".format(
                    iteration + 1,
                    transfer,
                )
            )
        iteration_retries = int(transfer.get("retries", 0))
        total_retries += iteration_retries
        if iteration_retries != 0:
            raise ClientError(
                "fragmented transfer {} required {} retry/retries; "
                "zero-fault communication test failed".format(
                    iteration + 1,
                    iteration_retries,
                )
            )

        readback = _wait_action_ack(
            client,
            "open_loop_config",
            timeout,
        )
        decoded = readback.get("decoded") or {}
        last_config_readback = decoded
        expected_exact = {
            "motor_id": 1,
            "backend": "SIMPLEFOC",
            "pole_pairs": int(args.pole_pairs),
            "flags": 0,
            "update_period_ms": int(args.update_period_ms),
            "startup_delay_ms": int(args.startup_delay_ms),
            "max_runtime_ms": int(args.max_runtime_ms),
        }
        expected_float = {
            "bus_voltage_v": float(args.bus_voltage),
            "voltage_limit_v": float(args.voltage_limit),
            "target_velocity_rad_s": target_velocity,
            "acceleration_rad_s2": float(args.acceleration),
        }
        mismatches = {
            name: {
                "expected": expected,
                "actual": decoded.get(name),
            }
            for name, expected in expected_exact.items()
            if decoded.get(name) != expected
        }
        for name, expected in expected_float.items():
            try:
                actual = float(decoded[name])
            except (KeyError, TypeError, ValueError):
                mismatches[name] = {
                    "expected": expected,
                    "actual": decoded.get(name),
                }
            else:
                if abs(actual - expected) > 0.001:
                    mismatches[name] = {
                        "expected": expected,
                        "actual": actual,
                    }
        if mismatches:
            raise ClientError(
                "iteration {} readback mismatch: {}".format(
                    iteration + 1,
                    mismatches,
                )
            )

    after_reply = _wait_action_ack(client, "diagnostics", timeout)
    after_decoded = after_reply.get("decoded") or {}
    if not after_decoded.get("rx_scheduler_available", False):
        raise ClientError(
            "device stopped returning 46-byte RX scheduler diagnostics"
        )
    after = _diagnostic_error_counters(after_reply)
    activity_names = (
        "rx_isr_entries",
        "rx_poll_drains",
        "rx_poll_bytes",
    )
    deltas = {
        name: (
            (after[name] - before[name]) & 0xFFFF
            if name in activity_names
            else after[name] - before[name]
        )
        for name in before
    }
    faults = {
        name: value
        for name, value in deltas.items()
        if name not in activity_names and value != 0
    }
    if faults:
        raise ClientError(
            "communication counters increased: {}".format(faults)
        )
    return {
        "state": "pass",
        "iterations": iterations,
        "fragment_frames": iterations * 14,
        "commit_frames": iterations,
        "readback_frames": iterations,
        "retries": total_retries,
        "counter_deltas": deltas,
        "rx_activity_deltas": {
            name: deltas[name]
            for name in activity_names
        },
        "last_readback": last_config_readback,
        "final_diagnostics": after_reply.get("decoded"),
    }


def main(argv: Optional[Any] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = BridgeClient(args.manifest)
        if args.command == "status":
            result = client.get("/status")
        elif args.command == "logs":
            result = client.get("/logs", limit=args.limit)
        elif args.command == "history":
            result = client.get(
                "/history",
                seconds=args.seconds,
                limit=args.limit,
            )
        elif args.command == "ports":
            result = client.get("/ports")
        elif args.command == "arm-status":
            result = client.get("/arm")
        elif args.command == "read-config":
            result = _read_config_sequentially(
                client,
                args.no_wait,
                args.timeout,
            )
        elif args.command == "communication-test":
            result = _run_communication_test(client, args)
        else:
            ignored = {
                "command",
                "manifest",
                "no_wait",
                "timeout",
            }
            payload = {
                key: value
                for key, value in vars(args).items()
                if key not in ignored
            }
            result = client.action(_action_name(args.command), **payload)
            if hasattr(args, "no_wait"):
                result = _transaction_result(
                    client,
                    result,
                    args.no_wait,
                    args.timeout,
                )
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except ClientError as exc:
        safe_message = str(exc).encode(
            "ascii",
            errors="backslashreplace",
        ).decode("ascii")
        print("error: {}".format(safe_message), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
