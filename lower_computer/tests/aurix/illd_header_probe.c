#include "Ifx_Cfg.h"
#include "IfxLldVersion.h"

#include "Asclin/Asc/IfxAsclin_Asc.h"
#include "Evadc/Adc/IfxEvadc_Adc.h"
#include "Gtm/Atom/Pwm/IfxGtm_Atom_Pwm.h"
#include "Qspi/SpiMaster/IfxQspi_SpiMaster.h"

#if !defined(DEVICE_TC37X)
#error "The TC37x device macro must be selected for the TC375 Lite iLLD package."
#endif

#if !defined(IFX_PIN_PACKAGE_LQFP176)
#error "The TC375 Lite ADS template should select the LQFP176 package by default."
#endif

#if IFX_LLD_VERSION_MAJOR != 1 || IFX_LLD_VERSION_MINOR != 20 || IFX_LLD_VERSION_REVISION != 0
#error "Unexpected Infineon iLLD version."
#endif

int AurixIlldHeaderProbe(void)
{
    return IFX_LLD_VERSION_MAJOR + IFX_LLD_VERSION_MINOR + IFX_LLD_VERSION_REVISION;
}
