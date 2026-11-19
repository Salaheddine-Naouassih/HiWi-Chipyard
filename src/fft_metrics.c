#include <stdint.h>
#include <stdio.h>
/* RV64 unsigned long is 64 bits; Newlib-nano supports %lu/%lx. */
#include <stdlib.h>
#include <math.h>

#include "fftw3.h"
#include "image_data.h"

#define WIDTH ((int)(sizeof(image_data[0]) / sizeof(image_data[0][0])))
#define HEIGHT ((int)(sizeof(image_data) / sizeof(image_data[0])))
#define OUTPUT_PIXELS ((size_t)HEIGHT * (WIDTH / 2 + 1))

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

int main(void)
{
    uint64_t pixel_sum = 0;
    double *input =
        (double *)fftw_malloc(sizeof(double) * WIDTH * HEIGHT);
    fftw_complex *output =
        (fftw_complex *)fftw_malloc(sizeof(fftw_complex) * OUTPUT_PIXELS);

    if (input == NULL || output == NULL) {
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

    /* Measure planning, input reload, and execution as one interval. */
    uint64_t plan_start = read_cycle();
    uint64_t plan_inst_start = read_instret();
    fftw_plan plan = fftw_plan_dft_r2c_2d(
        HEIGHT, WIDTH, input, output, FFTW_ESTIMATE);
    if (plan == NULL) {
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

    fftw_execute(plan);
    uint64_t end_cycles = read_cycle();
    uint64_t end_instructions = read_instret();

    /* An unnormalized FFT's DC bin must equal the input pixel sum.
     * This correctness check is outside both measured regions. */
    if (!isfinite(output[0][0]) || !isfinite(output[0][1]) ||
        fabs(output[0][0] - (double)pixel_sum) > 1e-6 ||
        fabs(output[0][1]) > 1e-6) {
        fftw_destroy_plan(plan);
        fftw_free(output);
        fftw_free(input);
        return 1;
    }

    printf("%lu\n", (unsigned long)pixel_sum);
    printf("%lu\n", (unsigned long)(end_cycles - plan_start));
    printf("%lu\n", (unsigned long)(end_instructions - plan_inst_start));

    fftw_destroy_plan(plan);
    fftw_free(output);
    fftw_free(input);
    return 0;
}
