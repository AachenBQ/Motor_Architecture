#include "tc375_hal_stub.h"

#include <cassert>
#include <cstdio>

extern "C" bool Firmware_CreateStaticTasks(void);
extern "C" void Firmware_FocAdcIsr(void);

int main()
{
    Tc375HalStub_Reset();

    assert(Firmware_CreateStaticTasks());
    assert(!Tc375HalStub_GateEnabled());
    assert(!Tc375HalStub_PwmEnabled());

    Tc375HalStub_SetPhaseCurrentSample(0.1F, -0.05F, -0.05F, false);
    Firmware_FocAdcIsr();
    assert(!Tc375HalStub_GateEnabled());
    assert(!Tc375HalStub_PwmEnabled());

    puts("lower_computer firmware smoke: OK");
    return 0;
}
