from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


ALGORITHMS = ("spt", "vnd", "nsga2", "nsga2_alns")
ALGORITHM_LABELS = {
    "spt": "最短修复优先（SPT）",
    "vnd": "变邻域下降（VND）",
    "nsga2": "NSGA-II",
    "nsga2_alns": "NSGA-II+ALNS（本文）",
}
SIZE_GROUPS = ("small", "medium", "large")
SIZE_LABELS = {"small": "小规模 N=20", "medium": "中规模 N=60", "large": "大规模 N=120"}
NODE_COUNTS = {"small": 20, "medium": 60, "large": 120}
COLORS = {
    "spt": "#6c757d",
    "vnd": "#2a9d8f",
    "nsga2": "#2f6fbb",
    "nsga2_alns": "#d97706",
}
HATCHES = {"spt": "//", "vnd": "..", "nsga2": "", "nsga2_alns": "xx"}
MARKERS = {"small": "o", "medium": "s", "large": "^"}
SIZE_COLORS = {"small": "#6c757d", "medium": "#2f6fbb", "large": "#d97706"}
SIZE_HATCHES = {"small": "//", "medium": "..", "large": "xx"}


plt.rcParams["font.sans-serif"] = [
    "Arial Unicode MS",
    "Lantinghei SC",
    "PingFang HK",
    "STHeiti",
    "sans-serif",
]
plt.rcParams["axes.unicode_minus"] = False


def main() -> None:
    args = _parse_args()
    rows = _read_rows(args.input)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    figure = plt.figure(figsize=(16.5, 10.5), facecolor="white")
    grid = figure.add_gridspec(2, 3, wspace=0.28, hspace=0.38)
    axes = [figure.add_subplot(grid[row, col]) for row in range(2) for col in range(3)]

    _grouped_metric(
        axes[0],
        rows,
        mean_key="hypervolume_mean",
        sd_key="hypervolume_sd",
        title="(a) Pareto 前沿质量：Hypervolume",
        ylabel="HV（越大越好）",
    )
    _grouped_metric(
        axes[1],
        rows,
        mean_key="igd_mean",
        sd_key="igd_sd",
        title="(b) 与参考前沿距离：IGD",
        ylabel="IGD（越小越好）",
    )
    _grouped_metric(
        axes[2],
        rows,
        mean_key="unmet_area_mean",
        sd_key="unmet_area_sd",
        title="(c) 规划期平均未满足率",
        ylabel="平均未满足率（%，越小越好）",
        value_scale=100.0 / args.periods,
    )
    _grouped_metric(
        axes[3],
        rows,
        mean_key="final_min_satisfaction_mean",
        sd_key="final_min_satisfaction_sd",
        title="(d) 最弱需求点服务水平",
        ylabel="最终最低满足率（越大越好）",
        ylim=(0.0, 1.0),
    )
    _runtime_scaling(axes[4], rows)
    _quality_tradeoff(axes[5], rows)

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
        bbox_to_anchor=(0.5, 0.925),
        ncol=4,
        frameon=False,
        fontsize=10,
    )
    figure.suptitle(
        "不同基线算法在多规模实例上的结果比较",
        fontsize=18,
        fontweight="bold",
        y=0.985,
    )
    figure.text(
        0.5,
        0.018,
        f"误差线为跨求解种子的 ±1 SD；未满足指标按 {args.periods} 个决策期转换为时间平均百分比；"
        "每个规模仅 1 个实例种子，随机算法 3 次、100 次目标评价，SPT 为确定性单次构造。",
        ha="center",
        va="bottom",
        fontsize=9,
        color="#495057",
    )
    figure.subplots_adjust(left=0.065, right=0.98, top=0.865, bottom=0.075)
    png_path = output_dir / "benchmark_baselines_multiscale.png"
    svg_path = output_dir / "benchmark_baselines_multiscale.svg"
    figure.savefig(png_path, dpi=args.dpi, bbox_inches="tight")
    figure.savefig(svg_path, bbox_inches="tight")
    plt.close(figure)
    print(f"PNG: {png_path.resolve()}")
    print(f"SVG: {svg_path.resolve()}")
    _save_algorithm_figures(
        rows,
        output_dir=output_dir,
        dpi=args.dpi,
        periods=args.periods,
    )


