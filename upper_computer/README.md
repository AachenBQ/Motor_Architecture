# Motor Studio

一个用于 AURIX TC375 单电机控制器联调的中文桌面上位机。包含多窗口实时波形、原生串口协议 v2、电机指令、三环 PID、设备配置、心跳、数据记录、告警、通信日志和单电机仿真设备。

## 快速启动

支持 Python 3.6 及以上版本，推荐使用 Python 3.11 或更高版本。

```powershell
python -m pip install -r requirements.txt
python -m motor_control
```

Windows 也可以双击 `run.bat`。如果只使用仿真模式，界面无需 `pyserial` 也能运行；安装 `pyserial` 后才可枚举和连接真实串口。

## Codex 联调接口

上位机启动后会创建仅限本机访问的安全调试桥，使 Codex 可以在不争抢串口的
情况下读取状态、日志、最近遥测和设备诊断，也可以执行失能、快速停止和紧急
停止。修改参数、使能或启动开环需要用户在界面点击“Codex：只读”进行 10 分钟
授权；真实功率级启用时还需要命令显式确认。

完整命令和安全说明见 [Codex 接入说明](CODEX_DEBUG.md)。例如：

```powershell
python -m motor_control.codex_client status
python -m motor_control.codex_client diagnostics
python -m motor_control.codex_client logs --limit 100
```

如果电脑上已经安装 Python 3.6，可以直接使用现有环境；项目没有使用
`from __future__ import annotations`、内置泛型或 `dataclasses` 等新版本限定功能。

启动后点击“启动仿真”，选择右侧目标值并点击“发送目标值”，再点击“使能”，即可看到曲线响应。速度和位置指令分别使用 `rad/s` 与 `rad`，遥测显示使用 `rpm` 与角度。

右上角“设备配置”可读取和修改电流、转矩、速度、位置、电压、温度限值，
设置遥测频率，并查看 MCU/FPGA 后端与诊断状态。“应用限值”只修改运行
参数，确认无误后需要点击“保存到 Flash”才能掉电保留。电机使能时固件会
拒绝修改限值、保存或恢复默认配置。

“开环调试参数”可在线配置直接三相正弦或 SimpleFOC 开环、极对数、母线
电压、电压限幅、初始速度、加速度、更新周期、启动延时和最长运行时间。
除目标速度外，开环参数必须先停止再修改；运行中在主界面选择“开环速度”
即可实时调速。参数写入使用 14 个 16 字节短帧和一个 15 字节原子提交帧，
逐片确认并自动重试，避免旧 `0x26` 的 39 字节长帧在弱接收链路上丢失。
当前默认选择 SimpleFOC。PWM/ADC/ISR 频率、
`MOTOR_CONTROL_HARDWARE_ENABLED`、`MOTOR_POWER_STAGE_ENABLED` 和
`MOTOR_USE_SIMPLEFOC` 属于编译期安全参数，只读显示，不能在线修改。

串口按钮只负责“连接控制硬件”，不代表功率板或母线已经连接。上位机连接后
会自动读取固件分层状态，并在“设备配置”中分别显示：

- 控制硬件：允许 MCU 的 GTM/PWM 引脚输出，供示波器检查；
- 功率硬件：允许释放 DRV8313 nSLEEP/nRESET，真实电机可能动作。

默认固件为“控制硬件允许、功率硬件锁定”，可以在不接功率板和母线的情况下
检查 P00.0、P00.2、P00.3 三路 20 kHz PWM。启动开环前界面会根据固件状态
显示不同的确认提示；未读取到分层状态时禁止启动。

## 项目结构

```text
motor_control/
  protocol.py   帧编解码、CRC、命令与遥测载荷
  transport.py  串口后台线程和动态仿真设备
  data.py       环形缓存、CSV 记录与告警
  ui.py         Tkinter 桌面界面和实时绘图
tests/
  test_protocol.py
  test_transport.py
```

产品需求见 [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)，上下位机共享的完整帧格式见 [Native Protocol v2](../lower_computer/protocol/NATIVE_PROTOCOL_V2.md)。

## 运行测试

```powershell
python -m unittest discover -v
```

烧录支持分片协议的固件后，还可在不使能、不启动 PWM 的情况下通过运行中的
上位机执行真实串口压力测试：

```powershell
python -m motor_control.codex_client communication-test --iterations 20
```

## 接入实际控制器

当前协议已经与下位机需求统一为 v2。固件接入时主要核对 `motor_control/protocol.py` 与共享协议：

1. 调整 `encode_frame()` 和 `FrameParser` 的帧结构与校验。
2. 修改 `Command` 命令字。
3. 修改 `pack_*` 指令载荷与 `unpack_telemetry()` 遥测载荷。
4. 用实际串口日志补充协议测试，再连接设备。

通信线程、波形缓存和界面无需跟随协议整体重写。

## 安全说明

主界面提供受控停止、快速停止和广播急停。主动断开前发送快速停止，正常
关闭软件前发送广播急停；阈值、设备故障状态或遥测超时可触发可配置的软件
保护，触发后停止心跳，让 MCU 心跳超时保护成为最终兜底。

“串口已打开”不等于“下位机协议已连通”。刚连接且尚未收到任何有效协议帧
时，界面会提示检查固件、波特率和 TX/RX 接线，不会把空闲设备误报成遥测
保护；收到首个遥测帧或运行确认后，遥测超时保护才进入监控。

本项目仍用于研发联调，不应作为唯一的安全保护。真实设备必须在控制器固件
和硬件侧实现过流、过温、母线电压、通信超时、失控检测、DRV8313 nFAULT
和物理急停链路。当前唯一电机地址为 `1`，广播 `FF` 只用于安全停止类命令。
ADC/编码器仍为 BSP 集成项时，上位机不能替代硬件保护。TC375 ADS 示例已
接入 ASCLIN0 P14.0/P14.1、115200 8N1，板卡实际映射不同时需修改 BSP 配置。
