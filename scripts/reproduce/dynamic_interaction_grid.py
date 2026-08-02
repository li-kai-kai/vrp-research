from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.capacity_recovery import build_wenchuan_instance
from scripts.reproduce.dynamic_interaction_experiments import (
    MECHANISMS,
    _apply_stress,
    _write_csv,
    run_mechanism,
)


def run_grid(
    output_dir: Path,
    seed: int = 1,
    capacity_scale: float = 1.0,
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_rows = []
    for repair_scale in (1.0, 1.5, 2.0, 3.0):
        for crews in (1, 2, 3):
            instance = _apply_stress(
                build_wenchuan_instance(seed),
                repair_scale,
                crews,
                capacity_scale,
            )
            summaries, periods = [], []
            by_mechanism = {}
            for mechanism in MECHANISMS:
                summary, rows = run_mechanism(instance, mechanism, seed + 40000)
                summary.update({
                    "scenario": "wenchuan",
                    "repair_scale": repair_scale,
                    "crews": crews,
                    "capacity_scale": capacity_scale,
                })
                for row in rows:
                    row.update({
                        "scenario": "wenchuan",
                        "repair_scale": repair_scale,
                        "crews": crews,
                        "capacity_scale": capacity_scale,
                    })
                summaries.append(summary)
                periods.extend(rows)
                by_mechanism[mechanism.name] = summary

            scenario_dir = output_dir / f"s{repair_scale:g}_c{crews}"
            scenario_dir.mkdir(parents=True, exist_ok=True)
            _write_csv(scenario_dir / "mechanism_summary.csv", summaries)
            _write_csv(scenario_dir / "period_dynamics.csv", periods)
            comparison_rows.append(
                _comparison_row(repair_scale, crews, by_mechanism)
            )

    _write_csv(output_dir / "grid_comparison.csv", comparison_rows)
    return comparison_rows


def _comparison_row(repair_scale, crews, by_mechanism):
    first_summary = next(iter(by_mechanism.values()))
    row = {
        "repair_scale": repair_scale,
        "crews": crews,
        "capacity_scale": first_summary["capacity_scale"],
    }
    for name, summary in by_mechanism.items():
        for metric in (
            "cumulative_unmet_area",
            "average_reachable_ratio",
            "final_total_satisfaction",
            "final_min_satisfaction",
            "max_edge_utilization",
            "high_utilization_edge_periods",
            "capacity_blocked_tons",
            "total_vehicle_trips",
        ):
            row[f"{name}_{metric}"] = summary[metric]

    binary = by_mechanism["binary_static"]["cumulative_unmet_area"]
    progressive = by_mechanism["progressive_static"]["cumulative_unmet_area"]
    openloop = by_mechanism["progressive_openloop"]["cumulative_unmet_area"]
    rolling = by_mechanism["progressive_rolling"]["cumulative_unmet_area"]
    row.update({
        "progressive_vs_binary_pct": 100.0 * (binary - progressive) / binary,
        "rolling_vs_openloop_pct": 100.0 * (openloop - rolling) / openloop,
        "rolling_vs_binary_pct": 100.0 * (binary - rolling) / binary,
    })
    return row


def run_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--capacity-scale",
        type=float,
        default=1.0,
        help="Multiplier applied to every edge-period throughput capacity.",
    )
    parser.add_argument("--output-dir", default="outputs/dynamic_grid")
    args = parser.parse_args()
    if args.capacity_scale <= 0:
        parser.error("--capacity-scale must be greater than zero")
    rows = run_grid(
        Path(args.output_dir),
        seed=args.seed,
        capacity_scale=args.capacity_scale,
    )
    print(f"wrote {len(rows)} scenarios to {args.output_dir}")


if __name__ == "__main__":
    run_cli()
