# Native UART Protocol v2

该协议是 Motor Studio 上位机与 TC375 单电机控制器之间的 MVP 通信协议，
适用于当前 TASKING 协作式运行入口和后续 FreeRTOS 入口。

## 1. 基本约定

- 小端序。
- IEEE-754 float32。
- 唯一电机地址：`0x01`。
- 广播地址：`0xFF`，仅用于急停和失能。
- 版本：`0x02`。
- 默认 UART：115200, 8-N-1。

## 2. 帧格式

```text
AA 55 | VER | FLAGS | DEVICE | CMD | SEQ | LEN:u16 | PAYLOAD | CRC16:u16
```

| 字段 | 长度 | 说明 |
|---|---:|---|
| `SOF` | 2 | 固定 `AA 55` |
| `VER` | 1 | 当前 `02` |
| `FLAGS` | 1 | bit0 response，bit1 fault，其他保留 |
| `DEVICE` | 1 | `01` 或允许命令中的 `FF` |
| `CMD` | 1 | 命令字 |
| `SEQ` | 1 | 0–255 循环 |
| `LEN` | 2 | Payload 长度，最大 2048 |
| `PAYLOAD` | N | 命令数据 |
| `CRC16` | 2 | CRC16/MODBUS，覆盖 VER 至 Payload |

## 3. 命令字

| 命令 | 值 | 请求 Payload |
|---|---:|---|
| `PING` | `01` | 无 |
| `GET_DEVICE_INFO` | `02` | 无 |
| `GET_CAPABILITIES` | `03` | 无 |
| `HEARTBEAT` | `04` | `host_time_ms:u32, lease_ms:u16` |
| `SET_ENABLE` | `10` | `motor:u8, enabled:u8` |
| `SET_MODE` | `11` | `motor:u8, mode:u8` |
| `SET_TARGET` | `12` | `motor:u8, mode:u8, target:f32` |
| `SET_PID` | `13` | `motor:u8, loop:u8, kp:f32, ki:f32, kd:f32` |
| `CALIBRATE` | `15` | `motor:u8, type:u8` |
| `CLEAR_FAULT` | `16` | `motor:u8` |
| `SET_LIMITS` | `17` | 见第 7 节 |
| `GET_LIMITS` | `18` | `motor:u8` |
| `SAVE_CONFIG` | `19` | 无 |
| `RESTORE_DEFAULTS` | `1A` | 无 |
| `CONTROLLED_STOP` | `1B` | `motor:u8` |
| `QUICK_STOP` | `1C` | `motor:u8` |
| `EMERGENCY_STOP` | `1F` | `motor:u8`，允许 `FF` |
| `GET_PID` | `20` | `motor:u8, loop:u8` |
| `GET_DIAGNOSTICS` | `22` | 无 |
| `SET_TELEMETRY_PROFILE` | `23` | `rate_hz:u16, signal_mask:u32` |
| `GET_BACKEND_INFO` | `24` | 无 |
| `GET_TELEMETRY_PROFILE` | `25` | 无；ACK detail 返回 `rate_hz:u16, signal_mask:u32` |
| `SET_OPEN_LOOP_CONFIG` | `26` | 见第 9 节；仅停止状态可写 |
| `GET_OPEN_LOOP_CONFIG` | `27` | `motor:u8` |
| `START_OPEN_LOOP` | `28` | `motor:u8[, start_flags:u8]`；见第 9 节 |
| `GET_BUILD_CONFIG` | `29` | 无；返回只读编译配置 |
| `SET_OPEN_LOOP_CONFIG_PART` | `2A` | 见 9.1；固定 5 字节，整帧 16 字节 |
| `COMMIT_OPEN_LOOP_CONFIG` | `2B` | 见 9.1；固定 4 字节，整帧 15 字节 |
| `TELEMETRY` | `80` | MCU 主动发送 |
| `FAULT_EVENT` | `81` | MCU 主动发送 |
| `ACK` | `F0` | 应答 |
| `ERROR` | `F1` | 错误应答 |

## 4. 枚举

控制模式：

| 值 | 模式 | Target 单位 |
|---:|---|---|
| 0 | `TORQUE` | N·m |
| 1 | `SPEED` | rad/s |
| 2 | `POSITION` | rad，多圈 |
| 3 | `OPEN_LOOP_SPEED` | rad/s，仅开环已启动时允许更新 |

