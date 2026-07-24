################################################################################
# Automatically-generated file. Do not edit!
################################################################################

-include ../makefile.init

RM := rm -rf

# All of the sources participating in the build are defined here
-include sources.mk
-include Libraries/iLLD/TC3xx/Tricore/_PinMap/TC37x/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/_Impl/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Stm/Std/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Src/Std/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Scu/Std/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Port/Std/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Pms/Std/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Mtu/Std/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Gtm/Trig/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Gtm/Std/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Gtm/Pwm/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Cpu/Trap/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Cpu/Std/subdir.mk
-include Libraries/iLLD/TC3xx/Tricore/Cpu/Irq/subdir.mk
-include Libraries/Service/CpuGeneric/SysSe/Bsp/subdir.mk
-include Libraries/Infra/Ssw/TC3xx/Tricore/subdir.mk
-include Libraries/Infra/Platform/Tricore/Compilers/subdir.mk
-include Configurations/Debug/subdir.mk
-include Configurations/subdir.mk
-include subdir.mk
ifneq ($(MAKECMDGOALS),clean)
ifneq ($(strip $(C++M_DEPS)),)
-include $(C++M_DEPS)
endif
ifneq ($(strip $(C++_DEPS)),)
-include $(C++_DEPS)
endif
ifneq ($(strip $(CCM_DEPS)),)
-include $(CCM_DEPS)
endif
ifneq ($(strip $(CC_DEPS)),)
-include $(CC_DEPS)
endif
ifneq ($(strip $(CPP_DEPS)),)
-include $(CPP_DEPS)
endif
ifneq ($(strip $(CXXM_DEPS)),)
-include $(CXXM_DEPS)
endif
ifneq ($(strip $(CXX_DEPS)),)
-include $(CXX_DEPS)
endif
ifneq ($(strip $(C_DEPS)),)
-include $(C_DEPS)
endif
ifneq ($(strip $(C_UPPER_DEPS)),)
-include $(C_UPPER_DEPS)
endif
endif

-include ../makefile.defs

OPTIONAL_TOOL_DEPS := \
$(wildcard ../makefile.defs) \
$(wildcard ../makefile.init) \
$(wildcard ../makefile.targets) \


BUILD_ARTIFACT_NAME := open_loop_test
BUILD_ARTIFACT_EXTENSION := elf
BUILD_ARTIFACT_PREFIX :=
BUILD_ARTIFACT := $(BUILD_ARTIFACT_PREFIX)$(BUILD_ARTIFACT_NAME)$(if $(BUILD_ARTIFACT_EXTENSION),.$(BUILD_ARTIFACT_EXTENSION),)

# Add inputs and outputs from these tool invocations to the build variables 
SECONDARY_SIZE += \
open_loop_test.siz \


# All Target
all: main-build

# Main-build Target
main-build: open_loop_test.elf secondary-outputs

# Tool invocations
open_loop_test.elf: $(OBJS) makefile $(OPTIONAL_TOOL_DEPS) .open_loop_test.elf.opt
	@echo 'Building target: $@'
	@echo 'Invoking: TASKING Linker'
	cctc -f .open_loop_test.elf.opt
	@echo 'Finished building target: $@'
	@echo ' '

.open_loop_test.elf.opt:
	@argfile .open_loop_test.elf.opt --lsl-file="../Lcf_Tasking_Tricore_Tc.lsl" -Wl-Oc -Wl-OL -Wl-Ot -Wl-Ox -Wl-Oy -Wl--map-file="open_loop_test.map" -Wl-mc -Wl-mf -Wl-mi -Wl-mk -Wl-ml -Wl-mm -Wl-md -Wl-mr -Wl-mu --no-warnings= -Wl--error-limit=42 --fp-model=3 -lrt --lsl-core=vtc --exceptions --strict --anachronisms --force-c++ -Ctc37x -o"open_loop_test.elf" -Wl-o"open_loop_test.hex:IHEX" $(OBJS)

.PHONY: .open_loop_test.elf.opt

open_loop_test.siz: open_loop_test.elf makefile $(OPTIONAL_TOOL_DEPS)
	@echo 'Invoking: Print Size'
	elfsize  "open_loop_test.elf"
	@echo 'Finished building: $@'
	@echo ' '

# Other Targets
clean:
	-$(RM) open_loop_test.siz open_loop_test.elf
	-@echo ' '

secondary-outputs: $(SECONDARY_SIZE)

.PHONY: all clean dependents main-build

-include ../makefile.targets
