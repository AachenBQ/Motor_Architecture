"""串口帧协议与常用电机控制载荷。

默认帧格式（小端）::

    AA 55 | VER | FLAGS | DEVICE | CMD | SEQ | LEN(2) | PAYLOAD | CRC16(2)

CRC16/MODBUS 的计算范围为 ``VER`` 到 ``PAYLOAD``，不包含帧头和 CRC。
实际控制器协议不一致时，只需要替换本模块，界面和通信线程无需改动。
"""

from enum import IntEnum
import math
import struct
from typing import Iterable, List, Optional, Tuple, Union


SOF = b"\xAA\x55"
VERSION = 0x02
HEADER_STRUCT = struct.Struct("<2sBBBBBH")
HEADER_SIZE = HEADER_STRUCT.size
CRC_SIZE = 2
MAX_PAYLOAD = 2048
FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG = 1 << 6
START_FLAG_POWER_STAGE_CONFIRMED = 1 << 0

POWER_STAGE_SAFETY_CURRENT = 1 << 0
POWER_STAGE_SAFETY_BUS_VOLTAGE = 1 << 1
POWER_STAGE_SAFETY_TEMPERATURE = 1 << 2
POWER_STAGE_SAFETY_WATCHDOG = 1 << 3
POWER_STAGE_SAFETY_PHYSICAL_ESTOP = 1 << 4
POWER_STAGE_SAFETY_EXTERNAL_CURRENT_LIMIT = 1 << 5
POWER_STAGE_SAFETY_NFAULT_MONITOR = 1 << 6
POWER_STAGE_SAFETY_HEARTBEAT = 1 << 7
POWER_STAGE_SAFETY_SAFE_OUTPUT = 1 << 8
POWER_STAGE_REQUIRED_SAFETY_MASK = 0x01FF
POWER_STAGE_COMMISSIONING_OVERRIDE = 1 << 31
POWER_STAGE_COMMISSIONING_MAX_VOLTAGE_V = 0.10
POWER_STAGE_COMMISSIONING_MAX_SPEED_RAD_S = 1.0
POWER_STAGE_COMMISSIONING_MAX_ACCEL_RAD_S2 = 1.0
POWER_STAGE_COMMISSIONING_MAX_RUNTIME_MS = 1000

HARDWARE_FLAG_PWM_ENABLED = 1 << 0
HARDWARE_FLAG_GATE_ENABLED = 1 << 1
HARDWARE_FLAG_NFAULT_CLEAR = 1 << 2
HARDWARE_FLAG_SAFETY_READY = 1 << 3
HARDWARE_FLAG_POWER_STAGE_BUILD = 1 << 4
HARDWARE_FLAG_COMMISSIONING_OVERRIDE = 1 << 5


class Command(IntEnum):
    """TC375 单电机原生协议 v2 命令字。"""

    PING = 0x01
    GET_DEVICE_INFO = 0x02
    GET_CAPABILITIES = 0x03
    HEARTBEAT = 0x04
    SET_ENABLE = 0x10
    SET_MODE = 0x11
    SET_TARGET = 0x12
    SET_PID = 0x13
    CALIBRATE = 0x15
    CLEAR_FAULT = 0x16
    SET_LIMITS = 0x17
    GET_LIMITS = 0x18
    SAVE_CONFIG = 0x19
    RESTORE_DEFAULTS = 0x1A
    CONTROLLED_STOP = 0x1B
    QUICK_STOP = 0x1C
    EMERGENCY_STOP = 0x1F
    GET_PID = 0x20
    READ_PARAMETERS = 0x20  # 兼容上位机旧名称
    WRITE_PARAMETER = 0x21
    GET_DIAGNOSTICS = 0x22
    SET_TELEMETRY_PROFILE = 0x23
    GET_BACKEND_INFO = 0x24
    GET_TELEMETRY_PROFILE = 0x25
    SET_OPEN_LOOP_CONFIG = 0x26
    GET_OPEN_LOOP_CONFIG = 0x27
    START_OPEN_LOOP = 0x28
    GET_BUILD_CONFIG = 0x29
    SET_OPEN_LOOP_CONFIG_PART = 0x2A
    COMMIT_OPEN_LOOP_CONFIG = 0x2B
    TELEMETRY = 0x80
    FAULT_EVENT = 0x81
    ACK = 0xF0
    ERROR = 0xF1


