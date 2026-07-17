#ifndef PROJECT_CONFIG_H
#define PROJECT_CONFIG_H

/*
 * 安全默认值：板级引脚、电流采样极性、死区和保护未确认前禁止功率输出。
 * 真实硬件接入完成后由项目配置覆盖这些宏。
 */
#ifndef MOTOR_REAL_HARDWARE_ENABLED
#define MOTOR_REAL_HARDWARE_ENABLED 0
#endif

/*
 * Build and link the SimpleFOC core plus TC375 adapter classes. This can be
 * enabled for compile/smoke tests while MOTOR_REAL_HARDWARE_ENABLED remains 0.
 */
#ifndef MOTOR_USE_SIMPLEFOC
#define MOTOR_USE_SIMPLEFOC 0
#endif

#define MOTOR_DEVICE_ID                 1U
#define MOTOR_ADC_TRIGGER_HZ            10000U
#define MOTOR_PWM_FREQUENCY_HZ          MOTOR_ADC_TRIGGER_HZ
#define MOTOR_CONTROL_ISR_HZ            MOTOR_ADC_TRIGGER_HZ
#define MOTOR_OUTER_LOOP_HZ             1000U
#define MOTOR_TELEMETRY_HZ              100U
#define MOTOR_HEARTBEAT_DEFAULT_MS      750U
#define MOTOR_HEARTBEAT_MIN_MS          300U
#define MOTOR_HEARTBEAT_MAX_MS          5000U

#define MOTOR_POLE_PAIRS                 7U
#define MOTOR_TORQUE_CONSTANT_NM_PER_A   0.10F

#define MOTOR_DEFAULT_CURRENT_LIMIT_A    20.0F
#define MOTOR_DEFAULT_TORQUE_LIMIT_NM    2.0F
#define MOTOR_DEFAULT_SPEED_LIMIT_RAD_S  100.0F
#define MOTOR_DEFAULT_POSITION_MIN_RAD  -1000.0F
#define MOTOR_DEFAULT_POSITION_MAX_RAD   1000.0F
#define MOTOR_DEFAULT_BUS_MIN_V          18.0F
#define MOTOR_DEFAULT_BUS_MAX_V          60.0F
#define MOTOR_DEFAULT_TEMP_MAX_C         80.0F

#endif

