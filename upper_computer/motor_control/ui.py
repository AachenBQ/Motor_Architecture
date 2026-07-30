"""Motor Studio 桌面界面。"""

import csv
from datetime import datetime
import math
from pathlib import Path
import struct
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from .codex_bridge import BridgeRequestError, CodexBridge
from .data import AlarmMonitor, CsvRecorder, HistoryStore
from .protocol import (
    CalibrationType,
    Command,
    ControlMode,
    FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG,
    Frame,
    FrameParser,
    HARDWARE_FLAG_COMMISSIONING_OVERRIDE,
    HARDWARE_FLAG_GATE_ENABLED,
    HARDWARE_FLAG_NFAULT_CLEAR,
    HARDWARE_FLAG_POWER_STAGE_BUILD,
    HARDWARE_FLAG_PWM_ENABLED,
    HARDWARE_FLAG_SAFETY_READY,
    MODE_LABELS,
    OPEN_LOOP_BACKEND_LABELS,
    OpenLoopBackend,
    OpenLoopConfig,
    PID_LOOP_LABELS,
    PidLoop,
    POWER_STAGE_COMMISSIONING_MAX_ACCEL_RAD_S2,
    POWER_STAGE_COMMISSIONING_MAX_RUNTIME_MS,
    POWER_STAGE_COMMISSIONING_MAX_SPEED_RAD_S,
    POWER_STAGE_COMMISSIONING_MAX_VOLTAGE_V,
    POWER_STAGE_COMMISSIONING_OVERRIDE,
    POWER_STAGE_REQUIRED_SAFETY_MASK,
    bytes_to_hex,
    encode_frame,
    hex_to_bytes,
    pack_calibrate,
    pack_enable,
    pack_heartbeat,
    pack_limits,
    pack_mode,
    pack_open_loop_config_commit,
    pack_open_loop_config,
    pack_open_loop_config_fragments,
    pack_pid,
    pack_target,
    pack_start_open_loop,
    pack_telemetry_profile,
    unpack_limits,
    unpack_build_config,
    unpack_diagnostics,
    unpack_open_loop_config,
    unpack_telemetry_profile,
    unpack_telemetry,
)
from .transport import ControllerLink, list_serial_ports


COLORS = {
    "bg": "#0C111B",
    "panel": "#121A27",
    "panel_alt": "#172131",
    "panel_hover": "#1E2B3E",
    "border": "#25344A",
    "text": "#E7EDF7",
    "muted": "#8A9AB2",
    "accent": "#2F9BFF",
    "accent_hover": "#55ADFF",
    "success": "#36D399",
    "warning": "#F6B94A",
    "danger": "#F05265",
    "grid": "#263448",
    "canvas": "#0B1018",
}


MODE_FROM_LABEL = {label: mode for mode, label in MODE_LABELS.items()}
OPEN_LOOP_BACKEND_FROM_LABEL = {
    label: backend for backend, label in OPEN_LOOP_BACKEND_LABELS.items()
}
PID_LOOP_FROM_LABEL = {label: loop for loop, label in PID_LOOP_LABELS.items()}
PID_DEFAULT_VALUES = {
    PidLoop.CURRENT: (0.80, 0.12, 0.01),
    PidLoop.SPEED: (0.50, 0.05, 0.00),
    PidLoop.POSITION: (2.00, 0.00, 0.02),
}
OPEN_LOOP_FRAGMENT_ACK_TIMEOUT_MS = 400
OPEN_LOOP_FRAGMENT_MAX_ATTEMPTS = 3

STOP_REASON_LABELS = {
    0: "无",
    1: "失能命令",
    2: "受控停止",
    3: "快速停止",
    4: "紧急停止",
    5: "心跳超时",
    6: "开环运行到期",
    7: "硬件或软件故障",
}


