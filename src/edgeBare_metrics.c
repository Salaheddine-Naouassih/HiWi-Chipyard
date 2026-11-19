#include <stdint.h>
#include <stdio.h>
/* RV64 unsigned long is 64 bits; Newlib-nano supports %lu/%lx. */
#include <math.h>

#include "image_data.h"

#define WIDTH ((int)(sizeof(image_data[0]) / sizeof(image_data[0][0])))
#define HEIGHT ((int)(sizeof(image_data) / sizeof(image_data[0])))
#define NPIX ((size_t)WIDTH * HEIGHT)

static uint8_t gray[NPIX];
static uint8_t edges[NPIX];

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
    for (int y = 0; y < HEIGHT; y++) {
        for (int x = 0; x < WIDTH; x++) {
            gray[y * WIDTH + x] = image_data[y][x];
        }
    }

    const int gx[3][3] = {
        {-1, 0, 1},
        {-2, 0, 2},
        {-1, 0, 1}
    };
    const int gy[3][3] = {
        {-1, -2, -1},
        {0, 0, 0},
        {1, 2, 1}
    };

    /* Counter snapshots include a small read overhead. */
    uint64_t start_cycles = read_cycle();
    uint64_t start_instructions = read_instret();

    for (int y = 1; y < HEIGHT - 1; y++) {
        for (int x = 1; x < WIDTH - 1; x++) {
            int sum_x = 0;
            int sum_y = 0;

            for (int ky = -1; ky <= 1; ky++) {
                for (int kx = -1; kx <= 1; kx++) {
                    int pixel = gray[(y + ky) * WIDTH + (x + kx)];
                    sum_x += pixel * gx[ky + 1][kx + 1];
                    sum_y += pixel * gy[ky + 1][kx + 1];
                }
            }

            int magnitude = (int)sqrt(
                (double)(sum_x * sum_x + sum_y * sum_y));
            if (magnitude > 255) {
                magnitude = 255;
            }
            edges[y * WIDTH + x] = (uint8_t)magnitude;
        }
    }

    uint64_t end_cycles = read_cycle();
    uint64_t end_instructions = read_instret();

    /* Benchmark only Sobel. The unused visualization overlay is omitted. */
    uint64_t checksum = 0;
    for (size_t i = 0; i < NPIX; i++) {
        checksum += edges[i];
    }

    uint64_t cycles = end_cycles - start_cycles;
    uint64_t instructions = end_instructions - start_instructions;
    printf("%lu\n", (unsigned long)cycles);
    printf("%lu\n", (unsigned long)instructions);
    printf("%lu\n", (unsigned long)checksum);
    return 0;
}
