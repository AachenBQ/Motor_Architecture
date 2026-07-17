# Motor Studio

一个用于 AURIX TC375 单电机控制器联调的中文桌面上位机。包含多窗口实时波形、原生串口协议 v2、电机指令、三环 PID、设备配置、心跳、数据记录、告警、通信日志和单电机仿真设备。

## 快速启动

支持 Python 3.6 及以上版本，推荐使用 Python 3.11 或更高版本。

```powershell
python -m pip install -r requirements.txt
python -m motor_control
```

Windows 也可以双击 `run.bat`。如果只使用仿真模式，界面无需 `pyserial` 也能运行；安装 `pyserial` 后才可枚举和连接真实串口。

如果电脑上已经安装 Python 3.6，可以直接使用现有环境；项目没有使用
`from __future__ import annotations`、内置泛型或 `dataclasses` 等新版本限定功能。

启动后点击“启动仿真”，选择右侧目标值并点击“发送目标值”，再点击“使能”，即可看到曲线响应。速度和位置指令分别使用 `rad/s` 与 `rad`，遥测显示使用 `rpm` 与角度。

右上角“设备配置”可读取和修改电流、转矩、速度、位置、电压、温度限值，
设置遥测频率，并查看 MCU/FPGA 后端与诊断状态。“应用限值”只修改运行
参数，确认无误后需要点击“保存到 Flash”才能掉电保留。电机使能时固件会
拒绝修改限值、保存或恢复默认配置。

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

## 接入实际控制器

当前协议已经与下位机需求统一为 v2。固件接入时主要核对 `motor_control/protocol.py` 与共享协议：

1. 调整 `encode_frame()` 和 `FrameParser` 的帧结构与校验。
2. 修改 `Command` 命令字。
3. 修改 `pack_*` 指令载荷与 `unpack_telemetry()` 遥测载荷。
4. 用实际串口日志补充协议测试，再连接设备。

通信线程、波形缓存和界面无需跟随协议整体重写。

## 安全说明

本项目当前用于研发联调，不应作为唯一的安全保护。真实设备必须在控制器固件和硬件侧实现过流、过温、通信超时、失控检测和急停链路。当前唯一电机地址为 `1`，广播 `FF` 只用于安全停止类命令。
