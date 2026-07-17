#ifndef MOTOR_CONTROL_H
#define MOTOR_CONTROL_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    MOTOR_MODE_TORQUE = 0,
    MOTOR_MODE_SPEED = 1,
    MOTOR_MODE_POSITION = 2
} MotorMode;

typedef enum
{
    MOTOR_PID_CURRENT = 0,
    MOTOR_PID_SPEED = 1,
    MOTOR_PID_POSITION = 2,
    MOTOR_PID_COUNT = 3
} MotorPidLoop;

typedef enum
{
    MOTOR_STATE_BOOT = 0,
    MOTOR_STATE_IDLE,
    MOTOR_STATE_CALIBRATING,
    MOTOR_STATE_READY,
    MOTOR_STATE_RUNNING,
    MOTOR_STATE_STOPPING,
    MOTOR_STATE_FAULT,
    MOTOR_STATE_ESTOP
} MotorState;

typedef enum
{
    MOTOR_RESULT_OK = 0,
    MOTOR_RESULT_INVALID_STATE,
    MOTOR_RESULT_OUT_OF_RANGE,
    MOTOR_RESULT_NOT_CALIBRATED,
    MOTOR_RESULT_HEARTBEAT_REQUIRED,
    MOTOR_RESULT_HARDWARE_FAULT
} MotorResult;

enum
{
    MOTOR_FAULT_OVERCURRENT = 1UL << 0,
    MOTOR_FAULT_OVERVOLTAGE = 1UL << 1,
    MOTOR_FAULT_UNDERVOLTAGE = 1UL << 2,
    MOTOR_FAULT_OVERTEMPERATURE = 1UL << 3,
    MOTOR_FAULT_ENCODER = 1UL << 4,
    MOTOR_FAULT_GATE_DRIVER = 1UL << 5,
    MOTOR_FAULT_DEADLINE = 1UL << 6,
    MOTOR_FAULT_COMM_TIMEOUT = 1UL << 8
};

typedef struct
{
    float kp;
    float ki;
    float kd;
} MotorPid;

typedef struct
{
    float current_a;
    float torque_nm;
    float speed_rad_s;
    float position_min_rad;
    float position_max_rad;
    float bus_min_v;
    float bus_max_v;
    float temperature_max_c;
} MotorLimits;

typedef struct
{
    float speed_rad_s;
    float iq_current_a;
    float bus_voltage_v;
    float temperature_c;
    float position_rad;
    uint16_t status;
} MotorTelemetry;

typedef struct
{
    MotorState state;
    MotorMode mode;
    float target;
    bool enabled;
    bool calibrated;
    bool heartbeat_valid;
    uint32_t last_heartbeat_ms;
    uint16_t heartbeat_lease_ms;
    uint32_t faults;
    uint8_t calibration_type;
    MotorPid pid[MOTOR_PID_COUNT];
    MotorPid pending_pid[MOTOR_PID_COUNT];
    uint8_t pending_pid_mask;
    MotorLimits limits;
    MotorTelemetry telemetry;
} MotorControl;

#define MOTOR_PERSISTENT_MAGIC 0x4D435432UL
#define MOTOR_PERSISTENT_VERSION 3U

typedef struct
{
    uint32_t magic;
    uint16_t version;
    uint8_t calibration_valid;
    uint8_t reserved;
    uint16_t telemetry_rate_hz;
    uint16_t reserved_2;
    uint32_t telemetry_mask;
    MotorPid pid[MOTOR_PID_COUNT];
    MotorLimits limits;
} MotorPersistentConfig;

void MotorControl_Init(MotorControl *motor, uint32_t now_ms);
void MotorControl_SetCalibrationValid(MotorControl *motor, bool valid);
void MotorControl_Heartbeat(
    MotorControl *motor,
    uint32_t now_ms,
    uint16_t lease_ms);
void MotorControl_Tick(MotorControl *motor, uint32_t now_ms);
MotorResult MotorControl_SetEnable(MotorControl *motor, bool enable);
MotorResult MotorControl_SetMode(MotorControl *motor, MotorMode mode);
MotorResult MotorControl_SetTarget(
    MotorControl *motor,
    MotorMode mode,
    float target);
MotorResult MotorControl_SetPid(
    MotorControl *motor,
    MotorPidLoop loop,
    const MotorPid *pid);
void MotorControl_ApplyPendingPid(MotorControl *motor);
MotorResult MotorControl_StartCalibration(
    MotorControl *motor,
    uint8_t calibration_type);
void MotorControl_FinishCalibration(MotorControl *motor, bool success);
MotorResult MotorControl_ClearFault(MotorControl *motor, uint32_t active_faults);
void MotorControl_Stop(MotorControl *motor, bool emergency);
void MotorControl_TripFault(MotorControl *motor, uint32_t fault);
void MotorControl_UpdateTelemetry(
    MotorControl *motor,
    const MotorTelemetry *telemetry);
void MotorControl_RestoreDefaults(MotorControl *motor);
void MotorControl_ExportPersistentConfig(
    const MotorControl *motor,
    MotorPersistentConfig *config);
bool MotorControl_ImportPersistentConfig(
    MotorControl *motor,
    const MotorPersistentConfig *config);

#ifdef __cplusplus
}
#endif

#endif
