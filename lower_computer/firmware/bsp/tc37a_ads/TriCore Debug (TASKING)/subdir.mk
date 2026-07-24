################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
CPP_SRCS += \
"../simplefoc_arduino_compat_ads.cpp" \
"../simplefoc_bldc_motor_ads.cpp" \
"../simplefoc_current_sense_ads.cpp" \
"../simplefoc_debug_ads.cpp" \
"../simplefoc_foc_motor_ads.cpp" \
"../simplefoc_lowpass_filter_ads.cpp" \
"../simplefoc_pid_ads.cpp" \
"../simplefoc_sensor_ads.cpp" \
"../simplefoc_tc375_port_ads.cpp" \
"../simplefoc_time_utils_ads.cpp" 

C_SRCS += \
"../Cpu0_Main.c" \
"../Cpu1_Main.c" \
"../Cpu2_Main.c" \
"../DRV8313_handle.c" \
"../GTM_ATOM_3_Phase_Inverter_PWM.c" \
"../IfxAsclin_Asc_ads.c" \
"../IfxAsclin_Std_ads.c" \
"../Ifx_CircularBuffer_ads.c" \
"../Ifx_Fifo_ads.c" \
"../command_router_ads.c" \
"../cooperative_app_ads.c" \
"../motor_control_ads.c" \
"../native_protocol_ads.c" \
"../tc375_hal_ads.c" 

COMPILED_SRCS += \
"Cpu0_Main.src" \
"Cpu1_Main.src" \
"Cpu2_Main.src" \
"DRV8313_handle.src" \
"GTM_ATOM_3_Phase_Inverter_PWM.src" \
"IfxAsclin_Asc_ads.src" \
"IfxAsclin_Std_ads.src" \
"Ifx_CircularBuffer_ads.src" \
"Ifx_Fifo_ads.src" \
"command_router_ads.src" \
"cooperative_app_ads.src" \
"motor_control_ads.src" \
"native_protocol_ads.src" \
"simplefoc_arduino_compat_ads.src" \
"simplefoc_bldc_motor_ads.src" \
"simplefoc_current_sense_ads.src" \
"simplefoc_debug_ads.src" \
"simplefoc_foc_motor_ads.src" \
"simplefoc_lowpass_filter_ads.src" \
"simplefoc_pid_ads.src" \
"simplefoc_sensor_ads.src" \
"simplefoc_tc375_port_ads.src" \
"simplefoc_time_utils_ads.src" \
"tc375_hal_ads.src" 

CPP_DEPS += \
"./simplefoc_arduino_compat_ads.d" \
"./simplefoc_bldc_motor_ads.d" \
"./simplefoc_current_sense_ads.d" \
"./simplefoc_debug_ads.d" \
"./simplefoc_foc_motor_ads.d" \
"./simplefoc_lowpass_filter_ads.d" \
"./simplefoc_pid_ads.d" \
"./simplefoc_sensor_ads.d" \
"./simplefoc_tc375_port_ads.d" \
"./simplefoc_time_utils_ads.d" 

C_DEPS += \
"./Cpu0_Main.d" \
"./Cpu1_Main.d" \
"./Cpu2_Main.d" \
"./DRV8313_handle.d" \
"./GTM_ATOM_3_Phase_Inverter_PWM.d" \
"./IfxAsclin_Asc_ads.d" \
"./IfxAsclin_Std_ads.d" \
"./Ifx_CircularBuffer_ads.d" \
"./Ifx_Fifo_ads.d" \
"./command_router_ads.d" \
"./cooperative_app_ads.d" \
"./motor_control_ads.d" \
"./native_protocol_ads.d" \
"./tc375_hal_ads.d" 

