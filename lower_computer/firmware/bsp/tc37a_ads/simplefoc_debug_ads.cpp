/* Keep the pinned SimpleFOC source set complete; debug output is disabled. */
#include "project_config.h"
#if MOTOR_USE_SIMPLEFOC
#ifndef SIMPLEFOC_DISABLE_DEBUG
#define SIMPLEFOC_DISABLE_DEBUG
#endif
#include "../../../third_party/Arduino-FOC/src/communication/SimpleFOCDebug.cpp"
#endif
