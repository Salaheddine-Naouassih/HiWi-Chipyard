#!/usr/bin/env python3
"""Generate each image header, then build/run FFTW and Sobel sequentially."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


TESTS = Path(__file__).resolve().parent
SIM = TESTS.parent / "sims" / "verilator"
RESULTS = TESTS / "metrics_results"
CONFIG = "OwnMemoryRocketConfig"
CORE_HZ = 500_000_000
SIZES = (32, 64, 128, 256)
ALGORITHMS = (
    ("fft", "fft_metrics.riscv", "FFT METRICS COMPLETED SUCCESSFULLY"),
    ("edge", "edgeBare_metrics.riscv", "EDGE METRICS COMPLETED SUCCESSFULLY"),
)


def check_log(log, algorithm, success):
    output = log.read_text()
    if success not in output:
        raise RuntimeError(f"Completion marker missing; inspect {log}")
    count = 2 if algorithm == "fft" else 1
    fields = {key: (count, r"\d+")
              for key in ("cycles", "instructions", "ipc_milli")}
    if algorithm == "fft":
        fields.update(pixel_sum=(1, r"\d+"), dc_real_bits=(1, r"0x[0-9a-fA-F]+"),
                      real_bits=(4, r"0x[0-9a-fA-F]+"), imag_bits=(4, r"0x[0-9a-fA-F]+"))
        if sorted(re.findall(r"\bphase=(\S+)", output)) != ["execute", "plan"]:
            raise RuntimeError(f"Missing or duplicate FFT phases; inspect {log}")
    else:
        fields["edge_checksum"] = (1, r"\d+")
    for key, (expected, pattern) in fields.items():
        values = re.findall(rf"\b{key}=(\S+)", output)
        if len(values) != expected or any(not re.fullmatch(pattern, v) for v in values):
            raise RuntimeError(f"Missing or nonnumeric {key}; inspect {log}")


def add_timing_metrics(log, algorithm, wall_seconds):
    """Append target time and host time after a successful simulation."""
    output = log.read_text()
    if algorithm == "fft":
        measurements = re.findall(r"phase=(plan|execute) cycles=(\d+)", output)
    else:
        measurements = [("sobel", re.search(r"^METRIC cycles=(\d+)$",
                                             output, re.MULTILINE).group(1))]

    lines = [
        f"DERIVED_METRIC phase={phase} simulated_seconds={int(cycles) / CORE_HZ:.9f} "
        f"core_hz={CORE_HZ}"
        for phase, cycles in measurements
    ]
    lines.append(
        f"HOST_METRIC scope=full_verilator_run wall_seconds={wall_seconds:.3f}"
    )
    with log.open("a") as output_file:
        output_file.write("\n" + "\n".join(lines) + "\n")


def main():
    if not os.environ.get("RISCV") or not shutil.which("riscv64-unknown-elf-gcc"):
        raise RuntimeError("Source chipyard/env.sh before running this script")
    simulator = SIM / f"simulator-chipyard.harness-{CONFIG}"
    if not os.access(simulator, os.X_OK):
        raise RuntimeError(f"Built simulator is missing or not executable: {simulator}")

    images = []
    for size in SIZES:
        folder = TESTS / f"{size}x{size}"
        pictures = sorted(
            (p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")),
            key=lambda p: (0, int(p.stem)) if p.stem.isdigit() else (1, p.name),
        )
        if not pictures:
            raise RuntimeError(f"No images found in {folder}")
        if len({p.stem for p in pictures}) != len(pictures):
            raise RuntimeError(f"Image names would overwrite results in {folder}")
        images.extend((size, picture) for picture in pictures)

    RESULTS.mkdir(exist_ok=True)
    total = len(images) * len(ALGORITHMS)
    completed = 0
    for size, picture in images:
        print(f"\nPreparing {picture.relative_to(TESTS)}", flush=True)
        # Feed the existing image.py prompts: filename, width, height.
        subprocess.run(
            [sys.executable, str(TESTS / "image.py")], cwd=TESTS,
            input=f"{picture}\n{size}\n{size}\n", text=True, check=True,
        )
        for algorithm, binary, success in ALGORITHMS:
            name = f"{algorithm}_{picture.stem}_{size}x{size}"
            print(f"[{completed + 1}/{total}] Building and running {name}", flush=True)
            subprocess.run(["make", binary], cwd=TESTS, check=True)
            # Chipyard itself writes <name>.log (program output) and
            # <name>.out (simulator diagnostics). Disable instruction tracing.
            wall_start = time.perf_counter()
            subprocess.run([
                "make", "run-binary", f"CONFIG={CONFIG}",
                f"BINARY={TESTS / binary}", "LOADMEM=1",
                "TIMEOUT_CYCLES=100000000000", "BREAK_SIM_PREREQ=1",
                "VERBOSE_FLAGS=", f"output_dir={RESULTS}",
                f"get_sim_out_name={RESULTS / name}",
            ], cwd=SIM, check=True)
            wall_seconds = time.perf_counter() - wall_start
            log = RESULTS / f"{name}.log"
            check_log(log, algorithm, success)
            add_timing_metrics(log, algorithm, wall_seconds)
            completed += 1
            print(f"Saved {log}", flush=True)

    print(f"\nALL {completed} RUNS COMPLETED. Results: {RESULTS}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Pipeline stopped: {error}")