OBJS += \
"Cpu0_Main.o" \
"Cpu1_Main.o" \
"Cpu2_Main.o" \
"DRV8313_handle.o" \
"GTM_ATOM_3_Phase_Inverter_PWM.o" \
"IfxAsclin_Asc_ads.o" \
"IfxAsclin_Std_ads.o" \
"Ifx_CircularBuffer_ads.o" \
"Ifx_Fifo_ads.o" \
"command_router_ads.o" \
"cooperative_app_ads.o" \
"motor_control_ads.o" \
"native_protocol_ads.o" \
"simplefoc_arduino_compat_ads.o" \
"simplefoc_bldc_motor_ads.o" \
"simplefoc_current_sense_ads.o" \
"simplefoc_debug_ads.o" \
"simplefoc_foc_motor_ads.o" \
"simplefoc_lowpass_filter_ads.o" \
"simplefoc_pid_ads.o" \
"simplefoc_sensor_ads.o" \
"simplefoc_tc375_port_ads.o" \
"simplefoc_time_utils_ads.o" \
"tc375_hal_ads.o" 


# Each subdirectory must supply rules for building sources it contributes
"Cpu0_Main.src":"../Cpu0_Main.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Cpu0_Main.o":"Cpu0_Main.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"Cpu1_Main.src":"../Cpu1_Main.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Cpu1_Main.o":"Cpu1_Main.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"Cpu2_Main.src":"../Cpu2_Main.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Cpu2_Main.o":"Cpu2_Main.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"DRV8313_handle.src":"../DRV8313_handle.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"DRV8313_handle.o":"DRV8313_handle.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"GTM_ATOM_3_Phase_Inverter_PWM.src":"../GTM_ATOM_3_Phase_Inverter_PWM.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"GTM_ATOM_3_Phase_Inverter_PWM.o":"GTM_ATOM_3_Phase_Inverter_PWM.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"IfxAsclin_Asc_ads.src":"../IfxAsclin_Asc_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"IfxAsclin_Asc_ads.o":"IfxAsclin_Asc_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"IfxAsclin_Std_ads.src":"../IfxAsclin_Std_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"IfxAsclin_Std_ads.o":"IfxAsclin_Std_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"Ifx_CircularBuffer_ads.src":"../Ifx_CircularBuffer_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Ifx_CircularBuffer_ads.o":"Ifx_CircularBuffer_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"Ifx_Fifo_ads.src":"../Ifx_Fifo_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"Ifx_Fifo_ads.o":"Ifx_Fifo_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"command_router_ads.src":"../command_router_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"command_router_ads.o":"command_router_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"cooperative_app_ads.src":"../cooperative_app_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"cooperative_app_ads.o":"cooperative_app_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"motor_control_ads.src":"../motor_control_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"motor_control_ads.o":"motor_control_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"native_protocol_ads.src":"../native_protocol_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"native_protocol_ads.o":"native_protocol_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_arduino_compat_ads.src":"../simplefoc_arduino_compat_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_arduino_compat_ads.o":"simplefoc_arduino_compat_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_bldc_motor_ads.src":"../simplefoc_bldc_motor_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_bldc_motor_ads.o":"simplefoc_bldc_motor_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_current_sense_ads.src":"../simplefoc_current_sense_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_current_sense_ads.o":"simplefoc_current_sense_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_debug_ads.src":"../simplefoc_debug_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_debug_ads.o":"simplefoc_debug_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_foc_motor_ads.src":"../simplefoc_foc_motor_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_foc_motor_ads.o":"simplefoc_foc_motor_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_lowpass_filter_ads.src":"../simplefoc_lowpass_filter_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_lowpass_filter_ads.o":"simplefoc_lowpass_filter_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_pid_ads.src":"../simplefoc_pid_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_pid_ads.o":"simplefoc_pid_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_sensor_ads.src":"../simplefoc_sensor_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_sensor_ads.o":"simplefoc_sensor_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_tc375_port_ads.src":"../simplefoc_tc375_port_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_tc375_port_ads.o":"simplefoc_tc375_port_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"simplefoc_time_utils_ads.src":"../simplefoc_time_utils_ads.cpp" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"simplefoc_time_utils_ads.o":"simplefoc_time_utils_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"
"tc375_hal_ads.src":"../tc375_hal_ads.c" "subdir.mk"
	cctc -cs --dep-file="$*.d" --misrac-version=2012 "-fC:/Users/BQ/Documents/motor_control/lower_computer/firmware/bsp/tc37a_ads/TriCore Debug (TASKING)/TASKING_C_C___Compiler-Include_paths__-I_.opt" --iso=99 --c++14 --language=+volatile --exceptions --anachronisms --fp-model=3 -O0 --tradeoff=4 --compact-max-size=200 -g -Wc-w544 -Wc-w557 -Ctc37x -Y0 -N0 -Z0 -o "$@" "$<"
