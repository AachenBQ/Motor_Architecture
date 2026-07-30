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
    FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG,
    HARDWARE_FLAG_COMMISSIONING_OVERRIDE,
    HARDWARE_FLAG_GATE_ENABLED,
    HARDWARE_FLAG_NFAULT_CLEAR,
    HARDWARE_FLAG_POWER_STAGE_BUILD,
    HARDWARE_FLAG_PWM_ENABLED,
    HARDWARE_FLAG_SAFETY_READY,
    OPEN_LOOP_CONFIG_FRAGMENT_COUNT,
    OpenLoopBackend,
    OpenLoopConfig,
    PidLoop,
    POWER_STAGE_COMMISSIONING_MAX_ACCEL_RAD_S2,
    POWER_STAGE_COMMISSIONING_MAX_RUNTIME_MS,
    POWER_STAGE_COMMISSIONING_MAX_SPEED_RAD_S,
    POWER_STAGE_COMMISSIONING_MAX_VOLTAGE_V,
    POWER_STAGE_COMMISSIONING_OVERRIDE,
    POWER_STAGE_REQUIRED_SAFETY_MASK,
    START_FLAG_POWER_STAGE_CONFIRMED,
    Telemetry,
    VERSION,
    crc16_modbus,
    encode_frame,
    pack_telemetry,
    pack_open_loop_config,
    unpack_enable,
    unpack_pid,
    unpack_target,
    unpack_open_loop_config,
    unpack_open_loop_config_commit,
    unpack_open_loop_config_fragment,
)


EventKind = str


