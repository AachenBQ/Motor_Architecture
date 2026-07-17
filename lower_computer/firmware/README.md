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

## Third-party libraries

当前已作为 git submodule 下载并固定：

- FreeRTOS-Kernel `V11.3.0`：`third_party/FreeRTOS-Kernel`
- SimpleFOC / Arduino-FOC `v2.4.0`：`third_party/Arduino-FOC`
- Infineon iLLD `1.0.1.20.0` / TC37A，来自 AURIX Development Studio
  `tricore-tc3xx` project-initializer `1.16-17`：
  `third_party/infineon/iLLD_1_0_1_20_0_TC37A`

FreeRTOS 包中包含 `portable/GCC/TriCore_1782`，可作为 TC375/TriCore 接入起点。
PC 侧 smoke test 使用 `portable/MSVC-MingW` 仅验证静态任务创建和链接边界。

iLLD/ADS 侧入口在 `firmware/bsp/tc37a_ads` 和
`cmake/aurix_ads_illd.cmake`。当前已生成 `Ifx_Cfg.h`，选择
`DEVICE_TC37X` 和 TC375 Lite 模板中的 `IFX_PIN_PACKAGE_LQFP176`；如果实物
封装不同，需要先改这里再做真机编译。

SimpleFOC 通过 `simplefoc_port` 下的固定 C 接口隔离；当前已有静态
`BLDCMotor`、`Tc375BldcDriver`、`Tc375CurrentSense`、`Tc375Encoder`
骨架和最小 `Arduino.h` 兼容层，可在 PC 上编译 SimpleFOC 核心算法。
由于功率板引脚、采样拓扑、编码器型号和保护参数尚未给出，默认
`MOTOR_REAL_HARDWARE_ENABLED=0`，即使 `MOTOR_USE_SIMPLEFOC=1` 也不会打开 gate。

协议解析和状态机可以在电脑上做快速回归：

```powershell
gcc -std=c11 -Ifirmware/include -Ifirmware/config `
  tests/test_core.c firmware/src/native_protocol.c firmware/src/motor_control.c `
  -o tests/core_test.exe
.\tests\core_test.exe
```

完整 PC 侧集成 smoke test：

```powershell
git submodule update --init --recursive
cmake -S . -B build/host -G "MinGW Makefiles"
cmake --build build/host --parallel
ctest --test-dir build/host --output-on-failure
```

该 smoke test 会编译并链接：

- FreeRTOS host port；
- SimpleFOC 核心子集；
- TC375 SimpleFOC adapter；
- `Firmware_CreateStaticTasks()` 和 `Firmware_FocAdcIsr()`；
- host HAL stub。

它验证当前无真实硬件配置时 gate/PWM 保持关闭。真机闭环还需要补齐
Infineon iLLD/BSP、GTM/EVADC/ASCLIN/Flash 实现和板级参数后再开启
`MOTOR_REAL_HARDWARE_ENABLED=1`。
