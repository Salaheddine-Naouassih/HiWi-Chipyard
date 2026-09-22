#!/usr/bin/env python3
"""Average four benchmark images per resolution and plot grouped bar charts."""

import csv
import os
from pathlib import Path
import re
from statistics import mean, pstdev
import sys


TESTS = Path(__file__).resolve().parent
RESULTS = TESTS / "metrics_results"
PLOTS = TESTS / "metrics_plots"
RESOLUTIONS = (32, 64, 128, 256)
IMAGE_NUMBERS = (1, 2, 3, 4)

# Keep Matplotlib's cache in a writable location on the shared machine.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/chipyard-matplotlib")
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


FFT_COLOR = "#4C78A8"
EDGE_COLOR = "#F58518"


def required_match(pattern, text, path):
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing expected metric in {path.name}")
    return match


def parse_fft(path):
    text = path.read_text()
    if "FFT METRICS COMPLETED SUCCESSFULLY" not in text:
        raise ValueError(f"incomplete FFT run in {path.name}")

    plan = required_match(
        r"^METRIC phase=plan cycles=(\d+) instructions=(\d+) ipc_milli=\d+$",
        text, path,
    )
    execute = required_match(
        r"^METRIC phase=execute cycles=(\d+) instructions=(\d+) ipc_milli=\d+$",
        text, path,
    )
    plan_time = required_match(
        r"^DERIVED_METRIC phase=plan simulated_seconds=([0-9.]+) core_hz=\d+$",
        text, path,
    )
    execute_time = required_match(
        r"^DERIVED_METRIC phase=execute simulated_seconds=([0-9.]+) core_hz=\d+$",
        text, path,
    )
    return {
        "plan_cycles": int(plan.group(1)),
        "plan_instructions": int(plan.group(2)),
        "plan_seconds": float(plan_time.group(1)),
        "cycles": int(execute.group(1)),
        "instructions": int(execute.group(2)),
        "simulated_seconds": float(execute_time.group(1)),
        "pixel_sum": int(required_match(
            r"^METRIC pixel_sum=(\d+)$", text, path).group(1)),
        "host_seconds": float(required_match(
            r"^HOST_METRIC scope=full_verilator_run wall_seconds=([0-9.]+)$",
            text, path).group(1)),
    }


def parse_edge(path):
    text = path.read_text()
    if "EDGE METRICS COMPLETED SUCCESSFULLY" not in text:
        raise ValueError(f"incomplete edge run in {path.name}")

    return {
        "cycles": int(required_match(
            r"^METRIC cycles=(\d+)$", text, path).group(1)),
        "instructions": int(required_match(
            r"^METRIC instructions=(\d+)$", text, path).group(1)),
        "simulated_seconds": float(required_match(
            r"^DERIVED_METRIC phase=sobel simulated_seconds=([0-9.]+) core_hz=\d+$",
            text, path).group(1)),
        "host_seconds": float(required_match(
            r"^HOST_METRIC scope=full_verilator_run wall_seconds=([0-9.]+)$",
            text, path).group(1)),
    }


def load_results():
    data = {}
    problems = []

    for resolution in RESOLUTIONS:
        label = f"{resolution}x{resolution}"
        data[resolution] = {"fft": [], "edge": []}
        for image_number in IMAGE_NUMBERS:
            for algorithm, parser in (("fft", parse_fft), ("edge", parse_edge)):
                path = RESULTS / f"{algorithm}_{image_number}_{label}.log"
                if not path.is_file():
                    problems.append(f"missing {path.name}")
                    continue
                try:
                    data[resolution][algorithm].append(parser(path))
                except (OSError, ValueError) as error:
                    problems.append(str(error))

    if problems:
        details = "\n  - ".join(problems)
        raise RuntimeError(
            "Cannot calculate four-image averages yet:\n  - " + details
        )
    return data


def average_and_std(data, algorithm, field, scale=1.0):
    averages = []
    deviations = []
    for resolution in RESOLUTIONS:
        values = [record[field] * scale
                  for record in data[resolution][algorithm]]
        averages.append(mean(values))
        deviations.append(pstdev(values))
    return averages, deviations


