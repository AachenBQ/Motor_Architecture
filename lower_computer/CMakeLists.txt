cmake_minimum_required(VERSION 3.20)

project(lower_computer_firmware C CXX)

option(LOWER_BUILD_TESTS "Build host-side regression and smoke tests" ON)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(FREERTOS_KERNEL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/FreeRTOS-Kernel")
set(SIMPLEFOC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/Arduino-FOC")

include(cmake/aurix_ads_illd.cmake)

if(NOT EXISTS "${FREERTOS_KERNEL_DIR}/tasks.c")
    message(FATAL_ERROR "FreeRTOS-Kernel submodule is missing. Run: git submodule update --init --recursive")
endif()

if(NOT EXISTS "${SIMPLEFOC_DIR}/src/BLDCMotor.cpp")
    message(FATAL_ERROR "Arduino-FOC submodule is missing. Run: git submodule update --init --recursive")
endif()

add_library(lower_core STATIC
    firmware/src/motor_control.c
    firmware/src/native_protocol.c
)
target_include_directories(lower_core
    PUBLIC
        firmware/config
        firmware/include
)

add_library(freertos_kernel_host STATIC
    tests/host/freertos_hooks.c
    ${FREERTOS_KERNEL_DIR}/list.c
    ${FREERTOS_KERNEL_DIR}/queue.c
    ${FREERTOS_KERNEL_DIR}/tasks.c
    ${FREERTOS_KERNEL_DIR}/portable/MSVC-MingW/port.c
)
target_include_directories(freertos_kernel_host
    PUBLIC
        firmware/freertos
        ${FREERTOS_KERNEL_DIR}/include
        ${FREERTOS_KERNEL_DIR}/portable/MSVC-MingW
)
target_compile_definitions(freertos_kernel_host
    PRIVATE
        WIN32_LEAN_AND_MEAN
        NOMINMAX
)
if(WIN32)
    target_link_libraries(freertos_kernel_host PUBLIC winmm)
endif()

add_library(simplefoc_core STATIC
    firmware/simplefoc_port/arduino_compat/Arduino.cpp
    firmware/simplefoc_port/arduino_compat/simplefoc_math_overrides.cpp
    ${SIMPLEFOC_DIR}/src/BLDCMotor.cpp
    ${SIMPLEFOC_DIR}/src/common/base_classes/CurrentSense.cpp
    ${SIMPLEFOC_DIR}/src/common/base_classes/FOCMotor.cpp
    ${SIMPLEFOC_DIR}/src/common/base_classes/Sensor.cpp
    ${SIMPLEFOC_DIR}/src/common/lowpass_filter.cpp
    ${SIMPLEFOC_DIR}/src/common/pid.cpp
    ${SIMPLEFOC_DIR}/src/common/time_utils.cpp
    ${SIMPLEFOC_DIR}/src/communication/SimpleFOCDebug.cpp
)
target_include_directories(simplefoc_core
    PUBLIC
        firmware/config
        firmware/include
        firmware/simplefoc_port/arduino_compat
        ${SIMPLEFOC_DIR}/src
)
target_compile_definitions(simplefoc_core
    PUBLIC
        SIMPLEFOC_DISABLE_DEBUG
        MOTOR_HOST_BUILD=1
)

add_library(lower_firmware_host STATIC
    firmware/app/cooperative_app.c
    firmware/app/freertos_app.c
    firmware/simplefoc_port/simplefoc_tc375_port.cpp
    firmware/simplefoc_port/tc375_simplefoc_adapters.cpp
    firmware/src/command_router.c
    tests/host/tc375_hal_stub.c
)
target_include_directories(lower_firmware_host
    PUBLIC
        firmware/app
        firmware/config
        firmware/include
        firmware/simplefoc_port
        tests/host
)
target_compile_definitions(lower_firmware_host
    PUBLIC
        MOTOR_CONTROL_HARDWARE_ENABLED=1
        MOTOR_POWER_STAGE_ENABLED=0
        MOTOR_USE_SIMPLEFOC=1
)
target_link_libraries(lower_firmware_host
    PUBLIC
        lower_core
        freertos_kernel_host
        simplefoc_core
)

if(LOWER_BUILD_TESTS)
    enable_testing()

    add_executable(lower_core_test tests/test_core.c)
    target_link_libraries(lower_core_test PRIVATE lower_core)
    add_test(NAME lower_core_test COMMAND lower_core_test)

    add_executable(
        lower_command_router_test
        tests/test_command_router.c
        firmware/src/command_router.c
        tests/host/tc375_hal_stub.c
    )
    target_include_directories(
        lower_command_router_test
        PRIVATE
            firmware/config
            firmware/include
            tests/host
    )
    target_link_libraries(
        lower_command_router_test
        PRIVATE
            lower_core
    )
    add_test(
        NAME lower_command_router_test
        COMMAND lower_command_router_test
    )

    add_executable(lower_firmware_smoke tests/test_firmware_smoke.cpp)
    target_link_libraries(lower_firmware_smoke PRIVATE lower_firmware_host)
    add_test(NAME lower_firmware_smoke COMMAND lower_firmware_smoke)
endif()
