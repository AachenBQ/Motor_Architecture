#include "project_config.h"
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
#define TC375_HAL_ADS_BUS_VOLTAGE_V (7.0f)
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
static uint16_t g_uart_high_priority_failures;
static uint16_t g_uart_telemetry_drops;
static volatile uint16_t g_uart_rx_sw_fifo_overflows;
static volatile uint16_t g_uart_rx_hw_fifo_overflows;
static volatile uint16_t g_uart_rx_frame_errors;
static volatile uint16_t g_uart_rx_parity_errors;
static volatile uint16_t g_uart_rx_isr_entries;
static volatile uint16_t g_uart_rx_poll_drains;
static volatile uint16_t g_uart_rx_poll_bytes;

IFX_ALIGN(4)
static uint8 g_uart_rx_buffer[
    TC375_BOARD_UART_RX_BUFFER_SIZE + sizeof(Ifx_Fifo) + 8U];

IFX_ALIGN(4)
static uint8 g_uart_tx_buffer[
    TC375_BOARD_UART_TX_BUFFER_SIZE + sizeof(Ifx_Fifo) + 8U];

static void Tc375Hal_IncrementUartCounter(
    volatile uint16_t *counter)
{
    if (*counter != UINT16_MAX)
    {
        ++(*counter);
    }
}

static void Tc375Hal_AddUartCounter(
    volatile uint16_t *counter,
    uint16_t amount)
{
    uint32_t sum = (uint32_t)(*counter) + (uint32_t)amount;

    *counter =
        sum > (uint32_t)UINT16_MAX
            ? UINT16_MAX
            : (uint16_t)sum;
}

/*
 * Move every byte currently present in the 16-byte ASCLIN hardware FIFO into
 * the iLLD software FIFO. Both the RX ISR and the bounded polling fallback use
 * this ordinary helper, so there is only one producer implementation.
 *
 * The caller serializes access by either running in the ISR or disabling CPU
 * interrupts. Reading RXDATA makes the FIFO level fall naturally; do not
 * manually clear RFL or the SRC request because a concurrently arriving byte
 * could otherwise lose its interrupt indication.
 */
static uint8_t Tc375Hal_DrainUartRxHardwareFifo(void)
{
    uint8 data[16];
    uint8_t count =
        (uint8_t)IfxAsclin_getRxFifoFillLevel(g_uart.asclin);

    if (count == 0U)
    {
        return 0U;
    }

    (void)IfxAsclin_read8(
        g_uart.asclin,
        data,
        (uint32)count);
    if (Ifx_Fifo_write(
            g_uart.rx,
            data,
            (Ifx_SizeT)count,
            TIME_NULL) != 0)
    {
        Tc375Hal_IncrementUartCounter(
            &g_uart_rx_sw_fifo_overflows);
    }

    return count;
}

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
    Tc375Hal_IncrementUartCounter(&g_uart_rx_isr_entries);
    (void)Tc375Hal_DrainUartRxHardwareFifo();
}

void Tc375Hal_AsclinErrorIsr(void)
{
    /*
     * iLLD stores detected hardware errors in sticky handle fields. Clear
     * the previous snapshot first so every interrupt is counted once.
     */
    g_uart.errorFlags.ALL = 0U;
    IfxAsclin_Asc_isrError(&g_uart);
    if (g_uart.errorFlags.flags.rxFifoOverflow != 0U)
    {
        Tc375Hal_IncrementUartCounter(
            &g_uart_rx_hw_fifo_overflows);
    }
    if (g_uart.errorFlags.flags.frameError != 0U)
    {
        Tc375Hal_IncrementUartCounter(
            &g_uart_rx_frame_errors);
    }
    if (g_uart.errorFlags.flags.parityError != 0U)
    {
        Tc375Hal_IncrementUartCounter(
            &g_uart_rx_parity_errors);
    }
    g_uart.errorFlags.ALL = 0U;
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
    config.baudrate.oversampling =
        TC375_BOARD_UART_OVERSAMPLING;
    config.bitTiming.samplePointPosition =
        TC375_BOARD_UART_SAMPLE_POINT;
    config.bitTiming.medianFilter =
        TC375_BOARD_UART_SAMPLES_PER_BIT;
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
    /*
     * Drain every received byte into the software FIFO immediately. Keeping
     * the level explicit prevents a future iLLD default change from leaving
     * the tail of a short or segmented command in the 16-byte hardware FIFO.
     */
    config.fifo.rxFifoInterruptLevel =
        IfxAsclin_RxFifoInterruptLevel_1;
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
    return (uint32_t)Tc375Hal_TimeMs64();
}