PID 环：

| 值 | 环路 |
|---:|---|
| 0 | `CURRENT_BOTH`，同时更新 d/q |
| 1 | `SPEED` |
| 2 | `POSITION` |

校准类型：

| 值 | 类型 |
|---:|---|
| 0 | `ALL` |
| 1 | `CURRENT_OFFSET` |
| 2 | `ENCODER_OFFSET` |
| 3 | `ENCODER_DIRECTION` |
| 4 | `ZERO_POSITION` |

## 5. ACK 与 ERROR

ACK：

```text
original_cmd:u8 | status:u8=0 | detail...
```

ERROR：

```text
original_cmd:u8 | error_code:u8 | detail...
```

错误码：

| 值 | 名称 |
|---:|---|
| 1 | `UNSUPPORTED_COMMAND` |
| 2 | `INVALID_PAYLOAD` |
| 3 | `INVALID_DEVICE` |
| 4 | `INVALID_STATE` |
| 5 | `OUT_OF_RANGE` |
| 6 | `NOT_CALIBRATED` |
| 7 | `HEARTBEAT_REQUIRED` |
| 8 | `BUSY` |
| 9 | `STORAGE_ERROR` |
| 10 | `HARDWARE_FAULT` |
| 11 | `CAPABILITY_UNAVAILABLE` |
| 12 | `SAFETY_INTERLOCK` |

每个请求必须在 100 ms 内 ACK/ERROR。校准、保存等耗时命令先返回
`accepted`，最终结果通过 `FAULT_EVENT` 或后续状态查询返回。

## 6. 设备信息与能力

`GET_DEVICE_INFO` ACK detail：

```text
fw_major:u8
fw_minor:u8
fw_patch:u8
hw_major:u8
hw_minor:u8
serial_number:u32
name:char[16]
git_hash:char[8]
```

`GET_CAPABILITIES` ACK detail：

```text
motor_count:u8       // 固定 1
backend_mask:u8      // bit0 MCU，bit1 FPGA
control_mode_mask:u8 // bit0 torque，bit1 speed，bit2 position
feature_flags:u32
max_telemetry_hz:u16
```

MVP：

- `motor_count = 1`
- `backend_mask = 0x01`
- FPGA reserved flag = 1
- FPGA control available flag = 0
- `feature_flags bit6 = 1` 表示支持 9.1 的开环配置分片写入；
  bit6 为 0 时设备只提供兼容命令 `0x26`。由于本项目已经观察到长帧接收
  不稳定，当前 Motor Studio 不静默回退，而是提示烧录支持分片的新固件。
- `feature_flags bit7 = 1` 表示支持带 `start_flags` 的 `0x28`。真实功率级
  固件必须报告此能力；否则上位机不得尝试启动。

## 7. Limits Payload

```text
motor:u8
current_limit_a:f32
torque_limit_nm:f32
speed_limit_rad_s:f32
position_min_rad:f32
position_max_rad:f32
bus_voltage_min_v:f32
bus_voltage_max_v:f32
temperature_max_c:f32
```

设置限值只更新 shadow 参数；`SAVE_CONFIG` 才写入 Flash。

## 8. PID 返回

`GET_PID` ACK detail：

```text
loop:u8
kp:f32
ki:f32
kd:f32
```

与现有上位机三环下拉框一致。

## 9. Open-loop commissioning

`SET_OPEN_LOOP_CONFIG` 和 `GET_OPEN_LOOP_CONFIG` ACK detail 使用相同布局：

```text
motor:u8
backend:u8            // 0 direct sine, 1 SimpleFOC
pole_pairs:u8
flags:u8              // 当前保留，发送 0
bus_voltage_v:f32
voltage_limit_v:f32
target_velocity_rad_s:f32
acceleration_rad_s2:f32
update_period_ms:u16
startup_delay_ms:u16
max_runtime_ms:u32
```

运行时约束：

- 除目标速度外，所有开环参数只能在输出停止时修改。
- 运行中调速使用 `SET_TARGET(motor, mode=3, target)`。
- 启动要求心跳有效、无活动故障且输出处于停止状态。
- 达到 `max_runtime_ms`、心跳超时、限值越界或驱动故障时自动撤销输出。
- `CONTROLLED_STOP` 按 `acceleration_rad_s2` 斜坡降到零；
  `QUICK_STOP` 立即撤销 PWM；`EMERGENCY_STOP` 立即撤销 PWM 和 gate。
