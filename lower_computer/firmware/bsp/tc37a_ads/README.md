# TC375 ADS BSP

此工程是 `AURIX TC375 Lite + TASKING Debug` 的真机入口。默认启动
Native Protocol v2 协作式运行循环，已接入：

- ASCLIN0 中断式 UART 收发；
- 协议解析、ACK/ERROR、设备信息和能力查询；
- 心跳、遥测、三环 PID、限值和开环配置；
- 快速停止、急停、通信超时、nFAULT 和安全 PWM/gate 状态；
- 共享 `motor_control`、`command_router` 和 SimpleFOC 边界。

## 默认串口

| 项目 | 默认值 |
|---|---|
| ASCLIN | ASCLIN0 |
| MCU TX | P14.0 / `IfxAsclin0_TX_P14_0_OUT` |
| MCU RX | P14.1 / `IfxAsclin0_RXA_P14_1_IN` |
| 格式 | 115200, 8 data bits, no parity, 1 stop bit |
| TX/RX 软件 FIFO | 各 4096 bytes |
| TX/RX/ERR 中断优先级 | 8 / 9 / 10 |

外置 USB-TTL 需要交叉连接：

```text
TC375 P14.0 (TX)  -> USB-TTL RX
TC375 P14.1 (RX)  <- USB-TTL TX
TC375 GND         -- USB-TTL GND
```

这里只能连接与板卡电平兼容的 TTL UART，不能直接接传统正负电压
RS-232。自定义板卡应修改 [tc375_board_config.h](tc375_board_config.h)，
不要在 HAL 中散落修改引脚和中断号。

## 运行模式

`Cpu0_Main.c` 的 `BSP_RUNTIME_MODE` 默认是
`BSP_RUNTIME_NATIVE_PROTOCOL`。此模式每 1 ms 轮询一次共享协议运行时，
但串口 ISR 会独立把数据搬入软件 FIFO。

原来的独立 PWM/开环测试仍保留。需要它时显式设置：

```c
#define BSP_RUNTIME_MODE BSP_RUNTIME_STANDALONE_TEST
```

不要同时运行两种入口。

当前 TASKING 工具链没有随仓库附带可用的 TASKING TriCore FreeRTOS port，
因此真机 TASKING 配置使用无动态内存的协作式调度。它与 FreeRTOS 版本共用
同一套协议、状态机和保护逻辑。切换到 GCC TriCore 或加入经过验证的
TASKING port 后，可改用 `Firmware_CreateStaticTasks()`。

## 安全默认值

`project_config.h` 默认：

```c
#define MOTOR_CONTROL_HARDWARE_ENABLED 1
#define MOTOR_POWER_STAGE_ENABLED      0
#define MOTOR_USE_SIMPLEFOC            1
```

因此烧录后可以验证双向串口、ACK、遥测、配置界面和 SimpleFOC 开环：
P00.0、P00.2、P00.3 可输出 20 kHz 三相 PWM，但 DRV8313 nSLEEP/nRESET
始终保持关闭。未接功率板时不检查 nFAULT。只有 ADC、编码器、PWM 极性、
nFAULT、母线、电流保护和物理急停全部验证后，才能在项目配置中把
`MOTOR_POWER_STAGE_ENABLED` 改为 `1`。

## 构建与首次联调

1. 在 AURIX Development Studio 中刷新工程。
2. 执行 `Project > Clean...`，再构建 `TriCore Debug (TASKING)`。
   首次清理会让 ADS 把根目录中的共享源码 wrapper 加入 makefile；修改
   `firmware/app`、`src` 或 `simplefoc_port` 中的共享源码后也应 Clean，
   因为 TASKING 的中间文件依赖不会可靠追踪 wrapper 内部的 `.c` 文件。
3. 烧录新的 ELF，并让 CPU 正常运行，不要停在 `core0_main` 断点。
4. Motor Studio 选择实际 COM 口和 `115200` 后连接。

正确结果应同时出现：

```text
TX ... command 0x02 / 0x03
RX ACK ... command 0x02 / 0x03
RX telemetry ...
```

如果只有 TX：

- 确认烧录的是本次生成的 ELF；
- 确认 MCU TX/RX 与 USB-TTL 已交叉且共地；
- 用示波器检查 P14.0 是否在发送数据；
- 确认板卡实际 USB 虚拟串口确实连接 P14.0/P14.1；
- 如板卡映射不同，修改 `tc375_board_config.h`；
- 确认调试器没有暂停 CPU。

当前 ADS TASKING Debug 配置已实测完整链接通过。ADC、编码器和 Flash HAL
仍是下一阶段的板级实现项，不影响本阶段协议双向通信。
