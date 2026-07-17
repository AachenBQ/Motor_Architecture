# TC375 FreeRTOS Single-Motor Firmware

这是 MCU 模式的可移植固件骨架。它已经固定为：

- 一台电机，地址 `1`；
- FreeRTOS 调度；
- 原生 UART 协议 v2；
- SimpleFOC 单实例；
- FOC 快环在 PWM/ADC 中断中运行；
- FPGA 仅初始化并检查 QSPI 预留接口，不参与控制。

## Directory

```text
app/                 FreeRTOS 静态任务与 ISR 接口
config/              电机、控制频率和安全默认值
include/             协议、状态机和 TC375 HAL 接口
src/                 无动态内存的协议解析、命令路由和电机状态机
simplefoc_port/       SimpleFOC 与 TC375 HAL 的单实例适配入口
drivers/qspi_fpga/    FPGA QSPI 预留与回环自检
```

## Integration order

1. 在 AURIX Development Studio 或现有 iLLD 工程中加入这些源文件。
2. 实现 `tc375_hal.h` 的 GTM、EVADC、编码器、ASCLIN、Flash 和安全关断。
3. 将官方/已验证的 TriCore FreeRTOS port 接入并调用
   `Firmware_CreateStaticTasks()`。
4. 在 PWM/ADC 同步中断中调用 `Firmware_FocAdcIsr()`。
5. 在 `simplefoc_tc375_port.cpp` 中绑定实际 SimpleFOC 版本和自定义
   Driver、Sensor、CurrentSense。
6. 保持 `MOTOR_REAL_HARDWARE_ENABLED=0` 完成无功率输出联调；硬件参数、
   电流极性、死区和保护全部验证后才改为 `1`。

当前代码不包含 Infineon iLLD、FreeRTOS 或 SimpleFOC 第三方源码，也没有
猜测功率板引脚。缺少这些板级信息时，gate enable 必须保持关闭。

协议解析和状态机可以在电脑上做快速回归：

```powershell
gcc -std=c11 -Ifirmware/include -Ifirmware/config `
  tests/test_core.c firmware/src/native_protocol.c firmware/src/motor_control.c `
  -o tests/core_test.exe
.\tests\core_test.exe
```
