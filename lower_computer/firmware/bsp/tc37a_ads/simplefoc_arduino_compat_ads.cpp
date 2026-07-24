/* Minimal Arduino timing/Print compatibility required by SimpleFOC. */
#include "project_config.h"
#if MOTOR_USE_SIMPLEFOC
#ifndef SIMPLEFOC_DISABLE_DEBUG
#define SIMPLEFOC_DISABLE_DEBUG
#endif
#include "../../simplefoc_port/arduino_compat/Arduino.cpp"
#include "../../simplefoc_port/arduino_compat/simplefoc_math_overrides.cpp"
#endif
