/* SimpleFOC BLDC motor implementation required by velocity_openloop. */
#include "project_config.h"
#if MOTOR_USE_SIMPLEFOC
#ifndef SIMPLEFOC_DISABLE_DEBUG
#define SIMPLEFOC_DISABLE_DEBUG
#endif
#include "../../simplefoc_port/tasking/simplefoc_tasking_compat.hpp"
#include "../../../third_party/Arduino-FOC/src/BLDCMotor.h"
#undef SIMPLEFOC_MOTOR_DEBUG
#undef SIMPLEFOC_MOTOR_ERROR
#undef SIMPLEFOC_MOTOR_WARN
#define SIMPLEFOC_MOTOR_DEBUG(...) do { } while (0)
#define SIMPLEFOC_MOTOR_ERROR(...) do { } while (0)
#define SIMPLEFOC_MOTOR_WARN(...) do { } while (0)
#include "../../../third_party/Arduino-FOC/src/BLDCMotor.cpp"
#endif
