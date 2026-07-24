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
| `START_OPEN_LOOP` | `28` | `motor:u8` |
| `GET_BUILD_CONFIG` | `29` | 无；返回只读编译配置 |
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
- 固件硬上限不能由上位机提高：母线 60 V、电压限幅 6 V、
  速度绝对值 100 rad/s、最长运行 600 s。

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
```

当前 detail 长度为 33 字节。上位机仍兼容旧版 32 字节
`real_hardware_enabled` 格式，并把旧字段同时映射为控制硬件和功率硬件状态。
这些字段来自编译期宏，只读显示；PWM/ADC/ISR 频率和两个硬件输出开关不能
在线修改。串口连接只表示控制器通信连通，不代表功率硬件已经连接或可用。

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

- 上位机主动断开前发送 `QUICK_STOP`。
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
