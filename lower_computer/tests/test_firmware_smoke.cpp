#include "tc375_hal_stub.h"
#include "simplefoc_tc375_port.hpp"

#include <cassert>
#include <cstdio>

extern "C" bool Firmware_CreateStaticTasks(void);
extern "C" void Firmware_FocAdcIsr(void);
extern "C" bool Firmware_CooperativeInit(void);
extern "C" void Firmware_CooperativePoll(void);
extern "C" void Firmware_CooperativeFocAdcIsr(void);

int main()
{
    MotorOpenLoopConfig open_loop = {};
    float duty_a;
    float duty_b;
    float duty_c;

    Tc375HalStub_Reset();

    assert(Firmware_CooperativeInit());
    Firmware_CooperativePoll();
    Firmware_CooperativeFocAdcIsr();
    assert(!Tc375HalStub_GateEnabled());
    assert(!Tc375HalStub_PwmEnabled());

    assert(Firmware_CreateStaticTasks());
    assert(!Tc375HalStub_GateEnabled());
    assert(!Tc375HalStub_PwmEnabled());

    Tc375HalStub_SetPhaseCurrentSample(0.1F, -0.05F, -0.05F, false);
    Firmware_FocAdcIsr();
    assert(!Tc375HalStub_GateEnabled());
    assert(!Tc375HalStub_PwmEnabled());

    open_loop.backend = MOTOR_OPEN_LOOP_SIMPLEFOC;
    open_loop.pole_pairs = 7U;
    open_loop.bus_voltage_v = 24.0F;
    open_loop.voltage_limit_v = 2.0F;
    open_loop.target_velocity_rad_s = 5.0F;
    open_loop.acceleration_rad_s2 = 10.0F;
    open_loop.update_period_ms = 10U;
    open_loop.startup_delay_ms = 0U;
    open_loop.max_runtime_ms = 5000U;
    assert(SimpleFocTc375_OpenLoopStart(&open_loop));
    assert(!Tc375HalStub_GateEnabled());
    assert(Tc375HalStub_PwmEnabled());
    SimpleFocTc375_OpenLoopStep(5.0F);
    Tc375HalStub_GetPhaseDuty(&duty_a, &duty_b, &duty_c);
    assert((duty_a != duty_b) || (duty_b != duty_c));
    SimpleFocTc375_OpenLoopStop();
    assert(!Tc375HalStub_GateEnabled());
    assert(!Tc375HalStub_PwmEnabled());

    puts("lower_computer firmware smoke: OK");
    return 0;
}
