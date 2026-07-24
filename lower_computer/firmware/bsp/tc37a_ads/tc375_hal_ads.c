#include "tc375_hal.h"

#include "DRV8313_handle.h"
#include "GTM_ATOM_3_Phase_Inverter_PWM.h"
#include "tc375_board_config.h"

#include "Asclin/Asc/IfxAsclin_Asc.h"
#include "Bsp.h"
#include "IfxAsclin_PinMap.h"
#include "IfxCpu.h"
#include "IfxCpu_Irq.h"
#include "IfxStm.h"

#ifndef TC375_HAL_ADS_BUS_VOLTAGE_V
#define TC375_HAL_ADS_BUS_VOLTAGE_V (24.0f)
#endif

#ifndef TC375_HAL_ADS_TEMPERATURE_C
#define TC375_HAL_ADS_TEMPERATURE_C (25.0f)
#endif

#define TC375_HAL_FAULT_GATE_DRIVER (1UL << 5)

static boolean g_motor_peripherals_initialized = FALSE;
static boolean g_pwm_enabled = FALSE;
static boolean g_gate_enabled = FALSE;

#if TC375_BOARD_UART_ENABLED
static IfxAsclin_Asc g_uart;
static boolean g_uart_initialized = FALSE;

IFX_ALIGN(4)
static uint8 g_uart_rx_buffer[
    TC375_BOARD_UART_RX_BUFFER_SIZE + sizeof(Ifx_Fifo) + 8U];

IFX_ALIGN(4)
static uint8 g_uart_tx_buffer[
    TC375_BOARD_UART_TX_BUFFER_SIZE + sizeof(Ifx_Fifo) + 8U];

IFX_INTERRUPT(
    Tc375Hal_AsclinTxIsr,
    0,
    TC375_BOARD_UART_TX_ISR_PRIORITY);
IFX_INTERRUPT(
    Tc375Hal_AsclinRxIsr,
    0,
    TC375_BOARD_UART_RX_ISR_PRIORITY);
IFX_INTERRUPT(
    Tc375Hal_AsclinErrorIsr,
    0,
    TC375_BOARD_UART_ERR_ISR_PRIORITY);

void Tc375Hal_AsclinTxIsr(void)
{
    IfxAsclin_Asc_isrTransmit(&g_uart);
}

void Tc375Hal_AsclinRxIsr(void)
{
    IfxAsclin_Asc_isrReceive(&g_uart);
}

void Tc375Hal_AsclinErrorIsr(void)
{
    IfxAsclin_Asc_isrError(&g_uart);
}

static boolean Tc375Hal_UartInit(void)
{
    IfxAsclin_Asc_Config config;
    IfxAsclin_Status status;
    const IfxAsclin_Asc_Pins pins = {
        NULL_PTR,
        IfxPort_InputMode_pullUp,
        &TC375_BOARD_UART_RX_PIN,
        IfxPort_InputMode_pullUp,
        NULL_PTR,
        IfxPort_OutputMode_pushPull,
        &TC375_BOARD_UART_TX_PIN,
        IfxPort_OutputMode_pushPull,
        IfxPort_PadDriver_cmosAutomotiveSpeed1
    };

    if (g_uart_initialized != FALSE)
    {
        return TRUE;
    }

    IfxAsclin_Asc_initModuleConfig(
        &config,
        &TC375_BOARD_UART_MODULE);
    config.baudrate.prescaler = 1U;
    config.baudrate.baudrate =
        (float32)TC375_BOARD_UART_BAUDRATE;
    config.interrupt.txPriority =
        TC375_BOARD_UART_TX_ISR_PRIORITY;
    config.interrupt.rxPriority =
        TC375_BOARD_UART_RX_ISR_PRIORITY;
    config.interrupt.erPriority =
        TC375_BOARD_UART_ERR_ISR_PRIORITY;
    config.interrupt.typeOfService =
        IfxCpu_Irq_getTos(IfxCpu_getCoreIndex());
    config.txBuffer = g_uart_tx_buffer;
    config.txBufferSize =
        (Ifx_SizeT)TC375_BOARD_UART_TX_BUFFER_SIZE;
    config.rxBuffer = g_uart_rx_buffer;
    config.rxBufferSize =
        (Ifx_SizeT)TC375_BOARD_UART_RX_BUFFER_SIZE;
    config.pins = &pins;

    status = IfxAsclin_Asc_initModule(&g_uart, &config);
    if (status != IfxAsclin_Status_noError)
    {
        return FALSE;
    }

    g_uart_initialized = TRUE;
    return TRUE;
}
#endif

static float Tc375Hal_ClampUnitDuty(float duty)
{
    if (duty < 0.0f)
    {
        return 0.0f;
    }

    if (duty > 1.0f)
    {
        return 1.0f;
    }

    return duty;
}

bool Tc375Hal_BoardInit(void)
{
#if TC375_BOARD_UART_ENABLED
    return Tc375Hal_UartInit() != FALSE;
#else
    return true;
#endif
}

uint32_t Tc375Hal_TimeMs(void)
{
    return Tc375Hal_TimeUs() / 1000U;
}

uint32_t Tc375Hal_TimeUs(void)
{
    uint32 ticks;
    uint32 frequency_hz;

    ticks = IfxStm_getLower(BSP_DEFAULT_TIMER);
    frequency_hz = (uint32)IfxStm_getFrequency(BSP_DEFAULT_TIMER);

    if (frequency_hz == 0U)
    {
        return 0U;
    }

    return (uint32_t)(((uint64)ticks * 1000000ULL) / (uint64)frequency_hz);
}

void Tc375Hal_ServiceWatchdogs(void)
{
}

