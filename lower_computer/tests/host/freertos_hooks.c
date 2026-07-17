#include "FreeRTOS.h"
#include "task.h"

#include <stdlib.h>

static StaticTask_t g_idle_task_tcb;
static StackType_t g_idle_task_stack[configMINIMAL_STACK_SIZE];

void vApplicationGetIdleTaskMemory(
    StaticTask_t **tcb,
    StackType_t **stack,
    configSTACK_DEPTH_TYPE *stack_size)
{
    *tcb = &g_idle_task_tcb;
    *stack = g_idle_task_stack;
    *stack_size = configMINIMAL_STACK_SIZE;
}

void vApplicationStackOverflowHook(
    TaskHandle_t task,
    char *task_name)
{
    (void)task;
    (void)task_name;
    abort();
}
