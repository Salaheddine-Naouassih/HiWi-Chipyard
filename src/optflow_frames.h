#ifndef OPTFLOW_FRAMES_H
#define OPTFLOW_FRAMES_H

#include <stdint.h>
#include "/scratch/naouasal/Dennis/input/videos/split/split_video/headers/image_0015.h"
#include "/scratch/naouasal/Dennis/input/videos/split/split_video/headers/image_0016.h"

#define IMG_WIDTH 426
#define IMG_HEIGHT 240
#define IMG_COUNT 2

static const uint8_t* const frames[IMG_COUNT] = {
    image_0015,
    image_0016,
};

#endif
