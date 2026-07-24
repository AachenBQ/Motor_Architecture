################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
"../Cpu0_Main.c" \
"../Cpu1_Main.c" \
"../Cpu2_Main.c" \
"../DRV8313_handle.c" \
"../GTM_ATOM_3_Phase_Inverter_PWM.c" \
"../tc375_hal_ads.c" 

COMPILED_SRCS += \
"Cpu0_Main.src" \
"Cpu1_Main.src" \
"Cpu2_Main.src" \
"DRV8313_handle.src" \
"GTM_ATOM_3_Phase_Inverter_PWM.src" \
"tc375_hal_ads.src" 

C_DEPS += \
"./Cpu0_Main.d" \
"./Cpu1_Main.d" \
"./Cpu2_Main.d" \
"./DRV8313_handle.d" \
"./GTM_ATOM_3_Phase_Inverter_PWM.d" \
"./tc375_hal_ads.d" 

OBJS += \
"Cpu0_Main.o" \
"Cpu1_Main.o" \
"Cpu2_Main.o" \
"DRV8313_handle.o" \
"GTM_ATOM_3_Phase_Inverter_PWM.o" \
"tc375_hal_ads.o" 


# Each subdirectory must supply rules for building sources it contributes
"Cpu0_Main.src":"../Cpu0_Main.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2004 "-fD:/Violin_demo/Motor_Architecture/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Cpu0_Main.o":"Cpu0_Main.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"Cpu1_Main.src":"../Cpu1_Main.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2004 "-fD:/Violin_demo/Motor_Architecture/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Cpu1_Main.o":"Cpu1_Main.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"Cpu2_Main.src":"../Cpu2_Main.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2004 "-fD:/Violin_demo/Motor_Architecture/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Cpu2_Main.o":"Cpu2_Main.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"DRV8313_handle.src":"../DRV8313_handle.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2004 "-fD:/Violin_demo/Motor_Architecture/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"DRV8313_handle.o":"DRV8313_handle.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"GTM_ATOM_3_Phase_Inverter_PWM.src":"../GTM_ATOM_3_Phase_Inverter_PWM.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2004 "-fD:/Violin_demo/Motor_Architecture/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"GTM_ATOM_3_Phase_Inverter_PWM.o":"GTM_ATOM_3_Phase_Inverter_PWM.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"tc375_hal_ads.src":"../tc375_hal_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2004 "-fD:/Violin_demo/Motor_Architecture/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"tc375_hal_ads.o":"tc375_hal_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"

clean: clean--2e-

clean--2e-:
	-$(RM) ./Cpu0_Main.d ./Cpu0_Main.o ./Cpu0_Main.src ./Cpu1_Main.d ./Cpu1_Main.o ./Cpu1_Main.src ./Cpu2_Main.d ./Cpu2_Main.o ./Cpu2_Main.src ./DRV8313_handle.d ./DRV8313_handle.o ./DRV8313_handle.src ./GTM_ATOM_3_Phase_Inverter_PWM.d ./GTM_ATOM_3_Phase_Inverter_PWM.o ./GTM_ATOM_3_Phase_Inverter_PWM.src ./tc375_hal_ads.d ./tc375_hal_ads.o ./tc375_hal_ads.src

.PHONY: clean--2e-