class _SimulatedProtocolError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = int(status)


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
        "open_loop_config",
        "open_loop_active",
        "open_loop_velocity",
        "open_loop_started",
        "last_stop_reason",
    )

    def __init__(self):
        self.enabled = False
        self.mode = ControlMode.SPEED
        self.target = 0.0
        self.speed = 0.0
        self.current = 0.0
        self.voltage = 7.0
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
        self.limits = (0.3, 0.03, 100.0, -1000.0, 1000.0, 5.0, 8.0, 80.0)
        self.open_loop_config = OpenLoopConfig(
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
        self.open_loop_active = False
        self.open_loop_velocity = 0.0
        self.open_loop_started = 0.0
        self.last_stop_reason = 0


def _validate_simulated_open_loop_config(
    config: OpenLoopConfig,
    motor: _MotorState,
) -> None:
    finite_values = (
        config.bus_voltage_v,
        config.voltage_limit_v,
        config.target_velocity_rad_s,
        config.acceleration_rad_s2,
    )
    if (
        config.flags != 0
        or not 1 <= config.pole_pairs <= 64
        or (
            config.backend is OpenLoopBackend.SIMPLEFOC
            and config.pole_pairs != 7
        )
        or not all(math.isfinite(value) for value in finite_values)
        or not 0.0 < config.bus_voltage_v <= 8.0
        or not 0.0 < config.voltage_limit_v
        <= config.bus_voltage_v
        or config.voltage_limit_v > 2.0
        or abs(config.target_velocity_rad_s) > 100.0
        or abs(config.target_velocity_rad_s) > motor.limits[2]
        or not 0.01 <= config.acceleration_rad_s2 <= 10000.0
        or not 1 <= config.update_period_ms <= 100
        or not 0 <= config.startup_delay_ms <= 5000
        or not 1000 <= config.max_runtime_ms <= 600000
        or not motor.limits[5]
        <= config.bus_voltage_v
        <= motor.limits[6]
    ):
        raise _SimulatedProtocolError(
            5,
            "open-loop config exceeds firmware limits",
        )


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
        self.tx_queued_packets = 0
        self.tx_queued_bytes = 0
        self.tx_written_packets = 0
        self.tx_written_bytes = 0
        self.tx_write_failures = 0

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
        self.tx_queued_packets = 0
        self.tx_queued_bytes = 0
        self.tx_written_packets = 0
        self.tx_written_bytes = 0
        self.tx_write_failures = 0
        while not self._tx.empty():
            try:
                self._tx.get_nowait()
            except queue.Empty:
                break

    def send(self, data: bytes, quiet: bool = False) -> None:
        if not self._connected:
            raise RuntimeError("控制器尚未连接")
        packet = bytes(data)
        self._tx.put((packet, bool(quiet)))
        self.tx_queued_packets += 1
        self.tx_queued_bytes += len(packet)

    def _record_tx_written(
        self,
        packet: bytes,
        quiet: bool,
        transport: str,
    ) -> None:
        self.tx_written_packets += 1
        self.tx_written_bytes += len(packet)
        self._emit(
            "tx_written",
            {
                "packet": packet,
                "written": len(packet),
                "quiet": bool(quiet),
                "transport": transport,
            },
        )

    def _record_tx_failure(
        self,
        packet: bytes,
        written: int,
        message: str,
    ) -> None:
        self.tx_write_failures += 1
        self._emit(
            "tx_write_error",
            {
                "packet": packet,
                "requested": len(packet),
                "written": int(written),
                "message": str(message),
            },
        )

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
            # Configure DTR/RTS before opening. Some USB-UART adapters wire
            # either signal to board reset; pyserial defaults could
            # otherwise restart the MCU during the first connection.
            serial_port = serial.Serial()
            serial_port.port = port
            serial_port.baudrate = baudrate
            serial_port.bytesize = serial.EIGHTBITS
            serial_port.parity = serial.PARITY_NONE
            serial_port.stopbits = serial.STOPBITS_ONE
            serial_port.timeout = 0.02
            serial_port.write_timeout = 0.5
            serial_port.dtr = False
            serial_port.rts = False
            serial_port.open()
            self._connected = True
            self._emit("connected", f"{port} @ {baudrate}")
            while not self._stop.is_set():
                try:
                    while True:
                        packet, quiet = self._tx.get_nowait()
                        try:
                            written = serial_port.write(packet)
                        except Exception as exc:
                            self._record_tx_failure(packet, 0, str(exc))
                            raise
                        if written is None:
                            written = 0
                        if int(written) != len(packet):
                            message = (
                                "串口短写：请求 {} B，实际写入 {} B"
                            ).format(len(packet), int(written))
                            self._record_tx_failure(
                                packet,
                                int(written),
                                message,
                            )
                            raise IOError(message)
                        self._record_tx_written(
                            packet,
                            quiet,
                            "serial",
                        )
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
            "commands_received": 0,
            "saved": None,
            "open_loop_staging": {},
            "open_loop_committed": {},
            "rx_isr_entries": 0,
            "rx_poll_drains": 0,
            "rx_poll_bytes": 0,
            "control_hardware_enabled": True,
            "power_stage_enabled": False,
            "simplefoc_enabled": True,
            "safety_mask": POWER_STAGE_REQUIRED_SAFETY_MASK,
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
                        packet, quiet = self._tx.get_nowait()
                        self._record_tx_written(
                            packet,
                            quiet,
                            "simulator",
                        )
                        simulator_config["rx_poll_drains"] = (
                            int(simulator_config["rx_poll_drains"]) + 1
                        ) & 0xFFFF
                        simulator_config["rx_poll_bytes"] = (
                            int(simulator_config["rx_poll_bytes"])
                            + len(packet)
                        ) & 0xFFFF
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
                        motor.open_loop_active = False
                        motor.open_loop_velocity = 0.0
                        motor.faults |= 1 << 8
                        motor.last_stop_reason = 5
                    motor.status = 0
                    if motor.enabled:
                        motor.status |= 1 << 0
                    if motor.calibrated:
                        motor.status |= 1 << 1
                    if motor.faults:
                        motor.status |= 1 << 3
                    if heartbeat_valid:
                        motor.status |= 1 << 4
                    if motor.open_loop_active:
                        motor.status |= 1 << 5
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
            if motor.mode is ControlMode.OPEN_LOOP_SPEED:
                elapsed_ms = (now - motor.open_loop_started) * 1000.0
                if elapsed_ms >= motor.open_loop_config.max_runtime_ms:
                    motor.enabled = False
                    motor.open_loop_active = False
                    motor.target = 0.0
                    motor.open_loop_velocity = 0.0
                    motor.last_stop_reason = 6
                elif elapsed_ms >= motor.open_loop_config.startup_delay_ms:
                    maximum_step = (
                        motor.open_loop_config.acceleration_rad_s2 * dt
                    )
                    difference = motor.target - motor.open_loop_velocity
                    difference = max(-maximum_step, min(maximum_step, difference))
                    motor.open_loop_velocity += difference
                    target_speed = motor.open_loop_velocity
            elif motor.mode is ControlMode.SPEED:
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
        motor.voltage = max(
            0.0,
            motor.open_loop_config.bus_voltage_v - motor.current * 0.09,
        )

    @staticmethod
    def _handle_simulated_command(
        frame: Frame,
        motors: Dict[int, _MotorState],
        simulator_config: Dict[str, Any],
    ) -> List[Frame]:
        status = 0
        detail = b""
        simulator_config["commands_received"] = (
            int(simulator_config.get("commands_received", 0)) + 1
        )
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
                feature_flags = (
                    (1 << 0) | (1 << 2) | (1 << 3) |
                    (1 << 4) | (1 << 5) |
                    FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG
                )
                detail = struct.pack("<BBBIH", 1, 0x01, 0x0F, feature_flags, 1000)
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
                        motor.open_loop_active = False
                        motor.open_loop_velocity = 0.0
                        motor.last_stop_reason = 1
                else:
                    motor = motors[motor_id]
                    if enabled and motor.mode is ControlMode.OPEN_LOOP_SPEED:
                        raise ValueError("open loop requires START_OPEN_LOOP")
                    motor.enabled = enabled
                    if enabled:
                        simulator_config["open_loop_staging"].pop(
                            motor_id,
                            None,
                        )
                    if not enabled:
                        motor.target = 0.0
                        motor.open_loop_active = False
                        motor.open_loop_velocity = 0.0
                        motor.last_stop_reason = 1
            elif command is Command.SET_MODE:
                motor_id, mode = struct.unpack("<BB", frame.payload)
                if ControlMode(mode) is ControlMode.OPEN_LOOP_SPEED:
                    raise ValueError("open loop requires START_OPEN_LOOP")
                motors[motor_id].mode = ControlMode(mode)
            elif command is Command.SET_TARGET:
                motor_id, mode, target = unpack_target(frame.payload)
                if (
                    mode is ControlMode.OPEN_LOOP_SPEED
                    and not motors[motor_id].open_loop_active
                ):
                    raise ValueError("open loop is not running")
                motors[motor_id].mode = mode
                motors[motor_id].target = float(target)
                if mode is ControlMode.OPEN_LOOP_SPEED:
                    motors[motor_id].open_loop_config.target_velocity_rad_s = (
                        float(target)
                    )
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
                    or abs(
                        motor.open_loop_config.target_velocity_rad_s
                    ) > limits[2]
                    or not limits[5]
                    <= motor.open_loop_config.bus_voltage_v
                    <= limits[6]
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
                    "open_loop_config": motors[1].open_loop_config,
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
                        0.3,
                        0.03,
                        100.0,
                        -1000.0,
                        1000.0,
                        5.0,
                        8.0,
                        80.0,
                    )
                    motor.open_loop_config = OpenLoopConfig(
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
                simulator_config["telemetry_rate_hz"] = 20
                simulator_config["signal_mask"] = 0x1F
                simulator_config["open_loop_staging"].clear()
                simulator_config["open_loop_committed"].clear()
            elif command in (Command.CONTROLLED_STOP, Command.QUICK_STOP):
                motor_id = frame.payload[0]
                motors[motor_id].target = 0.0
                motors[motor_id].enabled = False
                motors[motor_id].open_loop_active = False
                motors[motor_id].open_loop_velocity = 0.0
                motors[motor_id].last_stop_reason = (
                    2 if command is Command.CONTROLLED_STOP else 3
                )
            elif command is Command.EMERGENCY_STOP:
                selected = frame.payload[0] if frame.payload else 0xFF
                for motor_id, motor in motors.items():
                    if selected in (0xFF, motor_id):
                        motor.enabled = False
                        motor.target = 0.0
                        motor.open_loop_active = False
                        motor.open_loop_velocity = 0.0
                        motor.last_stop_reason = 4
            elif command is Command.GET_PID:
                motor_id = frame.payload[0]
                loop = PidLoop(
                    frame.payload[1] if len(frame.payload) > 1 else PidLoop.SPEED
                )
                kp, ki, kd = motors[motor_id].pid_values[loop]
                detail = struct.pack("<Bfff", int(loop), kp, ki, kd)
            elif command is Command.GET_DIAGNOSTICS:
                motor = motors.get(1)
                now = time.monotonic()
                fault_bits = motor.faults if motor is not None else 0
                heartbeat_age_ms = (
                    min(
                        0xFFFF,
                        int((now - motor.last_heartbeat) * 1000.0),
                    )
                    if motor is not None
                    else 0xFFFF
                )
                heartbeat_lease_ms = (
                    motor.lease_ms if motor is not None else 0
                )
                runtime_flags = 0
                if (
                    motor is not None
                    and heartbeat_age_ms <= motor.lease_ms
                ):
                    runtime_flags |= 1 << 0
                if motor is not None and motor.enabled:
                    runtime_flags |= 1 << 1
                if motor is not None and motor.open_loop_active:
                    runtime_flags |= 1 << 2
                hardware_flags = HARDWARE_FLAG_NFAULT_CLEAR
                safety_mask = int(simulator_config["safety_mask"])
                power_stage_enabled = bool(
                    simulator_config["power_stage_enabled"]
                )
                if motor is not None and motor.enabled:
                    hardware_flags |= HARDWARE_FLAG_PWM_ENABLED
                    if power_stage_enabled:
                        hardware_flags |= HARDWARE_FLAG_GATE_ENABLED
                if (
                    safety_mask & POWER_STAGE_REQUIRED_SAFETY_MASK
                ) == POWER_STAGE_REQUIRED_SAFETY_MASK:
                    hardware_flags |= HARDWARE_FLAG_SAFETY_READY
                if power_stage_enabled:
                    hardware_flags |= HARDWARE_FLAG_POWER_STAGE_BUILD
                if safety_mask & POWER_STAGE_COMMISSIONING_OVERRIDE:
                    hardware_flags |= (
                        HARDWARE_FLAG_COMMISSIONING_OVERRIDE
                    )
                motor_state = (
                    6
                    if fault_bits
                    else (4 if motor is not None and motor.enabled else 1)
                )
                diagnostic_values = [
                    int(
                        (now - simulator_config["started_at"])
                        * 1000
                    )
                    & 0xFFFFFFFF,
                    int(simulator_config["protocol_errors"]) & 0xFFFF,
                    fault_bits,
                    int(simulator_config["commands_received"])
                    & 0xFFFFFFFF,
                    heartbeat_age_ms,
                    heartbeat_lease_ms,
                    motor_state,
                    motor.last_stop_reason if motor is not None else 0,
                    runtime_flags,
                    hardware_flags,
                    0,
                    0,
                ]
                sections = frame.payload[0] if frame.payload else 0
                if sections & 0x04:
                    detail = struct.pack(
                        "<IHHIHHBBBBHHHHHHHHHHHHH",
                        *(
                            diagnostic_values
                            + [0] * 8
                            + [
                                int(simulator_config["rx_isr_entries"]),
                                int(simulator_config["rx_poll_drains"]),
                                int(simulator_config["rx_poll_bytes"]),
                            ]
                        )
                    )
                elif sections & 0x02:
                    detail = struct.pack(
                        "<IHHIHHBBBBHHHHHHHHHH",
                        *(diagnostic_values + [0] * 8)
                    )
                elif sections & 0x01:
                    detail = struct.pack(
                        "<IHHIHHBBBBHHHHHH",
                        *(diagnostic_values + [0] * 4)
                    )
                else:
                    detail = struct.pack(
                        "<IHHIHHBBBBHH",
                        *diagnostic_values
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
            elif command is Command.SET_OPEN_LOOP_CONFIG:
                config = unpack_open_loop_config(frame.payload)
                motor = motors[config.motor_id]
                if motor.enabled or motor.open_loop_active:
                    raise _SimulatedProtocolError(
                        4,
                        "open-loop config cannot change while running",
                    )
                _validate_simulated_open_loop_config(config, motor)
                motor.open_loop_config = config
                simulator_config["open_loop_staging"].pop(
                    config.motor_id,
                    None,
                )
                simulator_config["open_loop_committed"].pop(
                    config.motor_id,
                    None,
                )
            elif command is Command.SET_OPEN_LOOP_CONFIG_PART:
                motor_id, generation, index, data = (
                    unpack_open_loop_config_fragment(frame.payload)
                )
                motor = motors[motor_id]
                if motor.enabled or motor.open_loop_active:
                    raise _SimulatedProtocolError(
                        4,
                        "open-loop config cannot change while running"
                    )
                staging = simulator_config["open_loop_staging"]
                transfer = staging.get(motor_id)
                now = time.monotonic()
                if (
                    transfer is not None
                    and now - transfer.get("updated_at", now) >= 5.0
                ):
                    del staging[motor_id]
                    transfer = None
                if (
                    transfer is None
                    or transfer["generation"] != generation
                ):
                    transfer = {
                        "generation": generation,
                        "parts": {},
                        "updated_at": now,
                    }
                    staging[motor_id] = transfer
                transfer["parts"][index] = data
                transfer["updated_at"] = now
                detail = bytes((generation, index))
            elif command is Command.COMMIT_OPEN_LOOP_CONFIG:
                motor_id, generation, expected_crc = (
                    unpack_open_loop_config_commit(frame.payload)
                )
                motor = motors[motor_id]
                staging = simulator_config["open_loop_staging"]
                transfer = staging.get(motor_id)
                now = time.monotonic()
                if (
                    transfer is not None
                    and now - transfer.get("updated_at", now) >= 5.0
                ):
                    del staging[motor_id]
                    transfer = None
                committed = simulator_config["open_loop_committed"]
                committed_value = committed.get(motor_id)
                if (
                    committed_value is not None
                    and now - committed_value[2] >= 5.0
                ):
                    del committed[motor_id]
                    committed_value = None
                if (
                    transfer is None
                    and committed_value is not None
                    and committed_value[:2]
                    == (generation, expected_crc)
                    and now - committed_value[2] < 5.0
                ):
                    detail = bytes((generation,))
                else:
                    if motor.enabled or motor.open_loop_active:
                        raise _SimulatedProtocolError(
                            4,
                            "open-loop config cannot change while running"
                        )
                    if (
                        transfer is None
                        or transfer["generation"] != generation
                        or len(transfer["parts"]) !=
                        OPEN_LOOP_CONFIG_FRAGMENT_COUNT
                    ):
                        raise _SimulatedProtocolError(
                            4,
                            "open-loop config fragments incomplete"
                        )
                    raw_config = b"".join(
                        transfer["parts"][index]
                        for index in range(
                            OPEN_LOOP_CONFIG_FRAGMENT_COUNT
                        )
                    )
                    if crc16_modbus(raw_config) != expected_crc:
                        raise ValueError(
                            "open-loop config fragment CRC mismatch"
                        )
                    config = unpack_open_loop_config(raw_config)
                    if config.motor_id != motor_id:
                        raise ValueError("open-loop config motor mismatch")
                    _validate_simulated_open_loop_config(config, motor)
                    motor.open_loop_config = config
                    committed[motor_id] = (
                        generation,
                        expected_crc,
                        now,
                    )
                    del staging[motor_id]
                    detail = bytes((generation,))
            elif command is Command.GET_OPEN_LOOP_CONFIG:
                motor_id = frame.payload[0]
                detail = pack_open_loop_config(
                    motors[motor_id].open_loop_config
                )
            elif command is Command.START_OPEN_LOOP:
                power_stage_enabled = bool(
                    simulator_config["power_stage_enabled"]
                )
                expected_length = 2 if power_stage_enabled else 1
                if len(frame.payload) != expected_length:
                    raise _SimulatedProtocolError(
                        4,
                        "open-loop start confirmation is invalid",
                    )
                motor_id = frame.payload[0]
                motor = motors[motor_id]
                safety_mask = int(simulator_config["safety_mask"])
                if power_stage_enabled:
                    if not (
                        frame.payload[1]
                        & START_FLAG_POWER_STAGE_CONFIRMED
                    ):
                        raise _SimulatedProtocolError(
                            4,
                            "power-stage confirmation is required",
                        )
                    missing_safety = (
                        POWER_STAGE_REQUIRED_SAFETY_MASK
                        & ~safety_mask
                    )
                    commissioning_override = bool(
                        safety_mask
                        & POWER_STAGE_COMMISSIONING_OVERRIDE
                    )
                    if missing_safety and not commissioning_override:
                        raise _SimulatedProtocolError(
                            10,
                            "power-stage safety readiness is incomplete",
                        )
                    config = motor.open_loop_config
                    if commissioning_override and missing_safety and (
                        config.voltage_limit_v
                        > POWER_STAGE_COMMISSIONING_MAX_VOLTAGE_V
                        or abs(config.target_velocity_rad_s)
                        > POWER_STAGE_COMMISSIONING_MAX_SPEED_RAD_S
                        or config.acceleration_rad_s2
                        > POWER_STAGE_COMMISSIONING_MAX_ACCEL_RAD_S2
                        or config.max_runtime_ms
                        > POWER_STAGE_COMMISSIONING_MAX_RUNTIME_MS
                    ):
                        raise _SimulatedProtocolError(
                            5,
                            "commissioning parameters are not conservative",
                        )
                heartbeat_valid = (
                    time.monotonic() - motor.last_heartbeat
                ) * 1000.0 <= motor.lease_ms
                if motor.faults or not heartbeat_valid or motor.enabled:
                    raise ValueError("open-loop start interlock failed")
                motor.mode = ControlMode.OPEN_LOOP_SPEED
                motor.target = motor.open_loop_config.target_velocity_rad_s
                motor.open_loop_velocity = 0.0
                motor.open_loop_started = time.monotonic()
                motor.open_loop_active = True
                motor.enabled = True
                motor.last_stop_reason = 0
                simulator_config["open_loop_staging"].pop(
                    motor_id,
                    None,
                )
            elif command is Command.GET_BUILD_CONFIG:
                detail = struct.pack(
                    "<BBBBBIIIIHHHHfI",
                    1,
                    int(bool(simulator_config["control_hardware_enabled"])),
                    int(bool(simulator_config["power_stage_enabled"])),
                    int(bool(simulator_config["simplefoc_enabled"])),
                    7,
                    10000,
                    20000,
                    10000,
                    1000,
                    100,
                    750,
                    300,
                    5000,
                    0.10,
                    int(simulator_config["safety_mask"]),
                )
            else:
                status = 1
        except _SimulatedProtocolError as exc:
            status = exc.status
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
