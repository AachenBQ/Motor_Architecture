"""Minimal read-only serial probe for the TC375 native protocol.

This module intentionally does not use ``ControllerLink``, the GUI command
queue, or the GUI heartbeat timer.  It is useful for determining whether a
communication fault is in the raw serial/protocol path or in higher layers.

Only four commands are permitted:

* PING
* GET_DEVICE_INFO
* GET_CAPABILITIES
* GET_DIAGNOSTICS

No heartbeat, enable, configuration, target, or motor-start frame can be sent
through :class:`RawSerialProbe`.
"""

import argparse
import json
import math
import struct
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .protocol import (
    Command,
    Diagnostics,
    Frame,
    FrameParser,
    VERSION,
    bytes_to_hex,
    encode_frame,
    unpack_diagnostics,
    unpack_telemetry,
)


READ_ONLY_REQUESTS = (
    (Command.PING, b""),
    (Command.GET_DEVICE_INFO, b""),
    (Command.GET_CAPABILITIES, b""),
    # Request UART, parser and RX scheduler diagnostic extensions.
    (Command.GET_DIAGNOSTICS, b"\x07"),
)
READ_ONLY_COMMANDS = frozenset(item[0] for item in READ_ONLY_REQUESTS)

DIAGNOSTIC_COMMUNICATION_COUNTERS = (
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
)


class ProbeError(Exception):
    """Raised for probe setup, serial, or safety errors."""


def _command_name(command: Any) -> str:
    try:
        return Command(int(command)).name
    except (TypeError, ValueError):
        return "0x{:02X}".format(int(command) & 0xFF)


def _diagnostics_to_dict(value: Diagnostics) -> Dict[str, Any]:
    return {
        "uptime_ms": value.uptime_ms,
        "protocol_errors": value.protocol_errors,
        "fault_bits": value.fault_bits,
        "commands_received": value.commands_received,
        "heartbeat_age_ms": value.heartbeat_age_ms,
        "heartbeat_lease_ms": value.heartbeat_lease_ms,
        "motor_state": value.motor_state,
        "last_stop_reason": value.last_stop_reason,
        "runtime_flags": value.runtime_flags,
        "hardware_flags": value.hardware_flags,
        "tx_high_priority_failures": value.tx_high_priority_failures,
        "telemetry_drops": value.telemetry_drops,
        "rx_sw_fifo_overflows": value.rx_sw_fifo_overflows,
        "rx_hw_fifo_overflows": value.rx_hw_fifo_overflows,
        "rx_frame_errors": value.rx_frame_errors,
        "rx_parity_errors": value.rx_parity_errors,
        "parser_crc_errors": value.parser_crc_errors,
        "parser_length_errors": value.parser_length_errors,
        "parser_timeout_errors": value.parser_timeout_errors,
        "parser_resync_events": value.parser_resync_events,
        "rx_isr_entries": value.rx_isr_entries,
        "rx_poll_drains": value.rx_poll_drains,
        "rx_poll_bytes": value.rx_poll_bytes,
    }


def decode_read_only_detail(command: Any, detail: bytes) -> Dict[str, Any]:
    """Decode a successful response and reject malformed command payloads."""

    command = Command(int(command))
    if command is Command.PING:
        return {
            "device": detail.decode("ascii", errors="replace"),
        }
    if command is Command.GET_DEVICE_INFO:
        if len(detail) != 33:
            raise ValueError(
                "GET_DEVICE_INFO detail must be 33 bytes, got {}".format(
                    len(detail)
                )
            )
        values = struct.unpack("<BBBBBI16s8s", detail)
        return {
            "firmware": "{}.{}.{}".format(*values[:3]),
            "hardware": "{}.{}".format(values[3], values[4]),
            "serial_number": "{:08X}".format(values[5]),
            "name": values[6].rstrip(b"\x00").decode(
                "ascii",
                errors="replace",
            ),
            "build_id": values[7].rstrip(b"\x00").decode(
                "ascii",
                errors="replace",
            ),
        }
    if command is Command.GET_CAPABILITIES:
        if len(detail) != 9:
            raise ValueError(
                "GET_CAPABILITIES detail must be 9 bytes, got {}".format(
                    len(detail)
                )
            )
        values = struct.unpack("<BBBIH", detail)
        return {
            "motor_count": values[0],
            "backend_mask": values[1],
            "mode_mask": values[2],
            "features": values[3],
            "max_telemetry_hz": values[4],
        }
    if command is Command.GET_DIAGNOSTICS:
        return _diagnostics_to_dict(unpack_diagnostics(detail))
    raise ProbeError(
        "command {} is outside the read-only probe allow-list".format(
            _command_name(command)
        )
    )


