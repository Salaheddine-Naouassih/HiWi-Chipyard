#include <stdint.h>
#include <stdio.h>
/* RV64 unsigned long is 64 bits; Newlib-nano supports %lu/%lx. */
#include <stdlib.h>
#include <math.h>

#include "fftw3.h"
#include "image_data.h"

#define WIDTH ((int)(sizeof(image_data[0]) / sizeof(image_data[0][0])))
#define HEIGHT ((int)(sizeof(image_data) / sizeof(image_data[0])))
#define OUTPUT_WIDTH (WIDTH / 2 + 1)
#define OUTPUT_PIXELS ((size_t)HEIGHT * OUTPUT_WIDTH)

static inline uint64_t read_cycle(void)
{
    uint64_t value;
    asm volatile ("csrr %0, mcycle" : "=r"(value) : : "memory");
    return value;
}

static inline uint64_t read_instret(void)
{
    uint64_t value;
    asm volatile ("csrr %0, minstret" : "=r"(value) : : "memory");
    return value;
}

static void print_metrics(const char *phase, uint64_t cycles,
                          uint64_t instructions)
{
    uint64_t ipc_milli = cycles == 0 ? 0 : (instructions * 1000) / cycles;
    printf("METRIC phase=%s cycles=%lu instructions=%lu ipc_milli=%lu\n",
           phase,
           (unsigned long)cycles,
           (unsigned long)instructions,
           (unsigned long)ipc_milli);
}

int main(void)
{
    /* Full output is deferred until both measured regions have ended. */
    uint64_t pixel_sum = 0;
    double *input =
        (double *)fftw_malloc(sizeof(double) * WIDTH * HEIGHT);
    fftw_complex *output =
        (fftw_complex *)fftw_malloc(sizeof(fftw_complex) * OUTPUT_PIXELS);

    if (input == NULL || output == NULL) {
        printf("FATAL: FFTW allocation failed\n");
        fftw_free(output);
        fftw_free(input);
        return 1;
    }

    for (int y = 0; y < HEIGHT; y++) {
        for (int x = 0; x < WIDTH; x++) {
            input[(size_t)y * WIDTH + x] = (double)image_data[y][x];
            pixel_sum += image_data[y][x];
        }
    }

    /* Counter snapshots include a small read/call overhead. */
    uint64_t plan_start = read_cycle();
    uint64_t plan_inst_start = read_instret();
    fftw_plan plan = fftw_plan_dft_r2c_2d(
        HEIGHT, WIDTH, input, output, FFTW_ESTIMATE);
    uint64_t plan_end = read_cycle();
    uint64_t plan_inst_end = read_instret();

    if (plan == NULL) {
        printf("FATAL: FFTW plan creation failed\n");
        fftw_free(output);
        fftw_free(input);
        return 1;
    }

    /* Preserve the FPGA execution path's explicit input reload. */
    for (int y = 0; y < HEIGHT; y++) {
        for (int x = 0; x < WIDTH; x++) {
            input[(size_t)y * WIDTH + x] = (double)image_data[y][x];
        }
    }

    uint64_t exec_start = read_cycle();
    uint64_t exec_inst_start = read_instret();
    fftw_execute(plan);
    uint64_t exec_end = read_cycle();
    uint64_t exec_inst_end = read_instret();

    /* An unnormalized FFT's DC bin must equal the input pixel sum.
     * This correctness check is outside both measured regions. */
    if (!isfinite(output[0][0]) || !isfinite(output[0][1]) ||
        fabs(output[0][0] - (double)pixel_sum) > 1e-6 ||
        fabs(output[0][1]) > 1e-6) {
        printf("FATAL: FFT DC check failed\n");
        fftw_destroy_plan(plan);
        fftw_free(output);
        fftw_free(input);
        return 1;
    }

    uint64_t dc_real_bits = 0;
    __builtin_memcpy(&dc_real_bits, &output[0][0], sizeof(dc_real_bits));

    print_metrics("plan", plan_end - plan_start,
                  plan_inst_end - plan_inst_start);
    print_metrics("execute", exec_end - exec_start,
                  exec_inst_end - exec_inst_start);
    printf("METRIC algorithm=fftw_r2c_2d\n");
    printf("METRIC dimensions=%dx%d\n", WIDTH, HEIGHT);
    printf("METRIC pixel_sum=%lu\n", (unsigned long)pixel_sum);
    printf("METRIC dc_real_bits=0x%lx\n",
           (unsigned long)dc_real_bits);
    printf("METRIC branch_hits=unavailable\n");
    printf("METRIC branch_misses=unavailable\n");
    /* Raw double bits avoid Newlib-nano's optional floating-point printf.
     * These bins can be decoded on the host for additional checking. */
    const int bins[][2] = {{0, 0}, {0, 1}, {1, 0}, {HEIGHT / 2, WIDTH / 2}};
    for (size_t i = 0; i < sizeof(bins) / sizeof(bins[0]); i++) {
        size_t index = (size_t)bins[i][0] * OUTPUT_WIDTH + bins[i][1];
        uint64_t real_bits, imag_bits;
        __builtin_memcpy(&real_bits, &output[index][0], sizeof(real_bits));
        __builtin_memcpy(&imag_bits, &output[index][1], sizeof(imag_bits));
        printf("CHECK bin_y=%d bin_x=%d real_bits=0x%lx imag_bits=0x%lx\n",
               bins[i][0], bins[i][1], (unsigned long)real_bits,
               (unsigned long)imag_bits);
    }
    printf("FFT METRICS COMPLETED SUCCESSFULLY\n");

    fftw_destroy_plan(plan);
    fftw_free(output);
    fftw_free(input);
    return 0;
}
