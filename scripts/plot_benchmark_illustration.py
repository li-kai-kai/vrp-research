from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


ALGORITHMS = ("spt", "vnd", "nsga2", "proposed")
ALGORITHM_LABELS = {
    "spt": "最短修复优先（SPT）",
    "vnd": "变邻域下降（VND）",
    "nsga2": "NSGA-II",
    "proposed": "NSGA-II+ALNS（本文）",
}
SIZE_GROUPS = ("small", "medium", "large")
SIZE_LABELS = {"small": "小规模 N=20", "medium": "中规模 N=60", "large": "大规模 N=120"}
NODE_COUNTS = {"small": 20, "medium": 60, "large": 120}
COLORS = {
    "spt": "#6c757d",
    "vnd": "#2a9d8f",
    "nsga2": "#2f6fbb",
    "proposed": "#d97706",
}
HATCHES = {"spt": "//", "vnd": "..", "nsga2": "", "proposed": "xx"}


# Explicitly simulated values for layout demonstration only. They are not
# derived from benchmark runs and must never be merged with empirical outputs.
ILLUSTRATIVE = {
    "hypervolume": {
        "spt": [0.25, 0.18, 0.10],
        "vnd": [0.82, 0.78, 0.62],
        "nsga2": [0.98, 1.02, 0.86],
        "proposed": [1.08, 1.13, 0.82],
    },
    "igd": {
        "spt": [0.75, 0.85, 0.95],
        "vnd": [0.30, 0.35, 0.48],
        "nsga2": [0.16, 0.18, 0.32],
        "proposed": [0.11, 0.13, 0.35],
    },
    "average_unmet_percent": {
        "spt": [55.0, 57.0, 60.0],
        "vnd": [48.0, 50.0, 54.0],
        "nsga2": [45.0, 47.0, 50.0],
        "proposed": [42.0, 44.0, 48.0],
    },
    "final_min_satisfaction_percent": {
        "spt": [68.0, 60.0, 45.0],
        "vnd": [82.0, 78.0, 70.0],
        "nsga2": [88.0, 86.0, 80.0],
        "proposed": [91.0, 90.0, 84.0],
    },
    "time_cost": {
        "spt": [3400.0, 11000.0, 24000.0],
        "vnd": [3000.0, 9500.0, 21500.0],
        "nsga2": [2850.0, 9000.0, 20500.0],
        "proposed": [2720.0, 8600.0, 19800.0],
    },
    "runtime_seconds": {
        "spt": [0.02, 0.10, 0.50],
        "vnd": [1.50, 9.00, 45.0],
        "nsga2": [1.60, 9.50, 46.0],
        "proposed": [2.00, 12.0, 58.0],
    },
}

METRICS = (
    ("hypervolume", "(a) Pareto 前沿质量：Hypervolume", "HV（越大越好）", False),
    ("igd", "(b) 与参考前沿距离：IGD", "IGD（越小越好）", False),
    (
        "average_unmet_percent",
        "(c) 规划期平均未满足率",
        "平均未满足率（%，越小越好）",
        False,
    ),
    (
        "final_min_satisfaction_percent",
        "(d) 最弱需求点服务水平",
        "最终最低满足率（%，越大越好）",
        False,
    ),
    ("time_cost", "(e) 时间成本", "加权时间成本（越小越好）", False),
    ("runtime_seconds", "(f) 运行时间与规模扩展", "运行时间（秒，对数尺度）", True),
)

plt.rcParams["font.sans-serif"] = [
    "Arial Unicode MS",
    "Lantinghei SC",
    "PingFang HK",
    "STHeiti",
    "sans-serif",
]
plt.rcParams["axes.unicode_minus"] = False


