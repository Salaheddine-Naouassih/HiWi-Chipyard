#include <stdlib.h>
#include "fftw3.h"    // The FFTW API
#include "printf.h"
#include "printf.c"   
#include "syscalls.c" 

#define UART_BASE 0x10020000
#define UART_TXDATA (UART_BASE + 0x00)
#define UART_TXCTRL (UART_BASE + 0x08)

void uart_init() {
    volatile int *txctrl = (int*)UART_TXCTRL;
    *txctrl = 1; 
}

void _putchar(char c) {
    volatile int *txdata = (int*)UART_TXDATA;
    while ((*txdata) & (1 << 31)); // Wait for buffer
    *txdata = (int)c;
}

int main() {
    uart_init();
    // printf("\n================================\n");
    // printf("FFTW Bare-Metal Benchmark Booting!\n");
    // printf("================================\n");

    // 1. Setup the math workload (Small 16-point array for fast simulation)
    int N = 16; 
    fftw_complex *in, *out;
    fftw_plan p;

    // printf("[1/4] Allocating DDR3 Memory...\n");
    // fftw_malloc automatically calls our custom _sbrk function!
    in = (fftw_complex*) fftw_malloc(sizeof(fftw_complex) * N);
    out = (fftw_complex*) fftw_malloc(sizeof(fftw_complex) * N);

    if (!in || !out) {
        printf("FATAL: Out of memory!\n");
        while(1){}
    }

    // printf("[2/4] Initializing Waveform Data...\n");
    for (int i = 0; i < N; i++) {
        in[i][0] = i; // Real part
        in[i][1] = 0; // Imaginary part
    }

    // printf("[3/4] Creating FFTW Plan (ESTIMATE mode)...\n");
    p = fftw_plan_dft_1d(N, in, out, FFTW_FORWARD, FFTW_ESTIMATE);

    // printf("[4/4] Executing Fast Fourier Transform...\n");
    fftw_execute(p);

    // Print results (Casting to int to avoid bare-metal float-printing bugs)
    printf("\n--- FFT Results (First 4 Bins) ---\n");
    for(int i = 0; i < 4; i++) {
        printf("Bin[%d]: Real: %d, Imag: %d\n", i, (int)out[i][0], (int)out[i][1]);
    }
    printf("----------------------------------\n");

    // Cleanup
    fftw_destroy_plan(p);
    fftw_free(in);
    fftw_free(out);
    
    printf("SUCCESS: Bare-Metal FFTW Execution Complete!\n\n");

    // Park the CPU gracefully so the UART can finish
    for (volatile int i = 0; i < 1000000; i++);
    return 0;
}