class ControlMode(IntEnum):
    TORQUE = 0
    SPEED = 1
    POSITION = 2
    OPEN_LOOP_SPEED = 3


class OpenLoopBackend(IntEnum):
    DIRECT_SINE = 0
    SIMPLEFOC = 1


class PidLoop(IntEnum):
    CURRENT = 0
    SPEED = 1
    POSITION = 2


class CalibrationType(IntEnum):
    ALL = 0
    CURRENT_OFFSET = 1
    ENCODER_OFFSET = 2
    ENCODER_DIRECTION = 3
    ZERO_POSITION = 4


class StopReason(IntEnum):
    NONE = 0
    DISABLE_COMMAND = 1
    CONTROLLED_COMMAND = 2
    QUICK_STOP_COMMAND = 3
    EMERGENCY_COMMAND = 4
    HEARTBEAT_TIMEOUT = 5
    OPEN_LOOP_RUNTIME = 6
    FAULT = 7


MODE_LABELS = {
    ControlMode.TORQUE: "转矩",
    ControlMode.SPEED: "速度",
    ControlMode.POSITION: "位置",
    ControlMode.OPEN_LOOP_SPEED: "开环速度",
}

OPEN_LOOP_BACKEND_LABELS = {
    OpenLoopBackend.DIRECT_SINE: "直接三相正弦",
    OpenLoopBackend.SIMPLEFOC: "SimpleFOC 开环",
}

PID_LOOP_LABELS = {
    PidLoop.CURRENT: "电流环",
    PidLoop.SPEED: "速度环",
    PidLoop.POSITION: "位置环",
}


class _ValueObject:
    """兼容 Python 3.6 的轻量值对象基类。"""

    __slots__ = ()

    def __repr__(self):
        values = ", ".join(
            "{}={!r}".format(name, getattr(self, name)) for name in self.__slots__
        )
        return "{}({})".format(type(self).__name__, values)

    def __eq__(self, other):
        return type(self) is type(other) and all(
            getattr(self, name) == getattr(other, name) for name in self.__slots__
        )


class Frame(_ValueObject):
    __slots__ = (
        "device_id",
        "command",
        "sequence",
        "payload",
        "flags",
        "version",
    )

    def __init__(
        self,
        device_id,
        command,
        sequence,
        payload=b"",
        flags=0,
        version=VERSION,
    ):
        self.device_id = device_id
        self.command = command
        self.sequence = sequence
        self.payload = payload
        self.flags = flags
        self.version = version


class Telemetry(_ValueObject):
    __slots__ = (
        "motor_id",
        "speed_rpm",
        "current_a",
        "voltage_v",
        "temperature_c",
        "position_deg",
        "status",
    )

    def __init__(
        self,
        motor_id,
        speed_rpm,
        current_a,
        voltage_v,
        temperature_c,
        position_deg,
        status,
    ):
        self.motor_id = motor_id
        self.speed_rpm = speed_rpm
        self.current_a = current_a
        self.voltage_v = voltage_v
        self.temperature_c = temperature_c
        self.position_deg = position_deg
        self.status = status


class OpenLoopConfig(_ValueObject):
    __slots__ = (
        "motor_id",
        "backend",
        "pole_pairs",
        "flags",
        "bus_voltage_v",
        "voltage_limit_v",
        "target_velocity_rad_s",
        "acceleration_rad_s2",
        "update_period_ms",
        "startup_delay_ms",
        "max_runtime_ms",
    )

    def __init__(
        self,
        motor_id,
        backend,
        pole_pairs,
        flags,
        bus_voltage_v,
        voltage_limit_v,
        target_velocity_rad_s,
        acceleration_rad_s2,
        update_period_ms,
        startup_delay_ms,
        max_runtime_ms,
    ):
        self.motor_id = int(motor_id)
        self.backend = OpenLoopBackend(backend)
        self.pole_pairs = int(pole_pairs)
        self.flags = int(flags)
        self.bus_voltage_v = float(bus_voltage_v)
        self.voltage_limit_v = float(voltage_limit_v)
        self.target_velocity_rad_s = float(target_velocity_rad_s)
        self.acceleration_rad_s2 = float(acceleration_rad_s2)
        self.update_period_ms = int(update_period_ms)
        self.startup_delay_ms = int(startup_delay_ms)
        self.max_runtime_ms = int(max_runtime_ms)


