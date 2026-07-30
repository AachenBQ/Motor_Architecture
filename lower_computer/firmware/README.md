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

## 功率级接入门禁与首次启动流程

功率级不是“连接串口后再勾选”的运行时选项，而是独立的编译期安全层。
推荐按以下顺序推进，不能跳级：

1. **控制板示波器阶段**
   - 保持 `MOTOR_CONTROL_HARDWARE_ENABLED=1`、
     `MOTOR_POWER_STAGE_ENABLED=0`；
   - 不连接功率板，只检查三相 TOUT 的频率、相位、占空比和安全停止；
   - `GET_BUILD_CONFIG (0x29)` 必须报告 `power_stage_enabled=0`；
   - `GET_DIAGNOSTICS (0x22)` 的 `hardware_flags.gate_enabled` 必须始终为 0；
   - 发送 `QUICK_STOP (0x1C)` 后，在 ACK 到达前 PWM 和 gate 必须均已关闭。

2. **逐项完成安全证据**
   - 三相电流采样、零偏、极性和软件过流；
   - 母线电压采样及欠压/过压；
   - 功率温度采样及过温；
   - CPU watchdog；
   - 独立于软件的物理急停；
   - 外部硬件限流；
   - DRV8313 nFAULT/gate 监测；
   - 心跳超时关断；
   - PWM/gate 安全输出路径。

   只有实际实现并在硬件上验证一项后，才能把对应的
   `MOTOR_*_READY` 宏改为 1。完整安全掩码为 `0x000001FF`。
   `MOTOR_POWER_STAGE_ENABLED=1` 且未启用 override 时，只要缺少任意一项，
   `project_config.h` 就会在编译期阻止构建。

3. **受限 commissioning（确有必要时）**
   - 只能在限流电源、外部硬件限流和可立即操作的物理急停均到位时使用；
   - 显式设置 `MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE=1`，不得把它作为
     默认发布配置；
   - `0x29.safety_mask` 的 bit31 会置位，缺失的 bit0–8 仍保持为 0；
   - 每次启动都必须重新由操作者确认，并发送
     `START_OPEN_LOOP` payload `01 01`；
   - 首次测试建议额外限制为电压不高于 0.10 V、速度不高于 1 rad/s、
     加速度不高于 1 rad/s²、单次运行不超过 1000 ms。

4. **完整功率级阶段**
   - 所有安全位均完成后使用 `MOTOR_POWER_STAGE_ENABLED=1`、
     `MOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE=0`；
   - 烧录后先读 `0x29`，确认 `power_stage_enabled=1` 且
     `(safety_mask & 0x1FF) == 0x1FF`；
   - 再读 `0x22`，确认 `power_stage_build=1`、`safety_ready=1`、
     `nFAULT_clear=1`、`pwm_enabled=0`、`gate_enabled=0`；
   - 建立并持续发送心跳，通过 `0x2A/0x2B` 写入低风险参数，再用 `0x27`
     回读逐字段核对；
   - 操作者完成真实功率级确认后才发送 `0x28: 01 01`；
   - 测试结束发送 `0x1C` 并重新读取诊断，必须观察到 PWM/gate 均为 0。

`start_flags` 的确认位不会绕过任何保护。未知 flag、缺少功率级确认、启动前
PWM/gate 状态不安静、活动硬件故障、心跳无效或参数超限都会拒绝启动。
闭环 `SET_ENABLE` 还要求编码器、电流采样和闭环控制实现均标记为 ready。

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

命令路由、安全字段和立即停止可在 host HAL stub 上以两种编译模式回归；
第二种只是电脑侧模拟，不会访问或使能真实硬件：

```powershell
$routerSources = @(
  "tests/test_command_router.c",
  "firmware/src/command_router.c",
  "firmware/src/motor_control.c",
  "firmware/src/native_protocol.c",
  "tests/host/tc375_hal_stub.c"
)

gcc -std=c11 -Wall -Wextra -Werror `
  -DMOTOR_CONTROL_HARDWARE_ENABLED=1 `
  -DMOTOR_POWER_STAGE_ENABLED=0 -DMOTOR_USE_SIMPLEFOC=1 `
  -Ifirmware/config -Ifirmware/include -Itests/host `
  $routerSources -o tests/router_control_test.exe
.\tests\router_control_test.exe

gcc -std=c11 -Wall -Wextra -Werror `
  -DMOTOR_CONTROL_HARDWARE_ENABLED=1 `
  -DMOTOR_POWER_STAGE_ENABLED=1 `
  -DMOTOR_POWER_STAGE_COMMISSIONING_OVERRIDE=1 `
  -DMOTOR_USE_SIMPLEFOC=1 `
  -Ifirmware/config -Ifirmware/include -Itests/host `
  $routerSources -o tests/router_power_override_test.exe
.\tests\router_power_override_test.exe
```

两次均应输出 `lower_computer command router: OK`。测试覆盖 `0x28`
确认位、`0x29.safety_mask`、诊断 `hardware_flags`、分片配置原子提交以及
`QUICK_STOP` 返回前关闭 PWM/gate。

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
