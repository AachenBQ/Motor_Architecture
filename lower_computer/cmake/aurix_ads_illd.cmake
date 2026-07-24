# AURIX Development Studio 1.10.16 bundles tricore-tc3xx project-initializer
# 1.16-17, which carries iLLD 1.0.1.20.0.  The TC375 Lite kit is a TC37x
# device, so this project vendors the TC37A package from that ADS bundle.

set(INFINEON_ADS_TC3XX_INITIALIZER_VERSION "1.16-17")
set(INFINEON_ILLD_TC37A_VERSION "1.0.1.20.0")

set(INFINEON_ILLD_TC37A_ROOT
    "${CMAKE_CURRENT_LIST_DIR}/../third_party/infineon/iLLD_1_0_1_20_0_TC37A"
    CACHE PATH "Vendored Infineon iLLD 1.0.1.20.0 TC37A package root")
set(INFINEON_TC37A_ADS_BSP_DIR
    "${CMAKE_CURRENT_LIST_DIR}/../firmware/bsp/tc37a_ads"
    CACHE PATH "AURIX Development Studio TC37A startup/linker configuration")
set(LOWER_FIRMWARE_INCLUDE_DIR
    "${CMAKE_CURRENT_LIST_DIR}/../firmware/include")
set(LOWER_FIRMWARE_CONFIG_DIR
    "${CMAKE_CURRENT_LIST_DIR}/../firmware/config")
set(LOWER_SIMPLEFOC_PORT_DIR
    "${CMAKE_CURRENT_LIST_DIR}/../firmware/simplefoc_port")
if(NOT DEFINED SIMPLEFOC_DIR)
    set(SIMPLEFOC_DIR "${CMAKE_CURRENT_LIST_DIR}/../third_party/Arduino-FOC")
endif()

set(INFINEON_ILLD_TC37A_TRICORE
    "${INFINEON_ILLD_TC37A_ROOT}/iLLD/TC3xx/Tricore")
set(INFINEON_ILLD_TC37A_INCLUDE_DIRS
    "${INFINEON_TC37A_ADS_BSP_DIR}"
    "${INFINEON_TC37A_ADS_BSP_DIR}/Configurations"
    "${LOWER_FIRMWARE_INCLUDE_DIR}"
    "${LOWER_FIRMWARE_CONFIG_DIR}"
    "${LOWER_SIMPLEFOC_PORT_DIR}"
    "${LOWER_SIMPLEFOC_PORT_DIR}/arduino_compat"
    "${INFINEON_ILLD_TC37A_ROOT}/iLLD"
    "${INFINEON_ILLD_TC37A_ROOT}/iLLD/TC3xx"
    "${INFINEON_ILLD_TC37A_TRICORE}"
    "${INFINEON_ILLD_TC37A_TRICORE}/Cpu/Std"
    "${INFINEON_ILLD_TC37A_TRICORE}/Gtm/Pwm"
    "${INFINEON_ILLD_TC37A_TRICORE}/Gtm/Std"
    "${INFINEON_ILLD_TC37A_TRICORE}/Gtm/Trig"
    "${INFINEON_ILLD_TC37A_TRICORE}/Pms/Std"
    "${INFINEON_ILLD_TC37A_TRICORE}/Port/Std"
    "${INFINEON_ILLD_TC37A_TRICORE}/Scu/Std"
    "${INFINEON_ILLD_TC37A_TRICORE}/Src/Std"
    "${INFINEON_ILLD_TC37A_TRICORE}/Stm/Std"
    "${INFINEON_ILLD_TC37A_TRICORE}/_Impl"
    "${INFINEON_ILLD_TC37A_TRICORE}/_PinMap"
    "${INFINEON_ILLD_TC37A_TRICORE}/_PinMap/TC37x"
    "${INFINEON_ILLD_TC37A_ROOT}/Infra"
    "${INFINEON_ILLD_TC37A_ROOT}/Infra/Sfr/TC37x"
    "${INFINEON_ILLD_TC37A_ROOT}/Infra/Platform"
    "${INFINEON_ILLD_TC37A_ROOT}/Infra/Ssw/TC3xx/Tricore"
    "${INFINEON_ILLD_TC37A_ROOT}/Service"
    "${INFINEON_ILLD_TC37A_ROOT}/Service/CpuGeneric"
    "${INFINEON_ILLD_TC37A_ROOT}/Service/CpuGeneric/SysSe/Bsp")

if(EXISTS "${INFINEON_ILLD_TC37A_TRICORE}/IfxLldVersion.h")
    add_library(infineon_illd_tc37a INTERFACE)
    target_include_directories(infineon_illd_tc37a INTERFACE
        ${INFINEON_ILLD_TC37A_INCLUDE_DIRS}
    )
    target_compile_definitions(infineon_illd_tc37a INTERFACE
        DEVICE_TC37X=1
        IFX_PIN_PACKAGE_LQFP176=1
    )
endif()

set(LOWER_TC37A_ADS_BSP_SOURCES
    "${INFINEON_TC37A_ADS_BSP_DIR}/GTM_ATOM_3_Phase_Inverter_PWM.c"
    "${INFINEON_TC37A_ADS_BSP_DIR}/DRV8313_handle.c"
    "${INFINEON_TC37A_ADS_BSP_DIR}/tc375_hal_ads.c"
    CACHE INTERNAL "TC37A ADS board-level BSP source files owned by lower_computer")

set(LOWER_TC37A_ADS_BSP_INCLUDE_DIRS
    ${INFINEON_ILLD_TC37A_INCLUDE_DIRS}
    CACHE INTERNAL "TC37A ADS BSP include directories")

set(LOWER_TC375_SIMPLEFOC_PORT_SOURCES
    "${LOWER_SIMPLEFOC_PORT_DIR}/arduino_compat/Arduino.cpp"
    "${LOWER_SIMPLEFOC_PORT_DIR}/arduino_compat/simplefoc_math_overrides.cpp"
    "${LOWER_SIMPLEFOC_PORT_DIR}/simplefoc_tc375_port.cpp"
    "${LOWER_SIMPLEFOC_PORT_DIR}/tc375_simplefoc_adapters.cpp"
    CACHE INTERNAL "TC375 SimpleFOC adapter source files")

set(LOWER_TC375_SIMPLEFOC_INCLUDE_DIRS
    "${LOWER_FIRMWARE_INCLUDE_DIR}"
    "${LOWER_FIRMWARE_CONFIG_DIR}"
    "${LOWER_SIMPLEFOC_PORT_DIR}"
    "${LOWER_SIMPLEFOC_PORT_DIR}/arduino_compat"
    "${SIMPLEFOC_DIR}/src"
    CACHE INTERNAL "TC375 SimpleFOC adapter include directories")
