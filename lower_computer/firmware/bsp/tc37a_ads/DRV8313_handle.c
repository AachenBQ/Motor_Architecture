/*********************************************************************************************************************/
/*-----------------------------------------------------Includes------------------------------------------------------*/
/*********************************************************************************************************************/

#include "DRV8313_handle.h"
#include "Bsp.h"

/*********************************************************************************************************************/
/*------------------------------------------------------Macros-------------------------------------------------------*/
/*********************************************************************************************************************/

#define DRV8313_WAKEUP_DELAY_MS        (2U)
#define DRV8313_RESET_PULSE_US         (100U)
#define DRV8313_RESET_DELAY_MS         (1U)

/*********************************************************************************************************************/
/*-------------------------------------------------Global variables--------------------------------------------------*/
/*********************************************************************************************************************/

/*********************************************************************************************************************/
/*-------------------------------------------------Data Structures---------------------------------------------------*/
/*********************************************************************************************************************/

/*********************************************************************************************************************/
/*--------------------------------------------Private Variables/Constants--------------------------------------------*/
/*********************************************************************************************************************/

static Drv8313_Status g_drv8313Status = DRV8313_STATUS_DISABLED;

/*********************************************************************************************************************/
/*---------------------------------------------Private Function Prototypes-------------------------------------------*/
/*********************************************************************************************************************/

static void Drv8313_delayMilliseconds(uint32 milliseconds);
static void Drv8313_delayMicroseconds(uint32 microseconds);

/*********************************************************************************************************************/
/*------------------------------------------------Function Implementations--------------------------------------------*/
/*********************************************************************************************************************/

void Drv8313_init(void)
{
    /*
     * Configure nRESET as push-pull output.
     * Set it low initially to keep the driver disabled.
     */
    IfxPort_setPinModeOutput(
        DRV8313_NRT_PORT,
        DRV8313_NRT_PIN,
        IfxPort_OutputMode_pushPull,
        IfxPort_OutputIdx_general
    );

    IfxPort_setPinLow(
        DRV8313_NRT_PORT,
        DRV8313_NRT_PIN
    );

    /*
     * Configure nSLEEP as push-pull output.
     * Set it low initially to keep the driver in sleep mode.
     */
    IfxPort_setPinModeOutput(
        DRV8313_NSP_PORT,
        DRV8313_NSP_PIN,
        IfxPort_OutputMode_pushPull,
        IfxPort_OutputIdx_general
    );

    IfxPort_setPinLow(
        DRV8313_NSP_PORT,
        DRV8313_NSP_PIN
    );

    /*
     * nFAULT is an active-low open-drain output.
     * The external pull-up resistor on the DRV8313 board is preferred.
     * The internal pull-up is also enabled here.
     */
    IfxPort_setPinModeInput(
        DRV8313_NFT_PORT,
        DRV8313_NFT_PIN,
        IfxPort_InputMode_pullUp
    );

    g_drv8313Status = DRV8313_STATUS_DISABLED;
}

void Drv8313_enable(void)
{
    /*
     * Release sleep first.
     */
    IfxPort_setPinHigh(
        DRV8313_NSP_PORT,
        DRV8313_NSP_PIN
    );

    Drv8313_delayMilliseconds(DRV8313_WAKEUP_DELAY_MS);

    /*
     * Release reset.
     */
    IfxPort_setPinHigh(
        DRV8313_NRT_PORT,
        DRV8313_NRT_PIN
    );

    Drv8313_delayMilliseconds(DRV8313_RESET_DELAY_MS);

    /*
     * Check the fault signal before marking the driver as ready.
     */
    if (Drv8313_hasFault() == TRUE)
    {
        g_drv8313Status = DRV8313_STATUS_FAULT;
    }
    else
    {
        g_drv8313Status = DRV8313_STATUS_READY;
    }
}

void Drv8313_disable(void)
{
    /*
     * Reset and disable the power stage.
     */
    IfxPort_setPinLow(
        DRV8313_NRT_PORT,
        DRV8313_NRT_PIN
    );

    /*
     * Enter sleep mode.
     */
    IfxPort_setPinLow(
        DRV8313_NSP_PORT,
        DRV8313_NSP_PIN
    );

    g_drv8313Status = DRV8313_STATUS_DISABLED;
}

void Drv8313_reset(void)
{
    /*
     * Pull nRESET low to reset faults and disable the outputs.
     */
    IfxPort_setPinLow(
        DRV8313_NRT_PORT,
        DRV8313_NRT_PIN
    );

    Drv8313_delayMicroseconds(DRV8313_RESET_PULSE_US);

    /*
     * Release nRESET.
     */
    IfxPort_setPinHigh(
        DRV8313_NRT_PORT,
        DRV8313_NRT_PIN
    );

    Drv8313_delayMilliseconds(DRV8313_RESET_DELAY_MS);

    if (Drv8313_hasFault() == TRUE)
    {
        g_drv8313Status = DRV8313_STATUS_FAULT;
    }
    else
    {
        g_drv8313Status = DRV8313_STATUS_READY;
    }
}

boolean Drv8313_hasFault(void)
{
    /*
     * nFAULT is active low:
     *
     * Low  = fault active
     * High = no fault
     */
    boolean faultPinState = IfxPort_getPinState(
        DRV8313_NFT_PORT,
        DRV8313_NFT_PIN
    );

    if (faultPinState == FALSE)
    {
        g_drv8313Status = DRV8313_STATUS_FAULT;
        return TRUE;
    }

    return FALSE;
}

Drv8313_Status Drv8313_getStatus(void)
{
    /*
     * Refresh the status when the driver is enabled.
     */
    if (g_drv8313Status != DRV8313_STATUS_DISABLED)
    {
        if (Drv8313_hasFault() == TRUE)
        {
            g_drv8313Status = DRV8313_STATUS_FAULT;
        }
        else
        {
            g_drv8313Status = DRV8313_STATUS_READY;
        }
    }

    return g_drv8313Status;
}

/*********************************************************************************************************************/
/*---------------------------------------------Private Function Implementations---------------------------------------*/
/*********************************************************************************************************************/

static void Drv8313_delayMilliseconds(uint32 milliseconds)
{
    Ifx_TickTime delayTicks;

    delayTicks = IfxStm_getTicksFromMilliseconds(
        BSP_DEFAULT_TIMER,
        milliseconds
    );

    waitTime(delayTicks);
}

static void Drv8313_delayMicroseconds(uint32 microseconds)
{
    Ifx_TickTime delayTicks;

    delayTicks = IfxStm_getTicksFromMicroseconds(
        BSP_DEFAULT_TIMER,
        microseconds
    );

    waitTime(delayTicks);
}
