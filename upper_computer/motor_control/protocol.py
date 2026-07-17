"""串口帧协议与常用电机控制载荷。

默认帧格式（小端）::

    AA 55 | VER | FLAGS | DEVICE | CMD | SEQ | LEN(2) | PAYLOAD | CRC16(2)

CRC16/MODBUS 的计算范围为 ``VER`` 到 ``PAYLOAD``，不包含帧头和 CRC。
实际控制器协议不一致时，只需要替换本模块，界面和通信线程无需改动。
"""

from enum import IntEnum
import struct
from typing import Iterable, List, Optional, Tuple, Union


SOF = b"\xAA\x55"
VERSION = 0x02
HEADER_STRUCT = struct.Struct("<2sBBBBBH")
HEADER_SIZE = HEADER_STRUCT.size
CRC_SIZE = 2
MAX_PAYLOAD = 2048


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
    TELEMETRY = 0x80
    FAULT_EVENT = 0x81
    ACK = 0xF0
    ERROR = 0xF1


class ControlMode(IntEnum):
    TORQUE = 0
    SPEED = 1
    POSITION = 2


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


MODE_LABELS = {
    ControlMode.TORQUE: "转矩",
    ControlMode.SPEED: "速度",
    ControlMode.POSITION: "位置",
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


TELEMETRY_STRUCT = struct.Struct("<BfffffH")
LIMITS_STRUCT = struct.Struct("<Bffffffff")
TELEMETRY_PROFILE_STRUCT = struct.Struct("<HI")


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
