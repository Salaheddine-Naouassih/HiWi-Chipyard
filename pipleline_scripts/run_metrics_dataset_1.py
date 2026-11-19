#!/usr/bin/env python3
"""Run FFTW and Sobel metrics for the rectangular dataset_1 headers."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


TESTS = Path(__file__).resolve().parent
HEADER_DIR = Path(
    "../dataset_1"
)
IMAGE_HEADER = TESTS / "image_data.h"
RESULTS = TESTS / "metrics_results_dataset_1"
CONFIG = "OwnMemoryRocketConfig"
CORE_HZ = 500_000_000
ALGORITHMS = (
    ("fft", "fft_metrics.riscv"),
    ("edge", "edgeBare_metrics.riscv"),
)


def header_dimensions(header):
    """Return (width, height) from a generated image header."""
    declarations = [
        line for line in header.read_text().splitlines()
        if "const uint8_t image_data[" in line
    ]
    if len(declarations) != 1:
        raise RuntimeError(f"Expected one image_data declaration in {header}")
    declaration = declarations[0].split("image_data[", 1)[1]
    height_text, width_text = declaration.split("]", 1)
    width_text = width_text.split("[", 1)[1].split("]", 1)[0]
    height, width = int(height_text), int(width_text)
    if width < 2 or height < 2:
        raise RuntimeError(f"Invalid image dimensions in {header}: {width}x{height}")
    return width, height


def metric_values(log):
    numbers = []
    for line in log.read_text().splitlines():
        value = line.strip()
        if value.isdigit():
            numbers.append(int(value))
    return numbers


def check_log(log):
    values = metric_values(log)
    if len(values) != 3:
        raise RuntimeError(f"Expected three numeric metrics; inspect {log}")
    return values


def add_timing_metrics(log, algorithm, wall_seconds):
    """Append target time and host time after a successful simulation."""
    values = metric_values(log)
    if algorithm == "fft":
        phase = "fft"
        cycles = values[1]
    else:
        phase = "sobel"
        cycles = values[0]
    lines = [
        f"DERIVED_METRIC phase={phase} simulated_seconds={cycles / CORE_HZ:.9f} "
        f"core_hz={CORE_HZ}",
        f"HOST_METRIC scope=full_verilator_run wall_seconds={wall_seconds:.3f}",
    ]
    with log.open("a") as output_file:
        output_file.write("\n" + "\n".join(lines) + "\n")


def run_algorithm(algorithm, binary, name):
    """Build and run one metrics program, returning its validated log path."""
    print(f"Building and running {name}", flush=True)
    subprocess.run(["make", binary], cwd=TESTS, check=True)
    wall_start = time.perf_counter()
    subprocess.run(
        [
            "make",
            "run-binary-fast",
            f"CONFIG={CONFIG}",
            f"BINARY={TESTS / binary}",
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
    wall_seconds = time.perf_counter() - wall_start
    log = RESULTS / f"{name}.log"
    check_log(log)
    add_timing_metrics(log, algorithm, wall_seconds)
    return log


def main():
    if not os.environ.get("RISCV") or not shutil.which("riscv64-unknown-elf-gcc"):
        raise RuntimeError("Source chipyard/env.sh before running this script")
    simulator = TESTS.parent / "sims" / "verilator" / (
        f"simulator-chipyard.harness-{CONFIG}"
    )
    if not os.access(simulator, os.X_OK):
        raise RuntimeError(f"Built simulator is missing or not executable: {simulator}")
    if not HEADER_DIR.is_dir():
        raise RuntimeError(f"Header directory is missing: {HEADER_DIR}")

    headers = [HEADER_DIR / f"image_data_{n}.h" for n in range(11, 25)]
    if not headers:
        raise RuntimeError(f"No image headers found in {HEADER_DIR}")

    RESULTS.mkdir(exist_ok=True)
    total = len(headers) * len(ALGORITHMS)
    completed = 0
    for header in headers:
        width, height = header_dimensions(header)
        print(
            f"\nPreparing {header.name}: width={width}, height={height}",
            flush=True,
        )
        image_name = header.stem.rsplit("_", 1)[1]
        shutil.copyfile(header, IMAGE_HEADER)
        for algorithm, binary in ALGORITHMS:
            name = f"{algorithm}_{image_name}_{width}x{height}"
            run_algorithm(algorithm, binary, name)
            completed += 1
            print(f"[{completed}/{total}] Saved {RESULTS / (name + '.log')}", flush=True)

    print(f"\nALL {completed} RUNS COMPLETED. Results: {RESULTS}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Pipeline stopped: {error}")
