#include "printf.h"
#include "printf.c" 

// 1. The exact base address from your Device Tree
#define UART_BASE 0x10020000

// 2. SiFive UART Hardware Offsets
#define UART_TXDATA (UART_BASE + 0x00) // Where we write the character
#define UART_TXCTRL (UART_BASE + 0x08) // The ON/OFF switch

// 3. Hardware Initialization
void uart_init() {
    volatile int *txctrl = (int*)UART_TXCTRL;
    *txctrl = 1; // Flip the switch to turn ON the TX hardware
}

// 4. The printf hook
void _putchar(char c) {
    volatile int *txdata = (int*)UART_TXDATA;
    
    // Safety check: Wait if the hardware transmit buffer is full (Bit 31)
    while ((*txdata) & (1 << 31)) {
        // spin and wait
    }
    
    // Write the character!
    *txdata = (int)c;
}
int main() {
    uart_init();
    
    int dummy_cycles = 673;
    
    printf("\n\n================================\n");
    printf("SUCCESS: Bare-Metal Printf Booted!\n");
    printf("UART Address Found: 0x%X\n", UART_BASE);
    printf("Execution Cycles: %d\n", dummy_cycles);
    printf("================================\n\n");
    
    // THE FIX: Do not let the CPU shut down the simulation yet!
    // We force it to count to 1 million, which wastes enough simulated cycles 
    // for the slow UART hardware to finish transmitting the text.
    for (volatile int i = 0; i < 1000000; i++) {
        // Just spin and waste time
    }
    
    return 0;
}