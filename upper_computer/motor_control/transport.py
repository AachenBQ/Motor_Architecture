"""真实串口与仿真设备的后台通信。"""

import math
import queue
import random
import struct
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .protocol import (
    Command,
    ControlMode,
    Frame,
    FrameParser,
    PidLoop,
    Telemetry,
    VERSION,
    encode_frame,
    pack_telemetry,
    unpack_enable,
    unpack_pid,
    unpack_target,
)


EventKind = str


class LinkEvent:
    __slots__ = ("kind", "data", "timestamp")

    def __init__(self, kind, data=None, timestamp=0.0):
        self.kind = kind
        self.data = data
        self.timestamp = timestamp


class _MotorState:
    __slots__ = (
        "enabled",
        "mode",
        "target",
        "speed",
        "current",
        "voltage",
        "temperature",
        "position",
        "status",
        "pid_values",
        "calibrated",
        "faults",
        "last_heartbeat",
        "lease_ms",
        "limits",
    )

    def __init__(self):
        self.enabled = False
        self.mode = ControlMode.SPEED
        self.target = 0.0
        self.speed = 0.0
        self.current = 0.0
        self.voltage = 48.0
        self.temperature = 28.0
        self.position = 0.0
        self.status = 0
        self.pid_values = {
            PidLoop.CURRENT: (0.80, 0.12, 0.01),
            PidLoop.SPEED: (0.50, 0.05, 0.00),
            PidLoop.POSITION: (2.00, 0.00, 0.02),
        }
        self.calibrated = True
        self.faults = 0
        self.last_heartbeat = time.monotonic()
        self.lease_ms = 750
        self.limits = (20.0, 2.0, 100.0, -1000.0, 1000.0, 18.0, 60.0, 80.0)