class Diagnostics(_ValueObject):
    __slots__ = (
        "uptime_ms",
        "protocol_errors",
        "fault_bits",
        "commands_received",
        "heartbeat_age_ms",
        "heartbeat_lease_ms",
        "motor_state",
        "last_stop_reason",
        "runtime_flags",
        "hardware_flags",
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

    def __init__(
        self,
        uptime_ms,
        protocol_errors,
        fault_bits,
        commands_received=0,
        heartbeat_age_ms=0xFFFF,
        heartbeat_lease_ms=0,
        motor_state=0,
        last_stop_reason=0,
        runtime_flags=0,
        hardware_flags=0,
        tx_high_priority_failures=0,
        telemetry_drops=0,
        rx_sw_fifo_overflows=0,
        rx_hw_fifo_overflows=0,
        rx_frame_errors=0,
        rx_parity_errors=0,
        parser_crc_errors=0,
        parser_length_errors=0,
        parser_timeout_errors=0,
        parser_resync_events=0,
        rx_isr_entries=0,
        rx_poll_drains=0,
        rx_poll_bytes=0,
    ):
        self.uptime_ms = int(uptime_ms)
        self.protocol_errors = int(protocol_errors)
        self.fault_bits = int(fault_bits)
        self.commands_received = int(commands_received)
        self.heartbeat_age_ms = int(heartbeat_age_ms)
        self.heartbeat_lease_ms = int(heartbeat_lease_ms)
        self.motor_state = int(motor_state)
        self.last_stop_reason = int(last_stop_reason)
        self.runtime_flags = int(runtime_flags)
        self.hardware_flags = int(hardware_flags)
        self.tx_high_priority_failures = int(
            tx_high_priority_failures
        )
        self.telemetry_drops = int(telemetry_drops)
        self.rx_sw_fifo_overflows = int(rx_sw_fifo_overflows)
        self.rx_hw_fifo_overflows = int(rx_hw_fifo_overflows)
        self.rx_frame_errors = int(rx_frame_errors)
        self.rx_parity_errors = int(rx_parity_errors)
        self.parser_crc_errors = int(parser_crc_errors)
        self.parser_length_errors = int(parser_length_errors)
        self.parser_timeout_errors = int(parser_timeout_errors)
        self.parser_resync_events = int(parser_resync_events)
        self.rx_isr_entries = int(rx_isr_entries)
        self.rx_poll_drains = int(rx_poll_drains)
        self.rx_poll_bytes = int(rx_poll_bytes)


TELEMETRY_STRUCT = struct.Struct("<BfffffH")
LIMITS_STRUCT = struct.Struct("<Bffffffff")
TELEMETRY_PROFILE_STRUCT = struct.Struct("<HI")
OPEN_LOOP_CONFIG_STRUCT = struct.Struct("<BBBBffffHHI")
OPEN_LOOP_CONFIG_FRAGMENT_STRUCT = struct.Struct("<BBB2s")
OPEN_LOOP_CONFIG_COMMIT_STRUCT = struct.Struct("<BBH")
OPEN_LOOP_CONFIG_FRAGMENT_SIZE = 2
OPEN_LOOP_CONFIG_FRAGMENT_COUNT = 14
LEGACY_BUILD_CONFIG_STRUCT = struct.Struct("<BBBBIIIIHHHHf")
LAYERED_BUILD_CONFIG_STRUCT = struct.Struct("<BBBBBIIIIHHHHf")
BUILD_CONFIG_STRUCT = struct.Struct("<BBBBBIIIIHHHHfI")
LEGACY_DIAGNOSTICS_STRUCT = struct.Struct("<IHH")
DIAGNOSTICS_FORMAT = "<IHHIHHBBBBHH"
DIAGNOSTICS_STRUCT = struct.Struct(DIAGNOSTICS_FORMAT)
UART_DIAGNOSTICS_STRUCT = struct.Struct(
    DIAGNOSTICS_FORMAT + "HHHH"
)
EXTENDED_DIAGNOSTICS_STRUCT = struct.Struct(
    DIAGNOSTICS_FORMAT + "HHHHHHHH"
)
RX_SCHEDULER_DIAGNOSTICS_STRUCT = struct.Struct(
    DIAGNOSTICS_FORMAT + "HHHHHHHHHHH"
)


def crc16_modbus(data: Union[bytes, bytearray, memoryview]) -> int:
    """计算 CRC16/MODBUS。"""

    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def encode_frame(frame: Frame) -> bytes:
    """将 :class:`Frame` 编码为线上的字节序列。"""

    payload = bytes(frame.payload)
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"载荷过长：{len(payload)} > {MAX_PAYLOAD}")
    for name, value in (
        ("version", frame.version),
        ("flags", frame.flags),
        ("device_id", frame.device_id),
        ("command", frame.command),
        ("sequence", frame.sequence),
    ):
        if not 0 <= int(value) <= 0xFF:
            raise ValueError(f"{name} 必须在 0..255 范围内")

    header = HEADER_STRUCT.pack(
        SOF,
        int(frame.version),
        int(frame.flags),
        int(frame.device_id),
        int(frame.command),
        int(frame.sequence),
        len(payload),
    )
    crc = crc16_modbus(header[2:] + payload)
    return header + payload + struct.pack("<H", crc)


