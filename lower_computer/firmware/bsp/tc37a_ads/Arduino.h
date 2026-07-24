#ifndef TC375_ADS_FORWARD_ARDUINO_H_
#define TC375_ADS_FORWARD_ARDUINO_H_

/*
 * Forwarding header for TASKING builds. The ADS Debug configuration always
 * includes the project root, so pinned SimpleFOC sources can find Arduino.h
 * even before Eclipse refreshes external include-path settings.
 */
#include "../../simplefoc_port/arduino_compat/Arduino.h"

#endif
