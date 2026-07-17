# Native UART Protocol v2

该协议是 Motor Studio 上位机与 TC375 FreeRTOS 单电机控制器之间的
MVP 通信协议。

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

## 9. Telemetry v2

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
- bit2 warning
- bit3 fault
- bit4 heartbeat valid
- bit5 target saturated
- bit6 current loop saturated
- bit7 encoder valid
- bit8 deadline miss
- bit9 gate driver fault
- 其余保留

更完整的 fault bitmask 通过 `FAULT_EVENT` 和 `GET_DIAGNOSTICS` 传输。

## 10. Heartbeat

- 上位机每 250 ms 发送一次。
- `lease_ms` 默认 750 ms，允许范围 300–5000 ms。
- MCU 使用接收时间判断，不依赖 host time 同步。
- 电机运行时超时必须 quick stop 并失能。
- 心跳恢复后不自动重新使能。

## 11. 兼容性规则

- v2 接收端拒绝不支持的主版本。
- 新增命令不能改变已有命令的字段含义。
- Payload 只允许尾部扩展。
- 保留字段发送方置 0，接收方忽略。
- 上位机连接后先发送 `GET_DEVICE_INFO` 和 `GET_CAPABILITIES`。
- 能力未报告的命令不得显示为可用。
