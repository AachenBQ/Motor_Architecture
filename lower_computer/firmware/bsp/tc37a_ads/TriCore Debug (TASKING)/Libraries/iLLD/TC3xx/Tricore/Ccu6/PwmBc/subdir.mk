################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
"../Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.c" 

COMPILED_SRCS += \
"Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.src" 

C_DEPS += \
"./Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.d" 

OBJS += \
"Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.o" 


# Each subdirectory must supply rules for building sources it contributes
"Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.src":"../Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.c" "Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2004 -D__CPU__=tc37x "-fC:/Users/bowen/AURIX-v1.10.16-workspace/aurix_TC375L/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Wc-w508 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.o":"Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.src" "Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"

clean: clean-Libraries-2f-iLLD-2f-TC3xx-2f-Tricore-2f-Ccu6-2f-PwmBc

clean-Libraries-2f-iLLD-2f-TC3xx-2f-Tricore-2f-Ccu6-2f-PwmBc:
	-$(RM) ./Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.d ./Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.o ./Libraries/iLLD/TC3xx/Tricore/Ccu6/PwmBc/IfxCcu6_PwmBc.src

.PHONY: clean-Libraries-2f-iLLD-2f-TC3xx-2f-Tricore-2f-Ccu6-2f-PwmBc