class FrameParser:
    """可增量喂入的帧解析器，支持拆包、粘包和错误后重新同步。"""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.crc_errors = 0
        self.length_errors = 0
        self.discarded_bytes = 0

    def reset(self) -> None:
        self._buffer.clear()
        self.crc_errors = 0
        self.length_errors = 0
        self.discarded_bytes = 0

    def feed(self, data: Union[bytes, bytearray, memoryview]) -> List[Frame]:
        if data:
            self._buffer.extend(data)
        frames = []  # type: List[Frame]

        while True:
            sof_index = self._buffer.find(SOF)
            if sof_index < 0:
                keep = 1 if self._buffer.endswith(SOF[:1]) else 0
                discarded = len(self._buffer) - keep
                if discarded:
                    del self._buffer[:discarded]
                    self.discarded_bytes += discarded
                break
            if sof_index:
                del self._buffer[:sof_index]
                self.discarded_bytes += sof_index
            if len(self._buffer) < HEADER_SIZE:
                break

            (
                _,
                version,
                flags,
                device_id,
                command,
                sequence,
                payload_length,
            ) = HEADER_STRUCT.unpack_from(self._buffer)
            if payload_length > MAX_PAYLOAD:
                del self._buffer[0]
                self.length_errors += 1
                continue

            frame_length = HEADER_SIZE + payload_length + CRC_SIZE
            if len(self._buffer) < frame_length:
                break

            packet = bytes(self._buffer[:frame_length])
            expected_crc = struct.unpack_from("<H", packet, frame_length - CRC_SIZE)[0]
            actual_crc = crc16_modbus(packet[2:-CRC_SIZE])
            if actual_crc != expected_crc:
                del self._buffer[0]
                self.crc_errors += 1
                continue

            payload = packet[HEADER_SIZE:-CRC_SIZE]
            frames.append(
                Frame(
                    device_id=device_id,
                    command=command,
                    sequence=sequence,
                    payload=payload,
                    flags=flags,
                    version=version,
                )
            )
            del self._buffer[:frame_length]
        return frames


def pack_enable(motor_id: int, enabled: bool) -> bytes:
    return struct.pack("<BB", motor_id, int(enabled))


def unpack_enable(payload: bytes) -> Tuple[int, bool]:
    motor_id, enabled = struct.unpack("<BB", payload)
    return motor_id, bool(enabled)


def pack_mode(motor_id: int, mode: Union[ControlMode, int]) -> bytes:
    return struct.pack("<BB", motor_id, int(mode))


def pack_target(
    motor_id: int, mode: Union[ControlMode, int], target: float
) -> bytes:
    return struct.pack("<BBf", motor_id, int(mode), float(target))


def unpack_target(payload: bytes) -> Tuple[int, ControlMode, float]:
    motor_id, mode, target = struct.unpack("<BBf", payload)
    return motor_id, ControlMode(mode), target


def pack_pid(
    motor_id: int,
    loop: Union[PidLoop, int],
    kp: float,
    ki: float,
    kd: float,
) -> bytes:
    return struct.pack("<BBfff", motor_id, int(loop), float(kp), float(ki), float(kd))


def unpack_pid(payload: bytes) -> Tuple[int, PidLoop, float, float, float]:
    motor_id, loop, kp, ki, kd = struct.unpack("<BBfff", payload)
    return motor_id, PidLoop(loop), kp, ki, kd


