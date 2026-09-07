"""Plot measured benchmark runs by case; accept smoke or publication cases."""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


METRICS = (
    ("hypervolume", "Normalized HV (higher is better)"),
    ("igd", "Normalized IGD (lower is better)"),
    ("unmet_area", "Cumulative unmet ratio (lower is better)"),
    ("final_min_satisfaction", "Minimum satisfaction (higher is better)"),
    ("time_cost", "Weighted time cost (lower is better)"),
    ("runtime_seconds", "Runtime (seconds)"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="run_benchmark.py runs.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/figures/benchmark"))
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()
    if args.dpi < 72:
        parser.error("--dpi must be at least 72")
    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        parser.error("input contains no benchmark runs")
    required = {"case_id", "num_nodes", "instance_seed", "algorithm", *(m for m, _ in METRICS)}
    if required - rows[0].keys():
        parser.error("input must be runs.csv, including case IDs, node counts and metrics")
    cases = sorted({(r["case_id"], int(r["num_nodes"])) for r in rows}, key=lambda c: (c[1], c[0]))
    algorithms = list(dict.fromkeys(r["algorithm"] for r in rows))
    # Average solver repeats inside each instance, then summarize instances.
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["case_id"], row["algorithm"], row["instance_seed"])].append(row)
    fig, axes = plt.subplots(2, 3, figsize=(max(12, len(cases) * 2), 8), layout="constrained")
    width = 0.8 / len(algorithms)
    for ax, (metric, title) in zip(axes.flat, METRICS):
        for index, algorithm in enumerate(algorithms):
            means, deviations = [], []
            for case, _ in cases:
                values = [statistics.fmean(float(r[metric]) for r in runs)
                          for (c, a, _), runs in grouped.items() if c == case and a == algorithm]
                means.append(statistics.fmean(values) if values else float("nan"))
                deviations.append(statistics.stdev(values) if len(values) > 1 else 0.0)
            xs = np.arange(len(cases)) + (index - (len(algorithms) - 1) / 2) * width
            ax.bar(xs, means, width, yerr=deviations, capsize=2, label=algorithm)
        ax.set_xticks(range(len(cases)), [f"{case}\nN={nodes}" for case, nodes in cases])
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Measured benchmark: instance means ± SD (solver repeats averaged within instance)")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output_dir / "benchmark_results.png", dpi=args.dpi)
    fig.savefig(args.output_dir / "benchmark_results.svg")
    plt.close(fig)


if __name__ == "__main__":
    main()
