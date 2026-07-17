#include "fpga_spi_reserve.h"

#include <string.h>

/*
 * 这里只管理“预留是否健康”，不发送控制目标、不接收 PWM，也不允许选择
 * FPGA backend。板级 QSPI init、CS、SYNC、FAULT、RESET 和 LOOPBACK 引脚
 * 应在 TC375 iLLD BSP 中实现后，再接入本文件的自检钩子。
 */

bool FpgaSpiReserve_Init(FpgaSpiReserve *link)
{
    memset(link, 0, sizeof(*link));
    link->state = FPGA_LINK_DISABLED;
    return true;
}

bool FpgaSpiReserve_LoopbackSelfTest(FpgaSpiReserve *link)
{
    link->transfers++;
    /* 没有 FPGA/回环板时保持 disabled，不伪报 FPGA 可用。 */
    link->state = FPGA_LINK_DISABLED;
    return false;
}

void FpgaSpiReserve_ForceDisabled(FpgaSpiReserve *link)
{
    link->state = FPGA_LINK_DISABLED;
}