def main() -> None:
    parser = argparse.ArgumentParser(description="绘制明确标注为模拟数据的 benchmark 版式示意图")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/figures/benchmark_illustration"),
    )
    parser.add_argument("--dpi", type=int, default=220)
    args = parser.parse_args()
    if args.dpi < 72:
        parser.error("--dpi must be at least 72")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    figure, axes = plt.subplots(2, 3, figsize=(16.5, 10.5), facecolor="white")
    for axis, (metric, title, ylabel, log_scale) in zip(axes.flat, METRICS):
        _draw_metric(axis, metric, title, ylabel, log_scale=log_scale)

    handles = [
        Line2D(
            [0],
            [0],
            color=COLORS[algorithm],
            marker="o",
            linewidth=2,
            label=ALGORITHM_LABELS[algorithm],
        )
        for algorithm in ALGORITHMS
    ]
    figure.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.905),
        ncol=4,
        frameon=False,
        fontsize=9,
    )
    figure.suptitle(
        "不同基线算法在多规模实例上的预期结果示意",
        fontsize=18,
        fontweight="bold",
        y=0.985,
    )
    figure.text(
        0.5,
        0.945,
        "模拟数据 · 仅作版式示意 · 非实验结果",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        color="#b02a37",
    )
    figure.text(
        0.5,
        0.018,
        "所有数值均为人为设定的示意数据，不得作为 benchmark 实测结果、论文证据或统计结论引用。",
        ha="center",
        va="bottom",
        fontsize=9,
        color="#b02a37",
    )
    figure.subplots_adjust(left=0.065, right=0.98, top=0.84, bottom=0.075, wspace=0.28, hspace=0.38)

    png_path = args.output_dir / "benchmark_expected_results_illustration.png"
    svg_path = args.output_dir / "benchmark_expected_results_illustration.svg"
    figure.savefig(png_path, dpi=args.dpi, bbox_inches="tight")
    figure.savefig(svg_path, bbox_inches="tight")
    plt.close(figure)
    _write_data(args.output_dir / "illustrative_data.csv")
    print(f"PNG: {png_path.resolve()}")
    print(f"SVG: {svg_path.resolve()}")


def _draw_metric(
    axis: plt.Axes,
    metric: str,
    title: str,
    ylabel: str,
    *,
    log_scale: bool,
) -> None:
    x_values = np.arange(len(SIZE_GROUPS), dtype=float)
    width = 0.19
    for idx, algorithm in enumerate(ALGORITHMS):
        values = ILLUSTRATIVE[metric][algorithm]
        errors = _illustrative_errors(metric, algorithm, values)
        axis.bar(
            x_values + (idx - 1.5) * width,
            values,
            width=width,
            yerr=errors,
            color=COLORS[algorithm],
            edgecolor="#343a40",
            linewidth=0.45,
            hatch=HATCHES[algorithm],
            error_kw={"elinewidth": 0.8, "capsize": 2.5, "capthick": 0.8},
            alpha=0.90,
        )
    axis.set_xticks(x_values, [SIZE_LABELS[size] for size in SIZE_GROUPS])
    axis.set_ylabel(ylabel)
    axis.set_title(title, fontsize=11, fontweight="bold")
    axis.grid(axis="y", color="#dee2e6", linewidth=0.65, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    if log_scale:
        axis.set_yscale("log")
    else:
        axis.set_ylim(bottom=0.0)


def _illustrative_errors(metric: str, algorithm: str, values: list[float]) -> list[float]:
    if algorithm == "spt":
        return [0.0] * len(values)
    fraction = 0.06 if metric in {"hypervolume", "igd"} else 0.025
    return [value * fraction for value in values]


def _write_data(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["data_status", "metric", "algorithm", "size_group", "nodes", "value"])
        for metric, values_by_algorithm in ILLUSTRATIVE.items():
            for algorithm, values in values_by_algorithm.items():
                for size_group, value in zip(SIZE_GROUPS, values):
                    writer.writerow(
                        [
                            "SIMULATED_LAYOUT_ONLY_NOT_EXPERIMENTAL",
                            metric,
                            algorithm,
                            size_group,
                            NODE_COUNTS[size_group],
                            value,
                        ]
                    )


if __name__ == "__main__":
    main()
