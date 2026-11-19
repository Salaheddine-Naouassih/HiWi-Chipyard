#!/usr/bin/env python3
"""Run bare-metal optical flow on every consecutive pair of frames."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import run_optflow_chunks as chunk_runner


TESTS = Path(__file__).resolve().parent
RESULTS = TESTS / "optflow_pair_results"
FRAME_COUNT = 17
CONFIG = "OwnMemoryRocketConfig"
CORE_HZ = 500_000_000
BINARY = "optflow_metrics.riscv"


def run_pair(pair_number, frame_numbers):
    name = f"optflow_pair_{pair_number:02d}_{frame_numbers[0] + 1:02d}_{frame_numbers[1] + 1:02d}"
    log = RESULTS / f"{name}.log"
    print(f"\nPreparing {name}: frames={frame_numbers}", flush=True)

    chunk_runner.create_chunk_header(frame_numbers)
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

    values = chunk_runner.metric_values(log)
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
    if not chunk_runner.FRAME_DIR.is_dir():
        raise RuntimeError(f"Frame directory is missing: {chunk_runner.FRAME_DIR}")
    RESULTS.mkdir(exist_ok=True)
    chunk_runner.RESULTS = RESULTS

    for pair_number in range(FRAME_COUNT - 1):
        run_pair(pair_number + 1, [pair_number, pair_number + 1])

    print(f"\nALL {FRAME_COUNT - 1} OPTICAL-FLOW PAIRS COMPLETED.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Pipeline stopped: {error}")
