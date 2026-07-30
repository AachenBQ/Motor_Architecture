#ifndef TC375_SIMPLEFOC_ADAPTERS_HPP
#define TC375_SIMPLEFOC_ADAPTERS_HPP

#include "project_config.h"

#if MOTOR_USE_SIMPLEFOC

#include "../../third_party/Arduino-FOC/src/BLDCMotor.h"
#include "../../third_party/Arduino-FOC/src/common/base_classes/CurrentSense.h"
#include "../../third_party/Arduino-FOC/src/common/base_classes/Sensor.h"

class Tc375BldcDriver final : public BLDCDriver
{
public:
    Tc375BldcDriver();
    int init() override;
    void enable() override;
    void disable() override;
    void setPwm(float ua, float ub, float uc) override;
    void setPhaseState(PhaseState sa, PhaseState sb, PhaseState sc) override;
    void setInitializationInhibit(bool inhibited);
    bool isOutputEnabled() const;

private:
    bool initialization_inhibit_ = false;
    bool output_enabled_ = false;
};

class Tc375Encoder final : public Sensor
{
public:
    void init() override;
    bool isValid() const;
    void update() override;
    float getMechanicalAngle() override;
    float getAngle() override;
    double getPreciseAngle() override;
    float getVelocity() override;
    int32_t getFullRotations() override;
    int needsSearch() override;

protected:
    float getSensorAngle() override;

private:
    float mechanical_angle_rad_ = 0.0F;
    float multi_turn_angle_rad_ = 0.0F;
    float velocity_rad_s_ = 0.0F;
    bool valid_ = false;
};

class Tc375CurrentSense final : public CurrentSense
{
public:
    Tc375CurrentSense();
    int init() override;
    PhaseCurrent_s getPhaseCurrents() override;
    int driverAlign(float align_voltage, bool modulation_centered = false) override;
};

#endif

#endif
