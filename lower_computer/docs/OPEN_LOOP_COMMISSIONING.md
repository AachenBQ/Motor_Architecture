# SimpleFOC 开环联调

## 两级硬件状态

固件把“能否输出 MCU PWM”和“能否驱动真实功率级”分开：

| 模式 | CONTROL_HARDWARE | POWER_STAGE | 行为 |
|---|---:|---:|---|
| 全锁定 | 0 | 0 | 不允许 PWM，不允许 gate |
| 控制板 PWM 检查（默认） | 1 | 0 | P00.0/P00.2/P00.3 可输出 PWM，DRV8313 始终关闭 |
| 完整功率硬件 | 1 | 1 | PWM 和 gate 都可用，真实电机可能动作 |

两个开关在 `firmware/config/project_config.h` 中设置，属于编译期安全参数，
不能通过串口实时打开。`POWER_STAGE=1` 不能与 `CONTROL_HARDWARE=0` 组合。

## 不接功率板检查 PWM

1. 保持默认宏：

   ```c
   #define MOTOR_CONTROL_HARDWARE_ENABLED 1
   #define MOTOR_POWER_STAGE_ENABLED      0
   #define MOTOR_USE_SIMPLEFOC            1
   ```

2. 在 AURIX Studio 执行 `Clean Project`，再构建并烧录
   `TriCore Debug (TASKING)`。
3. 只给 TC375 控制板供电。不要连接直流母线、电机三相线或功率板使能。
4. 示波器地夹接控制板 GND，探头分别接：

   - U：P00.0 / ATOM1 CH0 / TOUT9
   - V：P00.2 / ATOM1 CH1 / TOUT11
   - W：P00.3 / ATOM1 CH2 / TOUT12

5. 打开 Motor Studio，点击“连接控制硬件”。连接后会自动读取固件分层状态。
6. 打开“设备配置”，确认显示：

   ```text
   控制硬件已允许（仅 MCU PWM）｜功率硬件被固件锁定
   SIMPLEFOC=1
   PWM=20000 Hz
   ```

7. 在“开环调试参数”选择 `SimpleFOC 开环`，先使用默认低风险参数：

   ```text
   极对数 7
   母线参数 24 V
   电压限幅 2 V
   目标速度 5 rad/s
   加速度 10 rad/s²
   最长运行 30000 ms
   ```

8. 点击“启动开环”，确认弹窗明确显示“仅 MCU PWM”。三路引脚应出现
   20 kHz 载波（周期约 50 us），占空比包络互差 120°。默认 7 极对、
   5 rad/s 时，电角频率约为 5.57 Hz，包络周期约 180 ms。
9. 先点击“快速停止”，确认三路 PWM 被撤销；再测试“紧急停止”、软件关闭
   和串口断开路径。任一停止路径都必须保持功率 gate 关闭。

功率板未接时，固件不会用 DRV8313 nFAULT 阻断控制板 PWM 检查。该例外只在
`MOTOR_POWER_STAGE_ENABLED=0` 时生效；完整功率模式仍检查 nFAULT。

## 进入完整功率硬件前

只有在 PWM 频率、相序、停止路径、母线采样、相电流采样、nFAULT、限流电源
和物理急停都已验证后，才把 `MOTOR_POWER_STAGE_ENABLED` 改为 `1` 并重新
Clean、构建和烧录。上位机无法证明功率板物理上已经正确连接；它显示的是
固件输出权限，完整功率测试仍必须由操作者完成接线和安全检查。