- 固件通用硬上限不能由上位机提高：母线 10 V、电压限幅 2 V、
  速度绝对值 100 rad/s、最长运行 600 s。真实功率级编译还会收紧为：
  母线 8–10 V、电压限幅 0.3 V、速度绝对值 5 rad/s、加速度
  10 rad/s²、启动延时至少 500 ms、最长运行 3000 ms。

`START_OPEN_LOOP (0x28)` 支持以下两种 payload：

```text
motor:u8
start_flags:u8        // 可选；bit0 = power_stage_confirmed
```

- 控制板/PWM 示波器模式继续接受旧的单字节 payload；
- `MOTOR_POWER_STAGE_ENABLED=1` 时 payload 必须为 2 字节且 bit0 必须置位，
  缺少确认返回 `SAFETY_INTERLOCK`；
- 未定义的 flag 位必须为 0，否则返回 `INVALID_PAYLOAD`；
- bit0 只证明操作者对本次启动做了明确确认，不会绕过心跳、故障、参数、
  测量值、硬件静止状态或编译期安全门禁；
- 功率级启动前若 PWM 或 gate 已处于开启状态，固件先将两者关闭并返回
  `SAFETY_INTERLOCK`，不在不确定状态下继续启动。

`GET_BUILD_CONFIG` ACK detail：

```text
device_id:u8
control_hardware_enabled:u8
power_stage_enabled:u8
simplefoc_enabled:u8
default_pole_pairs:u8
adc_trigger_hz:u32
pwm_frequency_hz:u32
control_isr_hz:u32
outer_loop_hz:u32
default_telemetry_hz:u16
heartbeat_default_ms:u16
heartbeat_min_ms:u16
heartbeat_max_ms:u16
torque_constant_nm_per_a:f32
safety_mask:u32
```

当前 detail 长度为 37 字节，`safety_mask` 位定义如下：

| bit | 安全层 |
|---:|---|
| 0 | 三相电流采样和极性已验证 |
| 1 | 母线电压采样已验证 |
| 2 | 功率温度采样已验证 |
| 3 | CPU watchdog 已验证 |
| 4 | 物理急停已验证 |
| 5 | 外部硬件限流已验证 |
| 6 | gate/nFAULT 监测已验证 |
| 7 | 心跳失能链路已验证 |
| 8 | PWM/gate 安全输出路径已验证 |
| 31 | commissioning override 编译开关处于开启状态 |

完整功率级安全掩码为 `0x000001FF`。bit31 只是醒目的试运行标志，不能替代
bit0–8 中缺失的安全层。上位机仍兼容旧版 32/33 字节
`real_hardware_enabled` 格式，并把旧字段同时映射为控制硬件和功率硬件状态。
这些字段来自编译期宏，只读显示；PWM/ADC/ISR 频率和两个硬件输出开关不能
在线修改。串口连接只表示控制器通信连通，不代表功率硬件已经连接或可用；
真实功率级模式缺少 `safety_mask` 时，上位机必须拒绝启动。

### 9.1 开环配置分片写入（`0x2A` / `0x2B`）

旧命令 `SET_OPEN_LOOP_CONFIG (0x26)` 的 28 字节 payload 会形成 39 字节
UART 帧。在部分 ASCLIN 接收路径中，长帧更容易暴露 FIFO 服务延迟，因此
支持分片能力的设备使用以下两阶段传输。该机制不会改变第 9 节的配置布局，
只是把完全相同的 28 字节原始 payload 分成 14 片传输。

`SET_OPEN_LOOP_CONFIG_PART (0x2A)` 请求 payload 固定为 5 字节：

```text
motor:u8             // 固定 0x01
generation:u8        // 本次传输代号，0–255 循环
fragment_index:u8    // 0–13
data:u8[2]           // 原 28 字节 payload 的 [index*2 : index*2+2]
```

包括帧头和 CRC 的总长度固定为 16 字节。注意，`data` 的第 0 片仍包含原
payload 的 `motor` 字节；外层 `motor` 用于在写 staging 前校验设备，两者
不可省略或重排。

成功 ACK：

