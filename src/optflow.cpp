#include <stdio.h>
#include <stdint.h>
#include <math.h>
#include <stdlib.h>

#include "optflow_frames.h"

#define WIDTH IMG_WIDTH
#define HEIGHT IMG_HEIGHT
#define NPIX (WIDTH*HEIGHT)

// Flow
static float flow_x[NPIX];
static float flow_y[NPIX];

static inline int idx(int x,int y)
{
    return y*WIDTH + x;
}

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

int main()
{
    const uint8_t* img1;
    const uint8_t* img2;

    //--------------------------------------------------
    // Akkumulatoren für globalen Flow
    //--------------------------------------------------
    long count = 0;

    float threshold = 0.3f;

    uint64_t start_cycles = read_cycle();
    uint64_t start_instructions = read_instret();

    for(int f = 0; f < IMG_COUNT - 1; f++)
    {
        img1 = frames[f];
        img2 = frames[f+1];

        //-------------------------------
        // Flow berechnen
        //-------------------------------
        for(int y=1;y<HEIGHT-1;y++)
        {
            for(int x=1;x<WIDTH-1;x++)
            {
                int i = idx(x,y);

                float Ix = img1[idx(x+1,y)] - img1[idx(x-1,y)];
                float Iy = img1[idx(x,y+1)] - img1[idx(x,y-1)];
                float It = img2[i] - img1[i];

                float denom = Ix*Ix + Iy*Iy + 1e-4f;

                flow_x[i] = -Ix * It / denom;
                flow_y[i] = -Iy * It / denom;
            }
        }

        //-------------------------------
        // Mittelwert sammeln
        //-------------------------------
        for(int i = 0; i < NPIX; i++)
        {
            float vx = flow_x[i];
            float vy = flow_y[i];

            float mag = sqrtf(vx*vx + vy*vy);

            if(mag > threshold)
            {
                count++;
            }
        }
    }

    uint64_t end_cycles = read_cycle();
    uint64_t end_instructions = read_instret();

    printf("%ld\n", count);
    printf("%lu\n", (unsigned long)(end_cycles - start_cycles));
    printf("%lu\n", (unsigned long)(end_instructions - start_instructions));

    return 0;
}