def pack_heartbeat(host_time_ms: int, lease_ms: int = 750) -> bytes:
    if not 300 <= lease_ms <= 5000:
        raise ValueError("心跳租约必须在 300..5000 ms 范围内")
    return struct.pack("<IH", int(host_time_ms) & 0xFFFFFFFF, int(lease_ms))


def pack_start_open_loop(
    motor_id: int,
    power_stage_enabled: bool = False,
    power_stage_confirmed: bool = False,
) -> bytes:
    if not 1 <= int(motor_id) <= 0xFF:
        raise ValueError("电机地址必须在 1..255 范围内")
    if not power_stage_enabled:
        return bytes((int(motor_id),))
    if not power_stage_confirmed:
        raise ValueError("真实功率级启动必须经过明确确认")
    return bytes(
        (
            int(motor_id),
            START_FLAG_POWER_STAGE_CONFIRMED,
        )
    )


def pack_calibrate(
    motor_id: int, calibration_type: Union[CalibrationType, int]
) -> bytes:
    return struct.pack("<BB", motor_id, int(calibration_type))


def pack_limits(
    motor_id: int,
    current_limit_a: float,
    torque_limit_nm: float,
    speed_limit_rad_s: float,
    position_min_rad: float,
    position_max_rad: float,
    bus_voltage_min_v: float,
    bus_voltage_max_v: float,
    temperature_max_c: float,
) -> bytes:
    return LIMITS_STRUCT.pack(
        motor_id,
        float(current_limit_a),
        float(torque_limit_nm),
        float(speed_limit_rad_s),
        float(position_min_rad),
        float(position_max_rad),
        float(bus_voltage_min_v),
        float(bus_voltage_max_v),
        float(temperature_max_c),
    )


def unpack_limits(
    payload: bytes,
) -> Tuple[int, float, float, float, float, float, float, float, float]:
    if len(payload) != LIMITS_STRUCT.size:
        raise ValueError(
            f"限值载荷长度错误：应为 {LIMITS_STRUCT.size}，实际为 {len(payload)}"
        )
    return LIMITS_STRUCT.unpack(payload)


def pack_telemetry_profile(rate_hz: int, signal_mask: int = 0x1F) -> bytes:
    if not 1 <= int(rate_hz) <= 1000:
        raise ValueError("遥测频率必须在 1..1000 Hz 范围内")
    if not 0 <= int(signal_mask) <= 0xFFFFFFFF:
        raise ValueError("遥测信号掩码必须在 0..0xFFFFFFFF 范围内")
    return TELEMETRY_PROFILE_STRUCT.pack(int(rate_hz), int(signal_mask))


def unpack_telemetry_profile(payload: bytes) -> Tuple[int, int]:
    if len(payload) != TELEMETRY_PROFILE_STRUCT.size:
        raise ValueError(
            "遥测配置载荷长度错误：应为 {}，实际为 {}".format(
                TELEMETRY_PROFILE_STRUCT.size,
                len(payload),
            )
        )
    return TELEMETRY_PROFILE_STRUCT.unpack(payload)


def pack_open_loop_config(value: OpenLoopConfig) -> bytes:
    numeric_values = (
        value.bus_voltage_v,
        value.voltage_limit_v,
        value.target_velocity_rad_s,
        value.acceleration_rad_s2,
    )
    if not all(math.isfinite(item) for item in numeric_values):
        raise ValueError("开环参数不能包含无穷大或 NaN")
    if not 1 <= value.motor_id <= 0xFF:
        raise ValueError("电机地址必须在 1..255 范围内")
    if not 1 <= value.pole_pairs <= 64:
        raise ValueError("极对数必须在 1..64 范围内")
    if not 0 <= value.flags <= 0xFF:
        raise ValueError("开环标志必须在 0..255 范围内")
    if value.bus_voltage_v <= 0.0:
        raise ValueError("母线电压必须大于 0 V")
    if (
        value.voltage_limit_v <= 0.0
        or value.voltage_limit_v > value.bus_voltage_v
    ):
        raise ValueError("电压限幅必须大于 0 V 且不高于母线电压")
    if abs(value.target_velocity_rad_s) > 1000.0:
        raise ValueError("开环目标速度绝对值不能超过 1000 rad/s")
    if not 0.01 <= value.acceleration_rad_s2 <= 10000.0:
        raise ValueError("加速度必须在 0.01..10000 rad/s² 范围内")
    if not 1 <= value.update_period_ms <= 100:
        raise ValueError("更新周期必须在 1..100 ms 范围内")
    if not 0 <= value.startup_delay_ms <= 5000:
        raise ValueError("启动延时必须在 0..5000 ms 范围内")
    if not 1000 <= value.max_runtime_ms <= 600000:
        raise ValueError("最长运行时间必须在 1000..600000 ms 范围内")
    return OPEN_LOOP_CONFIG_STRUCT.pack(
        value.motor_id,
        int(value.backend),
        value.pole_pairs,
        value.flags,
        value.bus_voltage_v,
        value.voltage_limit_v,
        value.target_velocity_rad_s,
        value.acceleration_rad_s2,
        value.update_period_ms,
        value.startup_delay_ms,
        value.max_runtime_ms,
    )