def _save_algorithm_figures(
    rows: dict[tuple[str, str], dict[str, float]],
    *,
    output_dir: Path,
    dpi: int,
    periods: int,
) -> None:
    metric_specs = (
        ("(a) Hypervolume", "HV（越大越好）", "hypervolume_mean", "hypervolume_sd", 1.0, None, ".3f", False),
        ("(b) IGD", "IGD（越小越好）", "igd_mean", "igd_sd", 1.0, None, ".3f", False),
        (
            "(c) 规划期平均未满足率",
            "平均未满足率（%，越小越好）",
            "unmet_area_mean",
            "unmet_area_sd",
            100.0 / periods,
            (0.0, None),
            ".1f",
            False,
        ),
        (
            "(d) 最终最低满足率",
            "最终最低满足率（%，越大越好）",
            "final_min_satisfaction_mean",
            "final_min_satisfaction_sd",
            100.0,
            (0.0, 100.0),
            ".1f",
            False,
        ),
        ("(e) 时间成本", "加权时间成本（越小越好）", "time_cost_mean", "time_cost_sd", 1.0, None, ".0f", False),
        (
            "(f) 运行时间",
            "运行时间（秒，对数尺度）",
            "runtime_seconds_mean",
            "runtime_seconds_sd",
            1.0,
            None,
            ".3g",
            True,
        ),
    )
    for algorithm in ALGORITHMS:
        figure, axes = plt.subplots(2, 3, figsize=(15.5, 8.8), facecolor="white")
        for axis, metric in zip(axes.flat, metric_specs):
            _single_algorithm_metric(axis, rows, algorithm=algorithm, spec=metric)
        figure.suptitle(
            f"{ALGORITHM_LABELS[algorithm]} 在不同问题规模下的 Benchmark 结果",
            fontsize=17,
            fontweight="bold",
            y=0.985,
        )
        figure.text(
            0.5,
            0.018,
            f"误差线为跨求解种子的 ±1 SD；平均未满足率按 {periods} 个决策期换算；"
            "随机算法 3 次、100 次目标评价，SPT 为确定性单次构造。",
            ha="center",
            va="bottom",
            fontsize=9,
            color="#495057",
        )
        figure.subplots_adjust(
            left=0.07,
            right=0.985,
            top=0.90,
            bottom=0.10,
            wspace=0.27,
            hspace=0.38,
        )
        stem = f"benchmark_results_by_scale_{algorithm}"
        png_path = output_dir / f"{stem}.png"
        svg_path = output_dir / f"{stem}.svg"
        figure.savefig(png_path, dpi=dpi, bbox_inches="tight")
        figure.savefig(svg_path, bbox_inches="tight")
        plt.close(figure)
        print(f"{ALGORITHM_LABELS[algorithm]} PNG: {png_path.resolve()}")
        print(f"{ALGORITHM_LABELS[algorithm]} SVG: {svg_path.resolve()}")


def _single_algorithm_metric(
    axis: plt.Axes,
    rows: dict[tuple[str, str], dict[str, float]],
    *,
    algorithm: str,
    spec: tuple[str, str, str, str, float, tuple[float, float | None] | None, str, bool],
) -> None:
    title, ylabel, mean_key, sd_key, scale, ylim, value_format, log_scale = spec
    means = [rows[(size_group, algorithm)][mean_key] * scale for size_group in SIZE_GROUPS]
    errors = [rows[(size_group, algorithm)][sd_key] * scale for size_group in SIZE_GROUPS]
    x_values = np.arange(len(SIZE_GROUPS))
    bars = axis.bar(
        x_values,
        means,
        yerr=errors,
        width=0.68,
        color=[SIZE_COLORS[size_group] for size_group in SIZE_GROUPS],
        edgecolor="#343a40",
        linewidth=0.55,
        hatch=[SIZE_HATCHES[size_group] for size_group in SIZE_GROUPS],
        error_kw={"elinewidth": 0.9, "capsize": 3.0, "capthick": 0.9},
        alpha=0.92,
    )
    labels = [format(value, value_format) for value in means]
    axis.bar_label(bars, labels=labels, padding=4, fontsize=8.5)
    axis.set_xticks(
        x_values,
        [SIZE_LABELS[size_group].replace(" ", "\n", 1) for size_group in SIZE_GROUPS],
    )
    axis.set_ylabel(ylabel)
    axis.set_title(title, fontsize=11, fontweight="bold")
    axis.grid(axis="y", color="#dee2e6", linewidth=0.65, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    if log_scale:
        axis.set_yscale("log")
    elif ylim is not None:
        lower, upper = ylim
        axis.set_ylim(bottom=lower, top=upper)
    else:
        axis.set_ylim(bottom=0.0)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="绘制多规模 benchmark 质量、服务和扩展性图表")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("outputs/benchmark_development/aggregate_by_size.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/figures/benchmark_development"),
    )
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument(
        "--periods",
        type=int,
        default=9,
        help="用于将累计未满足程度转换为平均未满足率的决策期数（默认：9）",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"input file does not exist: {args.input}")
    if args.dpi < 72:
        parser.error("--dpi must be at least 72")
    if args.periods < 1:
        parser.error("--periods must be positive")
    return args


