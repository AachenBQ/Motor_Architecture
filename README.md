# TC375 Motor Control Project

本仓库同时管理 TC375 单电机控制系统的上位机和下位机。

## Directory Structure

```text
upper_computer/   桌面上位机、协议 v2、单电机仿真器和自动测试
lower_computer/   FreeRTOS 单电机固件骨架、TC375 HAL 和 FPGA 接口预留
```

上位机的安装、启动和协议说明见
[upper_computer/README.md](upper_computer/README.md)。

## Quick Start

```powershell
cd upper_computer
python -m pip install -r requirements.txt
python -m motor_control
```

Windows 也可以直接双击 `upper_computer/run.bat`。