uint64_t Tc375Hal_TimeMs64(void)
{
    uint64 ticks;
    uint64 whole_seconds;
    uint64 remaining_ticks;
    uint32 frequency_hz;

    ticks = IfxStm_get(BSP_DEFAULT_TIMER);
    frequency_hz =
        (uint32)IfxStm_getFrequency(BSP_DEFAULT_TIMER);

    if (frequency_hz == 0U)
    {
        return 0ULL;
    }

    /*
     * Use the full 64-bit STM value before converting to milliseconds.
     * IfxStm_getLower() wraps after roughly 42.95 s at 100 MHz; deriving
     * protocol timeouts from that 32-bit tick value made elapsed-time
     * subtraction report a huge false timeout at every wrap.
     */
    whole_seconds = ticks / (uint64)frequency_hz;
    remaining_ticks = ticks % (uint64)frequency_hz;
    return (uint64_t)(
        (whole_seconds * 1000ULL) +
        ((remaining_ticks * 1000ULL) /
         (uint64)frequency_hz));
}

uint32_t Tc375Hal_TimeUs(void)
{
    uint64 ticks;
    uint32 frequency_hz;

    ticks = IfxStm_get(BSP_DEFAULT_TIMER);
    frequency_hz = (uint32)IfxStm_getFrequency(BSP_DEFAULT_TIMER);

    if (frequency_hz == 0U)
    {
        return 0U;
    }

    return (uint32_t)(
        (ticks * 1000000ULL) / (uint64)frequency_hz);
}

void Tc375Hal_ServiceWatchdogs(void)
{
}

size_t Tc375Hal_UartRead(uint8_t *destination, size_t capacity)
{
#if TC375_BOARD_UART_ENABLED
    boolean interrupts_were_enabled;
    sint32 available;
    Ifx_SizeT count;
    uint8_t drain_attempt;
    uint8_t drained;

    if ((g_uart_initialized == FALSE) ||
        (destination == NULL) ||
        (capacity == 0U))
    {
        return 0U;
    }

    /*
     * Recover bytes even if the ASCLIN RX service request stops retriggering.
     * Interrupt masking prevents this polling producer from racing the normal
     * ISR producer. The pass limit keeps motor-control latency bounded.
     */
    interrupts_were_enabled = IfxCpu_disableInterrupts();
    for (drain_attempt = 0U;
         drain_attempt < TC375_BOARD_UART_RX_POLL_DRAIN_LIMIT;
         ++drain_attempt)
    {
        drained = Tc375Hal_DrainUartRxHardwareFifo();
        if (drained == 0U)
        {
            break;
        }
        Tc375Hal_IncrementUartCounter(
            &g_uart_rx_poll_drains);
        Tc375Hal_AddUartCounter(
            &g_uart_rx_poll_bytes,
            (uint16_t)drained);
    }
    IfxCpu_restoreInterrupts(interrupts_were_enabled);

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
    uint32_t wait_started_us;
    boolean interrupts_were_enabled;
    boolean written;
    sint32 free_bytes;
    Ifx_SizeT count;

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

    free_bytes = IfxAsclin_Asc_getWriteCount(&g_uart);
    if (!high_priority)
    {
        size_t required =
            length + (size_t)TC375_BOARD_UART_TX_PRIORITY_RESERVE;
        if ((free_bytes < 0) ||
            ((size_t)free_bytes < required))
        {
            Tc375Hal_IncrementUartCounter(
                &g_uart_telemetry_drops);
            return false;
        }
    }
    else
    {
        /*
         * ACK/ERROR frames must not be lost behind telemetry. The reserve
         * normally makes this loop unnecessary; the bounded wait also
         * handles a response burst without blocking motor control for an
         * unbounded time.
         */
        wait_started_us = Tc375Hal_TimeUs();
        while ((free_bytes < 0) ||
               ((size_t)free_bytes < length))
        {
            if ((uint32_t)(Tc375Hal_TimeUs() - wait_started_us) >=
                TC375_BOARD_UART_HIGH_PRIORITY_WAIT_US)
            {
                Tc375Hal_IncrementUartCounter(
                    &g_uart_high_priority_failures);
                return false;
            }
            free_bytes = IfxAsclin_Asc_getWriteCount(&g_uart);
        }
    }

    count = (Ifx_SizeT)length;
    interrupts_were_enabled = IfxCpu_disableInterrupts();
    written = IfxAsclin_Asc_write(
        &g_uart,
        data,
        &count,
        TIME_NULL);
    IfxCpu_restoreInterrupts(interrupts_were_enabled);
    if ((written == FALSE) || ((size_t)count != length))
    {
        if (high_priority)
        {
            Tc375Hal_IncrementUartCounter(
                &g_uart_high_priority_failures);
        }
        else
        {
            Tc375Hal_IncrementUartCounter(
                &g_uart_telemetry_drops);
        }
        return false;
    }
    return true;
#else
    (void)data;
    (void)length;
    (void)high_priority;
    return false;
#endif
}

