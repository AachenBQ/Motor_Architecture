/* SimpleFOC low-pass filter implementation. */
#include "project_config.h"
#if MOTOR_USE_SIMPLEFOC
#ifndef SIMPLEFOC_DISABLE_DEBUG
#define SIMPLEFOC_DISABLE_DEBUG
#endif
#include "../../../third_party/Arduino-FOC/src/common/lowpass_filter.cpp"
#endif
