"""实时信号缓存、告警和 CSV 记录。"""

from collections import deque
import csv
from pathlib import Path
import threading
import time
from typing import Deque, Dict, Iterable, List, Optional, TextIO, Tuple, Union

from .protocol import Telemetry


class SignalDefinition:
    __slots__ = ("key_suffix", "label", "unit")

    def __init__(self, key_suffix, label, unit):
        self.key_suffix = key_suffix
        self.label = label
        self.unit = unit


SIGNAL_DEFINITIONS = (
    SignalDefinition("speed", "转速", "rpm"),
    SignalDefinition("current", "电流", "A"),
    SignalDefinition("voltage", "母线电压", "V"),
    SignalDefinition("temperature", "温度", "°C"),
    SignalDefinition("position", "位置", "°"),
)

SIGNAL_COLORS = (
    "#55C2FF",
    "#FFB454",
    "#5EE6A8",
    "#FF6B8A",
    "#B99CFF",
    "#F7E36D",
    "#61D8D6",
    "#FF8F5E",
    "#8AD66D",
    "#D784FF",
    "#5E9EFF",
    "#E7A65C",
)


class HistoryStore:
    """保存最近一段时间的电机信号。"""

    def __init__(self, motor_count: int = 1, retention_seconds: float = 120.0) -> None:
        self.motor_count = motor_count
        self.retention_seconds = retention_seconds
        self._points = {}  # type: Dict[str, Deque[Tuple[float, float]]]
        self._latest = {}  # type: Dict[str, float]
        self._definitions = {}  # type: Dict[str, Tuple[str, str, str]]
        self._build_definitions()

    def _build_definitions(self) -> None:
        color_index = 0
        for motor_id in range(1, self.motor_count + 1):
            for definition in SIGNAL_DEFINITIONS:
                key = f"m{motor_id}.{definition.key_suffix}"
                color = SIGNAL_COLORS[color_index % len(SIGNAL_COLORS)]
                color_index += 1
                self._points[key] = deque()
                self._definitions[key] = (
                    f"M{motor_id} {definition.label}",
                    definition.unit,
                    color,
                )

    @property
    def keys(self) -> Tuple[str, ...]:
        return tuple(self._points)

    def definition(self, key: str) -> Tuple[str, str, str]:
        return self._definitions[key]

    def latest(self, key: str) -> Optional[float]:
        return self._latest.get(key)

    def points(self, key: str, since: float) -> List[Tuple[float, float]]:
        values = self._points.get(key)
        if not values:
            return []
        return [(stamp, value) for stamp, value in values if stamp >= since]

    def append_telemetry(
        self, telemetry: Telemetry, stamp: Optional[float] = None
    ) -> None:
        if not 1 <= telemetry.motor_id <= self.motor_count:
            return
        now = time.monotonic() if stamp is None else stamp
        values = {
            "speed": telemetry.speed_rpm,
            "current": telemetry.current_a,
            "voltage": telemetry.voltage_v,
            "temperature": telemetry.temperature_c,
            "position": telemetry.position_deg,
        }
        cutoff = now - self.retention_seconds
        for suffix, value in values.items():
            key = f"m{telemetry.motor_id}.{suffix}"
            series = self._points[key]
            series.append((now, float(value)))
            self._latest[key] = float(value)
            while series and series[0][0] < cutoff:
                series.popleft()

    def clear(self, keys: Optional[Iterable[str]] = None) -> None:
        selected = self._points.keys() if keys is None else keys
        for key in selected:
            if key in self._points:
                self._points[key].clear()
                self._latest.pop(key, None)

    def export_rows(self) -> List[Tuple[float, str, float]]:
        rows = []  # type: List[Tuple[float, str, float]]
        for key, points in self._points.items():
            rows.extend((stamp, key, value) for stamp, value in points)
        rows.sort(key=lambda row: row[0])
        return rows