def unpack_open_loop_config(payload: bytes) -> OpenLoopConfig:
    if len(payload) != OPEN_LOOP_CONFIG_STRUCT.size:
        raise ValueError(
            "开环配置载荷长度错误：应为 {}，实际为 {}".format(
                OPEN_LOOP_CONFIG_STRUCT.size,
                len(payload),
            )
        )
    return OpenLoopConfig(*OPEN_LOOP_CONFIG_STRUCT.unpack(payload))


def pack_open_loop_config_fragments(
    value: OpenLoopConfig,
    generation: int,
) -> Tuple[bytes, ...]:
    if not 0 <= int(generation) <= 0xFF:
        raise ValueError("开环配置传输代号必须在 0..255 范围内")
    raw = pack_open_loop_config(value)
    if len(raw) != (
        OPEN_LOOP_CONFIG_FRAGMENT_SIZE *
        OPEN_LOOP_CONFIG_FRAGMENT_COUNT
    ):
        raise ValueError("开环配置分片布局不匹配")
    return tuple(
        OPEN_LOOP_CONFIG_FRAGMENT_STRUCT.pack(
            value.motor_id,
            int(generation),
            index,
            raw[
                index * OPEN_LOOP_CONFIG_FRAGMENT_SIZE:
                (index + 1) * OPEN_LOOP_CONFIG_FRAGMENT_SIZE
            ],
        )
        for index in range(OPEN_LOOP_CONFIG_FRAGMENT_COUNT)
    )


def unpack_open_loop_config_fragment(
    payload: bytes,
) -> Tuple[int, int, int, bytes]:
    if len(payload) != OPEN_LOOP_CONFIG_FRAGMENT_STRUCT.size:
        raise ValueError("开环配置分片载荷长度错误")
    motor_id, generation, index, data = (
        OPEN_LOOP_CONFIG_FRAGMENT_STRUCT.unpack(payload)
    )
    if index >= OPEN_LOOP_CONFIG_FRAGMENT_COUNT:
        raise ValueError("开环配置分片索引超出范围")
    return motor_id, generation, index, data


def pack_open_loop_config_commit(
    value: OpenLoopConfig,
    generation: int,
) -> bytes:
    raw = pack_open_loop_config(value)
    return OPEN_LOOP_CONFIG_COMMIT_STRUCT.pack(
        value.motor_id,
        int(generation),
        crc16_modbus(raw),
    )


def unpack_open_loop_config_commit(
    payload: bytes,
) -> Tuple[int, int, int]:
    if len(payload) != OPEN_LOOP_CONFIG_COMMIT_STRUCT.size:
        raise ValueError("开环配置提交载荷长度错误")
    return OPEN_LOOP_CONFIG_COMMIT_STRUCT.unpack(payload)