def _read_rows(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    rows: dict[tuple[str, str], dict[str, float]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["size_group"], row["algorithm"])
            rows[key] = {
                name: float(value)
                for name, value in row.items()
                if name not in {"size_group", "algorithm"}
            }
    expected = {(size, algorithm) for size in SIZE_GROUPS for algorithm in ALGORITHMS}
    missing = expected - set(rows)
    if missing:
        raise ValueError(f"missing benchmark rows: {sorted(missing)}")
    return rows


def _grouped_metric(
    axis: plt.Axes,
    rows: dict[tuple[str, str], dict[str, float]],
    *,
    mean_key: str,
    sd_key: str,
    title: str,
    ylabel: str,
    ylim: tuple[float, float] | None = None,
    value_scale: float = 1.0,
) -> None:
    group_x = np.arange(len(SIZE_GROUPS), dtype=float)
    width = 0.19
    for idx, algorithm in enumerate(ALGORITHMS):
        means = [
            rows[(size, algorithm)][mean_key] * value_scale
            for size in SIZE_GROUPS
        ]
        errors = [
            rows[(size, algorithm)][sd_key] * value_scale
            for size in SIZE_GROUPS
        ]
        offsets = group_x + (idx - 1.5) * width
        axis.bar(
            offsets,
            means,
            width=width,
            yerr=errors,
            color=COLORS[algorithm],
            edgecolor="#343a40",
            linewidth=0.45,
            hatch=HATCHES[algorithm],
            error_kw={"elinewidth": 0.8, "capsize": 2.5, "capthick": 0.8},
            alpha=0.90,
        )
    axis.set_xticks(group_x, [SIZE_LABELS[size] for size in SIZE_GROUPS])
    axis.set_ylabel(ylabel)
    axis.set_title(title, fontsize=11, fontweight="bold")
    axis.grid(axis="y", color="#dee2e6", linewidth=0.65, alpha=0.8)
    axis.set_axisbelow(True)
    if ylim is not None:
        axis.set_ylim(*ylim)
    else:
        axis.set_ylim(bottom=0.0)
    axis.spines[["top", "right"]].set_visible(False)


def _runtime_scaling(
    axis: plt.Axes,
    rows: dict[tuple[str, str], dict[str, float]],
) -> None:
    xs = [NODE_COUNTS[size] for size in SIZE_GROUPS]
    for algorithm in ALGORITHMS:
        means = [rows[(size, algorithm)]["runtime_seconds_mean"] for size in SIZE_GROUPS]
        errors = [rows[(size, algorithm)]["runtime_seconds_sd"] for size in SIZE_GROUPS]
        axis.errorbar(
            xs,
            means,
            yerr=errors,
            color=COLORS[algorithm],
            marker="o",
            markersize=5,
            linewidth=1.9,
            capsize=2.5,
            label=ALGORITHM_LABELS[algorithm],
        )
    axis.set_yscale("log")
    axis.set_xticks(xs, [str(value) for value in xs])
    axis.set_xlabel("节点数 N")
    axis.set_ylabel("运行时间（秒，对数尺度）")
    axis.set_title("(e) 运行时间与规模扩展", fontsize=11, fontweight="bold")
    axis.grid(which="both", color="#dee2e6", linewidth=0.65, alpha=0.8)
    axis.spines[["top", "right"]].set_visible(False)


def _quality_tradeoff(
    axis: plt.Axes,
    rows: dict[tuple[str, str], dict[str, float]],
) -> None:
    for size_group in SIZE_GROUPS:
        for algorithm in ALGORITHMS:
            row = rows[(size_group, algorithm)]
            axis.scatter(
                row["igd_mean"],
                row["hypervolume_mean"],
                marker=MARKERS[size_group],
                s=78,
                color=COLORS[algorithm],
                edgecolor="#343a40",
                linewidth=0.55,
                alpha=0.92,
            )
    size_handles = [
        Line2D(
            [0],
            [0],
            marker=MARKERS[size],
            color="none",
            markerfacecolor="#adb5bd",
            markeredgecolor="#343a40",
            markersize=7,
            label=SIZE_LABELS[size],
        )
        for size in SIZE_GROUPS
    ]
    axis.legend(handles=size_handles, loc="upper right", frameon=False, fontsize=8)
    axis.set_xlabel("IGD（越小越好）")
    axis.set_ylabel("HV（越大越好）")
    axis.set_title("(f) 前沿质量—距离权衡", fontsize=11, fontweight="bold")
    axis.grid(color="#dee2e6", linewidth=0.65, alpha=0.8)
    axis.spines[["top", "right"]].set_visible(False)


if __name__ == "__main__":
    main()