class ProbeStats:
    """Mutable statistics for one raw serial probe run."""

    def __init__(self) -> None:
        self.started_at = 0.0
        self.finished_at = 0.0
        self.requests = 0
        self.matched_responses = 0
        self.timeouts = 0
        self.error_responses = 0
        self.malformed_responses = 0
        self.mismatched_responses = 0
        self.protocol_version_mismatches = 0
        self.device_mismatches = 0
        self.unexpected_frames = 0
        self.short_writes = 0
        self.rx_bytes = 0
        self.rx_frames = 0
        self.telemetry_frames = 0
        self.telemetry_decode_errors = 0
        self.fault_event_frames = 0
        self.diagnostics_decode_errors = 0
        self.diagnostics_samples = []  # type: List[Dict[str, Any]]
        self.by_command = {}  # type: Dict[int, Dict[str, Any]]

    def _command_stats(self, command: Any) -> Dict[str, Any]:
        code = int(command)
        if code not in self.by_command:
            self.by_command[code] = {
                "requests": 0,
                "responses": 0,
                "timeouts": 0,
                "errors": 0,
                "latencies_ms": [],
            }
        return self.by_command[code]

    def record_request(self, command: Any) -> None:
        self.requests += 1
        self._command_stats(command)["requests"] += 1

    def record_timeout(self, command: Any) -> None:
        self.timeouts += 1
        self._command_stats(command)["timeouts"] += 1

    def record_response(
        self,
        command: Any,
        latency_ms: float,
        is_error: bool,
    ) -> None:
        self.matched_responses += 1
        values = self._command_stats(command)
        values["responses"] += 1
        values["latencies_ms"].append(float(latency_ms))
        if is_error:
            self.error_responses += 1
            values["errors"] += 1

    def diagnostic_delta(self) -> Dict[str, Optional[int]]:
        if len(self.diagnostics_samples) < 2:
            return {}
        first = self.diagnostics_samples[0]
        last = self.diagnostics_samples[-1]
        result = {}  # type: Dict[str, Optional[int]]
        for name in DIAGNOSTIC_COMMUNICATION_COUNTERS:
            before = int(first[name])
            after = int(last[name])
            result[name] = after - before if after >= before else None
        return result

    def device_restarted(self) -> bool:
        if len(self.diagnostics_samples) < 2:
            return False
        return (
            int(self.diagnostics_samples[-1]["uptime_ms"])
            < int(self.diagnostics_samples[0]["uptime_ms"])
        )

    def local_fault_count(self, parser: FrameParser) -> int:
        return sum(
            (
                self.timeouts,
                self.error_responses,
                self.malformed_responses,
                self.mismatched_responses,
                self.protocol_version_mismatches,
                self.device_mismatches,
                self.unexpected_frames,
                self.short_writes,
                self.telemetry_decode_errors,
                self.diagnostics_decode_errors,
                parser.crc_errors,
                parser.length_errors,
            )
        )

    def successful(self, parser: FrameParser) -> bool:
        if self.local_fault_count(parser):
            return False
        if self.device_restarted():
            return False
        return not any(
            value is None or value > 0
            for value in self.diagnostic_delta().values()
        )

    @staticmethod
    def _latency_summary(values: List[float]) -> Dict[str, Optional[float]]:
        if not values:
            return {
                "count": 0,
                "min_ms": None,
                "mean_ms": None,
                "p95_ms": None,
                "max_ms": None,
            }
        ordered = sorted(values)
        p95_index = max(0, int(math.ceil(len(ordered) * 0.95)) - 1)
        return {
            "count": len(values),
            "min_ms": round(ordered[0], 3),
            "mean_ms": round(sum(ordered) / len(ordered), 3),
            "p95_ms": round(ordered[p95_index], 3),
            "max_ms": round(ordered[-1], 3),
        }

    def to_dict(self, parser: FrameParser) -> Dict[str, Any]:
        commands = {}
        for code in sorted(self.by_command):
            values = self.by_command[code]
            commands[_command_name(code)] = {
                "requests": values["requests"],
                "responses": values["responses"],
                "timeouts": values["timeouts"],
                "errors": values["errors"],
                "latency": self._latency_summary(
                    values["latencies_ms"]
                ),
            }
        duration = max(0.0, self.finished_at - self.started_at)
        diagnostics_first = (
            self.diagnostics_samples[0]
            if self.diagnostics_samples
            else None
        )
        diagnostics_last = (
            self.diagnostics_samples[-1]
            if self.diagnostics_samples
            else None
        )
        return {
            "success": self.successful(parser),
            "duration_s": round(duration, 3),
            "requests": self.requests,
            "matched_responses": self.matched_responses,
            "timeouts": self.timeouts,
            "error_responses": self.error_responses,
            "malformed_responses": self.malformed_responses,
            "mismatched_responses": self.mismatched_responses,
            "protocol_version_mismatches":
                self.protocol_version_mismatches,
            "device_mismatches": self.device_mismatches,
            "unexpected_frames": self.unexpected_frames,
            "short_writes": self.short_writes,
            "rx_bytes": self.rx_bytes,
            "rx_frames": self.rx_frames,
            "telemetry_frames": self.telemetry_frames,
            "telemetry_decode_errors": self.telemetry_decode_errors,
            "fault_event_frames": self.fault_event_frames,
            "host_parser": {
                "crc_errors": parser.crc_errors,
                "length_errors": parser.length_errors,
                "discarded_bytes": parser.discarded_bytes,
            },
            "diagnostics": {
                "samples": len(self.diagnostics_samples),
                "decode_errors": self.diagnostics_decode_errors,
                "first": diagnostics_first,
                "last": diagnostics_last,
                "delta": self.diagnostic_delta(),
                "device_restarted": self.device_restarted(),
            },
            "commands": commands,
        }