def unpack_diagnostics(payload: bytes) -> Diagnostics:
    if len(payload) == LEGACY_DIAGNOSTICS_STRUCT.size:
        return Diagnostics(*LEGACY_DIAGNOSTICS_STRUCT.unpack(payload))
    accepted_sizes = (
        DIAGNOSTICS_STRUCT.size,
        UART_DIAGNOSTICS_STRUCT.size,
        EXTENDED_DIAGNOSTICS_STRUCT.size,
        RX_SCHEDULER_DIAGNOSTICS_STRUCT.size,
    )
    if len(payload) not in accepted_sizes:
        raise ValueError(
            "诊断载荷长度错误：应为 {}、{}、{}、{} 或 {}，实际为 {}".format(
                LEGACY_DIAGNOSTICS_STRUCT.size,
                DIAGNOSTICS_STRUCT.size,
                UART_DIAGNOSTICS_STRUCT.size,
                EXTENDED_DIAGNOSTICS_STRUCT.size,
                RX_SCHEDULER_DIAGNOSTICS_STRUCT.size,
                len(payload),
            )
        )
    if len(payload) == DIAGNOSTICS_STRUCT.size:
        values = DIAGNOSTICS_STRUCT.unpack(payload)
    elif len(payload) == UART_DIAGNOSTICS_STRUCT.size:
        values = UART_DIAGNOSTICS_STRUCT.unpack(payload)
    elif len(payload) == EXTENDED_DIAGNOSTICS_STRUCT.size:
        values = EXTENDED_DIAGNOSTICS_STRUCT.unpack(payload)
    else:
        values = RX_SCHEDULER_DIAGNOSTICS_STRUCT.unpack(payload)
    extended = list(values[12:])
    extended.extend([0] * (11 - len(extended)))
    return Diagnostics(
        values[0],
        values[1],
        values[2],
        values[3],
        values[4],
        values[5],
        values[6],
        values[7],
        values[8],
        values[9],
        values[10],
        values[11],
        *extended,
    )


def unpack_build_config(
    payload: bytes,
) -> Tuple[
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    float,
    int,
]:
    if len(payload) == LEGACY_BUILD_CONFIG_STRUCT.size:
        legacy = LEGACY_BUILD_CONFIG_STRUCT.unpack(payload)
        (
            device_id,
            real_hardware_enabled,
            simplefoc_enabled,
            default_pole_pairs,
            adc_hz,
            pwm_hz,
            isr_hz,
            outer_hz,
            telemetry_hz,
            heartbeat_default_ms,
            heartbeat_min_ms,
            heartbeat_max_ms,
            torque_constant,
        ) = legacy
        return (
            device_id,
            real_hardware_enabled,
            real_hardware_enabled,
            simplefoc_enabled,
            default_pole_pairs,
            adc_hz,
            pwm_hz,
            isr_hz,
            outer_hz,
            telemetry_hz,
            heartbeat_default_ms,
            heartbeat_min_ms,
            heartbeat_max_ms,
            torque_constant,
            0,
        )
    if len(payload) == LAYERED_BUILD_CONFIG_STRUCT.size:
        return LAYERED_BUILD_CONFIG_STRUCT.unpack(payload) + (0,)
    if len(payload) != BUILD_CONFIG_STRUCT.size:
        raise ValueError(
            "固件构建配置载荷长度错误：应为 {}（或兼容长度 {}、{}），实际为 {}".format(
                BUILD_CONFIG_STRUCT.size,
                LAYERED_BUILD_CONFIG_STRUCT.size,
                LEGACY_BUILD_CONFIG_STRUCT.size,
                len(payload),
            )
        )
    return BUILD_CONFIG_STRUCT.unpack(payload)


def pack_telemetry(value: Telemetry) -> bytes:
    return TELEMETRY_STRUCT.pack(
        value.motor_id,
        value.speed_rpm,
        value.current_a,
        value.voltage_v,
        value.temperature_c,
        value.position_deg,
        value.status,
    )


def unpack_telemetry(payload: bytes) -> Telemetry:
    if len(payload) != TELEMETRY_STRUCT.size:
        raise ValueError(
            f"遥测载荷长度错误：应为 {TELEMETRY_STRUCT.size}，实际为 {len(payload)}"
        )
    return Telemetry(*TELEMETRY_STRUCT.unpack(payload))


def bytes_to_hex(data: bytes, limit: Optional[int] = None) -> str:
    displayed = data if limit is None else data[:limit]
    text = " ".join(f"{value:02X}" for value in displayed)
    if limit is not None and len(data) > limit:
        text += f" ... (+{len(data) - limit} bytes)"
    return text


def hex_to_bytes(text: str) -> bytes:
    cleaned = "".join(text.replace(",", " ").split())
    if len(cleaned) % 2:
        raise ValueError("十六进制字符数必须为偶数")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError("只能输入 0-9、A-F 的十六进制字节") from exc


def iter_encoded(frames: Iterable[Frame]) -> bytes:
    return b"".join(encode_frame(frame) for frame in frames)
