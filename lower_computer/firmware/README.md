# TC375 FreeRTOS Single-Motor Firmware

这是 MCU 模式的可移植固件骨架。它已经固定为：

- 一台电机，地址 `1`；
- FreeRTOS 应用入口，以及 TASKING ADS 使用的协作式运行入口；
- 原生 UART 协议 v2；
- SimpleFOC 单实例；
- FOC 快环在 PWM/ADC 中断中运行；
- FPGA 仅初始化并检查 QSPI 预留接口，不参与控制。

## Directory

```text
app/                 FreeRTOS 静态任务与 TASKING 协作式运行入口
config/              电机、控制频率和安全默认值
include/             协议、状态机和 TC375 HAL 接口
src/                 无动态内存的协议解析、命令路由和电机状态机
simplefoc_port/       SimpleFOC 与 TC375 HAL 的单实例适配入口
drivers/qspi_fpga/    FPGA QSPI 预留与回环自检
```

## Integration order

1. 在 AURIX Development Studio 或现有 iLLD 工程中加入这些源文件。
2. 实现 `tc375_hal.h` 的 GTM、EVADC、编码器、ASCLIN、Flash 和安全关断。
3. TASKING ADS 先调用 `Firmware_CooperativeInit()` 并周期执行
   `Firmware_CooperativePoll()`；拥有已验证的 TriCore FreeRTOS port 后
   可改用 `Firmware_CreateStaticTasks()`。
4. 在 PWM/ADC 同步中断中调用 `Firmware_FocAdcIsr()`。
5. 在 `simplefoc_tc375_port.cpp` 中绑定实际 SimpleFOC 版本和自定义
   Driver、Sensor、CurrentSense。
6. 保持 `MOTOR_CONTROL_HARDWARE_ENABLED=1`、
   `MOTOR_POWER_STAGE_ENABLED=0` 完成控制板 PWM 联调；硬件参数、电流极性、
   保护和物理急停全部验证后，才单独评审是否允许功率级。

## Third-party libraries

当前已作为 git submodule 下载并固定：

- FreeRTOS-Kernel `V11.3.0`：`third_party/FreeRTOS-Kernel`
- SimpleFOC / Arduino-FOC `v2.4.0`：`third_party/Arduino-FOC`
- Infineon iLLD `1.0.1.20.0` / TC37A，来自 AURIX Development Studio
  `tricore-tc3xx` project-initializer `1.16-17`：
  `third_party/infineon/iLLD_1_0_1_20_0_TC37A`

FreeRTOS 包中包含 `portable/GCC/TriCore_1782`，可作为 TC375/TriCore 接入起点。
它不是 TASKING TriCore port；当前 TASKING 真机工程使用等价的协作式协议
运行时，不直接启动 FreeRTOS。
PC 侧 smoke test 使用 `portable/MSVC-MingW` 仅验证静态任务创建和链接边界。

iLLD/ADS 侧入口在 `firmware/bsp/tc37a_ads` 和
`cmake/aurix_ads_illd.cmake`。当前已生成 `Ifx_Cfg.h`，选择
`DEVICE_TC37X` 和 TC375 Lite 模板中的 `IFX_PIN_PACKAGE_LQFP176`；如果实物
封装不同，需要先改这里再做真机编译。

SimpleFOC 通过 `simplefoc_port` 下的固定 C 接口隔离；当前已有静态
`BLDCMotor`、`Tc375BldcDriver`、`Tc375CurrentSense`、`Tc375Encoder`
骨架、最小 `Arduino.h` 兼容层和 TASKING ADS 编译包装。SimpleFOC v2.4.0
核心已进入真机工程。默认 `MOTOR_CONTROL_HARDWARE_ENABLED=1`、
`MOTOR_POWER_STAGE_ENABLED=0`、`MOTOR_USE_SIMPLEFOC=1`：GTM 可以输出三相
PWM，但 DRV8313 gate 在编译期锁定，未接功率板时也不会把 nFAULT 作为活动故障。

开环调试不再依赖修改 `Cpu0_Main.c` 中的测试宏：协议 v2 提供开环参数
读写、启动和运行中目标速度更新。直接三相正弦模式不要求编码器，
SimpleFOC 开环模式要求固件已链接 SimpleFOC 且极对数与编译配置一致。
母线电压、电压限幅、速度和最长运行时间同时受 `project_config.h` 中
不可在线提高的硬上限约束。心跳超时、测量限值、nFAULT 和最长运行时间
都会撤销输出。

`tc375_hal_ads.c` 已实现 ASCLIN0 中断式 UART，默认使用 P14.0 TX、
P14.1 RX、115200 8N1；具体接线、宏和构建步骤见
[bsp/tc37a_ads/README.md](bsp/tc37a_ads/README.md)。ADC、编码器和 Flash
仍有待按实际板卡补齐。ADC 未实现时不存在有效的软件过流保护，首次功率
测试必须使用限流电源和物理急停。

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
- `Firmware_CooperativeInit()`、轮询入口和安全状态；
- host HAL stub。

它验证控制板模式下 PWM 可以输出、gate 始终关闭。真机闭环还需要补齐
EVADC、编码器、Flash 和板级保护参数后再评审
`MOTOR_POWER_STAGE_ENABLED=1`。

不接功率板的 SimpleFOC PWM 检查步骤见
[docs/OPEN_LOOP_COMMISSIONING.md](../docs/OPEN_LOOP_COMMISSIONING.md)。