class CsvRecorder:
    """将解码后的遥测记录为宽表 CSV。"""

    HEADER = (
        "local_time",
        "elapsed_s",
        "motor_id",
        "speed_rpm",
        "current_a",
        "voltage_v",
        "temperature_c",
        "position_deg",
        "status",
    )

    def __init__(self) -> None:
        self._file = None  # type: Optional[TextIO]
        self._writer = None
        self._start = 0.0
        self._lock = threading.Lock()
        self.path = None  # type: Optional[Path]

    @property
    def active(self) -> bool:
        return self._file is not None

    def start(self, path: Union[str, Path]) -> None:
        self.stop()
        selected = Path(path)
        selected.parent.mkdir(parents=True, exist_ok=True)
        file = selected.open("w", newline="", encoding="utf-8-sig")
        writer = csv.writer(file)
        writer.writerow(self.HEADER)
        self._file = file
        self._writer = writer
        self._start = time.monotonic()
        self.path = selected

    def write(self, telemetry: Telemetry) -> None:
        with self._lock:
            if self._file is None or self._writer is None:
                return
            now = time.time()
            elapsed = time.monotonic() - self._start
            local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
            millis = int((now % 1) * 1000)
            self._writer.writerow(
                (
                    f"{local_time}.{millis:03d}",
                    f"{elapsed:.6f}",
                    telemetry.motor_id,
                    f"{telemetry.speed_rpm:.6f}",
                    f"{telemetry.current_a:.6f}",
                    f"{telemetry.voltage_v:.6f}",
                    f"{telemetry.temperature_c:.6f}",
                    f"{telemetry.position_deg:.6f}",
                    telemetry.status,
                )
            )

    def stop(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.flush()
                self._file.close()
            self._file = None
            self._writer = None


class Alarm:
    __slots__ = ("motor_id", "level", "message")

    def __init__(self, motor_id, level, message):
        self.motor_id = motor_id
        self.level = level
        self.message = message


class AlarmMonitor:
    """基础安全阈值监控，返回新出现或已恢复的告警。"""

    def __init__(
        self,
        max_current_a: float = 0.3,
        max_temperature_c: float = 80.0,
        min_voltage_v: float = 5.0,
        max_voltage_v: float = 8.0,
    ) -> None:
        self.max_current_a = max_current_a
        self.max_temperature_c = max_temperature_c
        self.min_voltage_v = min_voltage_v
        self.max_voltage_v = max_voltage_v
        self._active = {}  # type: Dict[Tuple[int, str], Alarm]

    @property
    def active(self) -> Tuple[Alarm, ...]:
        return tuple(self._active.values())

    def configure(
        self,
        max_current_a: float,
        max_temperature_c: float,
        min_voltage_v: float,
        max_voltage_v: float,
    ) -> None:
        self.max_current_a = float(max_current_a)
        self.max_temperature_c = float(max_temperature_c)
        self.min_voltage_v = float(min_voltage_v)
        self.max_voltage_v = float(max_voltage_v)

    def clear(self) -> None:
        self._active.clear()

    def evaluate(self, value: Telemetry) -> Tuple[List[Alarm], List[Alarm]]:
        candidates = {}  # type: Dict[str, Alarm]
        if abs(value.current_a) > self.max_current_a:
            candidates["current"] = Alarm(
                value.motor_id, "critical", f"M{value.motor_id} 过流：{value.current_a:.2f} A"
            )
        if value.temperature_c > self.max_temperature_c:
            candidates["temperature"] = Alarm(
                value.motor_id,
                "critical",
                f"M{value.motor_id} 过温：{value.temperature_c:.1f} °C",
            )
        if not self.min_voltage_v <= value.voltage_v <= self.max_voltage_v:
            candidates["voltage"] = Alarm(
                value.motor_id,
                "warning",
                f"M{value.motor_id} 电压异常：{value.voltage_v:.2f} V",
            )
        if value.status & ((1 << 2) | (1 << 3)):
            candidates["status"] = Alarm(
                value.motor_id,
                "critical",
                f"M{value.motor_id} 故障/急停状态：0x{value.status:04X}",
            )

        raised = []  # type: List[Alarm]
        cleared = []  # type: List[Alarm]
        types = {"current", "temperature", "voltage", "status"}
        for alarm_type in types:
            key = (value.motor_id, alarm_type)
            candidate = candidates.get(alarm_type)
            previous = self._active.get(key)
            if candidate is not None and previous is None:
                self._active[key] = candidate
                raised.append(candidate)
            elif candidate is not None:
                self._active[key] = candidate
            elif previous is not None:
                cleared.append(previous)
                del self._active[key]
        return raised, cleared
