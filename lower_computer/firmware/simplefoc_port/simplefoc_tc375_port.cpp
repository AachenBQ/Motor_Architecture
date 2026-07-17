#include "simplefoc_tc375_port.hpp"

#include "project_config.h"
#include "tc375_hal.h"

/*
 * 集成实际 SimpleFOC 库时在此文件中包含 SimpleFOC.h，并创建：
 *
 *   static BLDCMotor motor(MOTOR_POLE_PAIRS);
 *   static Tc375BldcDriver driver;
 *   static Tc375CurrentSense current_sense;
 *   static Tc375Encoder sensor;
 *
 * Tc375BldcDriver/Tc375CurrentSense/Tc375Encoder 必须使用 iLLD 实现，
 * 不得回退到 Arduino analogRead/analogWrite。由于功率板引脚、采样拓扑
 * 和编码器型号尚未给出，本文件故意保持 gate disabled，防止猜测硬件参数
 * 后直接驱动功率级。
 */

bool SimpleFocTc375_Init(MotorControl *motor)
{
    (void)motor;
    Tc375Hal_SetGateEnabled(false);
    Tc375Hal_SetPwmEnabled(false);
    if (!Tc375Hal_MotorPeripheralsInit())
    {
        return false;
    }
#if MOTOR_REAL_HARDWARE_ENABLED
    /* 在板级适配完成后替换为静态 SimpleFOC 对象的 init/link/initFOC。 */
    return false;
#else
    return true;
#endif
}

void SimpleFocTc375_AdcPwmIsr(MotorControl *motor)
{
    Tc375PhaseCurrents currents = Tc375Hal_ReadPhaseCurrents();
    if (!currents.sample_valid || !motor->enabled)
    {
        Tc375Hal_SetPwmEnabled(false);
        return;
    }
#if MOTOR_REAL_HARDWARE_ENABLED
    /*
     * 1. 更新自定义 CurrentSense 的同步采样；
     * 2. 调用唯一 SimpleFOC 电机实例的 current-loop/loopFOC；
     * 3. Driver 通过 GTM shadow register 同步更新 PWM。
     */
#else
    (void)currents;
#endif
}

void SimpleFocTc375_OuterLoop(MotorControl *motor)
{
    Tc375EncoderSample encoder = Tc375Hal_ReadEncoder();
    MotorTelemetry telemetry;

    MotorControl_ApplyPendingPid(motor);
    if (!motor->enabled)
    {
        SimpleFocTc375_ForceSafeState();
    }
#if MOTOR_REAL_HARDWARE_ENABLED
    else
    {
        Tc375Hal_SetGateEnabled(true);
        Tc375Hal_SetPwmEnabled(true);
    }
#endif
    if (!encoder.valid)
    {
        MotorControl_TripFault(motor, MOTOR_FAULT_ENCODER);
        SimpleFocTc375_ForceSafeState();
    }

#if MOTOR_REAL_HARDWARE_ENABLED
    /*
     * 将 motor->mode / target / pid 映射到 SimpleFOC：
     * torque: target / MOTOR_TORQUE_CONSTANT_NM_PER_A -> iq target
     * speed:  MotionControlType::velocity, rad/s
     * angle:  MotionControlType::angle, rad
     */
#endif

    telemetry.speed_rad_s = encoder.velocity_rad_s;
    telemetry.iq_current_a = 0.0F; /* 由 CurrentSense 实现填入。 */
    telemetry.bus_voltage_v = Tc375Hal_ReadBusVoltage();
    telemetry.temperature_c = Tc375Hal_ReadPowerTemperature();
    telemetry.position_rad = encoder.multi_turn_angle_rad;
    telemetry.status = encoder.valid ? (uint16_t)(1U << 7) : 0U;
    MotorControl_UpdateTelemetry(motor, &telemetry);
}

bool SimpleFocTc375_RunCalibration(unsigned int calibration_type)
{
    (void)calibration_type;
#if MOTOR_REAL_HARDWARE_ENABLED
    /* 调用电流零偏、编码器方向和电角度零位校准。 */
    return false;
#else
    return false;
#endif
}

void SimpleFocTc375_ForceSafeState(void)
{
    Tc375Hal_SetPwmEnabled(false);
    Tc375Hal_SetGateEnabled(false);
}