class WaveformPlot(ttk.Frame):
    """一个可独立配置的实时波形窗口。"""

    def __init__(
        self,
        master: tk.Misc,
        history: HistoryStore,
        title: str,
        on_close: Callable[["WaveformPlot"], None],
        on_visibility_changed: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=0)
        self.history = history
        self.title = title
        self.visible_signals = set()  # type: Set[str]
        self.paused = False
        self._on_close = on_close
        self._on_visibility_changed = on_visibility_changed
        self.time_span = tk.StringVar(value="10 s")
        self.y_range = tk.StringVar(value="自动")
        self._build()

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 7))
        toolbar.pack(fill=tk.X)
        self.title_label = ttk.Label(
            toolbar, text=self.title, style="PlotTitle.TLabel"
        )
        self.title_label.pack(side=tk.LEFT)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=12, pady=2
        )
        ttk.Label(toolbar, text="时间窗", style="Muted.TLabel").pack(side=tk.LEFT)
        time_combo = ttk.Combobox(
            toolbar,
            textvariable=self.time_span,
            values=("5 s", "10 s", "30 s", "60 s"),
            state="readonly",
            width=6,
        )
        time_combo.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(toolbar, text="Y 轴", style="Muted.TLabel").pack(side=tk.LEFT)
        range_combo = ttk.Combobox(
            toolbar,
            textvariable=self.y_range,
            values=("自动", "±10", "±100", "±1000", "±5000"),
            state="readonly",
            width=7,
        )
        range_combo.pack(side=tk.LEFT, padx=(6, 12))
        self.pause_button = ttk.Button(
            toolbar, text="暂停", width=7, command=self.toggle_pause
        )
        self.pause_button.pack(side=tk.LEFT)
        ttk.Button(
            toolbar,
            text="关闭窗口",
            width=9,
            style="Quiet.TButton",
            command=lambda: self._on_close(self),
        ).pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(
            self,
            background=COLORS["canvas"],
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.configure(text="继续" if self.paused else "暂停")

    def set_title(self, title: str) -> None:
        self.title = title
        self.title_label.configure(text=title)

    def set_visible(self, keys: Set[str]) -> None:
        self.visible_signals = set(keys)
        self._on_visibility_changed()

    def render(self, now: float) -> None:
        if self.paused:
            return
        canvas = self.canvas
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 120 or height < 100:
            return
        canvas.delete("all")

        left, top, right, bottom = 62, 28, 18, 36
        plot_width = max(1, width - left - right)
        plot_height = max(1, height - top - bottom)
        span = float(self.time_span.get().split()[0])
        since = now - span

        # 网格与时间刻度
        for index in range(6):
            y = top + plot_height * index / 5
            canvas.create_line(
                left, y, width - right, y, fill=COLORS["grid"], width=1
            )
        for index in range(11):
            x = left + plot_width * index / 10
            canvas.create_line(
                x, top, x, height - bottom, fill=COLORS["grid"], width=1
            )
            seconds = -span + span * index / 10
            canvas.create_text(
                x,
                height - bottom + 17,
                text=f"{seconds:.0f}",
                fill=COLORS["muted"],
                font=("Microsoft YaHei UI", 8),
            )
        canvas.create_text(
            width - right,
            height - 7,
            text="时间 / s",
            anchor=tk.E,
            fill=COLORS["muted"],
            font=("Microsoft YaHei UI", 8),
        )

        series = {}  # type: Dict[str, List[Tuple[float, float]]]
        all_values = []  # type: List[float]
        for key in self.visible_signals:
            points = self.history.points(key, since)
            if points:
                series[key] = points
                all_values.extend(value for _, value in points)

        if not series:
            canvas.create_text(
                left + plot_width / 2,
                top + plot_height / 2,
                text="双击左侧信号以添加波形",
                fill=COLORS["muted"],
                font=("Microsoft YaHei UI", 13),
            )
            self._draw_y_labels(canvas, top, plot_height, -1.0, 1.0)
            return

        selected_range = self.y_range.get()
        if selected_range == "自动":
            minimum = min(all_values)
            maximum = max(all_values)
            if maximum - minimum < 1e-9:
                padding = max(1.0, abs(maximum) * 0.1)
            else:
                padding = (maximum - minimum) * 0.1
            y_min, y_max = minimum - padding, maximum + padding
        else:
            radius = float(selected_range.replace("±", ""))
            y_min, y_max = -radius, radius
        self._draw_y_labels(canvas, top, plot_height, y_min, y_max)

        for key in sorted(series):
            _, _, color = self.history.definition(key)
            points = series[key]
            step = max(1, len(points) // max(1, int(plot_width)))
            coordinates = []  # type: List[float]
            sampled = points[::step]
            if sampled[-1] != points[-1]:
                sampled.append(points[-1])
            for stamp, value in sampled:
                x = left + (stamp - since) / span * plot_width
                y = top + (y_max - value) / (y_max - y_min) * plot_height
                coordinates.extend((x, y))
            if len(coordinates) >= 4:
                canvas.create_line(
                    *coordinates,
                    fill=color,
                    width=2,
                    smooth=False,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                )

        self._draw_legend(canvas, left, width - right)

    @staticmethod
    def _draw_y_labels(
        canvas: tk.Canvas, top: int, plot_height: int, y_min: float, y_max: float
    ) -> None:
        for index in range(6):
            value = y_max - (y_max - y_min) * index / 5
            y = top + plot_height * index / 5
            canvas.create_text(
                54,
                y,
                text=f"{value:.4g}",
                anchor=tk.E,
                fill=COLORS["muted"],
                font=("Consolas", 8),
            )

    def _draw_legend(self, canvas: tk.Canvas, start: int, end: int) -> None:
        x = start
        y = 14
        for key in sorted(self.visible_signals):
            label, unit, color = self.history.definition(key)
            latest = self.history.latest(key)
            value_text = "--" if latest is None else f"{latest:.2f}"
            text = f"{label}  {value_text} {unit}"
            estimated_width = 14 + len(text) * 8
            if x + estimated_width > end:
                break
            canvas.create_line(x, y, x + 12, y, fill=color, width=3)
            canvas.create_text(
                x + 17,
                y,
                text=text,
                anchor=tk.W,
                fill=COLORS["text"],
                font=("Microsoft YaHei UI", 8),
            )
            x += estimated_width


class MotorStudioApp:
    """应用程序主控制器。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Motor Studio - TC375 单电机控制器")
        self.root.geometry("1480x900")
        self.root.minsize(1180, 720)
        self.root.configure(background=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.motor_count = 1
        self.heartbeat_lease_ms = 750
        self.history = HistoryStore(self.motor_count)
        self.link = ControllerLink()
        self.parser = FrameParser()
        self.recorder = CsvRecorder()
        self.alarms = AlarmMonitor()
        self.sequence = 0
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.rx_frames = 0
        self.plots = []  # type: List[WaveformPlot]
        self._last_parser_crc_errors = 0
        self._alarm_keys = set()  # type: Set[str]
        self._last_value_refresh = 0.0
        self._last_telemetry_at = 0.0
        self._connected_at = 0.0
        self._protocol_response_at = 0.0
        self._telemetry_watchdog_armed_at = 0.0
        self._no_response_reported = False
        self._no_telemetry_reported = False
        self._software_protection_latched = False
        self._shutdown_pending = False
        self._pending_open_loop_start = None  # type: Optional[OpenLoopConfig]
        self._open_loop_transfer = None  # type: Optional[Dict[str, Any]]
        self._open_loop_transfer_result = None  # type: Optional[Dict[str, Any]]
        self._open_loop_transfer_token = 0
        self._build_control_hardware_enabled = None  # type: Optional[bool]
        self._build_power_stage_enabled = None  # type: Optional[bool]
        self._build_simplefoc_enabled = None  # type: Optional[bool]
        self._build_safety_mask = None  # type: Optional[int]
        self._build_config_query_generation = 0
        self._build_config_query_attempt = 0
        self._build_config_query_started_at = 0.0
        self._device_firmware_version = None  # type: Optional[Tuple[int, int, int]]
        self._device_build_id = ""
        self._device_features = None  # type: Optional[int]
        self._latest_diagnostics = None  # type: Optional[Dict[str, Any]]
        self._device_open_loop_config = None  # type: Optional[OpenLoopConfig]
        self._codex_control_until = 0.0
        self._codex_transactions = {}  # type: Dict[int, Dict[str, Any]]
        self._codex_bridge = None  # type: Optional[CodexBridge]
        self.pid_values = {
            (motor_id, loop): values
            for motor_id in range(1, self.motor_count + 1)
            for loop, values in PID_DEFAULT_VALUES.items()
        }
        self._active_pid_motor_id = 1
        self._active_pid_loop = PidLoop.SPEED
        self.config_window = None  # type: Optional[tk.Toplevel]
        self.limit_vars = {
            "current": tk.StringVar(master=root, value="0.3"),
            "torque": tk.StringVar(master=root, value="0.03"),
            "speed": tk.StringVar(master=root, value="100"),
            "position_min": tk.StringVar(master=root, value="-1000"),
            "position_max": tk.StringVar(master=root, value="1000"),
            "bus_min": tk.StringVar(master=root, value="5"),
            "bus_max": tk.StringVar(master=root, value="8"),
            "temperature": tk.StringVar(master=root, value="80"),
        }
        self.telemetry_rate_var = tk.StringVar(master=root, value="20")
        self.open_loop_backend_var = tk.StringVar(
            master=root,
            value=OPEN_LOOP_BACKEND_LABELS[OpenLoopBackend.SIMPLEFOC],
        )
        self.open_loop_vars = {
            "pole_pairs": tk.StringVar(master=root, value="7"),
            "bus_voltage": tk.StringVar(master=root, value="7"),
            "voltage_limit": tk.StringVar(master=root, value="0.3"),
            "target_velocity": tk.StringVar(master=root, value="5"),
            "acceleration": tk.StringVar(master=root, value="10"),
            "update_period": tk.StringVar(master=root, value="10"),
            "startup_delay": tk.StringVar(master=root, value="500"),
            "max_runtime": tk.StringVar(master=root, value="30000"),
        }
        self.auto_protection_var = tk.BooleanVar(master=root, value=True)
        self.protection_response_var = tk.StringVar(
            master=root, value="快速停止"
        )
        self.telemetry_timeout_var = tk.StringVar(master=root, value="1000")
        self.heartbeat_lease_var = tk.StringVar(master=root, value="750")
        self.config_status_var = tk.StringVar(master=root, value="尚未读取设备配置")
        self.backend_info_var = tk.StringVar(master=root, value="控制后端：未读取")
        self.diagnostics_var = tk.StringVar(master=root, value="诊断信息：未读取")
        self.build_config_var = tk.StringVar(master=root, value="固件宏：未读取")
        self.hardware_layer_var = tk.StringVar(
            master=root,
            value="连接层级：控制硬件未确认｜功率硬件未确认",
        )
        self.codex_bridge_var = tk.StringVar(
            master=root,
            value="Codex：只读",
        )

        self._configure_theme()
        self._build_ui()
        self._refresh_ports()
        self._add_default_plots()
        self._set_connection_state(False, "未连接")

        self.root.after(20, self._poll_link)
        self.root.after(50, self._render_plots)
        self.root.after(200, self._refresh_values)
        self.root.after(250, self._heartbeat_tick)
        try:
            self._codex_bridge = CodexBridge(
                self.root,
                self._handle_codex_action,
            )
            self._codex_bridge.start()
            self._append_log(
                "Codex 调试桥已启动：仅本机访问，当前为只读模式",
                "ok",
            )
        except OSError as exc:
            self._append_log(
                "Codex 调试桥启动失败：{}".format(exc),
                "error",
            )

    def _configure_theme(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.option_add("*Font", ("Microsoft YaHei UI", 9))
        self.root.option_add("*TCombobox*Listbox.background", COLORS["panel_alt"])
        self.root.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", COLORS["accent"])
        style.configure(".", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Toolbar.TFrame", background=COLORS["panel_alt"])
        style.configure(
            "TLabel", background=COLORS["bg"], foreground=COLORS["text"]
        )
        style.configure(
            "Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"]
        )
        style.configure(
            "Muted.TLabel", background=COLORS["panel_alt"], foreground=COLORS["muted"]
        )
        style.configure(
            "PanelMuted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"]
        )
        style.configure(
            "Title.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["text"],
            font=("Microsoft YaHei UI", 15, "bold"),
        )
        style.configure(
            "PlotTitle.TLabel",
            background=COLORS["panel_alt"],
            foreground=COLORS["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure(
            "Section.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.configure(
            "Value.TLabel",
            background=COLORS["panel_alt"],
            foreground=COLORS["text"],
            font=("Consolas", 13, "bold"),
        )
        style.configure(
            "Unit.TLabel",
            background=COLORS["panel_alt"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "TButton",
            background=COLORS["panel_alt"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            focusthickness=1,
            focuscolor=COLORS["accent"],
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", COLORS["panel_hover"]), ("disabled", COLORS["panel"])],
            foreground=[("disabled", COLORS["muted"])],
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground="#FFFFFF",
            bordercolor=COLORS["accent"],
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.map("Accent.TButton", background=[("active", COLORS["accent_hover"])])
        style.configure(
            "Success.TButton",
            background="#167A5A",
            foreground="#FFFFFF",
            bordercolor="#1B9970",
        )
        style.map("Success.TButton", background=[("active", "#1D906B")])
        style.configure(
            "Danger.TButton",
            background=COLORS["danger"],
            foreground="#FFFFFF",
            bordercolor=COLORS["danger"],
            font=("Microsoft YaHei UI", 10, "bold"),
            padding=(12, 9),
        )
        style.map("Danger.TButton", background=[("active", "#FF6A7B")])
        style.configure(
            "Quiet.TButton", background=COLORS["panel_alt"], foreground=COLORS["muted"]
        )
        style.configure(
            "TEntry",
            fieldbackground=COLORS["panel_alt"],
            foreground=COLORS["text"],
            insertcolor=COLORS["text"],
            bordercolor=COLORS["border"],
            padding=6,
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["panel_alt"],
            background=COLORS["panel_alt"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["muted"],
            bordercolor=COLORS["border"],
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["panel_alt"])],
            foreground=[("readonly", COLORS["text"])],
            selectbackground=[("readonly", COLORS["panel_alt"])],
            selectforeground=[("readonly", COLORS["text"])],
        )
        style.configure(
            "Treeview",
            background=COLORS["panel"],
            fieldbackground=COLORS["panel"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            rowheight=27,
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["panel_alt"],
            foreground=COLORS["muted"],
            bordercolor=COLORS["border"],
            relief=tk.FLAT,
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["panel_hover"])],
            foreground=[("selected", COLORS["text"])],
        )
        style.configure(
            "TNotebook",
            background=COLORS["bg"],
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            padding=(15, 7),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["panel_alt"]), ("active", COLORS["panel_hover"])],
            foreground=[("selected", COLORS["text"])],
        )
        style.configure(
            "TLabelframe",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            relief=tk.SOLID,
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
        )
        style.configure(
            "TCheckbutton", background=COLORS["panel_alt"], foreground=COLORS["text"]
        )
        style.map(
            "TCheckbutton",
            background=[("active", COLORS["panel_alt"])],
            indicatorcolor=[
                ("selected", COLORS["accent"]),
                ("!selected", COLORS["panel"]),
            ],
        )
        style.configure("TSeparator", background=COLORS["border"])
        style.configure("TPanedwindow", background=COLORS["border"])

    def _build_ui(self) -> None:
        self._build_header()
        body_panes = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        body_panes.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        workspace = ttk.Frame(body_panes)
        body_panes.add(workspace, weight=5)
        workspace.columnconfigure(1, weight=1)
        workspace.rowconfigure(0, weight=1)

        self._build_signal_panel(workspace)
        self._build_plot_area(workspace)
        self._build_control_panel(workspace)
        self._build_log_panel(body_panes)
        self._build_status_bar()

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, padding=(14, 10))
        header.pack(fill=tk.X)
        title_area = ttk.Frame(header)
        title_area.pack(side=tk.LEFT, padx=(0, 28))
        ttk.Label(title_area, text="Motor Studio", style="Title.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            title_area,
            text="TC375 单电机调试与数据采集",
            foreground=COLORS["muted"],
        ).pack(anchor=tk.W)

        connection = ttk.Frame(header)
        connection.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(connection, text="端口").pack(side=tk.LEFT)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(
            connection, textvariable=self.port_var, state="readonly", width=12
        )
        self.port_combo.pack(side=tk.LEFT, padx=(6, 5))
        ttk.Button(
            connection, text="刷新", width=6, command=self._refresh_ports
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(connection, text="波特率").pack(side=tk.LEFT)
        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(
            connection,
            textvariable=self.baud_var,
            values=("9600", "19200", "38400", "57600", "115200", "460800", "921600"),
            width=9,
        ).pack(side=tk.LEFT, padx=(6, 8))
        self.connect_button = ttk.Button(
            connection,
            text="连接控制硬件",
            style="Accent.TButton",
            command=self._toggle_serial_connection,
        )
        self.connect_button.pack(side=tk.LEFT, padx=(0, 6))
        self.sim_button = ttk.Button(
            connection, text="启动仿真", command=self._toggle_simulator
        )
        self.sim_button.pack(side=tk.LEFT, padx=(0, 18))

        self.record_button = ttk.Button(
            header, text="开始记录", command=self._toggle_recording
        )
        self.record_button.pack(side=tk.RIGHT)
        self.codex_bridge_button = ttk.Button(
            header,
            textvariable=self.codex_bridge_var,
            command=self._toggle_codex_control,
        )
        self.codex_bridge_button.pack(side=tk.RIGHT, padx=(0, 7))
        ttk.Button(
            header,
            text="设备配置",
            command=self._open_device_config,
        ).pack(side=tk.RIGHT, padx=(0, 7))
        self.connection_status = ttk.Label(header, text="● 未连接")
        self.connection_status.pack(side=tk.RIGHT, padx=(8, 16))

    def _build_signal_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10, width=300)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        panel.grid_propagate(False)
        panel.rowconfigure(3, weight=1)
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="波形选择", style="Section.TLabel").grid(
            row=0, column=0, sticky=tk.W
        )
        ttk.Label(
            panel,
            text="每个图窗独立配置，双击信号切换显示",
            style="PanelMuted.TLabel",
        ).grid(row=1, column=0, sticky=tk.W, pady=(2, 9))
        filters = ttk.Frame(panel, style="Panel.TFrame")
        filters.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(filters, text="筛选", style="Panel.TLabel").pack(side=tk.LEFT)
        self.motor_filter = tk.StringVar(value="全部信号")
        filter_combo = ttk.Combobox(
            filters,
            textvariable=self.motor_filter,
            values=("全部信号", "M1"),
            state="readonly",
            width=10,
        )
        filter_combo.pack(side=tk.LEFT, padx=7)
        filter_combo.bind("<<ComboboxSelected>>", lambda _event: self._rebuild_signal_tree())

        tree_frame = ttk.Frame(panel, style="Panel.TFrame")
        tree_frame.grid(row=3, column=0, sticky="nsew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.signal_tree = ttk.Treeview(
            tree_frame,
            columns=("show", "name", "value", "unit"),
            show="headings",
            selectmode="browse",
        )
        self.signal_tree.heading("show", text="显示")
        self.signal_tree.heading("name", text="信号")
        self.signal_tree.heading("value", text="当前值")
        self.signal_tree.heading("unit", text="单位")
        self.signal_tree.column("show", width=44, anchor=tk.CENTER, stretch=False)
        self.signal_tree.column("name", width=103, anchor=tk.W)
        self.signal_tree.column("value", width=72, anchor=tk.E)
        self.signal_tree.column("unit", width=45, anchor=tk.W, stretch=False)
        scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self.signal_tree.yview
        )
        self.signal_tree.configure(yscrollcommand=scrollbar.set)
        self.signal_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.signal_tree.bind("<Double-1>", self._toggle_tree_signal)

        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.grid(row=4, column=0, sticky="ew", pady=(8, 10))
        ttk.Button(actions, text="本组全选", command=self._select_filtered_signals).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3)
        )
        ttk.Button(actions, text="清空当前窗", command=self._clear_plot_selection).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0)
        )

        ttk.Separator(panel).grid(row=5, column=0, sticky="ew", pady=(1, 9))
        ttk.Label(panel, text="安全告警", style="Section.TLabel").grid(
            row=6, column=0, sticky=tk.W
        )
        self.alarm_text = tk.Text(
            panel,
            height=5,
            wrap=tk.WORD,
            background=COLORS["panel_alt"],
            foreground=COLORS["muted"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"],
            relief=tk.FLAT,
            padx=7,
            pady=6,
            font=("Microsoft YaHei UI", 8),
            state=tk.DISABLED,
        )
        self.alarm_text.grid(row=7, column=0, sticky="ew", pady=(5, 0))
        self._set_alarm_display()

    def _build_plot_area(self, parent: ttk.Frame) -> None:
        area = ttk.Frame(parent)
        area.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        area.rowconfigure(1, weight=1)
        area.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(area, style="Panel.TFrame", padding=(9, 7))
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(
            toolbar,
            text="+ 添加波形窗口",
            style="Accent.TButton",
            command=self._add_plot,
        ).pack(side=tk.LEFT)
        ttk.Button(
            toolbar, text="导出缓存", command=self._export_history
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            toolbar, text="清空全部", command=self._clear_history
        ).pack(side=tk.LEFT)
        ttk.Label(
            toolbar,
            text="提示：不同单位的信号建议放在不同窗口",
            style="PanelMuted.TLabel",
        ).pack(side=tk.RIGHT)
        self.notebook = ttk.Notebook(area)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self._sync_signal_tree())

    def _build_control_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=11, width=302)
        panel.grid(row=0, column=2, sticky="nsew")
        panel.grid_propagate(False)
        panel.columnconfigure(0, weight=1)

        title_row = ttk.Frame(panel, style="Panel.TFrame")
        title_row.grid(row=0, column=0, sticky="ew")
        ttk.Label(title_row, text="电机控制", style="Section.TLabel").pack(side=tk.LEFT)
        self.selected_motor = tk.StringVar(value="M1")
        motor_combo = ttk.Combobox(
            title_row,
            textvariable=self.selected_motor,
            values=tuple(f"M{i}" for i in range(1, self.motor_count + 1)),
            state="readonly",
            width=6,
        )
        motor_combo.pack(side=tk.RIGHT)
        motor_combo.bind("<<ComboboxSelected>>", self._on_motor_changed)

        self._build_live_cards(panel)

        target_box = ttk.LabelFrame(panel, text=" 运行指令 ", padding=9)
        target_box.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        target_box.columnconfigure(1, weight=1)
        ttk.Label(target_box, text="控制模式", style="Panel.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=4
        )
        self.control_mode = tk.StringVar(value="速度")
        mode_combo = ttk.Combobox(
            target_box,
            textvariable=self.control_mode,
            values=("转矩", "速度", "位置", "开环速度"),
            state="readonly",
            width=12,
        )
        mode_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=4)
        mode_combo.bind("<<ComboboxSelected>>", self._update_target_unit)
        self.target_label = ttk.Label(
            target_box, text="目标值（rad/s）", style="Panel.TLabel"
        )
        self.target_label.grid(
            row=1, column=0, sticky=tk.W, pady=4
        )
        self.target_value = tk.StringVar(value="10")
        ttk.Entry(target_box, textvariable=self.target_value).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=4
        )
        ttk.Button(
            target_box,
            text="发送目标值",
            style="Accent.TButton",
            command=self._send_target,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 5))
        enable_row = ttk.Frame(target_box, style="Panel.TFrame")
        enable_row.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Button(
            enable_row,
            text="使能",
            style="Success.TButton",
            command=lambda: self._send_enable(True),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        ttk.Button(
            enable_row,
            text="失能",
            command=lambda: self._send_enable(False),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
        stop_row = ttk.Frame(target_box, style="Panel.TFrame")
        stop_row.grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Button(
            stop_row,
            text="受控停止",
            command=self._controlled_stop,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        ttk.Button(
            stop_row,
            text="快速停止",
            command=self._quick_stop,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        pid_box = ttk.LabelFrame(panel, text=" PID 参数 ", padding=9)
        pid_box.grid(row=3, column=0, sticky="ew", pady=(9, 0))
        for column in range(3):
            pid_box.columnconfigure(column, weight=1)
        ttk.Label(pid_box, text="PID 环路", style="Panel.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 7)
        )
        self.pid_loop = tk.StringVar(value=PID_LOOP_LABELS[self._active_pid_loop])
        pid_loop_combo = ttk.Combobox(
            pid_box,
            textvariable=self.pid_loop,
            values=("电流环", "速度环", "位置环"),
            state="readonly",
            width=12,
        )
        pid_loop_combo.grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(0, 7)
        )
        pid_loop_combo.bind("<<ComboboxSelected>>", self._on_pid_loop_changed)

        initial_pid = self.pid_values[
            (self._active_pid_motor_id, self._active_pid_loop)
        ]
        self.kp_var = tk.StringVar(value=f"{initial_pid[0]:.3f}")
        self.ki_var = tk.StringVar(value=f"{initial_pid[1]:.3f}")
        self.kd_var = tk.StringVar(value=f"{initial_pid[2]:.3f}")
        for column, (name, variable) in enumerate(
            (("Kp", self.kp_var), ("Ki", self.ki_var), ("Kd", self.kd_var))
        ):
            ttk.Label(pid_box, text=name, style="PanelMuted.TLabel").grid(
                row=1, column=column, sticky=tk.W
            )
            ttk.Entry(pid_box, textvariable=variable, width=7).grid(
                row=2,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 3, 0 if column == 2 else 3),
            )
        pid_actions = ttk.Frame(pid_box, style="Panel.TFrame")
        pid_actions.grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(7, 0)
        )
        ttk.Button(
            pid_actions, text="读取此环", command=self._read_parameters
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        ttk.Button(
            pid_actions,
            text="写入此环",
            style="Accent.TButton",
            command=self._send_pid,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        quick_box = ttk.LabelFrame(panel, text=" 设备操作 ", padding=9)
        quick_box.grid(row=4, column=0, sticky="ew", pady=(9, 0))
        for column in range(3):
            quick_box.columnconfigure(column, weight=1)
        operations = (
            ("设备信息", self._query_device_info),
            ("能力查询", self._query_capabilities),
            ("PING", self._send_ping),
            ("校准全部", self._calibrate_all),
            ("清除故障", self._clear_fault),
            ("保存参数", self._save_config),
        )
        for index, (label, command) in enumerate(operations):
            ttk.Button(quick_box, text=label, command=command).grid(
                row=index // 3,
                column=index % 3,
                sticky="ew",
                padx=(0 if index % 3 == 0 else 3, 0 if index % 3 == 2 else 3),
                pady=(0 if index < 3 else 5, 0),
            )

        raw_box = ttk.LabelFrame(panel, text=" 原始帧发送 ", padding=9)
        raw_box.grid(row=5, column=0, sticky="ew", pady=(9, 0))
        self.raw_hex = tk.StringVar(value="AA 55")
        ttk.Entry(raw_box, textvariable=self.raw_hex).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(raw_box, text="发送", width=6, command=self._send_raw).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        ttk.Button(
            panel,
            text="电机紧急停止",
            style="Danger.TButton",
            command=self._emergency_stop,
        ).grid(row=6, column=0, sticky="ew", pady=(12, 0))

    def _open_device_config(self) -> None:
        if self.config_window is not None and self.config_window.winfo_exists():
            self.config_window.deiconify()
            self.config_window.lift()
            self.config_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.config_window = window
        window.title("TC375 设备配置")
        window.geometry("780x720")
        window.minsize(700, 560)
        window.configure(background=COLORS["bg"])
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_device_config)

        scroll_host = ttk.Frame(window, style="Panel.TFrame")
        scroll_host.pack(fill=tk.BOTH, expand=True)

        scroll_canvas = tk.Canvas(
            scroll_host,
            background=COLORS["panel"],
            highlightthickness=0,
            borderwidth=0,
        )
        scroll_bar = ttk.Scrollbar(
            scroll_host,
            orient=tk.VERTICAL,
            command=scroll_canvas.yview,
        )
        scroll_canvas.configure(yscrollcommand=scroll_bar.set)
        scroll_bar.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        body = ttk.Frame(scroll_canvas, style="Panel.TFrame", padding=16)
        body_window = scroll_canvas.create_window(
            (0, 0),
            window=body,
            anchor=tk.NW,
        )

        def update_scroll_region(_event=None) -> None:
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def fit_body_width(event: tk.Event) -> None:
            scroll_canvas.itemconfigure(body_window, width=event.width)

        def scroll_with_wheel(event: tk.Event) -> str:
            delta = getattr(event, "delta", 0)
            if delta:
                steps = -1 if delta > 0 else 1
            else:
                steps = -1 if getattr(event, "num", 0) == 4 else 1
            scroll_canvas.yview_scroll(steps, "units")
            return "break"

        body.bind("<Configure>", update_scroll_region)
        scroll_canvas.bind("<Configure>", fit_body_width)
        window.bind("<MouseWheel>", scroll_with_wheel)
        window.bind("<Button-4>", scroll_with_wheel)
        window.bind("<Button-5>", scroll_with_wheel)

        body.columnconfigure(0, weight=1)
        ttk.Label(
            body,
            text="设备配置",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            body,
            text="修改后先应用到运行参数，确认无误再保存到 Flash。",
            style="PanelMuted.TLabel",
        ).grid(row=1, column=0, sticky=tk.W, pady=(2, 12))

        limits_box = ttk.LabelFrame(body, text=" 安全与运动限值 ", padding=11)
        limits_box.grid(row=2, column=0, sticky="ew")
        limits_box.columnconfigure(1, weight=1)
        field_specs = (
            ("最大相电流", "current", "A"),
            ("最大转矩", "torque", "N·m"),
            ("最大速度", "speed", "rad/s"),
            ("最小位置", "position_min", "rad"),
            ("最大位置", "position_max", "rad"),
            ("最低母线电压", "bus_min", "V"),
            ("最高母线电压", "bus_max", "V"),
            ("最高温度", "temperature", "°C"),
        )
        for row, (label, key, unit) in enumerate(field_specs):
            ttk.Label(
                limits_box,
                text=label,
                style="Panel.TLabel",
            ).grid(row=row, column=0, sticky=tk.W, pady=3)
            ttk.Entry(
                limits_box,
                textvariable=self.limit_vars[key],
                width=17,
            ).grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=3)
            ttk.Label(
                limits_box,
                text=unit,
                width=7,
                style="PanelMuted.TLabel",
            ).grid(row=row, column=2, sticky=tk.W, pady=3)

        open_loop_box = ttk.LabelFrame(
            body, text=" 开环调试参数（停止状态下应用） ", padding=11
        )
        open_loop_box.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        open_loop_box.columnconfigure(1, weight=1)
        open_loop_box.columnconfigure(4, weight=1)
        ttk.Label(
            open_loop_box, text="实现方式", style="Panel.TLabel"
        ).grid(row=0, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(
            open_loop_box,
            textvariable=self.open_loop_backend_var,
            values=tuple(OPEN_LOOP_BACKEND_FROM_LABEL),
            state="readonly",
        ).grid(
            row=0, column=1, columnspan=4, sticky="ew", padx=(8, 8), pady=3
        )
        open_loop_specs = (
            (
                ("极对数", "pole_pairs", "pairs"),
                ("母线电压", "bus_voltage", "V"),
            ),
            (
                ("电压限幅", "voltage_limit", "V"),
                ("初始速度", "target_velocity", "rad/s"),
            ),
            (
                ("加速度", "acceleration", "rad/s²"),
                ("更新周期", "update_period", "ms"),
            ),
            (
                ("启动延时", "startup_delay", "ms"),
                ("最长运行", "max_runtime", "ms"),
            ),
        )
        for row, pair in enumerate(open_loop_specs, start=1):
            for index, (label, key, unit) in enumerate(pair):
                offset = index * 3
                ttk.Label(
                    open_loop_box, text=label, style="Panel.TLabel"
                ).grid(row=row, column=offset, sticky=tk.W, pady=3)
                ttk.Entry(
                    open_loop_box,
                    textvariable=self.open_loop_vars[key],
                    width=12,
                ).grid(
                    row=row,
                    column=offset + 1,
                    sticky="ew",
                    padx=(8, 5),
                    pady=3,
                )
                ttk.Label(
                    open_loop_box,
                    text=unit,
                    style="PanelMuted.TLabel",
                ).grid(row=row, column=offset + 2, sticky=tk.W, pady=3)
        open_loop_actions = ttk.Frame(
            open_loop_box, style="Panel.TFrame"
        )
        open_loop_actions.grid(
            row=5, column=0, columnspan=6, sticky="ew", pady=(7, 0)
        )
        ttk.Button(
            open_loop_actions,
            text="读取开环参数",
            command=self._read_open_loop_config,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        ttk.Button(
            open_loop_actions,
            text="应用开环参数",
            style="Accent.TButton",
            command=self._apply_open_loop_config,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
        ttk.Button(
            open_loop_actions,
            text="启动开环",
            style="Success.TButton",
            command=self._start_open_loop,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
        ttk.Label(
            open_loop_box,
            text=(
                "运行中仅允许通过右侧“开环速度”目标实时调速；"
                "开环为电压模式，0.3 A 软件限值不等于实时限流；"
                "提高电压限幅前请先停止，并使用电源硬件限流。"
            ),
            style="PanelMuted.TLabel",
        ).grid(row=6, column=0, columnspan=6, sticky=tk.W, pady=(7, 0))

        telemetry_box = ttk.LabelFrame(body, text=" 遥测配置 ", padding=11)
        telemetry_box.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        telemetry_box.columnconfigure(1, weight=1)
        ttk.Label(
            telemetry_box,
            text="上报频率",
            style="Panel.TLabel",
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(
            telemetry_box,
            textvariable=self.telemetry_rate_var,
            values=("10", "20", "50", "100", "200", "500", "1000"),
            width=12,
        ).grid(row=0, column=1, sticky="ew", padx=(12, 8))
        ttk.Label(
            telemetry_box,
            text="Hz",
            style="PanelMuted.TLabel",
        ).grid(row=0, column=2, sticky=tk.W)
        ttk.Label(
            telemetry_box,
            text="当前发送全部五项波形信号",
            style="PanelMuted.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(7, 0))

        protection_box = ttk.LabelFrame(
            body, text=" 上位机软件保护 ", padding=11
        )
        protection_box.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        protection_box.columnconfigure(2, weight=1)
        ttk.Checkbutton(
            protection_box,
            text="启用阈值与遥测超时自动停止",
            variable=self.auto_protection_var,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W)
        ttk.Label(
            protection_box, text="保护响应", style="Panel.TLabel"
        ).grid(row=1, column=0, sticky=tk.W, pady=(7, 0))
        ttk.Combobox(
            protection_box,
            textvariable=self.protection_response_var,
            values=("受控停止", "快速停止", "紧急停止"),
            state="readonly",
            width=11,
        ).grid(row=1, column=1, sticky=tk.W, padx=(8, 18), pady=(7, 0))
        ttk.Label(
            protection_box, text="遥测超时", style="Panel.TLabel"
        ).grid(row=1, column=2, sticky=tk.E, pady=(7, 0))
        ttk.Entry(
            protection_box,
            textvariable=self.telemetry_timeout_var,
            width=8,
        ).grid(row=1, column=3, padx=(8, 4), pady=(7, 0))
        ttk.Label(
            protection_box, text="ms", style="PanelMuted.TLabel"
        ).grid(row=1, column=4, sticky=tk.W, pady=(7, 0))
        ttk.Label(
            protection_box, text="心跳租约", style="Panel.TLabel"
        ).grid(row=2, column=2, sticky=tk.E, pady=(7, 0))
        ttk.Entry(
            protection_box,
            textvariable=self.heartbeat_lease_var,
            width=8,
        ).grid(row=2, column=3, padx=(8, 4), pady=(7, 0))
        ttk.Label(
            protection_box, text="ms", style="PanelMuted.TLabel"
        ).grid(row=2, column=4, sticky=tk.W, pady=(7, 0))
        ttk.Button(
            protection_box,
            text="应用软件保护",
            command=self._apply_software_protection,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 0))

        info_box = ttk.LabelFrame(body, text=" 设备信息 ", padding=11)
        info_box.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(
            info_box,
            textvariable=self.hardware_layer_var,
            style="Panel.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            info_box,
            textvariable=self.backend_info_var,
            style="Panel.TLabel",
        ).pack(anchor=tk.W, pady=(5, 0))
        ttk.Label(
            info_box,
            textvariable=self.diagnostics_var,
            style="PanelMuted.TLabel",
        ).pack(anchor=tk.W, pady=(5, 0))
        ttk.Label(
            info_box,
            textvariable=self.build_config_var,
            style="PanelMuted.TLabel",
            wraplength=700,
        ).pack(anchor=tk.W, pady=(5, 0))

        actions = ttk.Frame(body, style="Panel.TFrame")
        actions.grid(row=7, column=0, sticky="ew", pady=(12, 0))
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        action_specs = (
            ("读取全部", self._read_device_config, "TButton"),
            ("检测固件 / 硬件", self._query_build_config, "TButton"),
            ("应用限值", self._apply_limits, "Accent.TButton"),
            ("应用遥测", self._apply_telemetry_profile, "Accent.TButton"),
            ("保存到 Flash", self._save_config, "Success.TButton"),
            ("刷新诊断", self._query_diagnostics, "TButton"),
            ("恢复默认", self._restore_default_config, "Danger.TButton"),
        )
        for index, (label, command, style) in enumerate(action_specs):
            ttk.Button(
                actions,
                text=label,
                command=command,
                style=style,
            ).grid(
                row=index // 3,
                column=index % 3,
                sticky="ew",
                padx=(0 if index % 3 == 0 else 4, 0 if index % 3 == 2 else 4),
                pady=(0 if index < 3 else 7, 0),
            )

        ttk.Label(
            body,
            textvariable=self.config_status_var,
            style="PanelMuted.TLabel",
            wraplength=700,
        ).grid(row=8, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(
            body,
            text="关闭",
            command=self._close_device_config,
        ).grid(row=9, column=0, sticky="ew", pady=(12, 0))

    def _close_device_config(self) -> None:
        if self.config_window is not None:
            try:
                self.config_window.destroy()
            except tk.TclError:
                pass
        self.config_window = None

    def _set_config_status(self, message: str) -> None:
        self.config_status_var.set(message)

    def _read_device_config(self) -> None:
        if not self.link.connected:
            self._set_config_status("请先连接串口或启动仿真设备。")
            return
        self._query_build_config()
        queries = (
            (Command.GET_LIMITS, b"\x01"),
            (Command.GET_TELEMETRY_PROFILE, b""),
            (Command.GET_OPEN_LOOP_CONFIG, b"\x01"),
            (Command.GET_BACKEND_INFO, b""),
            (Command.GET_DIAGNOSTICS, b"\x07"),
        )
        for index, (command, payload) in enumerate(queries):
            self.root.after(
                120 * (index + 1),
                lambda cmd=command, data=payload: self._send_if_connected(
                    cmd, data, 1
                ),
            )
        self._set_config_status(
            "正在读取限值、开环参数、固件宏和诊断信息…"
        )

    def _send_if_connected(
        self,
        command: Union[Command, int],
        payload: bytes = b"",
        device: int = 0,
    ) -> None:
        if self.link.connected:
            self._send_frame(command, payload, device)

    def _query_build_config(self, retry: bool = False) -> None:
        if not self.link.connected:
            if not retry:
                self._set_config_status("请先连接串口或启动仿真设备。")
            return
        if retry:
            self._build_config_query_attempt += 1
        else:
            self._build_config_query_generation += 1
            self._build_config_query_attempt = 1
            self._build_config_query_started_at = time.monotonic()
            self._build_control_hardware_enabled = None
            self._build_power_stage_enabled = None
            self._build_simplefoc_enabled = None
            self._build_safety_mask = None
            self._device_open_loop_config = None
            self.hardware_layer_var.set(
                "连接层级：正在确认控制硬件与功率硬件…"
            )
            self.build_config_var.set("固件宏：正在读取命令 0x29…")
        generation = self._build_config_query_generation
        if self._send_frame(Command.GET_BUILD_CONFIG, b"", 1):
            self._set_config_status(
                "正在等待设备确认固件宏（0x29，第 {} 次）…".format(
                    self._build_config_query_attempt
                )
            )
            self.root.after(
                1000,
                lambda token=generation: self._check_build_config_reply(
                    token
                ),
            )

    def _check_build_config_reply(self, generation: int) -> None:
        if (
            generation != self._build_config_query_generation
            or not self.link.connected
            or self._build_config_query_started_at == 0.0
        ):
            return
        if self._build_config_query_attempt < 2:
            self._append_log(
                "未收到命令 0x29 的确认，正在自动重试一次。", "warn"
            )
            self._query_build_config(retry=True)
            return
        protocol_alive = (
            self._protocol_response_at
            > self._build_config_query_started_at
        )
        if protocol_alive:
            if (
                self._device_firmware_version is not None
                and self._device_firmware_version < (0, 3, 0)
            ):
                message = (
                    "板上当前运行 FW {}（build={}），不是支持 0x29 的 "
                    "FW 0.3.4 / CFG33；请重新 Download 最新 ELF 并 Resume。"
                ).format(
                    ".".join(
                        str(value)
                        for value in self._device_firmware_version
                    ),
                    self._device_build_id or "未知",
                )
            else:
                message = (
                    "串口有其他协议响应，但设备未回复 0x29；"
                    "请重新 Download 最新 open_loop_test.elf 并 Resume。"
                )
        else:
            message = (
                "设备未回复 0x29，且查询期间没有任何协议响应；"
                "请确认 CPU 处于 Run、波特率为 115200，并检查 TX/RX/GND。"
            )
        self._build_config_query_started_at = 0.0
        self.hardware_layer_var.set(
            "连接层级：未确认，禁止启动开环输出"
        )
        self.build_config_var.set("固件宏：读取失败（命令 0x29 无确认）")
        self._set_config_status(message)
        self.status_message.configure(text=message)
        self._append_log(message, "error")

    def _read_open_loop_config(self) -> None:
        if self._send_frame(
            Command.GET_OPEN_LOOP_CONFIG, b"\x01", 1
        ):
            self._set_config_status("正在读取设备开环参数…")

    def _open_loop_config_from_ui(self) -> OpenLoopConfig:
        try:
            backend = OPEN_LOOP_BACKEND_FROM_LABEL[
                self.open_loop_backend_var.get()
            ]
            pole_pairs = int(self.open_loop_vars["pole_pairs"].get())
            bus_voltage = float(
                self.open_loop_vars["bus_voltage"].get()
            )
            voltage_limit = float(
                self.open_loop_vars["voltage_limit"].get()
            )
            target_velocity = float(
                self.open_loop_vars["target_velocity"].get()
            )
            acceleration = float(
                self.open_loop_vars["acceleration"].get()
            )
            update_period = int(
                self.open_loop_vars["update_period"].get()
            )
            startup_delay = int(
                self.open_loop_vars["startup_delay"].get()
            )
            max_runtime = int(
                self.open_loop_vars["max_runtime"].get()
            )
        except (KeyError, ValueError):
            raise ValueError("所有开环参数都必须是有效数字")
        if bus_voltage > 8.0:
            raise ValueError("母线电压不能超过当前电机固件硬上限 8 V")
        if voltage_limit > 2.0:
            raise ValueError("开环电压限幅不能超过当前电机固件硬上限 2 V")
        if abs(target_velocity) > 100.0:
            raise ValueError("开环速度绝对值不能超过固件硬上限 100 rad/s")
        return OpenLoopConfig(
            1,
            backend,
            pole_pairs,
            0,
            bus_voltage,
            voltage_limit,
            target_velocity,
            acceleration,
            update_period,
            startup_delay,
            max_runtime,
        )

    def _validate_power_stage_open_loop(
        self,
        config: OpenLoopConfig,
    ) -> None:
        if not self._build_power_stage_enabled:
            return
        if self._build_safety_mask is None:
            raise ValueError(
                "尚未读取功率级安全清单；请先点击“读取全部”。"
            )

        safety_mask = int(self._build_safety_mask)
        missing = POWER_STAGE_REQUIRED_SAFETY_MASK & ~safety_mask
        commissioning_override = bool(
            safety_mask & POWER_STAGE_COMMISSIONING_OVERRIDE
        )
        if missing and not commissioning_override:
            raise ValueError(
                "功率级安全清单不完整（缺少 0x{:03X}），固件也未启用调试旁路。"
                .format(missing)
            )

        diagnostics = self._latest_diagnostics
        if diagnostics is None:
            raise ValueError(
                "尚未读取功率级运行诊断；请先点击“读取全部”或“刷新诊断”。"
            )
        hardware_flags = int(diagnostics.get("hardware_flags", 0))
        if not hardware_flags & HARDWARE_FLAG_POWER_STAGE_BUILD:
            raise ValueError(
                "诊断结果未确认当前固件为真实功率级构建，禁止启动。"
            )
        if not hardware_flags & HARDWARE_FLAG_NFAULT_CLEAR:
            raise ValueError("nFAULT 未确认释放，禁止启动功率级。")

        if commissioning_override:
            if not (
                hardware_flags
                & HARDWARE_FLAG_COMMISSIONING_OVERRIDE
            ):
                raise ValueError(
                    "构建配置与运行诊断的调试旁路状态不一致。"
                )
            conservative = (
                config.voltage_limit_v
                <= POWER_STAGE_COMMISSIONING_MAX_VOLTAGE_V
                and abs(config.target_velocity_rad_s)
                <= POWER_STAGE_COMMISSIONING_MAX_SPEED_RAD_S
                and config.acceleration_rad_s2
                <= POWER_STAGE_COMMISSIONING_MAX_ACCEL_RAD_S2
                and config.max_runtime_ms
                <= POWER_STAGE_COMMISSIONING_MAX_RUNTIME_MS
            )
            if not conservative:
                raise ValueError(
                    "调试旁路仅允许 U≤{:.2f} V、|ω|≤{:.1f} rad/s、"
                    "加速度≤{:.1f} rad/s²、运行≤{} ms。".format(
                        POWER_STAGE_COMMISSIONING_MAX_VOLTAGE_V,
                        POWER_STAGE_COMMISSIONING_MAX_SPEED_RAD_S,
                        POWER_STAGE_COMMISSIONING_MAX_ACCEL_RAD_S2,
                        POWER_STAGE_COMMISSIONING_MAX_RUNTIME_MS,
                    )
                )
        elif not hardware_flags & HARDWARE_FLAG_SAFETY_READY:
            raise ValueError(
                "固件安全清单完整，但运行诊断尚未进入 safety-ready 状态。"
            )

        if hardware_flags & (
            HARDWARE_FLAG_PWM_ENABLED | HARDWARE_FLAG_GATE_ENABLED
        ):
            raise ValueError(
                "诊断显示 PWM 或 gate 已经使能；请先快速停止并重新读取诊断。"
            )

    def _open_loop_start_payload(
        self,
        config: OpenLoopConfig,
        power_stage_confirmed: bool,
    ) -> bytes:
        self._validate_power_stage_open_loop(config)
        return pack_start_open_loop(
            config.motor_id,
            bool(self._build_power_stage_enabled),
            power_stage_confirmed,
        )

    def _apply_open_loop_config(self) -> None:
        try:
            config = self._open_loop_config_from_ui()
        except ValueError as exc:
            messagebox.showerror("开环配置错误", str(exc))
            return
        self._begin_open_loop_config_transfer(config, False)

    def _begin_open_loop_config_transfer(
        self,
        config: OpenLoopConfig,
        start_after_commit: bool,
        power_stage_confirmed: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not self.link.connected:
            self.status_message.configure(
                text="请先连接串口或启动仿真"
            )
            return None
        if self._open_loop_transfer is not None:
            self._set_config_status(
                "已有一组开环参数正在传输，请等待完成。"
            )
            return None
        if (
            self._device_features is not None
            and not (
                self._device_features
                & FEATURE_FRAGMENTED_OPEN_LOOP_CONFIG
            )
        ):
            message = (
                "当前固件不支持短帧分片配置；请烧录 FW 0.3.6 / FRG2 "
                "或更新版本。"
            )
            self._set_config_status(message)
            self.status_message.configure(text=message)
            return None

        start_payload = None  # type: Optional[bytes]
        if start_after_commit:
            try:
                start_payload = self._open_loop_start_payload(
                    config,
                    power_stage_confirmed,
                )
            except ValueError as exc:
                message = str(exc)
                self._set_config_status(message)
                self.status_message.configure(text=message)
                return None

        self._open_loop_transfer_token += 1
        generation = self._open_loop_transfer_token & 0xFF
        try:
            fragments = pack_open_loop_config_fragments(
                config,
                generation,
            )
            commit = pack_open_loop_config_commit(
                config,
                generation,
            )
        except ValueError as exc:
            self._set_config_status(str(exc))
            return None

        transfer = {
            "token": self._open_loop_transfer_token,
            "generation": generation,
            "config": config,
            "fragments": fragments,
            "commit": commit,
            "index": 0,
            "phase": "fragment",
            "attempts": 0,
            "expected_sequence": None,
            "start_after_commit": bool(start_after_commit),
            "start_payload": start_payload,
        }
        result = {
            "token": transfer["token"],
            "generation": generation,
            "state": "pending",
            "phase": "fragment",
            "fragment_index": 0,
            "fragment_count": len(fragments),
            "attempts": 0,
            "retries": 0,
            "started_at": time.time(),
        }
        transfer["result"] = result
        self._open_loop_transfer = transfer
        self._open_loop_transfer_result = result
        self._pending_open_loop_start = None
        self._send_open_loop_transfer_step()
        return transfer

    def _send_open_loop_transfer_step(self) -> None:
        transfer = self._open_loop_transfer
        if transfer is None:
            return
        if transfer["attempts"] >= OPEN_LOOP_FRAGMENT_MAX_ATTEMPTS:
            self._abort_open_loop_transfer(
                "开环配置传输失败：设备连续 {} 次未应答。".format(
                    OPEN_LOOP_FRAGMENT_MAX_ATTEMPTS
                )
            )
            return

        if transfer["phase"] == "fragment":
            index = int(transfer["index"])
            command = Command.SET_OPEN_LOOP_CONFIG_PART
            payload = transfer["fragments"][index]
            progress = "开环配置分片 {}/{}".format(
                index + 1,
                len(transfer["fragments"]),
            )
        elif transfer["phase"] == "commit":
            command = Command.COMMIT_OPEN_LOOP_CONFIG
            payload = transfer["commit"]
            progress = "开环配置原子提交"
        else:
            command = Command.GET_OPEN_LOOP_CONFIG
            payload = b"\x01"
            progress = "开环配置精确回读校验"

        sequence = self._next_sequence()
        frame = Frame(
            device_id=1,
            command=int(command),
            sequence=sequence,
            payload=payload,
        )
        try:
            self.link.send(encode_frame(frame))
        except RuntimeError as exc:
            self._abort_open_loop_transfer(str(exc))
            return

        transfer["attempts"] = int(transfer["attempts"]) + 1
        transfer["expected_sequence"] = sequence
        result = transfer["result"]
        result.update(
            {
                "phase": transfer["phase"],
                "fragment_index": int(transfer["index"]),
                "attempts": int(transfer["attempts"]),
                "sequence": sequence,
            }
        )
        self._set_config_status(
            "正在发送{}，第 {} 次尝试…".format(
                progress,
                transfer["attempts"],
            )
        )
        token = int(transfer["token"])
        self.root.after(
            OPEN_LOOP_FRAGMENT_ACK_TIMEOUT_MS,
            lambda: self._on_open_loop_transfer_timeout(
                token,
                sequence,
            ),
        )

    def _on_open_loop_transfer_timeout(
        self,
        token: int,
        sequence: int,
    ) -> None:
        transfer = self._open_loop_transfer
        if (
            transfer is None
            or transfer["token"] != token
            or transfer["expected_sequence"] != sequence
        ):
            return
        self._append_log(
            "开环配置 {} seq={} 等待 ACK 超时，正在重试。".format(
                transfer["phase"],
                sequence,
            ),
            "warn",
        )
        transfer["result"]["retries"] = (
            int(transfer["result"]["retries"]) + 1
        )
        self._send_open_loop_transfer_step()

    def _abort_open_loop_transfer(self, message: str) -> None:
        transfer = self._open_loop_transfer
        if transfer is not None:
            transfer["result"].update(
                {
                    "state": "error",
                    "message": message,
                    "completed_at": time.time(),
                }
            )
        self._open_loop_transfer = None
        self._pending_open_loop_start = None
        self._open_loop_transfer_token += 1
        self._set_config_status(message)
        self.status_message.configure(text=message)
        self._append_log(message, "error")

    def _handle_open_loop_transfer_reply(
        self,
        original: int,
        status: int,
        sequence: int,
        detail: bytes,
    ) -> bool:
        transfer = self._open_loop_transfer
        if (
            transfer is None
            or original not in (
                Command.SET_OPEN_LOOP_CONFIG_PART,
                Command.COMMIT_OPEN_LOOP_CONFIG,
                Command.GET_OPEN_LOOP_CONFIG,
            )
            or transfer["expected_sequence"] != sequence
        ):
            return False

        expected_commands = {
            "fragment": Command.SET_OPEN_LOOP_CONFIG_PART,
            "commit": Command.COMMIT_OPEN_LOOP_CONFIG,
            "verify": Command.GET_OPEN_LOOP_CONFIG,
        }
        expected_command = expected_commands.get(transfer["phase"])
        if original != expected_command:
            self._abort_open_loop_transfer(
                "开环配置 ACK 命令与当前传输阶段不匹配。"
            )
            return True

        if status != 0:
            self._abort_open_loop_transfer(
                "设备拒绝开环配置命令 0x{:02X}，错误码 {}。".format(
                    original,
                    status,
                )
            )
            return True

        generation = int(transfer["generation"])
        if original == Command.SET_OPEN_LOOP_CONFIG_PART:
            index = int(transfer["index"])
            if (
                len(detail) != 2
                or detail[0] != generation
                or detail[1] != index
            ):
                self._abort_open_loop_transfer(
                    "开环配置分片 ACK 与当前传输不匹配。"
                )
                return True
            transfer["expected_sequence"] = None
            transfer["attempts"] = 0
            transfer["index"] = index + 1
            transfer["result"].update(
                {
                    "fragment_index": int(transfer["index"]),
                    "attempts": 0,
                }
            )
            if transfer["index"] < len(transfer["fragments"]):
                self.root.after(
                    10,
                    self._send_open_loop_transfer_step,
                )
            else:
                transfer["phase"] = "commit"
                transfer["result"]["phase"] = "commit"
                self.root.after(
                    10,
                    self._send_open_loop_transfer_step,
                )
            return True

        if original == Command.COMMIT_OPEN_LOOP_CONFIG:
            if len(detail) != 1 or detail[0] != generation:
                self._abort_open_loop_transfer(
                    "开环配置提交 ACK 与当前传输不匹配。"
                )
                return True
            transfer["expected_sequence"] = None
            transfer["attempts"] = 0
            transfer["phase"] = "verify"
            transfer["result"].update(
                {
                    "phase": "verify",
                    "attempts": 0,
                }
            )
            self.root.after(
                10,
                self._send_open_loop_transfer_step,
            )
            return True

        config = transfer["config"]
        expected_config = pack_open_loop_config(config)
        if detail != expected_config:
            self._abort_open_loop_transfer(
                "设备回读的开环参数与刚提交的参数不一致，已禁止启动。"
            )
            return True
        try:
            verified_config = unpack_open_loop_config(detail)
        except ValueError as exc:
            self._abort_open_loop_transfer(str(exc))
            return True
        self._device_open_loop_config = verified_config
        start_after_commit = bool(
            transfer["start_after_commit"]
        )
        transfer["result"].update(
            {
                "state": "ack",
                "phase": "complete",
                "fragment_index": len(transfer["fragments"]),
                "attempts": int(transfer["attempts"]),
                "completed_at": time.time(),
            }
        )
        self._open_loop_transfer = None
        self._pending_open_loop_start = None
        if start_after_commit:
            if self._send_frame(
                Command.START_OPEN_LOOP,
                transfer["start_payload"],
                1,
            ):
                self.control_mode.set(
                    MODE_LABELS[ControlMode.OPEN_LOOP_SPEED]
                )
                self.target_value.set(
                    "{:g}".format(
                        config.target_velocity_rad_s
                    )
                )
                self._update_target_unit()
                self._set_config_status(
                    "参数已提交并精确回读一致，正在执行开环安全启动…"
                )
        else:
            self._set_config_status(
                "开环参数已通过 14 个短帧分片提交并精确回读一致。"
            )
        return True

    def _start_open_loop(self) -> None:
        try:
            config = self._open_loop_config_from_ui()
        except ValueError as exc:
            messagebox.showerror("开环配置错误", str(exc))
            return
        if self._software_protection_latched:
            messagebox.showerror(
                "保护已锁定",
                "上位机软件保护已触发。请先排除原因并点击“清除故障”。",
            )
            return
        if self._build_control_hardware_enabled is None:
            messagebox.showerror(
                "尚未确认硬件分层",
                "请先点击“读取设备”，确认控制硬件、功率级和 SimpleFOC 编译状态。",
            )
            return
        if not self._build_control_hardware_enabled:
            messagebox.showerror(
                "PWM 输出已锁定",
                "当前固件未启用控制硬件输出，不能在 MCU 引脚产生 PWM。",
            )
            return
        if (
            config.backend == OpenLoopBackend.SIMPLEFOC
            and not self._build_simplefoc_enabled
        ):
            messagebox.showerror(
                "SimpleFOC 未启用",
                "当前固件没有编译 SimpleFOC，请重新构建并烧录后再启动。",
            )
            return
        try:
            self._validate_power_stage_open_loop(config)
        except ValueError as exc:
            messagebox.showerror("功率级安全条件未满足", str(exc))
            return
        if self._build_power_stage_enabled:
            commissioning_override = bool(
                int(self._build_safety_mask or 0)
                & POWER_STAGE_COMMISSIONING_OVERRIDE
            )
            safety_text = (
                "功率级已由固件允许：电机可能立即转动。请确认电机已卸载、"
                "直流电源先限流到 0.1 A、物理急停可用，且 nFAULT 已验证。"
                "开环为电压模式，0.3 A 软件上限不会直接调节或限制相电流。"
            )
            stage_text = (
                "功率级：调试旁路（仅允许保守参数）"
                if commissioning_override
                else "功率级：安全清单与运行诊断均已就绪"
            )
        else:
            safety_text = (
                "当前为控制板 PWM 检查模式：DRV8313 nSLEEP/nRESET 将保持关闭。"
                "请保持功率板或母线电源断开，仅在 MCU PWM 引脚上测量。"
            )
            stage_text = "功率级：编译期锁定（仅 MCU PWM）"
        confirmed = messagebox.askyesno(
            "确认启动开环",
            (
                "{}\n\n实现：{}\n{}\n母线参数：{:g} V\n电压限幅：{:g} V\n"
                "目标速度：{:g} rad/s\n最长运行：{:.1f} s\n\n"
                "是否继续？"
            ).format(
                safety_text,
                OPEN_LOOP_BACKEND_LABELS[config.backend],
                stage_text,
                config.bus_voltage_v,
                config.voltage_limit_v,
                config.target_velocity_rad_s,
                config.max_runtime_ms / 1000.0,
            ),
            parent=self.config_window,
        )
        if not confirmed:
            return
        if self._begin_open_loop_config_transfer(
            config,
            True,
            power_stage_confirmed=(
                confirmed and bool(self._build_power_stage_enabled)
            ),
        ):
            self._set_config_status(
                "正在逐片应用开环参数；14 个分片和提交命令全部确认后将启动。"
            )

    def _apply_software_protection(self) -> None:
        try:
            timeout_ms = int(self.telemetry_timeout_var.get())
            lease_ms = int(self.heartbeat_lease_var.get())
            if not 300 <= lease_ms <= 5000:
                raise ValueError("心跳租约必须在 300..5000 ms 范围内")
            if not 500 <= timeout_ms <= 10000:
                raise ValueError("遥测超时必须在 500..10000 ms 范围内")
            limits = {
                key: float(variable.get())
                for key, variable in self.limit_vars.items()
            }
        except ValueError as exc:
            messagebox.showerror("保护配置错误", str(exc))
            return
        self.heartbeat_lease_ms = lease_ms
        self.alarms.configure(
            limits["current"],
            limits["temperature"],
            limits["bus_min"],
            limits["bus_max"],
        )
        self._set_config_status(
            "软件保护已应用：{}，遥测超时 {} ms，心跳租约 {} ms。".format(
                self.protection_response_var.get(),
                timeout_ms,
                lease_ms,
            )
        )

    def _apply_limits(self) -> None:
        try:
            values = {
                key: float(variable.get())
                for key, variable in self.limit_vars.items()
            }
        except ValueError:
            messagebox.showerror("配置错误", "所有限值都必须是有效数字。")
            return
        if not all(math.isfinite(value) for value in values.values()):
            messagebox.showerror("配置错误", "限值不能是无穷大或 NaN。")
            return
        if (
            values["current"] <= 0.0
            or values["torque"] <= 0.0
            or values["speed"] <= 0.0
            or values["temperature"] <= 0.0
            or values["bus_min"] <= 0.0
            or values["position_min"] >= values["position_max"]
            or values["bus_min"] >= values["bus_max"]
        ):
            messagebox.showerror(
                "配置错误",
                "最大值必须为正数，并且位置、电压的最小值必须小于最大值。",
            )
            return
        payload = pack_limits(
            1,
            values["current"],
            values["torque"],
            values["speed"],
            values["position_min"],
            values["position_max"],
            values["bus_min"],
            values["bus_max"],
            values["temperature"],
        )
        if self._send_frame(Command.SET_LIMITS, payload, 1):
            self.alarms.configure(
                values["current"],
                values["temperature"],
                values["bus_min"],
                values["bus_max"],
            )
            self._set_config_status("已发送限值配置，等待设备确认…")

    def _apply_telemetry_profile(self) -> None:
        try:
            rate_hz = int(self.telemetry_rate_var.get())
            payload = pack_telemetry_profile(rate_hz, 0x1F)
        except ValueError as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        if self._send_frame(Command.SET_TELEMETRY_PROFILE, payload, 1):
            self._set_config_status(
                f"已发送 {rate_hz} Hz 遥测配置，等待设备确认…"
            )

    def _query_backend(self) -> None:
        self._send_frame(Command.GET_BACKEND_INFO, b"", 1)

    def _query_diagnostics(self) -> None:
        if self._send_frame(Command.GET_DIAGNOSTICS, b"\x07", 1):
            self._set_config_status("正在读取设备诊断信息…")

    def _restore_default_config(self) -> None:
        confirmed = messagebox.askyesno(
            "恢复默认配置",
            "这会将 PID 和安全限值恢复为固件默认值，确定继续吗？",
            parent=self.config_window,
        )
        if not confirmed:
            return
        if self._send_frame(Command.RESTORE_DEFAULTS, b"", 1):
            self._set_config_status("已发送恢复默认配置指令，等待设备确认…")

    def _build_live_cards(self, parent: ttk.Frame) -> None:
        cards = ttk.Frame(parent, style="Panel.TFrame")
        cards.grid(row=1, column=0, sticky="ew", pady=(9, 0))
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)
        self.live_value_labels = {}  # type: Dict[str, ttk.Label]
        specs = (
            ("speed", "转速", "rpm"),
            ("current", "电流", "A"),
            ("voltage", "电压", "V"),
            ("temperature", "温度", "°C"),
        )
        for index, (key, label, unit) in enumerate(specs):
            card = ttk.Frame(cards, style="Toolbar.TFrame", padding=(9, 7))
            card.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 4) if index % 2 == 0 else (4, 0),
                pady=(0, 4) if index < 2 else (4, 0),
            )
            ttk.Label(card, text=label, style="Muted.TLabel").pack(anchor=tk.W)
            value_row = ttk.Frame(card, style="Toolbar.TFrame")
            value_row.pack(fill=tk.X, pady=(2, 0))
            value_label = ttk.Label(value_row, text="--", style="Value.TLabel")
            value_label.pack(side=tk.LEFT)
            ttk.Label(value_row, text=unit, style="Unit.TLabel").pack(
                side=tk.RIGHT, anchor=tk.S
            )
            self.live_value_labels[key] = value_label

    def _build_log_panel(self, parent: ttk.Panedwindow) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=(9, 7))
        parent.add(panel, weight=1)
        controls = ttk.Frame(panel, style="Panel.TFrame")
        controls.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(controls, text="通信日志", style="Section.TLabel").pack(side=tk.LEFT)
        self.show_telemetry_log = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls,
            text="显示遥测帧",
            variable=self.show_telemetry_log,
        ).pack(side=tk.LEFT, padx=14)
        ttk.Button(controls, text="清空日志", command=self._clear_log).pack(side=tk.RIGHT)
        text_frame = ttk.Frame(panel, style="Panel.TFrame")
        text_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(
            text_frame,
            height=7,
            wrap=tk.NONE,
            background=COLORS["canvas"],
            foreground=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"],
            relief=tk.FLAT,
            padx=8,
            pady=6,
            font=("Consolas", 9),
            state=tk.DISABLED,
        )
        scrollbar_y = ttk.Scrollbar(
            text_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        scrollbar_x = ttk.Scrollbar(
            text_frame, orient=tk.HORIZONTAL, command=self.log_text.xview
        )
        self.log_text.configure(
            yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.log_text.tag_configure("rx", foreground="#70D6FF")
        self.log_text.tag_configure("tx", foreground="#FFD670")
        self.log_text.tag_configure("ok", foreground=COLORS["success"])
        self.log_text.tag_configure("warn", foreground=COLORS["warning"])
        self.log_text.tag_configure("error", foreground=COLORS["danger"])
        self.log_text.tag_configure("muted", foreground=COLORS["muted"])

    def _build_status_bar(self) -> None:
        status = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(12, 4))
        status.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_message = ttk.Label(
            status, text="就绪", style="Muted.TLabel"
        )
        self.status_message.pack(side=tk.LEFT)
        self.counter_label = ttk.Label(
            status, text="RX 0 B / 0 帧   TX 0 B", style="Muted.TLabel"
        )
        self.counter_label.pack(side=tk.RIGHT)

    def _add_default_plots(self) -> None:
        speed_plot = self._add_plot()
        speed_plot.visible_signals = {"m1.speed"}
        current_plot = self._add_plot()
        current_plot.visible_signals = {"m1.current"}
        self.notebook.select(speed_plot)
        self._rebuild_signal_tree()

    def _add_plot(self) -> WaveformPlot:
        number = len(self.plots) + 1
        plot = WaveformPlot(
            self.notebook,
            self.history,
            f"波形窗口 {number}",
            self._close_plot,
            self._sync_signal_tree,
        )
        self.plots.append(plot)
        self.notebook.add(plot, text=f"窗口 {number}")
        self.notebook.select(plot)
        self._sync_signal_tree()
        return plot

    def _close_plot(self, plot: WaveformPlot) -> None:
        if len(self.plots) <= 1:
            self.status_message.configure(text="至少保留一个波形窗口")
            return
        self.notebook.forget(plot)
        self.plots.remove(plot)
        plot.destroy()
        self._renumber_plots()
        self._sync_signal_tree()

    def _renumber_plots(self) -> None:
        """按当前标签页顺序将窗口编号整理为 1..N。"""

        for number, plot in enumerate(self.plots, start=1):
            plot.set_title(f"波形窗口 {number}")
            self.notebook.tab(plot, text=f"窗口 {number}")

    def _active_plot(self) -> Optional[WaveformPlot]:
        selected = self.notebook.select()
        if not selected:
            return None
        widget = self.root.nametowidget(selected)
        return widget if isinstance(widget, WaveformPlot) else None

    def _filtered_signal_keys(self) -> List[str]:
        selected = self.motor_filter.get()
        if selected == "全部信号":
            return list(self.history.keys)
        motor_id = int(selected[1:])
        prefix = f"m{motor_id}."
        return [key for key in self.history.keys if key.startswith(prefix)]

    def _rebuild_signal_tree(self) -> None:
        selected_item = self.signal_tree.focus()
        for item in self.signal_tree.get_children():
            self.signal_tree.delete(item)
        plot = self._active_plot()
        visible = set() if plot is None else plot.visible_signals
        for key in self._filtered_signal_keys():
            label, unit, color = self.history.definition(key)
            latest = self.history.latest(key)
            value = "--" if latest is None else f"{latest:.2f}"
            tag = f"color_{key.replace('.', '_')}"
            self.signal_tree.tag_configure(tag, foreground=color)
            self.signal_tree.insert(
                "",
                tk.END,
                iid=key,
                values=("●" if key in visible else "○", label, value, unit),
                tags=(tag,),
            )
        if selected_item and self.signal_tree.exists(selected_item):
            self.signal_tree.focus(selected_item)

    def _sync_signal_tree(self) -> None:
        if not hasattr(self, "signal_tree"):
            return
        plot = self._active_plot()
        visible = set() if plot is None else plot.visible_signals
        for key in self.signal_tree.get_children():
            values = list(self.signal_tree.item(key, "values"))
            if values:
                values[0] = "●" if key in visible else "○"
                self.signal_tree.item(key, values=values)

    def _toggle_tree_signal(self, event: tk.Event) -> None:
        row = self.signal_tree.identify_row(event.y)
        plot = self._active_plot()
        if not row or plot is None:
            return
        if row in plot.visible_signals:
            plot.visible_signals.remove(row)
        else:
            plot.visible_signals.add(row)
        self._sync_signal_tree()

    def _select_filtered_signals(self) -> None:
        plot = self._active_plot()
        if plot is None:
            return
        plot.visible_signals.update(self._filtered_signal_keys())
        self._sync_signal_tree()

    def _clear_plot_selection(self) -> None:
        plot = self._active_plot()
        if plot is None:
            return
        plot.visible_signals.clear()
        self._sync_signal_tree()

    def _refresh_ports(self) -> None:
        ports, error = list_serial_ports()
        self.port_combo.configure(values=ports)
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])
        elif not ports:
            self.port_var.set("")
        if error:
            self.status_message.configure(text=error)
        elif not ports:
            self.status_message.configure(text="未发现串口设备")
        else:
            self.status_message.configure(text=f"发现 {len(ports)} 个串口")

    def _toggle_serial_connection(self) -> None:
        if self.link.connected or self.link.running:
            self._safe_disconnect()
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("未选择串口", "请选择串口，或使用“启动仿真”进行体验。")
            return
        try:
            baudrate = int(self.baud_var.get())
            self.link.connect_serial(port, baudrate)
            self._set_pending_state("正在连接串口…")
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("连接失败", str(exc))

    def _toggle_simulator(self) -> None:
        if self.link.connected or self.link.running:
            self._safe_disconnect()
            return
        try:
            self.link.connect_simulator(self.motor_count)
            self._set_pending_state("正在启动仿真设备…")
        except RuntimeError as exc:
            messagebox.showerror("启动失败", str(exc))

    def _codex_arm_state(self) -> Dict[str, Any]:
        remaining = max(0.0, self._codex_control_until - time.monotonic())
        armed = remaining > 0.0
        self.codex_bridge_var.set(
            "Codex：控制 {:d}s".format(int(remaining + 0.999))
            if armed
            else "Codex：只读"
        )
        return {
            "armed": armed,
            "remaining_seconds": round(remaining, 1),
            "scope": (
                "configuration-and-motor-control"
                if armed
                else "read-stop-connect"
            ),
        }

    def _refresh_codex_arm_label(self) -> None:
        state = self._codex_arm_state()
        if state["armed"]:
            self.root.after(1000, self._refresh_codex_arm_label)

    def _toggle_codex_control(self) -> None:
        if self._codex_arm_state()["armed"]:
            self._codex_control_until = 0.0
            self._codex_arm_state()
            self._append_log("Codex 控制授权已由用户撤销", "warn")
            return
        confirmed = messagebox.askyesno(
            "授权 Codex 控制",
            (
                "授权后 10 分钟内，Codex 可以修改 PID、目标值和开环配置，"
                "并可发送使能或启动开环指令。\n\n"
                "读取、连接、失能、快速停止和紧急停止不需要此授权。"
                "真实功率级启用时，危险动作仍需额外确认参数。\n\n"
                "是否继续？"
            ),
            parent=self.root,
        )
        if not confirmed:
            return
        self._codex_control_until = time.monotonic() + 600.0
        self._codex_arm_state()
        self.root.after(1000, self._refresh_codex_arm_label)
        self._append_log("Codex 控制授权已开启，有效期 10 分钟", "warn")

    def _require_codex_control(self) -> None:
        if not self._codex_arm_state()["armed"]:
            raise BridgeRequestError(
                "此操作需要用户在上位机点击“Codex：只读”并授权 10 分钟",
                403,
            )

    def _require_codex_power_confirmation(
        self,
        params: Dict[str, Any],
    ) -> None:
        if (
            self._build_power_stage_enabled
            and not bool(params.get("power_stage_confirmed", False))
        ):
            raise BridgeRequestError(
                "固件允许真实功率输出；请在命令中明确传入 "
                "power_stage_confirmed=true",
                403,
            )

    def _send_codex_frame(
        self,
        command: Union[Command, int],
        payload: bytes = b"",
        device: int = 1,
    ) -> Dict[str, Any]:
        if not self.link.connected:
            raise BridgeRequestError("控制器尚未连接", 409)
        sequence = self._next_sequence()
        command_code = int(command)
        try:
            command_name = Command(command_code).name
        except ValueError:
            command_name = "0x{:02X}".format(command_code)
        frame = Frame(
            device_id=device,
            command=command_code,
            sequence=sequence,
            payload=payload,
        )
        transaction = {
            "sequence": sequence,
            "command": command_name,
            "command_code": command_code,
            "state": "pending",
            "write_state": "queued",
            "queued_at": time.time(),
        }
        self._codex_transactions[sequence] = transaction
        try:
            self.link.send(encode_frame(frame))
        except RuntimeError as exc:
            self._codex_transactions.pop(sequence, None)
            raise BridgeRequestError(str(exc), 409)
        self._prune_codex_transactions()
        return dict(transaction)

    def _prune_codex_transactions(self) -> None:
        cutoff = time.time() - 60.0
        stale = [
            sequence
            for sequence, transaction in self._codex_transactions.items()
            if float(transaction.get("queued_at", 0.0)) < cutoff
        ]
        for sequence in stale:
            self._codex_transactions.pop(sequence, None)

    def _record_codex_write(
        self,
        packet: bytes,
        error: Optional[str] = None,
    ) -> None:
        parser = FrameParser()
        frames = parser.feed(packet)
        if len(frames) != 1:
            return
        frame = frames[0]
        transaction = self._codex_transactions.get(frame.sequence)
        if (
            transaction is None
            or transaction.get("command_code") != frame.command
        ):
            return
        if error is None:
            transaction.update(
                {
                    "write_state": "written",
                    "written_at": time.time(),
                }
            )
        else:
            transaction.update(
                {
                    "state": "error",
                    "write_state": "error",
                    "write_error": str(error),
                    "completed_at": time.time(),
                }
            )

    def _record_codex_reply(self, frame: Frame) -> None:
        if frame.command not in (Command.ACK, Command.ERROR):
            return
        if len(frame.payload) < 2:
            return
        original, status = frame.payload[:2]
        transaction = self._codex_transactions.get(frame.sequence)
        if (
            transaction is None
            or transaction.get("command_code") != original
        ):
            return
        transaction.update(
            {
                "state": "ack" if frame.command == Command.ACK else "error",
                "status": int(status),
                "detail_hex": bytes_to_hex(frame.payload[2:]),
                "received_at": time.time(),
            }
        )
        if status == 0:
            try:
                decoded = self._decode_codex_reply(
                    original,
                    frame.payload[2:],
                )
            except (ValueError, struct.error):
                decoded = None
            if decoded is not None:
                transaction["decoded"] = decoded

    @staticmethod
    def _decode_codex_reply(
        original: int,
        detail: bytes,
    ) -> Optional[Dict[str, Any]]:
        if original == Command.PING:
            return {
                "device": detail.decode("ascii", errors="replace")
            }
        if original == Command.GET_DEVICE_INFO and len(detail) == 33:
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
        if original == Command.GET_CAPABILITIES and len(detail) == 9:
            values = struct.unpack("<BBBIH", detail)
            return {
                "motor_count": values[0],
                "backend_mask": values[1],
                "mode_mask": values[2],
                "features": values[3],
                "max_telemetry_hz": values[4],
            }
        if original == Command.GET_LIMITS:
            values = unpack_limits(detail)
            keys = (
                "motor_id",
                "current_limit_a",
                "torque_limit_nm",
                "speed_limit_rad_s",
                "position_min_rad",
                "position_max_rad",
                "bus_voltage_min_v",
                "bus_voltage_max_v",
                "temperature_max_c",
            )
            return dict(zip(keys, values))
        if original == Command.GET_DIAGNOSTICS:
            value = unpack_diagnostics(detail)
            return {
                "payload_bytes": len(detail),
                "rx_scheduler_available": len(detail) == 46,
                "uptime_ms": value.uptime_ms,
                "protocol_errors": value.protocol_errors,
                "fault_bits": value.fault_bits,
                "commands_received": value.commands_received,
                "heartbeat_age_ms": value.heartbeat_age_ms,
                "heartbeat_lease_ms": value.heartbeat_lease_ms,
                "motor_state": value.motor_state,
                "last_stop_reason": value.last_stop_reason,
                "last_stop_reason_text": STOP_REASON_LABELS.get(
                    value.last_stop_reason,
                    "未知",
                ),
                "runtime_flags": value.runtime_flags,
                "hardware_flags": value.hardware_flags,
                "heartbeat_valid": bool(value.runtime_flags & (1 << 0)),
                "enabled": bool(value.runtime_flags & (1 << 1)),
                "open_loop_active": bool(
                    value.runtime_flags & (1 << 2)
                ),
                "output_ready": bool(value.runtime_flags & (1 << 3)),
                "pwm_enabled": bool(
                    value.hardware_flags & HARDWARE_FLAG_PWM_ENABLED
                ),
                "gate_enabled": bool(
                    value.hardware_flags & HARDWARE_FLAG_GATE_ENABLED
                ),
                "nfault_clear": bool(
                    value.hardware_flags & HARDWARE_FLAG_NFAULT_CLEAR
                ),
                "safety_ready": bool(
                    value.hardware_flags & HARDWARE_FLAG_SAFETY_READY
                ),
                "tx_high_priority_failures":
                    value.tx_high_priority_failures,
                "telemetry_drops": value.telemetry_drops,
                "rx_sw_fifo_overflows":
                    value.rx_sw_fifo_overflows,
                "rx_hw_fifo_overflows":
                    value.rx_hw_fifo_overflows,
                "rx_frame_errors": value.rx_frame_errors,
                "rx_parity_errors": value.rx_parity_errors,
                "parser_crc_errors": value.parser_crc_errors,
                "parser_length_errors":
                    value.parser_length_errors,
                "parser_timeout_errors":
                    value.parser_timeout_errors,
                "parser_resync_events":
                    value.parser_resync_events,
                "rx_isr_entries": value.rx_isr_entries,
                "rx_poll_drains": value.rx_poll_drains,
                "rx_poll_bytes": value.rx_poll_bytes,
            }
        if original == Command.GET_TELEMETRY_PROFILE:
            rate_hz, signal_mask = unpack_telemetry_profile(detail)
            return {
                "rate_hz": rate_hz,
                "signal_mask": signal_mask,
            }
        if original == Command.GET_BACKEND_INFO and len(detail) == 2:
            backend, available = struct.unpack("<BB", detail)
            return {
                "backend": "MCU" if backend == 0 else "FPGA",
                "available": bool(available),
            }
        if original == Command.GET_OPEN_LOOP_CONFIG:
            value = unpack_open_loop_config(detail)
            return {
                "motor_id": value.motor_id,
                "backend": value.backend.name,
                "pole_pairs": value.pole_pairs,
                "flags": value.flags,
                "bus_voltage_v": value.bus_voltage_v,
                "voltage_limit_v": value.voltage_limit_v,
                "target_velocity_rad_s":
                    value.target_velocity_rad_s,
                "acceleration_rad_s2": value.acceleration_rad_s2,
                "update_period_ms": value.update_period_ms,
                "startup_delay_ms": value.startup_delay_ms,
                "max_runtime_ms": value.max_runtime_ms,
            }
        if original == Command.GET_BUILD_CONFIG:
            values = unpack_build_config(detail)
            keys = (
                "device_id",
                "control_hardware_enabled",
                "power_stage_enabled",
                "simplefoc_enabled",
                "default_pole_pairs",
                "adc_hz",
                "pwm_hz",
                "isr_hz",
                "outer_loop_hz",
                "default_telemetry_hz",
                "heartbeat_default_ms",
                "heartbeat_min_ms",
                "heartbeat_max_ms",
                "torque_constant_nm_per_a",
                "safety_mask",
            )
            return dict(zip(keys, values))
        return None

    def _codex_status_snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        latest = {
            key: self.history.latest(key)
            for key in self.history.keys
        }
        alarms = [
            {
                "motor_id": alarm.motor_id,
                "level": alarm.level,
                "message": alarm.message,
            }
            for alarm in self.alarms.active
        ]
        telemetry_age_ms = None
        if self._last_telemetry_at > 0.0:
            telemetry_age_ms = int(
                max(0.0, now - self._last_telemetry_at) * 1000.0
            )
        protocol_age_ms = None
        if self._protocol_response_at > 0.0:
            protocol_age_ms = int(
                max(0.0, now - self._protocol_response_at) * 1000.0
            )
        return {
            "connection": {
                "connected": self.link.connected,
                "running": self.link.running,
                "mode": self.link.mode,
                "port": self.port_var.get(),
                "baudrate": self.baud_var.get(),
            },
            "protocol": {
                "rx_bytes": self.rx_bytes,
                "rx_frames": self.rx_frames,
                "tx_bytes": self.tx_bytes,
                "tx_queued_packets": self.link.tx_queued_packets,
                "tx_queued_bytes": self.link.tx_queued_bytes,
                "tx_written_packets": self.link.tx_written_packets,
                "tx_written_bytes": self.link.tx_written_bytes,
                "tx_write_failures": self.link.tx_write_failures,
                "crc_errors": self.parser.crc_errors,
                "last_response_age_ms": protocol_age_ms,
            },
            "diagnostics": (
                dict(self._latest_diagnostics)
                if self._latest_diagnostics is not None
                else None
            ),
            "telemetry": {
                "latest": latest,
                "age_ms": telemetry_age_ms,
            },
            "firmware": {
                "version": (
                    list(self._device_firmware_version)
                    if self._device_firmware_version is not None
                    else None
                ),
                "build_id": self._device_build_id or None,
                "control_hardware_enabled":
                    self._build_control_hardware_enabled,
                "power_stage_enabled":
                    self._build_power_stage_enabled,
                "simplefoc_enabled":
                    self._build_simplefoc_enabled,
                "safety_mask": self._build_safety_mask,
                "features": self._device_features,
            },
            "open_loop_transfer": (
                dict(self._open_loop_transfer_result)
                if self._open_loop_transfer_result is not None
                else None
            ),
            "protection": {
                "software_latched": self._software_protection_latched,
                "automatic_enabled": bool(
                    self.auto_protection_var.get()
                ),
                "response": self.protection_response_var.get(),
                "telemetry_timeout_ms":
                    self.telemetry_timeout_var.get(),
                "heartbeat_lease_ms": self.heartbeat_lease_ms,
                "alarms": alarms,
            },
            "codex_control": self._codex_arm_state(),
            "ui": {
                "status": str(self.status_message.cget("text")),
                "configuration": self.config_status_var.get(),
                "diagnostics": self.diagnostics_var.get(),
                "hardware_layer": self.hardware_layer_var.get(),
            },
        }

    def _codex_logs(self, limit_value: Any) -> Dict[str, Any]:
        try:
            limit = max(1, min(2000, int(limit_value)))
        except (TypeError, ValueError):
            raise BridgeRequestError("limit 必须是 1..2000 的整数")
        lines = self.log_text.get("1.0", "end-1c").splitlines()
        return {"lines": lines[-limit:], "count": min(limit, len(lines))}

    def _codex_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            seconds = max(0.1, min(120.0, float(params.get("seconds", 5))))
            limit = max(1, min(5000, int(params.get("limit", 500))))
        except (TypeError, ValueError):
            raise BridgeRequestError("seconds 或 limit 无效")
        now = time.monotonic()
        cutoff = now - seconds
        rows = [
            {
                "age_ms": int(max(0.0, now - stamp) * 1000.0),
                "signal": key,
                "value": value,
            }
            for stamp, key, value in self.history.export_rows()
            if stamp >= cutoff
        ]
        return {
            "seconds": seconds,
            "rows": rows[-limit:],
            "truncated": len(rows) > limit,
        }

    def _handle_codex_action(
        self,
        action: str,
        params: Dict[str, Any],
    ) -> Any:
        if action == "status":
            return self._codex_status_snapshot()
        if action == "logs":
            return self._codex_logs(params.get("limit", 200))
        if action == "history":
            return self._codex_history(params)
        if action == "ports":
            ports, error = list_serial_ports()
            return {"ports": ports, "error": error}
        if action == "arm_status":
            return self._codex_arm_state()
        if action == "transaction":
            try:
                sequence = int(params.get("sequence"))
            except (TypeError, ValueError):
                raise BridgeRequestError("sequence 必须是 0..255")
            transaction = self._codex_transactions.get(sequence)
            if transaction is None:
                raise BridgeRequestError("没有找到该事务", 404)
            return dict(transaction)

        self._append_log(
            "Codex 请求操作：{}".format(action),
            "warn" if action not in (
                "quick_stop",
                "emergency_stop",
                "disable",
            ) else "error",
        )
        if action == "connect":
            if self.link.connected or self.link.running:
                raise BridgeRequestError("已有连接正在运行", 409)
            port = str(params.get("port", "")).strip()
            if not port:
                raise BridgeRequestError("必须指定串口，例如 COM4")
            try:
                baudrate = int(params.get("baud", 115200))
                self.link.connect_serial(port, baudrate)
            except (TypeError, ValueError, RuntimeError) as exc:
                raise BridgeRequestError(str(exc))
            self.port_var.set(port)
            self.baud_var.set(str(baudrate))
            self._set_pending_state("Codex 正在连接串口…")
            return {"queued": True, "port": port, "baudrate": baudrate}
        if action == "simulator":
            if self.link.connected or self.link.running:
                raise BridgeRequestError("已有连接正在运行", 409)
            self.link.connect_simulator(1)
            self._set_pending_state("Codex 正在启动仿真设备…")
            return {"queued": True}
        if action == "disconnect":
            self._safe_disconnect()
            return {"queued": True}

        direct_queries = {
            "ping": (Command.PING, b"", 1),
            "device_info": (Command.GET_DEVICE_INFO, b"", 1),
            "capabilities": (Command.GET_CAPABILITIES, b"", 1),
            "limits": (Command.GET_LIMITS, b"\x01", 1),
            "telemetry_profile": (
                Command.GET_TELEMETRY_PROFILE,
                b"",
                1,
            ),
            "open_loop_config": (
                Command.GET_OPEN_LOOP_CONFIG,
                b"\x01",
                1,
            ),
            "backend": (Command.GET_BACKEND_INFO, b"", 1),
            "diagnostics": (Command.GET_DIAGNOSTICS, b"\x07", 1),
            "build_config": (Command.GET_BUILD_CONFIG, b"", 1),
        }
        if action in direct_queries:
            command, payload, device = direct_queries[action]
            return self._send_codex_frame(command, payload, device)
        if action == "read_config":
            raise BridgeRequestError(
                "read_config 必须逐条等待设备确认；"
                "请使用 codex_client read-config",
                409,
            )
        if action == "quick_stop":
            return self._send_codex_frame(
                Command.QUICK_STOP,
                b"\x01",
                1,
            )
        if action == "emergency_stop":
            self._software_protection_latched = True
            return self._send_codex_frame(
                Command.EMERGENCY_STOP,
                b"\xFF",
                0xFF,
            )
        if action == "disable":
            return self._send_codex_frame(
                Command.SET_ENABLE,
                pack_enable(1, False),
                1,
            )

        self._require_codex_control()
        if action == "clear_fault":
            return self._send_codex_frame(
                Command.CLEAR_FAULT,
                b"\x01",
                1,
            )
        if action == "enable":
            if self._software_protection_latched:
                raise BridgeRequestError(
                    "软件保护已锁定，请先排除原因并清除故障",
                    409,
                )
            if self._build_control_hardware_enabled is not True:
                raise BridgeRequestError(
                    "尚未确认固件允许控制硬件输出；请先读取 build-config",
                    409,
                )
            self._require_codex_power_confirmation(params)
            return self._send_codex_frame(
                Command.SET_ENABLE,
                pack_enable(1, True),
                1,
            )
        if action == "set_target":
            modes = {
                "torque": ControlMode.TORQUE,
                "speed": ControlMode.SPEED,
                "position": ControlMode.POSITION,
                "open-loop-speed": ControlMode.OPEN_LOOP_SPEED,
            }
            mode = modes.get(str(params.get("mode", "")))
            if mode is None:
                raise BridgeRequestError("mode 无效")
            try:
                value = float(params["value"])
            except (KeyError, TypeError, ValueError):
                raise BridgeRequestError("value 必须是数字")
            if not math.isfinite(value):
                raise BridgeRequestError("value 不能是 NaN 或无穷大")
            target_request = (
                Command.SET_TARGET,
                pack_target(1, mode, value),
                1,
            )
            if mode == ControlMode.OPEN_LOOP_SPEED:
                return self._send_codex_frame(*target_request)
            return {
                "transactions": [
                    self._send_codex_frame(
                        Command.SET_MODE,
                        pack_mode(1, mode),
                        1,
                    ),
                    self._send_codex_frame(*target_request),
                ]
            }
        if action == "set_pid":
            loops = {
                "current": PidLoop.CURRENT,
                "speed": PidLoop.SPEED,
                "position": PidLoop.POSITION,
            }
            loop = loops.get(str(params.get("loop", "")))
            if loop is None:
                raise BridgeRequestError("loop 无效")
            try:
                values = (
                    float(params["kp"]),
                    float(params["ki"]),
                    float(params["kd"]),
                )
            except (KeyError, TypeError, ValueError):
                raise BridgeRequestError("kp、ki、kd 必须是数字")
            if not all(math.isfinite(value) for value in values):
                raise BridgeRequestError("PID 不能包含 NaN 或无穷大")
            return self._send_codex_frame(
                Command.SET_PID,
                pack_pid(1, loop, *values),
                1,
            )
        if action == "configure_open_loop":
            try:
                config = OpenLoopConfig(
                    1,
                    OpenLoopBackend.SIMPLEFOC,
                    int(params.get("pole_pairs", 7)),
                    0,
                    float(params.get("bus_voltage", 7.0)),
                    float(params.get("voltage_limit", 0.3)),
                    float(params.get("target_velocity", 5.0)),
                    float(params.get("acceleration", 10.0)),
                    int(params.get("update_period_ms", 10)),
                    int(params.get("startup_delay_ms", 500)),
                    int(params.get("max_runtime_ms", 30000)),
                )
                if config.bus_voltage_v > 8.0:
                    raise ValueError("母线电压不能超过 8 V")
                if config.voltage_limit_v > 2.0:
                    raise ValueError("开环电压限幅不能超过 2 V")
                if abs(config.target_velocity_rad_s) > 100.0:
                    raise ValueError("开环速度绝对值不能超过 100 rad/s")
            except (TypeError, ValueError) as exc:
                raise BridgeRequestError(str(exc))
            transfer = self._begin_open_loop_config_transfer(
                config,
                False,
            )
            if transfer is None:
                raise BridgeRequestError(
                    "无法启动开环配置分片传输",
                    409,
                )
            return {
                "queued": True,
                "transfer_token": transfer["token"],
                "generation": transfer["generation"],
                "fragments": len(transfer["fragments"]),
            }
        if action == "start_open_loop":
            if self._software_protection_latched:
                raise BridgeRequestError(
                    "软件保护已锁定，请先排除原因并清除故障",
                    409,
                )
            if self._build_control_hardware_enabled is not True:
                raise BridgeRequestError(
                    "尚未确认固件允许控制硬件输出；请先读取 build-config",
                    409,
                )
            config = self._device_open_loop_config
            if (
                config is not None
                and config.backend == OpenLoopBackend.SIMPLEFOC
                and self._build_simplefoc_enabled is not True
            ):
                raise BridgeRequestError(
                    "固件未确认启用 SimpleFOC",
                    409,
                )
            self._require_codex_power_confirmation(params)
            if self._build_power_stage_enabled and config is None:
                raise BridgeRequestError(
                    "尚未精确回读设备开环参数；请先读取或配置 open-loop-config",
                    409,
                )
            try:
                if config is None:
                    start_payload = pack_start_open_loop(1)
                else:
                    start_payload = self._open_loop_start_payload(
                        config,
                        bool(params.get("power_stage_confirmed", False)),
                    )
            except ValueError as exc:
                raise BridgeRequestError(str(exc), 409)
            return self._send_codex_frame(
                Command.START_OPEN_LOOP,
                start_payload,
                1,
            )
        raise BridgeRequestError("不支持的 Codex 操作：{}".format(action), 404)

    def _safe_disconnect(self) -> None:
        if not self.link.connected:
            self.link.disconnect()
            return
        self._software_protection_latched = True
        self._send_frame(
            Command.QUICK_STOP,
            b"\x01",
            1,
            quiet=True,
        )
        self.status_message.configure(
            text="正在快速停止电机并断开连接…"
        )
        self.root.after(120, self.link.disconnect)

    def _set_pending_state(self, message: str) -> None:
        self.connection_status.configure(
            text=f"● {message}", foreground=COLORS["warning"]
        )
        self.connect_button.configure(text="断开")
        self.sim_button.configure(text="停止")

    def _set_connection_state(self, connected: bool, detail: str) -> None:
        if not connected:
            self._build_control_hardware_enabled = None
            self._build_power_stage_enabled = None
            self._build_simplefoc_enabled = None
            self._build_safety_mask = None
            self._device_open_loop_config = None
            self.hardware_layer_var.set(
                "连接层级：控制硬件未连接｜功率硬件未确认"
            )
        self.connection_status.configure(
            text=f"● {detail}",
            foreground=COLORS["success"] if connected else COLORS["muted"],
        )
        self.connect_button.configure(
            text="断开" if connected else "连接控制硬件"
        )
        self.sim_button.configure(
            text="停止仿真" if connected and self.link.mode == "simulator" else "启动仿真"
        )

    def _selected_motor_id(self) -> int:
        return int(self.selected_motor.get()[1:])

    def _store_active_pid_values(self) -> bool:
        try:
            values = (
                float(self.kp_var.get()),
                float(self.ki_var.get()),
                float(self.kd_var.get()),
            )
        except ValueError:
            return False
        self.pid_values[
            (self._active_pid_motor_id, self._active_pid_loop)
        ] = values
        return True

    def _load_active_pid_values(self) -> None:
        kp, ki, kd = self.pid_values[
            (self._active_pid_motor_id, self._active_pid_loop)
        ]
        self.kp_var.set(f"{kp:.3f}")
        self.ki_var.set(f"{ki:.3f}")
        self.kd_var.set(f"{kd:.3f}")

    def _on_motor_changed(self, _event: tk.Event) -> None:
        if not self._store_active_pid_values():
            self.status_message.configure(text="上一组 PID 含无效数字，未保存本次编辑")
        self._active_pid_motor_id = self._selected_motor_id()
        self._load_active_pid_values()

    def _on_pid_loop_changed(self, _event: tk.Event) -> None:
        if not self._store_active_pid_values():
            self.status_message.configure(text="上一组 PID 含无效数字，未保存本次编辑")
        self._active_pid_loop = PID_LOOP_FROM_LABEL[self.pid_loop.get()]
        self._load_active_pid_values()

    def _update_target_unit(self, _event: Optional[tk.Event] = None) -> None:
        unit = {
            "转矩": "N·m",
            "速度": "rad/s",
            "位置": "rad",
            "开环速度": "rad/s",
        }.get(self.control_mode.get(), "")
        self.target_label.configure(text=f"目标值（{unit}）")

    def _next_sequence(self) -> int:
        value = self.sequence
        self.sequence = (self.sequence + 1) & 0xFF
        return value

    def _send_frame(
        self,
        command: Union[Command, int],
        payload: bytes = b"",
        device: int = 0,
        quiet: bool = False,
    ) -> bool:
        if not self.link.connected:
            self.status_message.configure(text="请先连接串口或启动仿真")
            return False
        frame = Frame(
            device_id=device,
            command=int(command),
            sequence=self._next_sequence(),
            payload=payload,
        )
        try:
            self.link.send(encode_frame(frame), quiet=quiet)
        except RuntimeError as exc:
            self.status_message.configure(text=str(exc))
            return False
        return True

    def _send_enable(self, enabled: bool) -> None:
        if enabled and self._software_protection_latched:
            messagebox.showerror(
                "保护已锁定",
                "软件保护已触发，排除原因并清除故障后才能再次使能。",
            )
            return
        motor_id = self._selected_motor_id()
        if self._send_frame(
            Command.SET_ENABLE, pack_enable(motor_id, enabled), motor_id
        ):
            action = "使能" if enabled else "失能"
            self.status_message.configure(text=f"已发送 M{motor_id} {action}指令")

    def _send_target(self) -> None:
        motor_id = self._selected_motor_id()
        try:
            target = float(self.target_value.get())
            mode = MODE_FROM_LABEL[self.control_mode.get()]
        except (ValueError, KeyError):
            messagebox.showerror("参数错误", "目标值必须是有效数字。")
            return
        mode_sent = True
        if mode != ControlMode.OPEN_LOOP_SPEED:
            mode_sent = self._send_frame(
                Command.SET_MODE, pack_mode(motor_id, mode), motor_id
            )
        if mode_sent and self._send_frame(
            Command.SET_TARGET,
            pack_target(motor_id, mode, target),
            motor_id,
        ):
            self.status_message.configure(
                text=f"已发送 M{motor_id} {MODE_LABELS[mode]}目标 {target:g}"
            )

    def _send_pid(self) -> None:
        motor_id = self._selected_motor_id()
        try:
            kp = float(self.kp_var.get())
            ki = float(self.ki_var.get())
            kd = float(self.kd_var.get())
            loop = PID_LOOP_FROM_LABEL[self.pid_loop.get()]
        except (ValueError, KeyError):
            messagebox.showerror("参数错误", "Kp、Ki、Kd 必须是有效数字。")
            return
        self.pid_values[(motor_id, loop)] = (kp, ki, kd)
        self._active_pid_motor_id = motor_id
        self._active_pid_loop = loop
        if self._send_frame(
            Command.SET_PID, pack_pid(motor_id, loop, kp, ki, kd), motor_id
        ):
            self.status_message.configure(
                text=f"已发送 M{motor_id} {PID_LOOP_LABELS[loop]} PID 参数"
            )

    def _send_ping(self) -> None:
        self._send_frame(Command.PING, device=self._selected_motor_id())

    def _query_device_info(self) -> None:
        self._send_frame(Command.GET_DEVICE_INFO, device=1)

    def _query_capabilities(self) -> None:
        self._send_frame(Command.GET_CAPABILITIES, device=1)

    def _calibrate_all(self) -> None:
        if self._send_frame(
            Command.CALIBRATE,
            pack_calibrate(1, CalibrationType.ALL),
            1,
        ):
            self.status_message.configure(text="已发送电机全量校准指令")

    def _clear_fault(self) -> None:
        if self._send_frame(Command.CLEAR_FAULT, b"\x01", 1):
            self.status_message.configure(text="已发送清除故障指令")

    def _save_config(self) -> None:
        if self._send_frame(Command.SAVE_CONFIG, b"", 1):
            self.status_message.configure(text="已发送保存参数指令")
            self._set_config_status("正在将当前配置保存到设备 Flash…")

    def _heartbeat_tick(self) -> None:
        try:
            if self.link.connected:
                now = time.monotonic()
                try:
                    telemetry_timeout_ms = int(
                        self.telemetry_timeout_var.get()
                    )
                except ValueError:
                    telemetry_timeout_ms = 1000
                telemetry_reference = max(
                    self._last_telemetry_at,
                    self._telemetry_watchdog_armed_at,
                )
                if (
                    self.auto_protection_var.get()
                    and not self._software_protection_latched
                    and self._telemetry_watchdog_armed_at > 0.0
                    and telemetry_reference > 0.0
                    and (now - telemetry_reference) * 1000.0
                    > telemetry_timeout_ms
                ):
                    self._trigger_software_protection(
                        "遥测超过 {} ms 未更新".format(
                            telemetry_timeout_ms
                        )
                    )
                elif (
                    self._protocol_response_at == 0.0
                    and self._connected_at > 0.0
                    and not self._no_response_reported
                    and (now - self._connected_at) * 1000.0
                    > telemetry_timeout_ms
                ):
                    self._no_response_reported = True
                    message = (
                        "串口已打开，但设备未返回 V2 协议数据；"
                        "请检查固件、波特率和 TX/RX 接线。"
                    )
                    self.status_message.configure(text=message)
                    self._append_log(message, "warn")
                elif (
                    self._protocol_response_at > 0.0
                    and self._last_telemetry_at == 0.0
                    and not self._no_telemetry_reported
                    and (now - self._connected_at) * 1000.0
                    > telemetry_timeout_ms
                ):
                    self._no_telemetry_reported = True
                    message = "设备已有协议响应，但尚未收到遥测帧。"
                    self.status_message.configure(text=message)
                    self._append_log(message, "warn")
                if not self._software_protection_latched:
                    host_time_ms = int(now * 1000) & 0xFFFFFFFF
                    self._send_frame(
                        Command.HEARTBEAT,
                        pack_heartbeat(
                            host_time_ms,
                            self.heartbeat_lease_ms,
                        ),
                        1,
                        quiet=True,
                    )
        finally:
            self.root.after(250, self._heartbeat_tick)

    def _read_parameters(self) -> None:
        motor_id = self._selected_motor_id()
        loop = PID_LOOP_FROM_LABEL[self.pid_loop.get()]
        if self._send_frame(
            Command.GET_PID, bytes((motor_id, int(loop))), motor_id
        ):
            self.status_message.configure(
                text=f"正在读取 M{motor_id} {PID_LOOP_LABELS[loop]} PID"
            )

    def _emergency_stop(self) -> None:
        self._software_protection_latched = True
        if self._send_frame(Command.EMERGENCY_STOP, b"\xFF", 0xFF):
            self.status_message.configure(text="已发送电机紧急停止指令")
            self._append_log("紧急停止指令已发送（广播）", "error")

    def _controlled_stop(self) -> None:
        motor_id = self._selected_motor_id()
        if self._send_frame(
            Command.CONTROLLED_STOP, bytes((motor_id,)), motor_id
        ):
            self.status_message.configure(text="已发送受控减速停止指令")
            self._append_log("受控停止：按配置加速度降至零", "warn")

    def _quick_stop(self) -> None:
        motor_id = self._selected_motor_id()
        if self._send_frame(
            Command.QUICK_STOP, bytes((motor_id,)), motor_id
        ):
            self.status_message.configure(text="已发送快速停止指令")
            self._append_log("快速停止：立即撤销输出", "warn")

    def _trigger_software_protection(self, reason: str) -> None:
        if self._software_protection_latched:
            return
        self._software_protection_latched = True
        response = self.protection_response_var.get()
        if response == "紧急停止":
            command = Command.EMERGENCY_STOP
            payload = b"\xFF"
            device = 0xFF
        elif response == "受控停止":
            command = Command.CONTROLLED_STOP
            payload = b"\x01"
            device = 1
        else:
            command = Command.QUICK_STOP
            payload = b"\x01"
            device = 1
        self._send_frame(command, payload, device)
        self.status_message.configure(text="软件保护已触发：{}".format(reason))
        self._set_config_status(
            "软件保护已锁定并执行{}：{}。排除原因后清除故障。".format(
                response,
                reason,
            )
        )
        self._append_log(
            "软件保护触发（{}）：{}".format(response, reason),
            "error",
        )

    def _send_raw(self) -> None:
        if not self.link.connected:
            self.status_message.configure(text="请先建立连接")
            return
        try:
            packet = hex_to_bytes(self.raw_hex.get())
            if not packet:
                raise ValueError("发送内容不能为空")
            self.link.send(packet)
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("发送失败", str(exc))

    def _poll_link(self) -> None:
        try:
            for event in self.link.poll():
                if event.kind == "connected":
                    self.parser.reset()
                    self._connected_at = time.monotonic()
                    self._last_telemetry_at = 0.0
                    self._protocol_response_at = 0.0
                    self._telemetry_watchdog_armed_at = 0.0
                    self._no_response_reported = False
                    self._no_telemetry_reported = False
                    self._software_protection_latched = False
                    self._pending_open_loop_start = None
                    self._open_loop_transfer = None
                    self._open_loop_transfer_token += 1
                    self._build_config_query_generation += 1
                    self._build_config_query_started_at = 0.0
                    self._build_control_hardware_enabled = None
                    self._build_power_stage_enabled = None
                    self._build_simplefoc_enabled = None
                    self._build_safety_mask = None
                    self._device_firmware_version = None
                    self._device_build_id = ""
                    self._device_features = None
                    self._latest_diagnostics = None
                    self._device_open_loop_config = None
                    self.hardware_layer_var.set(
                        "连接层级：控制硬件未确认｜功率硬件未确认"
                    )
                    self.build_config_var.set("固件宏：未读取")
                    self.alarms.clear()
                    self._set_alarm_display()
                    self._set_connection_state(True, str(event.data))
                    self.status_message.configure(text=f"已连接：{event.data}")
                    self._append_log(f"连接成功：{event.data}", "ok")
                    self.root.after(
                        120,
                        self._query_device_info,
                    )
                    self.root.after(
                        220,
                        lambda: self._send_if_connected(
                            Command.GET_CAPABILITIES, b"", 1
                        ),
                    )
                    self.root.after(320, self._query_build_config)
                elif event.kind == "disconnected":
                    if self._open_loop_transfer is not None:
                        self._open_loop_transfer["result"].update(
                            {
                                "state": "error",
                                "message": "连接在开环配置传输期间断开。",
                                "completed_at": time.time(),
                            }
                        )
                    self._codex_control_until = 0.0
                    self._codex_arm_state()
                    self._connected_at = 0.0
                    self._last_telemetry_at = 0.0
                    self._protocol_response_at = 0.0
                    self._telemetry_watchdog_armed_at = 0.0
                    self._no_response_reported = False
                    self._no_telemetry_reported = False
                    self._pending_open_loop_start = None
                    self._open_loop_transfer = None
                    self._open_loop_transfer_token += 1
                    self._build_config_query_generation += 1
                    self._build_config_query_started_at = 0.0
                    self._build_control_hardware_enabled = None
                    self._build_power_stage_enabled = None
                    self._build_simplefoc_enabled = None
                    self._build_safety_mask = None
                    self._device_firmware_version = None
                    self._device_build_id = ""
                    self._device_features = None
                    self._latest_diagnostics = None
                    self._device_open_loop_config = None
                    self.hardware_layer_var.set(
                        "连接层级：控制硬件未确认｜功率硬件未确认"
                    )
                    self.build_config_var.set("固件宏：未读取")
                    self._set_connection_state(False, "未连接")
                    self.status_message.configure(text="连接已断开")
                    self._append_log("连接已断开", "muted")
                elif event.kind == "error":
                    self.status_message.configure(text=f"通信错误：{event.data}")
                    self._append_log(f"错误：{event.data}", "error")
                elif event.kind == "tx_write_error":
                    info = dict(event.data)
                    self._record_codex_write(
                        bytes(info.get("packet", b"")),
                        str(info.get("message", "未知错误")),
                    )
                    self.status_message.configure(
                        text="串口写入失败：{}".format(
                            info.get("message", "未知错误")
                        )
                    )
                    self._append_log(
                        "TX WRITE ERROR requested={} B written={} B: {}".format(
                            info.get("requested", 0),
                            info.get("written", 0),
                            info.get("message", ""),
                        ),
                        "error",
                    )
                elif event.kind == "tx_written":
                    info = dict(event.data)
                    packet = bytes(info.get("packet", b""))
                    written = int(info.get("written", len(packet)))
                    self._record_codex_write(packet)
                    self.tx_bytes += written
                    if not bool(info.get("quiet", False)):
                        self._append_log(
                            "TXW {:4d} B  {}".format(
                                written,
                                bytes_to_hex(packet, 96),
                            ),
                            "tx",
                        )
                elif event.kind == "rx":
                    packet = bytes(event.data)
                    self.rx_bytes += len(packet)
                    frames = self.parser.feed(packet)
                    for frame in frames:
                        self.rx_frames += 1
                        self._handle_frame(frame)
                    if self.parser.crc_errors > self._last_parser_crc_errors:
                        delta = self.parser.crc_errors - self._last_parser_crc_errors
                        self._last_parser_crc_errors = self.parser.crc_errors
                        self._append_log(f"检测到 {delta} 个 CRC 错误帧", "warn")
            self.counter_label.configure(
                text=(
                    "RX {:,} B / {:,} 帧   TXW {:,} B / {:,} 帧   写失败 {}"
                ).format(
                    self.rx_bytes,
                    self.rx_frames,
                    self.tx_bytes,
                    self.link.tx_written_packets,
                    self.link.tx_write_failures,
                )
            )
        finally:
            self.root.after(20, self._poll_link)

    def _handle_frame(self, frame: Frame) -> None:
        self._protocol_response_at = time.monotonic()
        self._no_response_reported = False
        self._record_codex_reply(frame)
        if frame.command == Command.TELEMETRY:
            try:
                telemetry = unpack_telemetry(frame.payload)
            except ValueError as exc:
                self._append_log(f"遥测解析失败：{exc}", "error")
                return
            self.history.append_telemetry(telemetry)
            self._last_telemetry_at = time.monotonic()
            if self._telemetry_watchdog_armed_at == 0.0:
                self._telemetry_watchdog_armed_at = (
                    self._last_telemetry_at
                )
            self._no_telemetry_reported = False
            self.recorder.write(telemetry)
            raised, cleared = self.alarms.evaluate(telemetry)
            for alarm in raised:
                self._append_log(f"告警：{alarm.message}", "error")
            if raised and self.auto_protection_var.get():
                self._trigger_software_protection(
                    "；".join(alarm.message for alarm in raised)
                )
            for alarm in cleared:
                self._append_log(f"恢复：{alarm.message.split('：')[0]}", "ok")
            if raised or cleared:
                self._set_alarm_display()
            if self.show_telemetry_log.get():
                self._append_log(
                    f"RX 遥测 M{telemetry.motor_id}  "
                    f"n={telemetry.speed_rpm:.1f} rpm  "
                    f"I={telemetry.current_a:.2f} A  "
                    f"U={telemetry.voltage_v:.2f} V  "
                    f"T={telemetry.temperature_c:.1f} °C",
                    "rx",
                )
            return

        if frame.command in (Command.ACK, Command.ERROR):
            if len(frame.payload) >= 2:
                original, status = frame.payload[:2]
                detail = frame.payload[2:]
                if original == Command.HEARTBEAT and status == 0:
                    return
                tag = "ok" if frame.command == Command.ACK and status == 0 else "error"
                message = (
                    f"RX {'ACK' if tag == 'ok' else 'ERROR'}  "
                    f"cmd=0x{original:02X} seq={frame.sequence} status={status}"
                )
                if original in (
                    Command.SET_OPEN_LOOP_CONFIG_PART,
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    Command.GET_OPEN_LOOP_CONFIG,
                ):
                    self._handle_open_loop_transfer_reply(
                        original,
                        status,
                        frame.sequence,
                        detail,
                    )
                configuration_commands = (
                    Command.SET_LIMITS,
                    Command.GET_LIMITS,
                    Command.SAVE_CONFIG,
                    Command.RESTORE_DEFAULTS,
                    Command.GET_DIAGNOSTICS,
                    Command.SET_TELEMETRY_PROFILE,
                    Command.GET_BACKEND_INFO,
                    Command.GET_TELEMETRY_PROFILE,
                    Command.SET_OPEN_LOOP_CONFIG,
                    Command.SET_OPEN_LOOP_CONFIG_PART,
                    Command.COMMIT_OPEN_LOOP_CONFIG,
                    Command.GET_OPEN_LOOP_CONFIG,
                    Command.START_OPEN_LOOP,
                    Command.GET_BUILD_CONFIG,
                )
                if status != 0 and original in configuration_commands:
                    if original == Command.SET_OPEN_LOOP_CONFIG:
                        self._pending_open_loop_start = None
                    if original == Command.GET_BUILD_CONFIG:
                        self._build_config_query_generation += 1
                        self._build_config_query_started_at = 0.0
                        self._set_config_status(
                            "设备拒绝命令 0x29（错误码 {}）；"
                            "请 Clean 后烧录最新固件。".format(status)
                        )
                    else:
                        self._set_config_status(
                            f"设备拒绝配置命令 0x{original:02X}，错误码 {status}。"
                        )
                if original == Command.PING and detail:
                    message += f"  device={detail.decode('ascii', errors='replace')}"
                elif original == Command.GET_DEVICE_INFO and len(detail) == 33:
                    (
                        fw_major,
                        fw_minor,
                        fw_patch,
                        hw_major,
                        hw_minor,
                        serial_number,
                        name,
                        build_id,
                    ) = struct.unpack("<BBBBBI16s8s", detail)
                    device_name = name.rstrip(b"\x00").decode(
                        "ascii", errors="replace"
                    )
                    build_name = build_id.rstrip(b"\x00").decode(
                        "ascii", errors="replace"
                    )
                    self._device_firmware_version = (
                        fw_major,
                        fw_minor,
                        fw_patch,
                    )
                    self._device_build_id = build_name
                    message += (
                        f"  {device_name} FW {fw_major}.{fw_minor}.{fw_patch} "
                        f"HW {hw_major}.{hw_minor} SN={serial_number:08X} "
                        f"build={build_name}"
                    )
                elif original == Command.GET_CAPABILITIES and len(detail) == 9:
                    motor_count, backend_mask, mode_mask, features, max_rate = (
                        struct.unpack("<BBBIH", detail)
                    )
                    self._device_features = int(features)
                    message += (
                        f"  motors={motor_count} backend=0x{backend_mask:02X} "
                        f"modes=0x{mode_mask:02X} features=0x{features:08X} "
                        f"telemetry≤{max_rate} Hz"
                    )
                    if motor_count != 1:
                        self._append_log(
                            "能力不匹配：当前上位机仅支持单电机 MCU 模式",
                            "warn",
                        )
                elif (
                    original == Command.GET_LIMITS
                    and status == 0
                    and len(detail) == 33
                ):
                    values = unpack_limits(detail)
                    value_keys = (
                        "current",
                        "torque",
                        "speed",
                        "position_min",
                        "position_max",
                        "bus_min",
                        "bus_max",
                        "temperature",
                    )
                    for key, value in zip(value_keys, values[1:]):
                        self.limit_vars[key].set(f"{value:g}")
                    self.alarms.configure(
                        values[1],
                        values[8],
                        values[6],
                        values[7],
                    )
                    message += (
                        f"  I≤{values[1]:g} A, T≤{values[2]:g} N·m, "
                        f"ω≤{values[3]:g} rad/s, Temp≤{values[8]:g} °C"
                    )
                    self._set_config_status("设备限值已读取并显示。")
                elif (
                    original == Command.GET_DIAGNOSTICS
                    and status == 0
                ):
                    try:
                        diagnostics = unpack_diagnostics(detail)
                    except ValueError as exc:
                        self._set_config_status(str(exc))
                    else:
                        self._latest_diagnostics = (
                            self._decode_codex_reply(original, detail)
                        )
                        stop_reason = STOP_REASON_LABELS.get(
                            diagnostics.last_stop_reason,
                            "未知({})".format(
                                diagnostics.last_stop_reason
                            ),
                        )
                        self.diagnostics_var.set(
                            (
                                "运行 {:.1f} s｜协议错误 {}｜故障 0x{:04X}｜"
                                "状态 {}｜停止原因 {}｜HB {}/{} ms｜"
                                "HW 0x{:02X}｜"
                                "ACK失败 {}｜遥测丢弃 {}｜"
                                "RX溢出 SW/HW {}/{}｜帧/奇偶 {}/{}｜"
                                "解析 CRC/LEN/TO/同步 {}/{}/{}/{}｜"
                                "RX调度 ISR/轮询/字节 {}/{}/{}"
                            ).format(
                                diagnostics.uptime_ms / 1000.0,
                                diagnostics.protocol_errors,
                                diagnostics.fault_bits,
                                diagnostics.motor_state,
                                stop_reason,
                                diagnostics.heartbeat_age_ms,
                                diagnostics.heartbeat_lease_ms,
                                diagnostics.hardware_flags,
                                diagnostics.tx_high_priority_failures,
                                diagnostics.telemetry_drops,
                                diagnostics.rx_sw_fifo_overflows,
                                diagnostics.rx_hw_fifo_overflows,
                                diagnostics.rx_frame_errors,
                                diagnostics.rx_parity_errors,
                                diagnostics.parser_crc_errors,
                                diagnostics.parser_length_errors,
                                diagnostics.parser_timeout_errors,
                                diagnostics.parser_resync_events,
                                diagnostics.rx_isr_entries,
                                diagnostics.rx_poll_drains,
                                diagnostics.rx_poll_bytes,
                            )
                        )
                        message += (
                            "  uptime={} ms protocol_errors={} "
                            "fault=0x{:04X} commands={} "
                            "stop={} hb_age={} ms hardware=0x{:02X} "
                            "tx_ack_fail={} "
                            "telem_drop={} rx_sw_ovf={} rx_hw_ovf={} "
                            "frame_err={} parity_err={} "
                            "parser_crc={} parser_len={} parser_timeout={} "
                            "parser_resync={} rx_isr_entries={} "
                            "rx_poll_drains={} rx_poll_bytes={}"
                        ).format(
                            diagnostics.uptime_ms,
                            diagnostics.protocol_errors,
                            diagnostics.fault_bits,
                            diagnostics.commands_received,
                            stop_reason,
                            diagnostics.heartbeat_age_ms,
                            diagnostics.hardware_flags,
                            diagnostics.tx_high_priority_failures,
                            diagnostics.telemetry_drops,
                            diagnostics.rx_sw_fifo_overflows,
                            diagnostics.rx_hw_fifo_overflows,
                            diagnostics.rx_frame_errors,
                            diagnostics.rx_parity_errors,
                            diagnostics.parser_crc_errors,
                            diagnostics.parser_length_errors,
                            diagnostics.parser_timeout_errors,
                            diagnostics.parser_resync_events,
                            diagnostics.rx_isr_entries,
                            diagnostics.rx_poll_drains,
                            diagnostics.rx_poll_bytes,
                        )
                        self._set_config_status("诊断信息已刷新。")
                elif (
                    original == Command.GET_BACKEND_INFO
                    and status == 0
                    and len(detail) == 2
                ):
                    backend, available = struct.unpack("<BB", detail)
                    backend_name = "MCU" if backend == 0 else "FPGA"
                    self.backend_info_var.set(
                        "控制后端：{}｜{}｜FPGA 控制未开放".format(
                            backend_name,
                            "可用" if available else "不可用",
                        )
                    )
                    message += (
                        f"  backend={backend_name} "
                        f"available={bool(available)}"
                    )
                elif (
                    original == Command.GET_TELEMETRY_PROFILE
                    and status == 0
                    and len(detail) == 6
                ):
                    rate_hz, signal_mask = unpack_telemetry_profile(detail)
                    self.telemetry_rate_var.set(str(rate_hz))
                    message += (
                        f"  rate={rate_hz} Hz mask=0x{signal_mask:08X}"
                    )
                    self._set_config_status("设备遥测配置已读取并显示。")
                elif (
                    original == Command.GET_OPEN_LOOP_CONFIG
                    and status == 0
                ):
                    try:
                        config = unpack_open_loop_config(detail)
                    except ValueError as exc:
                        self._set_config_status(str(exc))
                    else:
                        self._device_open_loop_config = config
                        self.open_loop_backend_var.set(
                            OPEN_LOOP_BACKEND_LABELS[config.backend]
                        )
                        open_loop_values = {
                            "pole_pairs": config.pole_pairs,
                            "bus_voltage": config.bus_voltage_v,
                            "voltage_limit": config.voltage_limit_v,
                            "target_velocity":
                                config.target_velocity_rad_s,
                            "acceleration": config.acceleration_rad_s2,
                            "update_period": config.update_period_ms,
                            "startup_delay": config.startup_delay_ms,
                            "max_runtime": config.max_runtime_ms,
                        }
                        for key, value in open_loop_values.items():
                            self.open_loop_vars[key].set(
                                "{:g}".format(value)
                            )
                        message += (
                            "  backend={} Ubus={:g} V Ulimit={:g} V "
                            "target={:g} rad/s"
                        ).format(
                            OPEN_LOOP_BACKEND_LABELS[config.backend],
                            config.bus_voltage_v,
                            config.voltage_limit_v,
                            config.target_velocity_rad_s,
                        )
                        self._set_config_status(
                            "设备开环参数已读取并显示。"
                        )
                elif (
                    original == Command.GET_BUILD_CONFIG
                    and status == 0
                ):
                    self._build_config_query_generation += 1
                    self._build_config_query_started_at = 0.0
                    try:
                        values = unpack_build_config(detail)
                    except ValueError as exc:
                        self._set_config_status(str(exc))
                    else:
                        (
                            device_id,
                            control_hardware_enabled,
                            power_stage_enabled,
                            simplefoc_enabled,
                            default_pole_pairs,
                            adc_hz,
                            pwm_hz,
                            isr_hz,
                            outer_hz,
                            default_telemetry_hz,
                            heartbeat_default_ms,
                            heartbeat_min_ms,
                            heartbeat_max_ms,
                            torque_constant,
                            safety_mask,
                        ) = values
                        self._build_control_hardware_enabled = bool(
                            control_hardware_enabled
                        )
                        self._build_power_stage_enabled = bool(
                            power_stage_enabled
                        )
                        self._build_simplefoc_enabled = bool(
                            simplefoc_enabled
                        )
                        self._build_safety_mask = int(safety_mask)
                        missing_safety = (
                            POWER_STAGE_REQUIRED_SAFETY_MASK
                            & ~int(safety_mask)
                        )
                        commissioning_override = bool(
                            int(safety_mask)
                            & POWER_STAGE_COMMISSIONING_OVERRIDE
                        )
                        if not control_hardware_enabled:
                            layer_text = (
                                "连接层级：控制器通信已连接，但 MCU PWM 被固件锁定｜"
                                "功率硬件被锁定"
                            )
                        elif power_stage_enabled:
                            if commissioning_override:
                                layer_text = (
                                    "连接层级：控制硬件已允许｜功率级调试旁路已启用"
                                    "（仅允许保守参数）"
                                )
                            elif missing_safety:
                                layer_text = (
                                    "连接层级：功率级编译已允许，但安全清单缺少 "
                                    "0x{:03X}｜启动已锁定"
                                ).format(missing_safety)
                            else:
                                layer_text = (
                                    "连接层级：控制硬件已允许｜功率级安全清单完整"
                                    "（启动仍需运行诊断与明确确认）"
                                )
                        else:
                            layer_text = (
                                "连接层级：控制硬件已允许（仅 MCU PWM）｜"
                                "功率硬件被固件锁定"
                            )
                        self.hardware_layer_var.set(layer_text)
                        self.build_config_var.set(
                            (
                                "固件宏：DEVICE={}｜CONTROL_HW={}｜POWER_STAGE={}｜"
                                "SIMPLEFOC={}｜"
                                "PP={}｜ADC/PWM/ISR={}/{}/{} Hz｜"
                                "OUTER={} Hz｜TELEM={} Hz｜HB={}"
                                " ({}..{}) ms｜Kt={:g} N·m/A｜SAFETY=0x{:08X}"
                            ).format(
                                device_id,
                                control_hardware_enabled,
                                power_stage_enabled,
                                simplefoc_enabled,
                                default_pole_pairs,
                                adc_hz,
                                pwm_hz,
                                isr_hz,
                                outer_hz,
                                default_telemetry_hz,
                                heartbeat_default_ms,
                                heartbeat_min_ms,
                                heartbeat_max_ms,
                                torque_constant,
                                safety_mask,
                            )
                        )
                        message += (
                            "  control_hw={} power_stage={} simplefoc={} "
                            "pwm={} Hz safety=0x{:08X}"
                        ).format(
                            control_hardware_enabled,
                            power_stage_enabled,
                            simplefoc_enabled,
                            pwm_hz,
                            safety_mask,
                        )
                elif (
                    original == Command.SET_OPEN_LOOP_CONFIG
                    and status == 0
                ):
                    pending = self._pending_open_loop_start
                    if pending is not None:
                        self._pending_open_loop_start = None
                        self._set_config_status(
                            "兼容命令 0x26 已应用，但不会自动启动；"
                            "请使用分片提交、精确回读和安全确认流程。"
                        )
                    else:
                        self._set_config_status(
                            "开环参数已应用；运行中只允许修改目标速度。"
                        )
                elif (
                    original == Command.START_OPEN_LOOP
                    and status == 0
                ):
                    self._telemetry_watchdog_armed_at = time.monotonic()
                    self._set_config_status(
                        "开环已启动；可发送开环速度目标，停止按钮始终有效。"
                    )
                    self.status_message.configure(text="设备已进入开环运行")
                elif original == Command.SET_ENABLE and status == 0:
                    self._telemetry_watchdog_armed_at = time.monotonic()
                elif original == Command.CONTROLLED_STOP and status == 0:
                    self.status_message.configure(text="设备正在受控减速停止")
                elif original == Command.QUICK_STOP and status == 0:
                    self._telemetry_watchdog_armed_at = 0.0
                    self.status_message.configure(text="设备已快速停止")
                elif original == Command.EMERGENCY_STOP and status == 0:
                    self._telemetry_watchdog_armed_at = 0.0
                    self.status_message.configure(text="设备已进入急停状态")
                elif original == Command.CLEAR_FAULT and status == 0:
                    self._software_protection_latched = False
                    self._last_telemetry_at = time.monotonic()
                    self.alarms.clear()
                    self._set_alarm_display()
                    self.status_message.configure(text="故障与软件保护锁定已清除")
                elif original == Command.SET_LIMITS and status == 0:
                    self._set_config_status(
                        "安全限值已应用到运行参数；如需掉电保存，请点击“保存到 Flash”。"
                    )
                elif (
                    original == Command.SET_TELEMETRY_PROFILE
                    and status == 0
                ):
                    self._set_config_status(
                        f"遥测频率已设置为 {self.telemetry_rate_var.get()} Hz。"
                    )
                elif original == Command.SAVE_CONFIG and status == 0:
                    self._set_config_status("配置已保存到设备 Flash。")
                elif original == Command.RESTORE_DEFAULTS and status == 0:
                    self._set_config_status("默认配置已恢复，正在重新读取设备参数…")
                    self._send_frame(Command.GET_LIMITS, b"\x01", 1)
                    for loop in (
                        PidLoop.CURRENT,
                        PidLoop.SPEED,
                        PidLoop.POSITION,
                    ):
                        self._send_frame(
                            Command.GET_PID,
                            bytes((1, int(loop))),
                            1,
                        )
                elif original == Command.GET_PID and len(detail) in (12, 13):
                    if len(detail) == 13:
                        loop_value, kp, ki, kd = struct.unpack("<Bfff", detail)
                        loop = PidLoop(loop_value)
                    else:
                        # 兼容未返回环路编号的旧固件。
                        kp, ki, kd = struct.unpack("<fff", detail)
                        loop = PID_LOOP_FROM_LABEL[self.pid_loop.get()]
                    motor_id = frame.device_id
                    self.pid_values[(motor_id, loop)] = (kp, ki, kd)
                    message += (
                        f"  {PID_LOOP_LABELS[loop]} "
                        f"Kp={kp:.3f}, Ki={ki:.3f}, Kd={kd:.3f}"
                    )
                    if (
                        motor_id == self._selected_motor_id()
                        and loop == PID_LOOP_FROM_LABEL[self.pid_loop.get()]
                    ):
                        self._active_pid_motor_id = motor_id
                        self._active_pid_loop = loop
                        self._load_active_pid_values()
                self._append_log(message, tag)
            else:
                self._append_log(
                    f"RX cmd=0x{frame.command:02X}  {bytes_to_hex(frame.payload)}",
                    "rx",
                )
            return

        self._append_log(
            f"RX cmd=0x{frame.command:02X} seq={frame.sequence} "
            f"payload={bytes_to_hex(frame.payload, 96)}",
            "rx",
        )

    def _render_plots(self) -> None:
        now = time.monotonic()
        for plot in self.plots:
            if plot.winfo_ismapped():
                plot.render(now)
        self.root.after(50, self._render_plots)

    def _refresh_values(self) -> None:
        motor_id = self._selected_motor_id()
        for suffix, label in self.live_value_labels.items():
            value = self.history.latest(f"m{motor_id}.{suffix}")
            label.configure(text="--" if value is None else f"{value:.2f}")

        for key in self.signal_tree.get_children():
            values = list(self.signal_tree.item(key, "values"))
            if len(values) >= 3:
                latest = self.history.latest(key)
                values[2] = "--" if latest is None else f"{latest:.2f}"
                self.signal_tree.item(key, values=values)
        self.root.after(200, self._refresh_values)

    def _set_alarm_display(self) -> None:
        active = self.alarms.active
        self.alarm_text.configure(state=tk.NORMAL)
        self.alarm_text.delete("1.0", tk.END)
        if not active:
            self.alarm_text.insert(tk.END, "当前无活动告警")
            self.alarm_text.configure(foreground=COLORS["muted"])
        else:
            for alarm in active:
                self.alarm_text.insert(tk.END, f"• {alarm.message}\n")
            self.alarm_text.configure(foreground=COLORS["danger"])
        self.alarm_text.configure(state=tk.DISABLED)

    def _toggle_recording(self) -> None:
        if self.recorder.active:
            path = self.recorder.path
            self.recorder.stop()
            self.record_button.configure(text="开始记录", style="TButton")
            self.status_message.configure(text=f"记录已保存：{path}")
            return
        default_name = datetime.now().strftime("motor_data_%Y%m%d_%H%M%S.csv")
        selected = filedialog.asksaveasfilename(
            title="保存实时数据",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=(("CSV 文件", "*.csv"), ("所有文件", "*.*")),
        )
        if not selected:
            return
        try:
            self.recorder.start(selected)
        except OSError as exc:
            messagebox.showerror("无法开始记录", str(exc))
            return
        self.record_button.configure(text="停止记录", style="Success.TButton")
        self.status_message.configure(text=f"正在记录：{selected}")

    def _export_history(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="导出波形缓存",
            defaultextension=".csv",
            initialfile=datetime.now().strftime("waveform_cache_%Y%m%d_%H%M%S.csv"),
            filetypes=(("CSV 文件", "*.csv"), ("所有文件", "*.*")),
        )
        if not selected:
            return
        rows = self.history.export_rows()
        try:
            with Path(selected).open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(("monotonic_time_s", "signal", "label", "unit", "value"))
                for stamp, key, value in rows:
                    label, unit, _ = self.history.definition(key)
                    writer.writerow((f"{stamp:.6f}", key, label, unit, f"{value:.6f}"))
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        self.status_message.configure(text=f"已导出 {len(rows):,} 条数据：{selected}")

    def _clear_history(self) -> None:
        self.history.clear()
        self.status_message.configure(text="波形缓存已清空")

    def _append_log(self, message: str, tag: str = "muted") -> None:
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{stamp}  {message}\n", tag)
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 2000:
            self.log_text.delete("1.0", "501.0")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_close(self) -> None:
        if self._shutdown_pending:
            return
        self._shutdown_pending = True
        self.recorder.stop()
        if self.link.connected:
            self._software_protection_latched = True
            self._send_frame(
                Command.EMERGENCY_STOP,
                b"\xFF",
                0xFF,
                quiet=True,
            )
            self.status_message.configure(
                text="正在发送急停并关闭软件…"
            )
            self.root.after(120, self._finalize_close)
            return
        self._finalize_close()

    def _finalize_close(self) -> None:
        if self._codex_bridge is not None:
            self._codex_bridge.stop()
            self._codex_bridge = None
        self.link.close()
        self.root.destroy()


def run() -> None:
    root = tk.Tk()
    MotorStudioApp(root)
    root.mainloop()
