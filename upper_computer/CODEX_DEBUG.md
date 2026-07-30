# Codex 接入 Motor Studio

Motor Studio 启动后会同时启动一个只监听 `127.0.0.1` 的调试桥。调试桥运行在
上位机进程内部，因此界面和 Codex 共用同一个串口连接，不会争抢 COM 端口。

每次启动都会生成新的随机访问令牌，令牌仅写入系统临时目录中的
`motor-studio-codex-bridge.json`。项目自带的客户端会自动发现该文件，无需手动
复制端口或令牌。关闭上位机后，清单文件会被删除。

## 快速使用

先启动上位机：

```powershell
cd upper_computer
python -m motor_control
```

在另一个终端或 Codex 中执行：

```powershell
cd upper_computer
python -m motor_control.codex_client status
python -m motor_control.codex_client ports
python -m motor_control.codex_client connect --port COM4 --baud 115200
python -m motor_control.codex_client device-info
python -m motor_control.codex_client diagnostics
python -m motor_control.codex_client logs --limit 100
python -m motor_control.codex_client history --seconds 5 --limit 500
```

Windows 也可以使用包装脚本：

```powershell
codex_debug.bat status
codex_debug.bat diagnostics
```

单条设备命令默认等待最多 2 秒的 ACK，并输出命令序号、设备状态码和附加数据。
可以通过 `--timeout 5` 修改等待时间，或通过 `--no-wait` 只发送不等待。

## 权限和安全

默认“Codex：只读”模式允许：

- 查看状态、通信日志、最近遥测和可用串口；
- 连接控制硬件或仿真器、读取设备信息和诊断；
- 失能、快速停止、广播紧急停止和安全断开。

修改参数、使能和启动开环默认禁止。需要用户在上位机标题栏点击
“Codex：只读”，阅读提示并授权，授权 10 分钟后自动失效，断开连接时也会立即
失效。

真实功率级由固件启用时，使能和启动开环还必须在命令中明确加入
`--power-stage-confirmed`。该参数只表示操作者已经确认风险，不会关闭过流、
遥测超时、心跳或固件保护。

```powershell
# 需要先在界面授权
python -m motor_control.codex_client set-pid `
  --loop speed --kp 0.5 --ki 0.05 --kd 0

python -m motor_control.codex_client configure-open-loop `
  --pole-pairs 7 --bus-voltage 7 --voltage-limit 0.3 `
  --target-velocity 5 --acceleration 10

python -m motor_control.codex_client start-open-loop
python -m motor_control.codex_client quick-stop
```

开环参数使用 14 个 16 字节短帧和一个 15 字节提交帧传输。每片会等待
ACK，超时自动重试；只有完整 CRC 校验和原子提交成功后才会报告完成。可在
不启动 PWM 的情况下执行重复通信校验：

```powershell
# 需要先在界面授权；只写入并读回安全配置，不使能、不启动电机
python -m motor_control.codex_client communication-test --iterations 20
```

测试会逐轮执行分片写入、`0x27` 读回，并比较测试前后的 UART、解析器、
CRC、超时和高优先级 ACK 失败计数。任何计数增加或读回不一致都会立即失败。

如果固件报告真实功率级已启用，启动命令应改为：

```powershell
python -m motor_control.codex_client start-open-loop --power-stage-confirmed
```

## 推荐的 Codex 调试顺序

1. 读取 `status`，确认上位机和桥接服务状态。
2. 用 `ports` 查找串口并连接。
3. 执行 `device-info`、`build-config` 和 `diagnostics`。
4. 用 `logs` 检查 `0x29`、心跳、CRC 和 ACK。
5. 断开功率硬件时再检查 PWM；需要控制时由用户在界面授权。
6. 修改参数后再次读取诊断，确认没有心跳超时或 ACK 发送失败。
7. 运行 `communication-test`，确认分片写入、读回及诊断计数均通过。
8. 任何异常优先执行 `quick-stop`；不确定设备状态时执行
   `emergency-stop`。

调试器暂停 TC375 CPU 时，心跳与遥测保护仍会按设计触发。断点恢复后看到
“心跳超时”或上位机发出快速停止属于预期保护行为。
