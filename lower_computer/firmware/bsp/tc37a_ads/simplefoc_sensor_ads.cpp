/* SimpleFOC sensor base class used by the TC375 encoder adapter. */
#include "project_config.h"
#if MOTOR_USE_SIMPLEFOC
#ifndef SIMPLEFOC_DISABLE_DEBUG
#define SIMPLEFOC_DISABLE_DEBUG
#endif
#include "../../simplefoc_port/tasking/simplefoc_tasking_compat.hpp"
#include "../../../third_party/Arduino-FOC/src/common/base_classes/Sensor.h"
#undef SIMPLEFOC_DEBUG
#define SIMPLEFOC_DEBUG(...) do { } while (0)
#include "../../../third_party/Arduino-FOC/src/common/base_classes/Sensor.cpp"
#endif