def derived_average_and_std(data, algorithm, value_function, scale=1.0):
    averages = []
    deviations = []
    for resolution in RESOLUTIONS:
        values = [value_function(record) * scale
                  for record in data[resolution][algorithm]]
        averages.append(mean(values))
        deviations.append(pstdev(values))
    return averages, deviations


def style_axes(ax, title, ylabel):
    ax.set_title(title)
    ax.set_xlabel("Image resolution")
    ax.set_ylabel(ylabel)
    ax.set_xticks(range(len(RESOLUTIONS)))
    ax.set_xticklabels([f"{size}×{size}" for size in RESOLUTIONS])
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)


def add_algorithm_comparison(ax, data, value_function, scale, title, ylabel):
    fft_mean, fft_std = derived_average_and_std(
        data, "fft", value_function, scale)
    edge_mean, edge_std = derived_average_and_std(
        data, "edge", value_function, scale)
    positions = list(range(len(RESOLUTIONS)))
    width = 0.36

    ax.bar(
        [position - width / 2 for position in positions],
        fft_mean, width, yerr=fft_std, capsize=4,
        label="FFTW execution", color=FFT_COLOR,
    )
    ax.bar(
        [position + width / 2 for position in positions],
        edge_mean, width, yerr=edge_std, capsize=4,
        label="Edge detection (Sobel)", color=EDGE_COLOR,
    )
    style_axes(ax, title, ylabel)