```text
original_cmd=0x2A | status=0 | generation:u8 | fragment_index:u8
```

同一 `generation + fragment_index` 可以重复发送，MCU 必须覆盖相同的两个
字节并再次 ACK，使 ACK 丢失后的重试保持幂等。收到不同 `generation` 的
首个合法分片时，MCU 清空旧 staging 和接收位图并开始新一代传输。电机已
使能或开环正在运行时返回 `INVALID_STATE`；长度、设备或索引错误返回
`INVALID_PAYLOAD`。staging 从最后一个合法分片开始保留 5000 ms；超时后
在处理下一条分片或提交命令时清空，防止未完成传输长期占用旧状态。

全部 14 片得到 ACK 后，上位机发送 `COMMIT_OPEN_LOOP_CONFIG (0x2B)`。
请求 payload 固定为 4 字节：

```text
motor:u8             // 固定 0x01
generation:u8        // 必须与 staging 一致
config_crc16:u16     // 对重组后的原始 28 字节计算 CRC16/MODBUS
```

包括帧头和 CRC 的总长度固定为 15 字节。这里的 `config_crc16` 是 payload
级完整性校验；外层帧仍有自己的 CRC16，两者都必须正确。

提交成功 ACK：

```text
original_cmd=0x2B | status=0 | generation:u8
```

提交按以下顺序原子执行：

1. 检查电机处于停止/失能状态、代号一致且 14 位接收位图完整；
2. 对 staging 的 28 字节计算 CRC 并与 `config_crc16` 比较；
3. 按第 9 节布局解析并执行全部范围检查；
4. 只有所有检查通过才一次性替换活动配置；任何错误都不得部分修改配置。

缺片、无活动 staging 或 generation 不一致返回 `INVALID_STATE`；payload
CRC 错误返回 `INVALID_PAYLOAD`；解析后的参数超限返回相应状态码。失败时
保留同一代 staging，允许补齐缺片或修正 CRC 后再次提交。接收端还必须
记住最近一次成功提交的 `generation + config_crc16`，对完全相同的重复
`0x2B` 返回成功 ACK，避免“配置已应用但提交 ACK 丢失”造成主机误判。
该幂等缓存保留 5000 ms；成功执行兼容命令 `0x26` 或恢复默认配置后，
接收端立即清除这份提交缓存。缓存年龄使用 64 位单调毫秒计数，过期检查后
立即撤销 valid 标志，不能因 32 位毫秒计数回绕重新生效。

当前 Motor Studio 的发送策略：

- 一次只发送一片，并等待 ACK 中的命令、SEQ、generation 和 index 都匹配
  后才发送下一片；
- 每片或提交等待 400 ms，超时后重发相同 payload（SEQ 可更新），最多
  尝试 3 次；
- 任一步返回 ERROR、ACK 内容不匹配或连续 3 次无应答时中止本代传输，
  且绝不发送 `START_OPEN_LOOP`；
- 提交 ACK 成功后再按需读取 `0x27` 校验，随后才能发送 `0x28`。

兼容规则：

- `GET_CAPABILITIES.feature_flags bit6 = 1` 时优先使用 `0x2A/0x2B`；
- bit6 未置位时协议层仍保留完整的 `0x26`，其字段布局保持不变；当前
  Motor Studio 会拒绝发送已知不稳定的长帧并提示升级固件；
- 新固件必须继续接受 `0x26`，便于旧上位机工作；
- `generation` 只用于区分相邻传输，不是持久化版本号，回绕不改变语义。

### 9.2 `GET_DIAGNOSTICS (0x22)` 扩展诊断

空 payload 请求仍返回 24 字节基础诊断，旧固件的 8 字节格式仍被上位机兼容：

```text
uptime_ms:u32
protocol_errors:u16
fault_bits:u16
commands_received:u32
heartbeat_age_ms:u16
heartbeat_lease_ms:u16
motor_state:u8
last_stop_reason:u8
runtime_flags:u8
hardware_flags:u8
tx_high_priority_failures:u16
telemetry_drops:u16
```

RXF1 可在请求 payload 中加入 `sections:u8`：

- bit0：在基础诊断后追加 UART RX 诊断（共 32 字节）
- bit1：追加解析器诊断；该段采用稳定布局并同时包含 bit0 数据（共 40 字节）
- bit2：追加 RX 服务路径计数；同时包含 bit0/bit1 数据（共 46 字节）