class RawSerialProbe:
    """Synchronous, single-outstanding-request, read-only protocol probe."""

    def __init__(
        self,
        serial_port: Any,
        device_id: int = 1,
        timeout: float = 0.5,
        interval: float = 0.05,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        if not 0 <= int(device_id) <= 0xFF:
            raise ValueError("device_id must be in 0..255")
        if float(timeout) <= 0.0:
            raise ValueError("timeout must be greater than zero")
        if float(interval) < 0.0:
            raise ValueError("interval cannot be negative")
        self.serial_port = serial_port
        self.device_id = int(device_id)
        self.timeout = float(timeout)
        self.interval = float(interval)
        self.clock = clock
        self.sleep = sleep
        self.on_result = on_result
        self.parser = FrameParser()
        self.stats = ProbeStats()
        self._sequence = 0

    def _next_sequence(self) -> int:
        value = self._sequence
        self._sequence = (self._sequence + 1) & 0xFF
        return value

    def _read_frames(self) -> List[Frame]:
        try:
            waiting = int(getattr(self.serial_port, "in_waiting", 0))
            data = self.serial_port.read(waiting if waiting > 0 else 1)
        except Exception as exc:
            raise ProbeError("serial read failed: {}".format(exc))
        if not data:
            return []
        self.stats.rx_bytes += len(data)
        frames = self.parser.feed(data)
        self.stats.rx_frames += len(frames)
        return frames

    def _handle_non_response(self, frame: Frame) -> None:
        if frame.command == Command.TELEMETRY:
            try:
                unpack_telemetry(frame.payload)
            except ValueError:
                self.stats.telemetry_decode_errors += 1
            else:
                self.stats.telemetry_frames += 1
            return
        if frame.command == Command.FAULT_EVENT:
            self.stats.fault_event_frames += 1
            return
        self.stats.unexpected_frames += 1

    def _inspect_frame(
        self,
        frame: Frame,
        expected_command: Command,
        expected_sequence: int,
        sent_at: float,
    ) -> Optional[Dict[str, Any]]:
        if frame.version != VERSION:
            self.stats.protocol_version_mismatches += 1
            return None
        if frame.command not in (Command.ACK, Command.ERROR):
            self._handle_non_response(frame)
            return None
        if len(frame.payload) < 2:
            self.stats.malformed_responses += 1
            return None

        original = frame.payload[0]
        status = frame.payload[1]
        if (
            frame.sequence != expected_sequence
            or original != int(expected_command)
        ):
            self.stats.mismatched_responses += 1
            return None
        if frame.device_id != self.device_id:
            self.stats.device_mismatches += 1
            return None

        detail = frame.payload[2:]
        is_error = frame.command == Command.ERROR or status != 0
        latency_ms = (self.clock() - sent_at) * 1000.0
        self.stats.record_response(
            expected_command,
            latency_ms,
            is_error,
        )
        decoded = None  # type: Optional[Dict[str, Any]]
        decode_error = None  # type: Optional[str]
        if not is_error:
            try:
                decoded = decode_read_only_detail(
                    expected_command,
                    detail,
                )
            except (ValueError, struct.error) as exc:
                decode_error = str(exc)
                self.stats.malformed_responses += 1
                if expected_command is Command.GET_DIAGNOSTICS:
                    self.stats.diagnostics_decode_errors += 1
            else:
                if expected_command is Command.GET_DIAGNOSTICS:
                    self.stats.diagnostics_samples.append(decoded)
        return {
            "command": _command_name(expected_command),
            "command_code": int(expected_command),
            "sequence": expected_sequence,
            "state": "error" if is_error else (
                "malformed" if decode_error else "ack"
            ),
            "status": int(status),
            "latency_ms": round(latency_ms, 3),
            "detail_hex": bytes_to_hex(detail),
            "decoded": decoded,
            "decode_error": decode_error,
        }

    def query(
        self,
        command: Any,
        payload: bytes = b"",
    ) -> Dict[str, Any]:
        try:
            command = Command(int(command))
        except (TypeError, ValueError):
            raise ProbeError("unknown command: {!r}".format(command))
        if command not in READ_ONLY_COMMANDS:
            raise ProbeError(
                "refusing non-read-only command {}".format(
                    _command_name(command)
                )
            )
        allowed_payload = dict(READ_ONLY_REQUESTS)[command]
        if bytes(payload) != allowed_payload:
            raise ProbeError(
                "refusing unexpected payload for {}".format(
                    _command_name(command)
                )
            )

        sequence = self._next_sequence()
        packet = encode_frame(
            Frame(
                device_id=self.device_id,
                command=command,
                sequence=sequence,
                payload=allowed_payload,
            )
        )
        self.stats.record_request(command)
        sent_at = self.clock()
        try:
            written = self.serial_port.write(packet)
        except Exception as exc:
            raise ProbeError("serial write failed: {}".format(exc))
        if written is not None and int(written) != len(packet):
            self.stats.short_writes += 1

        deadline = sent_at + self.timeout
        while self.clock() < deadline:
            for frame in self._read_frames():
                result = self._inspect_frame(
                    frame,
                    command,
                    sequence,
                    sent_at,
                )
                if result is not None:
                    if self.on_result is not None:
                        self.on_result(result)
                    return result
            remaining = deadline - self.clock()
            if remaining > 0.0:
                self.sleep(min(0.005, remaining))

        self.stats.record_timeout(command)
        result = {
            "command": _command_name(command),
            "command_code": int(command),
            "sequence": sequence,
            "state": "timeout",
            "status": None,
            "latency_ms": None,
            "detail_hex": "",
            "decoded": None,
            "decode_error": None,
        }
        if self.on_result is not None:
            self.on_result(result)
        return result

    def _pump_for(self, duration: float) -> None:
        deadline = self.clock() + max(0.0, float(duration))
        while self.clock() < deadline:
            frames = self._read_frames()
            for frame in frames:
                if frame.version != VERSION:
                    self.stats.protocol_version_mismatches += 1
                elif frame.command in (Command.ACK, Command.ERROR):
                    # There is no outstanding request during the interval.
                    self.stats.mismatched_responses += 1
                else:
                    self._handle_non_response(frame)
            remaining = deadline - self.clock()
            if remaining > 0.0:
                self.sleep(min(0.005, remaining))

    def run(self, iterations: int) -> Dict[str, Any]:
        if not 1 <= int(iterations) <= 10000:
            raise ValueError("iterations must be in 1..10000")
        self.stats.started_at = self.clock()
        total_requests = int(iterations) * len(READ_ONLY_REQUESTS)
        request_index = 0
        for _ in range(int(iterations)):
            for command, payload in READ_ONLY_REQUESTS:
                self.query(command, payload)
                request_index += 1
                if self.interval and request_index < total_requests:
                    self._pump_for(self.interval)
        self.stats.finished_at = self.clock()
        return self.stats.to_dict(self.parser)


def open_serial_port(port: str, baudrate: int, timeout: float) -> Any:
    """Open pyserial without asserting DTR or RTS."""

    serial_port = None
    try:
        import serial  # type: ignore[import-not-found]
    except ImportError:
        raise ProbeError(
            "pyserial is not installed; run: pip install -r requirements.txt"
        )
    try:
        serial_port = serial.Serial()
        serial_port.port = port
        serial_port.baudrate = int(baudrate)
        serial_port.bytesize = serial.EIGHTBITS
        serial_port.parity = serial.PARITY_NONE
        serial_port.stopbits = serial.STOPBITS_ONE
        serial_port.timeout = min(0.02, max(0.001, float(timeout)))
        serial_port.write_timeout = max(0.1, float(timeout))
        serial_port.dtr = False
        serial_port.rts = False
        serial_port.open()
        # Exclude bytes and ACKs left by an earlier application/session.
        serial_port.reset_input_buffer()
        serial_port.reset_output_buffer()
        return serial_port
    except Exception as exc:
        try:
            if serial_port is not None:
                serial_port.close()
        except Exception:
            pass
        raise ProbeError(
            "cannot open {} at {} baud: {}".format(
                port,
                baudrate,
                exc,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only TC375 raw serial probe; sends no heartbeat, enable, "
            "configuration, target, or motor-start commands."
        )
    )
    parser.add_argument("--port", required=True, help="serial port, e.g. COM4")
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="baud rate (default: 115200)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=20,
        help="number of four-query cycles (default: 20)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.5,
        help="per-request ACK timeout in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.05,
        help="receive-pumping interval between requests (default: 0.05)",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=1,
        help="device address (default: 1)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="suppress per-request output and print JSON only",
    )
    return parser