"tc375_hal_ads.o":"tc375_hal_ads.src" "subdir.mk"
	astc -Og -Os --no-warnings= --error-limit=42 -o  "$@" "$<"

clean: clean--2e-

clean--2e-:
	-$(RM) ./Cpu0_Main.d ./Cpu0_Main.o ./Cpu0_Main.src ./Cpu1_Main.d ./Cpu1_Main.o ./Cpu1_Main.src ./Cpu2_Main.d ./Cpu2_Main.o ./Cpu2_Main.src ./DRV8313_handle.d ./DRV8313_handle.o ./DRV8313_handle.src ./GTM_ATOM_3_Phase_Inverter_PWM.d ./GTM_ATOM_3_Phase_Inverter_PWM.o ./GTM_ATOM_3_Phase_Inverter_PWM.src ./IfxAsclin_Asc_ads.d ./IfxAsclin_Asc_ads.o ./IfxAsclin_Asc_ads.src ./IfxAsclin_Std_ads.d ./IfxAsclin_Std_ads.o ./IfxAsclin_Std_ads.src ./Ifx_CircularBuffer_ads.d ./Ifx_CircularBuffer_ads.o ./Ifx_CircularBuffer_ads.src ./Ifx_Fifo_ads.d ./Ifx_Fifo_ads.o ./Ifx_Fifo_ads.src ./command_router_ads.d ./command_router_ads.o ./command_router_ads.src ./cooperative_app_ads.d ./cooperative_app_ads.o ./cooperative_app_ads.src ./motor_control_ads.d ./motor_control_ads.o ./motor_control_ads.src ./native_protocol_ads.d ./native_protocol_ads.o ./native_protocol_ads.src ./simplefoc_arduino_compat_ads.d ./simplefoc_arduino_compat_ads.o ./simplefoc_arduino_compat_ads.src ./simplefoc_bldc_motor_ads.d ./simplefoc_bldc_motor_ads.o ./simplefoc_bldc_motor_ads.src ./simplefoc_current_sense_ads.d ./simplefoc_current_sense_ads.o ./simplefoc_current_sense_ads.src ./simplefoc_debug_ads.d ./simplefoc_debug_ads.o ./simplefoc_debug_ads.src ./simplefoc_foc_motor_ads.d ./simplefoc_foc_motor_ads.o ./simplefoc_foc_motor_ads.src ./simplefoc_lowpass_filter_ads.d ./simplefoc_lowpass_filter_ads.o ./simplefoc_lowpass_filter_ads.src ./simplefoc_pid_ads.d ./simplefoc_pid_ads.o ./simplefoc_pid_ads.src ./simplefoc_sensor_ads.d ./simplefoc_sensor_ads.o ./simplefoc_sensor_ads.src ./simplefoc_tc375_port_ads.d ./simplefoc_tc375_port_ads.o ./simplefoc_tc375_port_ads.src ./simplefoc_time_utils_ads.d ./simplefoc_time_utils_ads.o ./simplefoc_time_utils_ads.src ./tc375_hal_ads.d ./tc375_hal_ads.o ./tc375_hal_ads.src

.PHONY: clean--2e-