class ControllerLink:
    """线程安全的控制器连接。

    UI 只通过事件队列交互，不会因为串口读取而卡顿。
    """

    def __init__(self) -> None:
        self.events = queue.Queue()
        self._tx = queue.Queue()
        self._stop = threading.Event()
        self._thread = None  # type: Optional[threading.Thread]
        self._connected = False
        self.mode = None  # type: Optional[str]

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _emit(self, kind: EventKind, data: Any = None) -> None:
        self.events.put(LinkEvent(kind, data, time.time()))

    def connect_serial(self, port: str, baudrate: int) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("已有连接正在运行")
        self._prepare("serial")
        self._thread = threading.Thread(
            target=self._serial_worker,
            args=(port, baudrate),
            name="motor-serial",
            daemon=True,
        )
        self._thread.start()

    def connect_simulator(self, motor_count: int = 1) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("已有连接正在运行")
        if motor_count != 1:
            raise ValueError("TC375 MCU 模式仿真器仅支持 1 台电机")
        self._prepare("simulator")
        self._thread = threading.Thread(
            target=self._simulator_worker,
            args=(motor_count,),
            name="motor-simulator",
            daemon=True,
        )
        self._thread.start()

    def _prepare(self, mode: str) -> None:
        self._stop.clear()
        self._connected = False
        self.mode = mode
        while not self._tx.empty():
            try:
                self._tx.get_nowait()
            except queue.Empty:
                break

    def send(self, data: bytes, quiet: bool = False) -> None:
        if not self._connected:
            raise RuntimeError("控制器尚未连接")
        packet = bytes(data)
        self._tx.put(packet)
        self._emit("tx_quiet" if quiet else "tx", packet)

    def disconnect(self) -> None:
        self._stop.set()

    def close(self, timeout: float = 1.0) -> None:
        self.disconnect()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)
        self._connected = False

    def poll(self, limit: int = 200) -> List[LinkEvent]:
        result = []  # type: List[LinkEvent]
        for _ in range(limit):
            try:
                result.append(self.events.get_nowait())
            except queue.Empty:
                break
        return result

    def _serial_worker(self, port: str, baudrate: int) -> None:
        serial_port = None
        try:
            try:
                import serial  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError("未安装 pyserial，请先执行：pip install pyserial") from exc
            serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.02,
                write_timeout=0.5,
            )
            self._connected = True
            self._emit("connected", f"{port} @ {baudrate}")
            while not self._stop.is_set():
                try:
                    while True:
                        packet = self._tx.get_nowait()
                        serial_port.write(packet)
                except queue.Empty:
                    pass

                waiting = serial_port.in_waiting
                data = serial_port.read(waiting if waiting else 1)
                if data:
                    self._emit("rx", data)
        except Exception as exc:  # 串口驱动的异常类型因平台而异
            self._emit("error", str(exc))
        finally:
            self._connected = False
            if serial_port is not None:
                try:
                    serial_port.close()
                except Exception:
                    pass
            self._emit("disconnected", None)

    def _simulator_worker(self, motor_count: int) -> None:
        parser = FrameParser()
        motors = {index: _MotorState() for index in range(1, motor_count + 1)}
        rng = random.Random(20260717)
        telemetry_sequence = 0
        last_update = time.monotonic()
        next_telemetry = last_update
        simulator_config = {
            "telemetry_rate_hz": 20,
            "signal_mask": 0x1F,
            "started_at": last_update,
            "protocol_errors": 0,
            "saved": None,
        }  # type: Dict[str, Any]
        self._connected = True
        self._emit("connected", "TC375 单电机仿真设备")
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                dt = min(0.05, max(0.001, now - last_update))
                last_update = now

                try:
                    while True:
                        packet = self._tx.get_nowait()
                        for frame in parser.feed(packet):
                            simulator_config["protocol_errors"] = parser.crc_errors
                            responses = self._handle_simulated_command(
                                frame,
                                motors,
                                simulator_config,
                            )
                            for response in responses:
                                self._emit("rx", encode_frame(response))
                except queue.Empty:
                    pass

                for motor_id, motor in motors.items():
                    heartbeat_valid = (
                        now - motor.last_heartbeat
                    ) * 1000.0 <= motor.lease_ms
                    if not heartbeat_valid and motor.enabled:
                        motor.enabled = False
                        motor.target = 0.0
                        motor.faults |= 1 << 8
                    motor.status = 0
                    if motor.enabled:
                        motor.status |= 1 << 0
                    if motor.calibrated:
                        motor.status |= 1 << 1
                    if motor.faults:
                        motor.status |= 1 << 3
                    if heartbeat_valid:
                        motor.status |= 1 << 4
                    motor.status |= 1 << 7
                    self._update_motor(motor_id, motor, dt, now, rng)

                if now >= next_telemetry:
                    rate_hz = max(
                        1,
                        int(simulator_config["telemetry_rate_hz"]),
                    )
                    next_telemetry = now + 1.0 / rate_hz
                    for motor_id, motor in motors.items():
                        telemetry = Telemetry(
                            motor_id=motor_id,
                            speed_rpm=(
                                motor.speed * 60.0 / (2.0 * math.pi)
                                + rng.uniform(-1.5, 1.5)
                            ),
                            current_a=motor.current + rng.uniform(-0.03, 0.03),
                            voltage_v=motor.voltage + rng.uniform(-0.04, 0.04),
                            temperature_c=motor.temperature,
                            position_deg=motor.position * 180.0 / math.pi,
                            status=motor.status,
                        )
                        frame = Frame(
                            device_id=motor_id,
                            command=Command.TELEMETRY,
                            sequence=telemetry_sequence,
                            payload=pack_telemetry(telemetry),
                        )
                        telemetry_sequence = (telemetry_sequence + 1) & 0xFF
                        self._emit("rx", encode_frame(frame))
                time.sleep(0.005)
        except Exception as exc:
            self._emit("error", f"仿真器异常：{exc}")
        finally:
            self._connected = False
            self._emit("disconnected", None)

    @staticmethod
    def _update_motor(
        motor_id: int,
        motor: _MotorState,
        dt: float,
        now: float,
        rng: random.Random,
    ) -> None:
        target_speed = 0.0
        if motor.enabled:
            if motor.mode is ControlMode.SPEED:
                target_speed = motor.target
            elif motor.mode is ControlMode.TORQUE:
                target_speed = motor.target * 30.0
            else:
                error = motor.target - motor.position
                target_speed = max(-30.0, min(30.0, error * 8.0))
        response = 1.0 - math.exp(-dt / 0.22)
        motor.speed += (target_speed - motor.speed) * response
        motor.position += motor.speed * dt
        load = 0.35 + 0.1 * math.sin(now * 0.65 + motor_id)
        motor.current = (abs(motor.speed) / 100.0 + load) if motor.enabled else 0.05
        motor.current += rng.uniform(-0.01, 0.01)
        thermal_target = 28.0 + motor.current * 5.0
        motor.temperature += (thermal_target - motor.temperature) * min(1.0, dt / 8.0)
        motor.voltage = 48.0 - motor.current * 0.09

    @staticmethod
    def _handle_simulated_command(
        frame: Frame,
        motors: Dict[int, _MotorState],
        simulator_config: Dict[str, Any],
    ) -> List[Frame]:
        status = 0
        detail = b""
        try:
            if frame.version != VERSION:
                raise ValueError("unsupported protocol version")
            command = Command(frame.command)
            if command is Command.PING:
                detail = b"TC375-Sim/2.0"
            elif command is Command.GET_DEVICE_INFO:
                detail = struct.pack(
                    "<BBBBBI16s8s",
                    0,
                    2,
                    0,
                    1,
                    0,
                    0x37500001,
                    b"TC375-MCU",
                    b"SIM00001",
                )
            elif command is Command.GET_CAPABILITIES:
                feature_flags = (1 << 0) | (1 << 2) | (1 << 3) | (1 << 4)
                detail = struct.pack("<BBBIH", 1, 0x01, 0x07, feature_flags, 1000)
            elif command is Command.HEARTBEAT:
                _, lease_ms = struct.unpack("<IH", frame.payload)
                if not 300 <= lease_ms <= 5000:
                    raise ValueError("invalid heartbeat lease")
                for motor in motors.values():
                    motor.last_heartbeat = time.monotonic()
                    motor.lease_ms = lease_ms
            elif command is Command.SET_ENABLE:
                motor_id, enabled = unpack_enable(frame.payload)
                if motor_id == 0xFF and not enabled:
                    for motor in motors.values():
                        motor.enabled = False
                        motor.target = 0.0
                else:
                    motors[motor_id].enabled = enabled
            elif command is Command.SET_MODE:
                motor_id, mode = struct.unpack("<BB", frame.payload)
                motors[motor_id].mode = ControlMode(mode)
            elif command is Command.SET_TARGET:
                motor_id, mode, target = unpack_target(frame.payload)
                motors[motor_id].mode = mode
                motors[motor_id].target = float(target)
            elif command is Command.SET_PID:
                motor_id, loop, kp, ki, kd = unpack_pid(frame.payload)
                motors[motor_id].pid_values[loop] = (kp, ki, kd)
            elif command is Command.CALIBRATE:
                motor_id, _ = struct.unpack("<BB", frame.payload)
                motors[motor_id].calibrated = True
            elif command is Command.CLEAR_FAULT:
                motor_id = frame.payload[0]
                motors[motor_id].faults = 0
            elif command is Command.SET_LIMITS:
                values = struct.unpack("<Bffffffff", frame.payload)
                motor = motors[values[0]]
                limits = values[1:]
                if motor.enabled:
                    raise ValueError("limits cannot change while enabled")
                if (
                    not all(math.isfinite(value) for value in limits)
                    or limits[0] <= 0.0
                    or limits[1] <= 0.0
                    or limits[2] <= 0.0
                    or limits[3] >= limits[4]
                    or limits[5] <= 0.0
                    or limits[5] >= limits[6]
                    or limits[7] <= 0.0
                ):
                    raise ValueError("invalid limits")
                motor.limits = limits
            elif command is Command.GET_LIMITS:
                motor_id = frame.payload[0]
                detail = struct.pack("<Bffffffff", motor_id, *motors[motor_id].limits)
            elif command is Command.SAVE_CONFIG:
                if any(motor.enabled for motor in motors.values()):
                    raise ValueError("cannot save while enabled")
                simulator_config["saved"] = {
                    "limits": motors[1].limits,
                    "pid_values": dict(motors[1].pid_values),
                    "telemetry_rate_hz": simulator_config["telemetry_rate_hz"],
                }
            elif command is Command.RESTORE_DEFAULTS:
                if any(motor.enabled for motor in motors.values()):
                    raise ValueError("cannot restore while enabled")
                for motor in motors.values():
                    motor.pid_values = {
                        PidLoop.CURRENT: (0.80, 0.12, 0.01),
                        PidLoop.SPEED: (0.50, 0.05, 0.00),
                        PidLoop.POSITION: (2.00, 0.00, 0.02),
                    }
                    motor.limits = (
                        20.0,
                        2.0,
                        100.0,
                        -1000.0,
                        1000.0,
                        18.0,
                        60.0,
                        80.0,
                    )
                simulator_config["telemetry_rate_hz"] = 20
                simulator_config["signal_mask"] = 0x1F
            elif command in (Command.CONTROLLED_STOP, Command.QUICK_STOP):
                motor_id = frame.payload[0]
                motors[motor_id].target = 0.0
                motors[motor_id].enabled = False
            elif command is Command.EMERGENCY_STOP:
                selected = frame.payload[0] if frame.payload else 0xFF
                for motor_id, motor in motors.items():
                    if selected in (0xFF, motor_id):
                        motor.enabled = False
                        motor.target = 0.0
            elif command is Command.GET_PID:
                motor_id = frame.payload[0]
                loop = PidLoop(
                    frame.payload[1] if len(frame.payload) > 1 else PidLoop.SPEED
                )
                kp, ki, kd = motors[motor_id].pid_values[loop]
                detail = struct.pack("<Bfff", int(loop), kp, ki, kd)
            elif command is Command.GET_DIAGNOSTICS:
                fault_bits = motors[1].faults if 1 in motors else 0
                detail = struct.pack(
                    "<IHH",
                    int(
                        (time.monotonic() - simulator_config["started_at"])
                        * 1000
                    )
                    & 0xFFFFFFFF,
                    int(simulator_config["protocol_errors"]) & 0xFFFF,
                    fault_bits,
                )
            elif command is Command.SET_TELEMETRY_PROFILE:
                rate_hz, signal_mask = struct.unpack("<HI", frame.payload)
                if not 1 <= rate_hz <= 1000:
                    raise ValueError("invalid telemetry rate")
                simulator_config["telemetry_rate_hz"] = rate_hz
                simulator_config["signal_mask"] = signal_mask
            elif command is Command.GET_TELEMETRY_PROFILE:
                detail = struct.pack(
                    "<HI",
                    int(simulator_config["telemetry_rate_hz"]),
                    int(simulator_config["signal_mask"]),
                )
            elif command is Command.GET_BACKEND_INFO:
                detail = struct.pack("<BB", 0, 1)
            else:
                status = 1
        except (ValueError, KeyError, struct.error, IndexError):
            status = 2

        response = Frame(
            device_id=frame.device_id,
            command=Command.ACK if status == 0 else Command.ERROR,
            sequence=frame.sequence,
            payload=bytes((frame.command, status)) + detail,
        )
        return [response]


def list_serial_ports() -> Tuple[List[str], Optional[str]]:
    """返回可用串口；未安装 pyserial 时同时返回说明。"""

    try:
        from serial.tools import list_ports  # type: ignore[import-not-found]
    except ImportError:
        return [], "未安装 pyserial（仿真模式仍可使用）"
    ports = sorted((port.device for port in list_ports.comports()), key=str.casefold)
    return ports, None
