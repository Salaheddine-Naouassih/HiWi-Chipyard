#!/usr/bin/env python3
"""Run bare-metal optical flow on every consecutive pair of frames."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

SCRIPT_DIR = Path(__file__).resolve().parent
TESTS = Path(os.environ.get(
    "CHIPYARD_TESTS",
    str(SCRIPT_DIR.parents[1] / "chipyard" / "tests"),
)).resolve()
FRAME_DIR = Path(os.environ.get(
    "OPTFLOW_FRAME_DIR",
    str(SCRIPT_DIR.parent / "headers"),
)).resolve()
FRAME_HEADER = TESTS / "optflow_frames.h"
RESULTS = TESTS / "optflow_pair_results"
FRAME_COUNT = 17
CONFIG = "OwnMemoryRocketConfig"
CORE_HZ = 500_000_000
BINARY = "optflow_metrics.riscv"


def frame_dimensions(header):
    """Read the 426x240 dimensions from images_index.h, or infer a square."""
    index_header = header.parent / "images_index.h"
    if index_header.is_file():
        text = index_header.read_text()
        width_match = re.search(r"^\s*#define\s+IMG_WIDTH\s+(\d+)\s*$", text, re.MULTILINE)
        height_match = re.search(r"^\s*#define\s+IMG_HEIGHT\s+(\d+)\s*$", text, re.MULTILINE)
        if width_match and height_match:
            return int(width_match.group(1)), int(height_match.group(1))

    declaration = re.search(
        r"const\s+uint8_t\s+\w+\s*\[\s*(\d+)\s*\]",
        header.read_text(),
    )
    if not declaration:
        raise RuntimeError(f"Could not find a frame array declaration in {header}")
    pixels = int(declaration.group(1))
    side = int(pixels ** 0.5)
    if side * side != pixels:
        raise RuntimeError(
            f"Cannot infer rectangular dimensions from {header}; "
            "add IMG_WIDTH and IMG_HEIGHT to images_index.h"
        )
    return side, side


def create_chunk_header(frame_numbers):
    """Generate the frame-index header consumed by optflow.cpp."""
    if not FRAME_DIR.is_dir():
        raise RuntimeError(f"Frame directory is missing: {FRAME_DIR}")

    first = FRAME_DIR / f"image_{frame_numbers[0]:04d}.h"
    if not first.is_file():
        raise RuntimeError(f"Missing frame header: {first}")

    width, height = frame_dimensions(first)
    includes = []
    names = []
    for number in frame_numbers:
        frame = FRAME_DIR / f"image_{number:04d}.h"
        if not frame.is_file():
            raise RuntimeError(f"Missing frame header: {frame}")
        relative_frame = os.path.relpath(frame, FRAME_HEADER.parent).replace(os.sep, "/")
        includes.append(f'#include "{relative_frame}"')
        names.append(f"image_{number:04d}")

    content = [
        "#ifndef OPTFLOW_FRAMES_H",
        "#define OPTFLOW_FRAMES_H",
        "",
        "#include <stdint.h>",
        *includes,
        "",
        f"#define IMG_WIDTH {width}",
        f"#define IMG_HEIGHT {height}",
        f"#define IMG_COUNT {len(names)}",
        "",
        "static const uint8_t* const frames[IMG_COUNT] = {",
        *(f"    {name}," for name in names),
        "};",
        "",
        "#endif",
        "",
    ]
    FRAME_HEADER.write_text("\n".join(content))


def metric_values(log):
    return [
        int(line.strip())
        for line in log.read_text().splitlines()
        if line.strip().isdigit()
    ]


def run_pair(pair_number, frame_numbers):
    name = f"optflow_pair_{pair_number:02d}_{frame_numbers[0] + 1:02d}_{frame_numbers[1] + 1:02d}"
    log = RESULTS / f"{name}.log"
    print(f"\nPreparing {name}: frames={frame_numbers}", flush=True)

    if not (TESTS / "Makefile").is_file():
        raise RuntimeError(
            f"Chipyard Makefile is missing: {TESTS / 'Makefile'} "
            "(set CHIPYARD_TESTS to the actual chipyard/tests directory)"
        )
    create_chunk_header(frame_numbers)
    subprocess.run(["make", "-B", BINARY], cwd=TESTS, check=True)

    start = time.perf_counter()
    subprocess.run(
        [
            "make",
            "run-binary-fast",
            f"CONFIG={CONFIG}",
            f"BINARY={TESTS / BINARY}",
            "LOADMEM=1",
            "TIMEOUT_CYCLES=100000000000",
            "BREAK_SIM_PREREQ=1",
            "VERBOSE_FLAGS=",
            f"output_dir={RESULTS}",
            f"get_sim_out_name={RESULTS / name}",
        ],
        cwd=TESTS.parent / "sims" / "verilator",
        check=True,
    )
    wall_seconds = time.perf_counter() - start

    values = metric_values(log)
    if len(values) != 3:
        raise RuntimeError(f"Expected three metrics in {log}")
    with log.open("a") as output:
        output.write(
            "\n"
            f"DERIVED_METRIC phase=optflow "
            f"simulated_seconds={values[1] / CORE_HZ:.9f} "
            f"core_hz={CORE_HZ}\n"
            f"HOST_METRIC scope=full_verilator_run "
            f"wall_seconds={wall_seconds:.3f}\n"
        )
    print(f"Saved {log}", flush=True)


def main():
    if not os.environ.get("RISCV") or not shutil.which("riscv64-unknown-elf-g++"):
        raise RuntimeError("Source chipyard/env.sh before running this script")
    if not FRAME_DIR.is_dir():
        raise RuntimeError(f"Frame directory is missing: {FRAME_DIR}")
    RESULTS.mkdir(exist_ok=True)

    for pair_number in range(FRAME_COUNT - 1):
        run_pair(pair_number + 1, [pair_number, pair_number + 1])

    print(f"\nALL {FRAME_COUNT - 1} OPTICAL-FLOW PAIRS COMPLETED.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Pipeline stopped: {error}")
