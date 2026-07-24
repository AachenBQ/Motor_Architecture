#include "../../../third_party/Arduino-FOC/src/common/foc_utils.h"

float _sin(float angle)
{
    return sinf(angle);
}

float _cos(float angle)
{
    return cosf(angle);
}

void _sincos(float angle, float *sine, float *cosine)
{
    *sine = _sin(angle);
    *cosine = _cos(angle);
}

float _atan2(float y, float x)
{
    return atan2f(y, x);
}

float _normalizeAngle(float angle)
{
    float normalized = fmodf(angle, _2PI);
    return normalized >= 0.0F ? normalized : normalized + _2PI;
}

float _electricalAngle(float shaft_angle, int pole_pairs)
{
    return shaft_angle * (float)pole_pairs;
}

float _sqrtApprox(float value)
{
    return sqrtf(value);
}