uint16_t Tc375Hal_UartHighPriorityFailures(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_high_priority_failures;
#else
    return 0U;
#endif
}

uint16_t Tc375Hal_UartTelemetryDrops(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_telemetry_drops;
#else
    return 0U;
#endif
}

uint16_t Tc375Hal_UartRxSwFifoOverflows(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_rx_sw_fifo_overflows;
#else
    return 0U;
#endif
}

uint16_t Tc375Hal_UartRxHwFifoOverflows(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_rx_hw_fifo_overflows;
#else
    return 0U;
#endif
}

uint16_t Tc375Hal_UartRxFrameErrors(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_rx_frame_errors;
#else
    return 0U;
#endif
}

uint16_t Tc375Hal_UartRxParityErrors(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_rx_parity_errors;
#else
    return 0U;
#endif
}

uint16_t Tc375Hal_UartRxIsrEntries(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_rx_isr_entries;
#else
    return 0U;
#endif
}

uint16_t Tc375Hal_UartRxPollDrains(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_rx_poll_drains;
#else
    return 0U;
#endif
}

uint16_t Tc375Hal_UartRxPollBytes(void)
{
#if TC375_BOARD_UART_ENABLED
    return g_uart_rx_poll_bytes;
#else
    return 0U;
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
#if MOTOR_POWER_STAGE_ENABLED
    /*
     * A real inverter may receive PWM only after the gate driver has
     * positively reached READY. Control-board-only builds intentionally do
     * not have this restriction so the TOUT pins remain observable.
     */
    g_pwm_enabled =
        (enabled && (g_gate_enabled == TRUE)) ? TRUE : FALSE;
#else
    g_pwm_enabled = enabled ? TRUE : FALSE;
#endif
#else
    (void)enabled;
    g_pwm_enabled = FALSE;
#endif

    if (g_pwm_enabled == FALSE)
    {
        GtmAtom3phInv_setSafeDuty();
    }
}

bool Tc375Hal_SetGateEnabled(bool enabled)
{
#if MOTOR_POWER_STAGE_ENABLED
    /*
     * Gate transitions are fail-closed. PWM is always removed before
     * changing nRESET/nSLEEP, and a failed READY/nFAULT check immediately
     * returns the driver to sleep.
     */
    g_pwm_enabled = FALSE;
    GtmAtom3phInv_setSafeDuty();
    g_gate_enabled = FALSE;

    if (!enabled)
    {
        Drv8313_disable();
        return true;
    }

    if (!Tc375Hal_MotorPeripheralsInit())
    {
        Drv8313_disable();
        return false;
    }

    Drv8313_enable();
    if ((Drv8313_getStatus() != DRV8313_STATUS_READY) ||
        (Drv8313_hasFault() == TRUE))
    {
        Drv8313_disable();
        return false;
    }

    g_gate_enabled = TRUE;
    return true;
#else
    /*
     * POWER_STAGE=0 is a compile-time gate lock, not a PWM lock. Keep the
     * MCU TOUT waveform available for oscilloscope testing while the DRV8313
     * remains disabled. ForceSafeState() still clears PWM explicitly.
     */
    Drv8313_disable();
    g_gate_enabled = FALSE;
    return !enabled;
#endif
}

bool Tc375Hal_IsPwmEnabled(void)
{
    return g_pwm_enabled == TRUE;
}

bool Tc375Hal_IsGateEnabled(void)
{
    return g_gate_enabled == TRUE;
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