def _print_result(result: Dict[str, Any]) -> None:
    latency = (
        "-"
        if result["latency_ms"] is None
        else "{:.3f} ms".format(result["latency_ms"])
    )
    suffix = ""
    decoded = result.get("decoded")
    if result["command"] == "PING" and decoded:
        suffix = " device={}".format(decoded.get("device", ""))
    elif result["command"] == "GET_DEVICE_INFO" and decoded:
        suffix = " fw={} build={}".format(
            decoded.get("firmware", "?"),
            decoded.get("build_id", "?"),
        )
    elif result["command"] == "GET_CAPABILITIES" and decoded:
        suffix = " features=0x{:08X}".format(
            int(decoded.get("features", 0))
        )
    elif result["command"] == "GET_DIAGNOSTICS" and decoded:
        suffix = (
            " protocol_errors={} rx_overflow={}/{} "
            "rx_schedule={}/{}/{}"
        ).format(
            decoded.get("protocol_errors", "?"),
            decoded.get("rx_sw_fifo_overflows", "?"),
            decoded.get("rx_hw_fifo_overflows", "?"),
            decoded.get("rx_isr_entries", "?"),
            decoded.get("rx_poll_drains", "?"),
            decoded.get("rx_poll_bytes", "?"),
        )
    print(
        "{:<20} seq={:3d} {:<9} latency={}{}".format(
            result["command"],
            result["sequence"],
            result["state"].upper(),
            latency,
            suffix,
        )
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.baud <= 0:
        print("error: --baud must be greater than zero", file=sys.stderr)
        return 2
    if not 1 <= args.iterations <= 10000:
        print("error: --iterations must be in 1..10000", file=sys.stderr)
        return 2
    if args.timeout <= 0.0:
        print("error: --timeout must be greater than zero", file=sys.stderr)
        return 2
    if args.interval < 0.0:
        print("error: --interval cannot be negative", file=sys.stderr)
        return 2

    serial_port = None
    try:
        serial_port = open_serial_port(
            args.port,
            args.baud,
            args.timeout,
        )
        probe = RawSerialProbe(
            serial_port,
            device_id=args.device,
            timeout=args.timeout,
            interval=args.interval,
            on_result=None if args.json else _print_result,
        )
        summary = probe.run(args.iterations)
    except (ProbeError, ValueError, KeyboardInterrupt) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
