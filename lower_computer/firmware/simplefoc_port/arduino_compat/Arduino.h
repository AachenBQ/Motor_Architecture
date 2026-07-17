#ifndef TC375_SIMPLEFOC_ARDUINO_COMPAT_H
#define TC375_SIMPLEFOC_ARDUINO_COMPAT_H

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define ANALOG 3

#ifndef PI
#define PI 3.14159265358979323846
#endif

#ifndef TWO_PI
#define TWO_PI 6.28318530717958647692
#endif

#ifndef min
template <typename T>
static inline T min(T a, T b)
{
    return (a < b) ? a : b;
}
#endif

#ifndef max
template <typename T>
static inline T max(T a, T b)
{
    return (a > b) ? a : b;
}
#endif

template <typename T>
static inline T abs(T value)
{
    return (value < 0) ? -value : value;
}

class __FlashStringHelper;

#define F(value) reinterpret_cast<const __FlashStringHelper *>(value)

class StringSumHelper
{
public:
    StringSumHelper() = default;
    explicit StringSumHelper(const char *value) : value_(value) {}
    const char *c_str() const { return value_ == nullptr ? "" : value_; }

private:
    const char *value_ = nullptr;
};

class Print
{
public:
    virtual ~Print() = default;
    virtual size_t write(uint8_t value);
    virtual size_t write(const uint8_t *buffer, size_t size);

    size_t print(const char *value);
    size_t print(const __FlashStringHelper *value);
    size_t print(char value);
    size_t print(int value);
    size_t print(unsigned int value);
    size_t print(long value);
    size_t print(unsigned long value);
    size_t print(float value, int digits = 2);

    size_t println();
    size_t println(const char *value);
    size_t println(const __FlashStringHelper *value);
    size_t println(char value);
    size_t println(int value);
    size_t println(unsigned int value);
    size_t println(long value);
    size_t println(unsigned long value);
    size_t println(float value, int digits = 2);
};

extern Print Serial;

unsigned long micros(void);
unsigned long millis(void);
void delay(unsigned long ms);
void delayMicroseconds(unsigned int us);

void pinMode(int pin, int mode);
void digitalWrite(int pin, int value);
int digitalRead(int pin);
int analogRead(int pin);
void analogWrite(int pin, int value);

#endif