size_t Tc375Hal_UartRead(uint8_t *destination, size_t capacity)
{
#if TC375_BOARD_UART_ENABLED
    sint32 available;
    Ifx_SizeT count;

    if ((g_uart_initialized == FALSE) ||
        (destination == NULL) ||
        (capacity == 0U))
    {
        return 0U;
    }

    available = IfxAsclin_Asc_getReadCount(&g_uart);
    if (available <= 0)
    {
        return 0U;
    }

    count = (Ifx_SizeT)capacity;
    if (count > (Ifx_SizeT)available)
    {
        count = (Ifx_SizeT)available;
    }

    if (IfxAsclin_Asc_read(
            &g_uart,
            destination,
            &count,
            TIME_NULL) == FALSE)
    {
        return 0U;
    }

    return count > 0 ? (size_t)count : 0U;
#else
    (void)destination;
    (void)capacity;
    return 0U;
#endif
}

bool Tc375Hal_UartQueueTx(
    const uint8_t *data,
    size_t length,
    bool high_priority)
{
#if TC375_BOARD_UART_ENABLED
    boolean interrupts_were_enabled;
    boolean written;
    Ifx_SizeT count;

    (void)high_priority;
    if (length == 0U)
    {
        return true;
    }
    if ((g_uart_initialized == FALSE) ||
        (data == NULL) ||
        (length > (size_t)TC375_BOARD_UART_TX_BUFFER_SIZE))
    {
        return false;
    }

    count = (Ifx_SizeT)length;
    interrupts_were_enabled = IfxCpu_disableInterrupts();
    written = IfxAsclin_Asc_write(
        &g_uart,
        data,
        &count,
        TIME_NULL);
    IfxCpu_restoreInterrupts(interrupts_were_enabled);
    return (written != FALSE) && ((size_t)count == length);
#else
    (void)data;
    (void)length;
    (void)high_priority;
    return false;
#endif
}

bool Tc375Hal_MotorPeripheralsInit(void)
{
    if (g_motor_peripherals_initialized == FALSE)
    {
        Drv8313_init();
        initGtmAtom3phInv();
        GtmAtom3phInv_setSafeDuty();
        g_motor_peripherals_initialized = TRUE;
    }

    return true;
}

Tc375PhaseCurrents Tc375Hal_ReadPhaseCurrents(void)
{
    Tc375PhaseCurrents currents;

    currents.phase_a = 0.0f;
    currents.phase_b = 0.0f;
    currents.phase_c = 0.0f;
    currents.sample_valid = false;

    return currents;
}

Tc375EncoderSample Tc375Hal_ReadEncoder(void)
{
    Tc375EncoderSample sample;

    sample.mechanical_angle_rad = 0.0f;
    sample.multi_turn_angle_rad = 0.0f;
    sample.velocity_rad_s = 0.0f;
    sample.valid = false;

    return sample;
}

float Tc375Hal_ReadBusVoltage(void)
{
    return TC375_HAL_ADS_BUS_VOLTAGE_V;
}

float Tc375Hal_ReadPowerTemperature(void)
{
    return TC375_HAL_ADS_TEMPERATURE_C;
}

void Tc375Hal_SetPhaseDuty(float phase_a, float phase_b, float phase_c)
{
    float duty_u;
    float duty_v;
    float duty_w;

    /*
     * PWM pin generation and power-stage gating are intentionally separate.
     * With MOTOR_POWER_STAGE_ENABLED=0 the MCU TOUT pins can be inspected on
     * an oscilloscope while DRV8313 nSLEEP/nRESET stay asserted low.
     */
    if (g_pwm_enabled == FALSE)
    {
        GtmAtom3phInv_setSafeDuty();
        return;
    }

    duty_u = Tc375Hal_ClampUnitDuty(phase_a) * 100.0f;
    duty_v = Tc375Hal_ClampUnitDuty(phase_b) * 100.0f;
    duty_w = Tc375Hal_ClampUnitDuty(phase_c) * 100.0f;

    GtmAtom3phInv_setDuty(duty_u, duty_v, duty_w);
}

void Tc375Hal_SetPwmEnabled(bool enabled)
{
#if MOTOR_CONTROL_HARDWARE_ENABLED
    g_pwm_enabled = enabled ? TRUE : FALSE;
#else
    (void)enabled;
    g_pwm_enabled = FALSE;
#endif

    if (g_pwm_enabled == FALSE)
    {
        GtmAtom3phInv_setSafeDuty();
    }
}

void Tc375Hal_SetGateEnabled(bool enabled)
{
#if MOTOR_POWER_STAGE_ENABLED
    if (enabled)
    {
        if (Tc375Hal_MotorPeripheralsInit() == true)
        {
            Drv8313_enable();
            g_gate_enabled = (Drv8313_getStatus() == DRV8313_STATUS_READY) ? TRUE : FALSE;
        }
    }
    else
    {
        GtmAtom3phInv_setSafeDuty();
        Drv8313_disable();
        g_gate_enabled = FALSE;
    }
#else
    (void)enabled;
    GtmAtom3phInv_setSafeDuty();
    Drv8313_disable();
    g_gate_enabled = FALSE;
#endif
}

uint32_t Tc375Hal_ReadActiveFaults(void)
{
#if MOTOR_POWER_STAGE_ENABLED
    if (Drv8313_hasFault() == TRUE)
    {
        return TC375_HAL_FAULT_GATE_DRIVER;
    }
#endif

    return 0U;
}

bool Tc375Hal_LoadCalibration(void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}

bool Tc375Hal_LoadConfiguration(void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}

bool Tc375Hal_SaveConfiguration(const void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}
