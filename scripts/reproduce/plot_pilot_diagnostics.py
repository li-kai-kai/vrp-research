"""One diagnostic figure for the v2 small-budget pilot.

Reads only measured CSVs and the stored run records: nothing here invents a
number. Two panels answer the two questions the pilot was run for:

* does adaptive operator selection actually differ from a uniform control?
* do the heterogeneous-threshold and edge-capacity mechanisms change outcomes
  on the pilot instance at all?
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# Validated categorical slots 1 and 2 (light surface), used in fixed order.
SERIES_LIGHT = {"uniform": "#2a78d6", "adaptive": "#eb6834"}
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#d9d8d3"

OPERATOR_ORDER = (
    "swap_two_repairs",
    "insert_repair",
    "rebalance_team",
    "swap_two_dispatches",
    "move_high_demand_priority",
)


def main() -> None:
    args = _parse_args()
    algorithm_root = Path(args.algorithm_root)
    planning_root = Path(args.planning_root)

    operator_shares = _operator_shares(algorithm_root)
    binding_rows = _read_csv(planning_root / "fixed_decision_mechanism_binding.csv")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), constrained_layout=True)
    figure.patch.set_facecolor(SURFACE)
    _plot_operator_shares(axes[0], operator_shares, plt)
    _plot_mechanism_binding(axes[1], binding_rows, plt)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=170, facecolor=SURFACE)
    plt.close(figure)
    print(f"Wrote {output}")


def _plot_operator_shares(axis, shares: dict[str, dict[str, float]], plt) -> None:
    modes = ("uniform", "adaptive")
    labels = [name.replace("_", " ") for name in OPERATOR_ORDER]
    positions = list(range(len(OPERATOR_ORDER)))
    width = 0.38
    for offset, mode in enumerate(modes):
        values = [shares[mode].get(name, 0.0) for name in OPERATOR_ORDER]
        bars = axis.barh(
            [position + (offset - 0.5) * width for position in positions],
            values,
            height=width - 0.02,
            color=SERIES_LIGHT[mode],
            label=("nsga2_ls (uniform)" if mode == "uniform" else "nsga2_alns (adaptive)"),
        )
        for bar, value in zip(bars, values):
            axis.text(
                value + 0.5,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.1f}%",
                va="center",
                ha="left",
                fontsize=8.5,
                color=TEXT_SECONDARY,
            )
    axis.set_yticks(positions)
    axis.set_yticklabels(labels, fontsize=9)
    axis.invert_yaxis()
    axis.set_xlim(0.0, max(max(shares[m].values()) for m in modes) * 1.22)
    axis.set_xlabel("share of local-search evaluations (%)", fontsize=9.5)
    axis.set_title(
        "Operator selection: adaptive versus uniform control",
        fontsize=10.5,
        color=TEXT_PRIMARY,
        loc="left",
        pad=26,  # leaves the legend its own band above the plot area
    )
    # The legend sits between the title and the plot, clear of every value
    # label on the bars.
    axis.legend(
        frameon=False,
        fontsize=9,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.004),
        ncol=2,
    )
    _style_axis(axis, grid_axis="x")


def _plot_mechanism_binding(axis, rows: list[dict[str, str]], plt) -> None:
    if not rows:
        raise SystemExit("mechanism binding table is empty")
    baseline = next(
        float(row["F2"]) for row in rows if row["model_id"] == "PR0_HT0_EC0"
    )
    identifiers = [row["model_id"] for row in rows]
    deltas = [float(row["F2"]) - baseline for row in rows]
    positions = list(range(len(identifiers)))
    # One series, one hue: reusing the algorithm colours here would imply a
    # relationship between the two panels that does not exist.
    bars = axis.bar(positions, deltas, width=0.6, color=SERIES_LIGHT["uniform"])
    for bar, delta in zip(bars, deltas):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            delta - 1.2 if delta < 0 else -1.2,
            "0" if abs(delta) < 1e-9 else f"{delta:+.1f}",
            ha="center",
            va="top",
            fontsize=8.5,
            color=TEXT_SECONDARY,
        )
    axis.set_xticks(positions)
    axis.set_xticklabels(identifiers, rotation=45, ha="right", fontsize=8.5)
    axis.set_ylabel("change in F2 versus PR0_HT0_EC0 (minutes)", fontsize=9.5)
    axis.set_ylim(min(deltas) * 1.35, 0.0)
    axis.set_title(
        "Do the mechanisms move anything? Fixed decision on S025/seed 101",
        fontsize=10.5,
        color=TEXT_PRIMARY,
        loc="left",
        pad=26,  # matches the left panel so both titles sit at one height
    )
    axis.axhline(0.0, color=TEXT_SECONDARY, linewidth=1.0)
    axis.text(
        0.02,
        0.06,
        "At this one fixed decision: HT and EC change nothing.\n"
        "This does not generalise to other decisions or calibrations --\n"
        "front-wide replay does show non-zero effects on other solutions.",
        transform=axis.transAxes,
        fontsize=8.5,
        color=TEXT_SECONDARY,
        ha="left",
        va="bottom",
    )
    _style_axis(axis, grid_axis="y")


def _style_axis(axis, *, grid_axis: str) -> None:
    axis.set_facecolor(SURFACE)
    axis.grid(axis=grid_axis, color=GRID, linewidth=0.7, alpha=0.9)
    axis.set_axisbelow(True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)
    axis.tick_params(colors=TEXT_SECONDARY, labelsize=9)


def _operator_shares(algorithm_root: Path) -> dict[str, dict[str, float]]:
    """Mean operator share over runs, read from the stored run records."""
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, int] = defaultdict(int)
    for path in sorted((algorithm_root / "runs").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        algorithm = str(record["algorithm"])
        if algorithm == "nsga2":
            continue
        diagnostics = record.get("diagnostics") or {}
        total = sum(
            value for key, value in diagnostics.items() if key.startswith("operator.")
        )
        if total <= 0:
            continue
        counts[algorithm] += 1
        for key, value in diagnostics.items():
            if key.startswith("operator."):
                name = key.split(".", 1)[1].lstrip("_")
                totals[algorithm][name] += 100.0 * value / total
    if not counts:
        raise SystemExit(f"no local-search run records found under {algorithm_root}")
    shares: dict[str, dict[str, float]] = {}
    for algorithm, count in counts.items():
        share = {
            name: totals[algorithm][name] / count for name in OPERATOR_ORDER
        }
        shares["uniform" if algorithm == "nsga2_ls" else "adaptive"] = share
    return shares


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"missing measured input: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot the v2 pilot diagnostics.")
    parser.add_argument(
        "--algorithm-root",
        default="outputs/claude_v2/pilot_algorithm",
        help="Directory written by run_benchmark.py --suite benchmark.",
    )
    parser.add_argument(
        "--planning-root",
        default="outputs/claude_v2/pilot_planning",
        help="Directory containing fixed_decision_mechanism_binding.csv.",
    )
    parser.add_argument(
        "--output",
        default="outputs/claude_v2/pilot_diagnostics.png",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
