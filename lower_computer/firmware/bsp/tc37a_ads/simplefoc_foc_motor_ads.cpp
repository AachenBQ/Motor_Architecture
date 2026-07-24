/* SimpleFOC common motor control and open-loop time integration. */
#include "project_config.h"
#if MOTOR_USE_SIMPLEFOC
#ifndef SIMPLEFOC_DISABLE_DEBUG
#define SIMPLEFOC_DISABLE_DEBUG
#endif
#include "../../simplefoc_port/tasking/simplefoc_tasking_compat.hpp"
#include "../../../third_party/Arduino-FOC/src/common/base_classes/FOCMotor.h"
#undef SIMPLEFOC_MOTOR_DEBUG
#undef SIMPLEFOC_MOTOR_ERROR
#undef SIMPLEFOC_MOTOR_WARN
#define SIMPLEFOC_MOTOR_DEBUG(...) do { } while (0)
#define SIMPLEFOC_MOTOR_ERROR(...) do { } while (0)
#define SIMPLEFOC_MOTOR_WARN(...) do { } while (0)
#include "../../../third_party/Arduino-FOC/src/common/base_classes/FOCMotor.cpp"
#endif
