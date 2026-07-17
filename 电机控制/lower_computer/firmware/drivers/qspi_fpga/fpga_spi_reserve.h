#ifndef FPGA_SPI_RESERVE_H
#define FPGA_SPI_RESERVE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum
{
    FPGA_LINK_DISABLED = 0,
    FPGA_LINK_RESERVED_READY,
    FPGA_LINK_SELF_TEST_FAILED
} FpgaLinkState;

typedef struct
{
    FpgaLinkState state;
    uint32_t transfers;
    uint32_t errors;
} FpgaSpiReserve;

bool FpgaSpiReserve_Init(FpgaSpiReserve *link);
bool FpgaSpiReserve_LoopbackSelfTest(FpgaSpiReserve *link);
void FpgaSpiReserve_ForceDisabled(FpgaSpiReserve *link);

#endif

