#ifndef SIMPLEFOC_TC375_PORT_HPP
#define SIMPLEFOC_TC375_PORT_HPP

#include <stdbool.h>

#include "motor_control.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * 该边界保证应用层不直接依赖某个 SimpleFOC 版本。
 * 实现内部只允许一个静态 BLDCMotor 实例。
 */
bool SimpleFocTc375_Init(MotorControl *motor);
void SimpleFocTc375_AdcPwmIsr(MotorControl *motor);
void SimpleFocTc375_OuterLoop(MotorControl *motor);
bool SimpleFocTc375_RunCalibration(unsigned int calibration_type);
void SimpleFocTc375_ForceSafeState(void);

#ifdef __cplusplus
}
#endif

#endif
