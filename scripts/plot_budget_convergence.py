"""Plot budget diagnostics from measured CSVs, preserving paired seeds."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import statistics
import sys

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import csv
from scripts.plot_common_execution import COLORS, STYLES
MODEL_STYLES = {model: (color, STYLES[model]) for model, color in COLORS.items()}

def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))

def style_axis(axis):
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(alpha=.15)

def save_figure(figure, directory, stem, plt):
    paths = []
    for extension in ("png", "pdf"):
        path = directory / f"{stem}.{extension}"
        figure.savefig(path, dpi=180, bbox_inches="tight")
        paths.append(str(path))
    plt.close(figure)
    return paths

from scripts.reproduce.solution_io import code_environment, write_json_atomic

def configure_x(axis, budgets):
    axis.set_xscale("log")
    axis.set_xticks(budgets, [str(value) for value in budgets])
    axis.minorticks_off()
    axis.set_xlim(min(budgets) * 0.85, max(budgets) * 1.17)
    axis.set_xlabel("Objective evaluations (log scale)")
    style_axis(axis)

def plot_planning(rows, directory, plt):
    budgets = sorted({int(r["max_evaluations"]) for r in rows})
    seeds = sorted({int(r["solver_seed"]) for r in rows})
    lookup = {(int(r["max_evaluations"]), int(r["solver_seed"]), r["planning_model"]): r for r in rows}
    figure, axes = plt.subplots(2, 4, figsize=(14, 6.8))
    for column, (model, (color, _)) in enumerate(MODEL_STYLES.items()):
        for row_index, (metric, label) in enumerate((
            ("planning_hypervolume", "Planning HV (higher is better)"),
            ("planning_igd", "Planning IGD (lower is better)"),
        )):
            axis = axes[row_index, column]
            for seed in seeds:
                values = [float(lookup[(b, seed, model)][metric]) for b in budgets]
                axis.plot(budgets, values, color="#aaaaaa", linewidth=1, alpha=0.7, marker=".", markersize=5)
            medians = [statistics.median([float(lookup[(b, s, model)][metric]) for s in seeds]) for b in budgets]
            axis.plot(budgets, medians, color=color, linewidth=2.5, marker="o", markersize=5)
            axis.set_title(model, fontsize=11)
            if column == 0:
                axis.set_ylabel(label)
            configure_x(axis, budgets)
    figure.suptitle("WEN38: search progress within each planning model", fontsize=14, y=1.02)
    figure.text(0.5, 0.005,
                "Thin lines: paired solver seeds. Thick line: median. Reference frames are fixed across budgets within each model; "
                "planning HV/IGD values are not comparable between models.", ha="center", fontsize=8)
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    return save_figure(figure, directory, "planning_budget_curves", plt)

def plot_execution(rows, directory, plt):
    budgets = sorted({int(r["max_evaluations"]) for r in rows})
    figure, axes = plt.subplots(2, 2, figsize=(11.5, 7.2))
    metrics = (
        ("execution_hypervolume", "Full-execution HV (higher is better)", 1.0),
        ("execution_igd", "Full-execution IGD (lower is better)", 1.0),
        ("execution_min_satisfaction", "Representative: minimum satisfaction (%),", 100.0),
        ("execution_zero_service_ratio", "Representative: nodes without service (%),", 100.0),
    )
    for axis, (metric, label, scale) in zip(axes.flat, metrics):
        for model, (color, line) in MODEL_STYLES.items():
            values = [[float(r[metric]) * scale for r in rows
                       if int(r["max_evaluations"]) == b and r["planning_model"] == model] for b in budgets]
            medians = [statistics.median(v) for v in values]
            axis.fill_between(budgets, [min(v) for v in values], [max(v) for v in values], color=color, alpha=0.10)
            axis.plot(budgets, medians, label=model, color=color, linestyle=line,
                      linewidth=2.5 if model == "Full" else 1.8, marker="o", markersize=4)
        axis.set_title(label, fontsize=11)
        configure_x(axis, budgets)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(handles, labels, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 0.985), frameon=False)
    figure.suptitle("WEN38: common Full execution across evaluation budgets", fontsize=14, y=1.02)
    figure.text(0.5, 0.005,
                "Lines: medians; shading: observed seed ranges (not confidence intervals). "
                "Representatives were selected in their planning model before replay.", ha="center", fontsize=8)
    figure.tight_layout(rect=(0, 0.04, 1, 0.94))
    return save_figure(figure, directory, "execution_budget_curves", plt)

def plot_advantages(rows, directory, plt):
    budgets = sorted({int(r["max_evaluations"]) for r in rows})
    seeds = sorted({int(r["solver_seed"]) for r in rows})
    palette = ("#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00")
    lookup = {(int(r["max_evaluations"]), int(r["solver_seed"]), r["reduced_model"]): r for r in rows}
    figure, axes = plt.subplots(2, 3, figsize=(12, 7.2), sharey="row")
    for column, model in enumerate(("No-PR", "No-HT", "No-EC")):
        for row_index, (metric, label) in enumerate((
            ("full_hv_advantage", "HV(Full) - HV(reduced)"),
            ("full_igd_advantage", "IGD(reduced) - IGD(Full)"),
        )):
            axis = axes[row_index, column]
            for index, seed in enumerate(seeds):
                values = [float(lookup[(b, seed, model)][metric]) for b in budgets]
                axis.plot(budgets, values, color=palette[index % len(palette)], marker="o",
                          linewidth=1.25, markersize=4, label=str(seed), alpha=0.9)
            axis.axhline(0.0, color="#777777", linewidth=0.9)
            if row_index == 0:
                axis.set_title(f"Full versus {model}", fontsize=11)
            if column == 0:
                axis.set_ylabel(label + "\npositive favors Full")
            configure_x(axis, budgets)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(handles, labels, title="Paired solver seed", ncol=len(seeds), loc="upper center",
                  bbox_to_anchor=(0.5, 1.00), frameon=False)
    figure.suptitle("WEN38: model comparisons as search budgets increase", fontsize=14, y=1.055)
    figure.text(0.5, 0.005,
                "One line per paired seed, all evaluated in Full with one shared reference frame. "
                "Search convergence does not require Full to win.", ha="center", fontsize=8)
    figure.tight_layout(rect=(0, 0.04, 1, 0.91))
    return save_figure(figure, directory, "paired_model_budget_curves", plt)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    quality_path = args.input_dir / "run_quality.csv"
    pairs_path = args.input_dir / "model_pairs.csv"
    rows, pairs = read_csv(quality_path), read_csv(pairs_path)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    args.output_dir.mkdir(parents=True, exist_ok=True)
    paths = plot_planning(rows, args.output_dir, plt)
    paths.extend(plot_execution(rows, args.output_dir, plt))
    paths.extend(plot_advantages(pairs, args.output_dir, plt))
    inputs = (quality_path, pairs_path, args.input_dir / "analysis_manifest.json",
              Path(__file__), Path(__file__).with_name("plot_common_execution.py"))
    write_json_atomic(args.output_dir / "figure_manifest.json", {
        "code": code_environment(), "figures": paths,
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        "scope": "Measured paired seeds on one WEN38 case; shaded ranges are descriptive, not confidence intervals.",
    })
    print(f"Wrote {len(paths)} figure files to {args.output_dir}")

if __name__ == "__main__":
    main()