RXF1 上位机请求 `sections=0x07`。原有 `sections=0x03` 响应仍严格保持
40 字节，旧版固件则会忽略新增请求位并继续返回其支持的长度，因此可以
双向兼容。

```text
rx_sw_fifo_overflow_events:u16
rx_hw_fifo_overflow_events:u16
rx_frame_error_events:u16
rx_parity_error_events:u16
parser_crc_errors:u16
parser_length_errors:u16
parser_timeout_errors:u16
parser_resync_events:u16
rx_isr_entries:u16
rx_poll_drains:u16
rx_poll_bytes:u16
```

`rx_poll_drains` 或 `rx_poll_bytes` 增长表示主循环从硬件 FIFO 取回了未由
RX ISR 搬运的字节；它们是中断链路恢复路径的观测量，不代表协议错误。

`runtime_flags`：

- bit0 heartbeat valid
- bit1 motor enabled
- bit2 open-loop active
- bit3 open-loop output ready

`hardware_flags`：

- bit0 PWM 当前已开启
- bit1 gate 当前已释放
- bit2 当前未检测到 nFAULT/活动硬件故障
- bit3 `safety_mask` 的 bit0–8 已全部就绪
- bit4 当前固件为真实功率级编译
- bit5 commissioning override 编译开关处于开启状态

`hardware_flags` 是每次查询时读取的运行态，不应由上位机缓存为永久状态。
安全启动前必须至少确认 bit0/bit1 均为 0、bit2 为 1，并使其与 `0x29`
报告的编译配置一致。bit5 置位时 bit3 可能仍为 0，这是试运行警告而不是
“安全已完成”。

`last_stop_reason`：

- `0` 无/正在运行
- `1` 失能命令
- `2` 受控停止
- `3` 快速停止
- `4` 紧急停止
- `5` 心跳超时
- `6` 开环最长运行时间到期
- `7` 硬件或软件故障

发送端为高优先级 ACK/ERROR 预留 UART TX FIFO；FIFO 接近满载时优先丢弃
遥测帧。两个计数器用于区分“ACK 无法发送”和“为保护 ACK 主动丢弃遥测”。

## 10. Telemetry v2

为了保持上位机现有波形兼容，MVP 遥测继续使用：

```text
motor:u8
speed_rpm:f32
iq_current_a:f32
bus_voltage_v:f32
temperature_c:f32
position_deg:f32
status:u16
```

`status`：

- bit0 enabled
- bit1 calibrated
- bit2 emergency stop latched
- bit3 fault
- bit4 heartbeat valid
- bit5 open-loop active
- bit6 controlled stopping
- bit7 encoder valid
- bit8 deadline miss
- bit9 gate driver fault
- 其余保留

更完整的 fault bitmask 通过 `FAULT_EVENT` 和 `GET_DIAGNOSTICS` 传输。

## 11. Heartbeat

- 上位机每 250 ms 发送一次。
- `lease_ms` 默认 750 ms，允许范围 300–5000 ms。
- MCU 使用接收时间判断，不依赖 host time 同步。
- 电机运行时超时必须 quick stop 并失能。
- 心跳恢复后不自动重新使能。

## 12. 软件停止与保护

- 上位机主动断开前发送 `QUICK_STOP`。下位机在处理该命令并生成 ACK 前，
  必须已经把 PWM 和 gate 都拉回安全状态；不能等下一次控制循环。
- 上位机正常关闭前发送广播 `EMERGENCY_STOP`。
- 上位机检测到过流、过温、母线越界、设备 fault/estop 状态或遥测超时后，
  按配置发送受控停止、快速停止或急停，并停止发送心跳。
- 上位机保护只是第二道防线；MCU 必须独立执行心跳、限值、nFAULT 和
  最长运行时间保护。
- 软件或串口异常导致停止帧丢失时，MCU 心跳租约到期仍必须失能。

## 13. 兼容性规则

- v2 接收端拒绝不支持的主版本。
- 新增命令不能改变已有命令的字段含义。
- Payload 只允许尾部扩展。
- 保留字段发送方置 0，接收方忽略。
- 上位机连接后先发送 `GET_DEVICE_INFO` 和 `GET_CAPABILITIES`。
- 能力未报告的命令不得显示为可用。
