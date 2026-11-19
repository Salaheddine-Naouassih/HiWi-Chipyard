#ifndef OPTFLOW_FRAMES_H
#define OPTFLOW_FRAMES_H

#include <stdint.h>
#include "../headers/image_0000.h"
#include "../headers/image_0001.h"

#define IMG_WIDTH 426
#define IMG_HEIGHT 240
#define IMG_COUNT 2

static const uint8_t* const frames[IMG_COUNT] = {
    image_0000,
    image_0001,
};

#endif
