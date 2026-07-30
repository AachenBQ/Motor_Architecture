#include "Arduino.h"

#include "project_config.h"
#include "tc375_hal.h"

size_t Print::write(uint8_t value)
{
    (void)value;
    return 1U;
}

size_t Print::write(const uint8_t *buffer, size_t size)
{
    (void)buffer;
    return size;
}

size_t Print::print(const char *value)
{
    const char *cursor = value == nullptr ? "" : value;
    size_t count = 0U;
    while (*cursor != '\0')
    {
        count += write((uint8_t)*cursor);
        ++cursor;
    }
    return count;
}

size_t Print::print(const __FlashStringHelper *value)
{
    return print(reinterpret_cast<const char *>(value));
}

size_t Print::print(char value)
{
    return write((uint8_t)value);
}

size_t Print::print(int value)
{
    char buffer[16];
    (void)snprintf(buffer, sizeof(buffer), "%d", value);
    return print(buffer);
}

size_t Print::print(unsigned int value)
{
    char buffer[16];
    (void)snprintf(buffer, sizeof(buffer), "%u", value);
    return print(buffer);
}

size_t Print::print(long value)
{
    char buffer[24];
    (void)snprintf(buffer, sizeof(buffer), "%ld", value);
    return print(buffer);
}

size_t Print::print(unsigned long value)
{
    char buffer[24];
    (void)snprintf(buffer, sizeof(buffer), "%lu", value);
    return print(buffer);
}

size_t Print::print(float value, int digits)
{
    char format[8];
    char buffer[48];
    if (digits < 0)
    {
        digits = 0;
    }
    if (digits > 8)
    {
        digits = 8;
    }
    (void)snprintf(format, sizeof(format), "%%.%df", digits);
    (void)snprintf(buffer, sizeof(buffer), format, (double)value);
    return print(buffer);
}

size_t Print::println()
{
    return print("\n");
}

size_t Print::println(const char *value)
{
    return print(value) + println();
}

size_t Print::println(const __FlashStringHelper *value)
{
    return print(value) + println();
}

size_t Print::println(char value)
{
    return print(value) + println();
}

size_t Print::println(int value)
{
    return print(value) + println();
}

size_t Print::println(unsigned int value)
{
    return print(value) + println();
}

size_t Print::println(long value)
{
    return print(value) + println();
}

size_t Print::println(unsigned long value)
{
    return print(value) + println();
}

size_t Print::println(float value, int digits)
{
    return print(value, digits) + println();
}

Print Serial;

unsigned long micros(void)
{
    return (unsigned long)Tc375Hal_TimeUs();
}

unsigned long millis(void)
{
    return (unsigned long)Tc375Hal_TimeMs();
}

void delay(unsigned long ms)
{
#if MOTOR_POWER_STAGE_ENABLED
    uint32_t start = Tc375Hal_TimeUs();
    uint32_t wait_us = (uint32_t)(ms * 1000UL);
    while ((uint32_t)(Tc375Hal_TimeUs() - start) < wait_us)
    {
    }
#else
    /*
     * SimpleFOC uses two 500 ms stabilization waits in BLDCMotor::init().
     * They are unnecessary when the power stage is compile-time locked and
     * would otherwise delay the first protocol response after a board reset.
     */
    (void)ms;
#endif
}

void delayMicroseconds(unsigned int us)
{
    uint32_t start = Tc375Hal_TimeUs();
    while ((uint32_t)(Tc375Hal_TimeUs() - start) < us)
    {
    }
}

void pinMode(int pin, int mode)
{
    (void)pin;
    (void)mode;
}

void digitalWrite(int pin, int value)
{
    (void)pin;
    (void)value;
}

int digitalRead(int pin)
{
    (void)pin;
    return LOW;
}

int analogRead(int pin)
{
    (void)pin;
    return 0;
}

void analogWrite(int pin, int value)
{
    (void)pin;
    (void)value;
}
