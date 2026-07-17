# Lower Computer Firmware

该目录用于 AURIX TC375 Lite 单电机控制器的下位机固件、FPGA
预留接口和硬件相关资料。

当前已确定的主要方向：

- FreeRTOS + 原生 ASCLIN UART 协议作为第一阶段通信方案。
- 单电机 PMSM/BLDC SimpleFOC 移植。
- MCU 完成 ADC、编码器、FOC 和 PWM。
- micro-ROS 延后到电机闭环稳定后评估。
- 只预留 TC375 QSPI、同步、故障和复位接口，不实现 FPGA FOC。
- 电流/速度/位置控制、参数配置、遥测和安全状态机。

完整需求见
[docs/LOWER_COMPUTER_REQUIREMENTS.md](docs/LOWER_COMPUTER_REQUIREMENTS.md)。
共享通信定义见
[protocol/NATIVE_PROTOCOL_V2.md](protocol/NATIVE_PROTOCOL_V2.md)，可移植固件骨架和
接入顺序见 [firmware/README.md](firmware/README.md)。

当前目录：

```text
lower_computer/
  firmware/       FreeRTOS 应用、协议、状态机、HAL 和 SimpleFOC 适配入口
  protocol/       与上位机共享的协议定义
  docs/           固件架构和硬件接口文档
```

当前尚未确定电机、功率板、编码器和最终编译工具链，因此
不能安全生成真实引脚、采样极性和死区配置。固件默认
`MOTOR_REAL_HARDWARE_ENABLED=0`，协议和状态机可以集成验证，但不会打开
gate；板级参数完成评审后再启用真实功率输出。
