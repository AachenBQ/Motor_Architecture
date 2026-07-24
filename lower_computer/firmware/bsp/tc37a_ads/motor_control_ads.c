/*
 * ADS keeps its build inputs inside this project directory. This wrapper
 * compiles the shared firmware implementation without duplicating it.
 * Run an ADS Clean build after changing the included shared source.
 */
#include "../../src/motor_control.c"