def save_performance_summary(data):
    metrics = (
        (lambda record: record["cycles"], 1 / 1_000_000,
         "Target cycles", "Cycles (millions)"),
        (lambda record: record["host_seconds"], 1 / 60,
         "Verilator host wall time", "Wall time (minutes)"),
        (lambda record: record["simulated_seconds"], 1_000,
         "Simulated target time", "Target time (ms)"),
        (lambda record: record["instructions"], 1 / 1_000_000,
         "Retired instructions", "Instructions (millions)"),
        (lambda record: record["instructions"] / record["cycles"], 1,
         "Instructions per cycle", "IPC"),
    )

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    flat_axes = axes.flat
    for ax, (value_function, scale, title, ylabel) in zip(flat_axes, metrics):
        add_algorithm_comparison(
            ax, data, value_function, scale, title, ylabel)

    legend_ax = axes[1, 2]
    legend_ax.axis("off")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    legend_ax.legend(handles, labels, loc="center", fontsize=12)
    legend_ax.text(
        0.5, 0.25,
        "FFTW bars use the execution phase.\n"
        "Edge bars use the measured Sobel region.",
        ha="center", va="center", fontsize=11,
    )

    fig.suptitle("Mean execution metrics by image resolution", fontsize=18)
    fig.text(
        0.5, 0.01,
        "Bars show the mean of four images; error bars show population standard deviation.",
        ha="center", fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(PLOTS / "performance_metrics_by_resolution.png", dpi=180)
    plt.close(fig)


def save_fftw_phase_plot(data):
    positions = list(range(len(RESOLUTIONS)))
    width = 0.36
    metrics = (
        ("plan_cycles", "cycles", 1 / 1_000_000,
         "Cycles (millions)", "Target cycles"),
        ("plan_instructions", "instructions", 1 / 1_000_000,
         "Instructions (millions)", "Retired instructions"),
        ("plan_seconds", "simulated_seconds", 1_000,
         "Simulated target time (ms)", "Simulated target time"),
    )

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))
    for ax, (plan_field, execute_field, scale, ylabel, title) in zip(axes, metrics):
        plan_mean, plan_std = average_and_std(
            data, "fft", plan_field, scale)
        execute_mean, execute_std = average_and_std(
            data, "fft", execute_field, scale)
        ax.bar(
            [position - width / 2 for position in positions],
            plan_mean, width, yerr=plan_std, capsize=4,
            label="Planning", color="#9ECAE1",
        )
        ax.bar(
            [position + width / 2 for position in positions],
            execute_mean, width, yerr=execute_std, capsize=4,
            label="Execution", color=FFT_COLOR,
        )
        style_axes(ax, title, ylabel)

    axes[0].legend()
    fig.suptitle("Mean FFTW planning and execution costs")
    fig.text(
        0.5, 0.01,
        "Bars show the mean of four images; error bars show population standard deviation.",
        ha="center", fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(PLOTS / "fftw_planning_vs_execution.png", dpi=180)
    plt.close(fig)


def save_planning_plus_execution_plot(data):
    positions = list(range(len(RESOLUTIONS)))
    width = 0.36
    fft_mean, fft_std = derived_average_and_std(
        data, "fft",
        lambda record: record["plan_seconds"] + record["simulated_seconds"],
        scale=1_000,
    )
    edge_mean, edge_std = average_and_std(
        data, "edge", "simulated_seconds", scale=1_000)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.bar(
        [position - width / 2 for position in positions],
        fft_mean, width, yerr=fft_std, capsize=4,
        label="FFTW planning + one execution", color=FFT_COLOR,
    )
    ax.bar(
        [position + width / 2 for position in positions],
        edge_mean, width, yerr=edge_std, capsize=4,
        label="Edge detection (Sobel)", color=EDGE_COLOR,
    )
    style_axes(
        ax, "Mean FFTW planning + execution vs Sobel target time",
        "Simulated target time (ms)",
    )
    ax.legend()
    fig.text(
        0.5, 0.01,
        "FFTW includes one plan and one execution; edge includes the measured Sobel region.",
        ha="center", fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(PLOTS / "planning_plus_execution_latency.png", dpi=180)
    plt.close(fig)


def write_averages_csv(data):
    path = PLOTS / "averaged_metrics.csv"
    fields = (
        "resolution", "algorithm", "phase", "image_count",
        "cycles_mean", "cycles_std",
        "instructions_mean", "instructions_std",
        "ipc_mean", "ipc_std",
        "simulated_seconds_mean", "simulated_seconds_std",
        "host_seconds_mean", "host_seconds_std",
        "pixel_sum_mean", "pixel_sum_std",
    )
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for resolution in RESOLUTIONS:
            fft = data[resolution]["fft"]
            edge = data[resolution]["edge"]
            rows = (
                ("fftw", "plan", fft, "plan_cycles",
                 "plan_instructions", "plan_seconds", False),
                ("fftw", "execute", fft, "cycles",
                 "instructions", "simulated_seconds", True),
                ("edge", "sobel", edge, "cycles",
                 "instructions", "simulated_seconds", True),
            )
            for algorithm, phase, records, cycle_key, instruction_key, time_key, host in rows:
                row = {
                    "resolution": f"{resolution}x{resolution}",
                    "algorithm": algorithm,
                    "phase": phase,
                    "image_count": len(records),
                }
                for output_name, source_name in (
                    ("cycles", cycle_key),
                    ("instructions", instruction_key),
                    ("simulated_seconds", time_key),
                ):
                    values = [record[source_name] for record in records]
                    row[f"{output_name}_mean"] = mean(values)
                    row[f"{output_name}_std"] = pstdev(values)
                ipc_values = [record[instruction_key] / record[cycle_key]
                              for record in records]
                row["ipc_mean"] = mean(ipc_values)
                row["ipc_std"] = pstdev(ipc_values)
                if host:
                    values = [record["host_seconds"] for record in records]
                    row["host_seconds_mean"] = mean(values)
                    row["host_seconds_std"] = pstdev(values)
                if algorithm == "fftw" and phase == "execute":
                    values = [record["pixel_sum"] for record in records]
                    row["pixel_sum_mean"] = mean(values)
                    row["pixel_sum_std"] = pstdev(values)
                writer.writerow(row)
    return path


def main():
    data = load_results()
    PLOTS.mkdir(exist_ok=True)

    save_performance_summary(data)
    save_fftw_phase_plot(data)
    save_planning_plus_execution_plot(data)
    csv_path = write_averages_csv(data)

    print(f"Created plots in {PLOTS}")
    print(f"Created averaged data in {csv_path}")
    print("Performance charts compare FFTW execution with the Sobel region.")
    print("FFTW planning is also shown separately and in planning + execution latency.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        sys.exit(f"Plotting stopped: {error}")
