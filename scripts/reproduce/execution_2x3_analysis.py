"""Execution-side 2^3 factor effects for the formal model-value experiment.

Reads the shared-execution replay of the full factorial
(``common_execution_analysis.py --factorial`` over the formal model track) and
recomputes the paired 2^3 factor effects on the execution-side endpoints by
swapping the outcome columns of the planning rows and reusing the validated
estimator and tests of ``model_ablation_analysis`` (per-instance effects,
sign-flip p-values, bootstrap CIs, Holm within (case, metric); WEN38 is analysed
per solver run as in the planning-side module).

Execution-side columns swapped in:

- ``F1``/``F2``/``F3`` -- the planning-preselected representative re-evaluated
  in the shared Full environment (``representative_*`` of the replay);
- ``hypervolume``/``igd`` -- the execution front against the per-instance
  pooled reference (same convention as the planning-side quality columns);
- ``final_total_satisfaction``/``final_min_satisfaction`` -- execution-side
  service outcomes.

The remaining mechanism-diagnostic columns are not available execution-side.
They are carried over from the planning rows so the estimator accepts every
row, and are dropped from the reported tables. The Holm family is per
(case, metric), so the carried columns do not change the adjusted p-values of
the reported metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.model_ablation_analysis import (
    analyze_model_ablation,
    merge_model_ablation_shards,
)


EXECUTION_COLUMNS = {
    "F1": "representative_F1",
    "F2": "representative_F2",
    "F3": "representative_F3",
    "hypervolume": "hypervolume",
    "igd": "igd",
    "final_total_satisfaction": "final_total_satisfaction",
    "final_min_satisfaction": "final_min_satisfaction",
}
CARRIED_COLUMNS = (
    "average_reachable_ratio",
    "final_repaired_ratio",
    "partial_recovery_edge_periods",
    "small_vehicle_share",
    "max_edge_utilization",
    "high_utilization_edge_periods",
    "capacity_blocked_tons",
    "total_vehicle_trips",
    "total_delivery_time",
    "total_repair_work",
    "total_crew_transfer_time",
)
IDENTITY = ("case_id", "instance_seed", "solver_seed", "model_id")


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", type=Path, required=True, help="formal model track root")
    parser.add_argument("--exec-dir", type=Path, required=True, help="exec_all output directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=5_000)
    parser.add_argument("--permutation-samples", type=int, default=20_000)
    args = parser.parse_args()

    shards = sorted(args.track.glob("*/model_ablation.csv"))
    if not shards:
        parser.error(f"no model_ablation.csv below {args.track}")
    rows, _, _ = merge_model_ablation_shards(shards)

    with (args.exec_dir / "execution_runs.csv").open(newline="", encoding="utf-8") as handle:
        execution = {row["run_key"]: row for row in csv.DictReader(handle)}
    if len(execution) != len(rows):
        parser.error("execution replay and planning rows disagree on run count")

    swapped = 0
    for row in rows:
        source = execution.get(row["run_key"])
        if source is None:
            raise SystemExit(f"run missing from execution replay: {row['run_key']}")
        for identity in IDENTITY:
            if str(source[identity]) != str(row[identity]):
                raise SystemExit(f"identity mismatch on {identity}: {row['run_key']}")
        for column, source_column in EXECUTION_COLUMNS.items():
            value = source[source_column]
            if value in (None, ""):
                raise SystemExit(f"execution value missing: {row['run_key']} {source_column}")
            row[column] = float(value)
        swapped += 1

    model_summary, raw_effects, effect_summary, completeness = analyze_model_ablation(
        rows,
        bootstrap_samples=args.bootstrap_samples,
        permutation_samples=args.permutation_samples,
    )

    reported_metrics = set(EXECUTION_COLUMNS)
    effect_rows = [row for row in effect_summary if row["metric"] in reported_metrics]
    summary_rows = [row for row in model_summary if row["metric"] in reported_metrics]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "execution_factor_effects.csv", effect_rows)
    _write_csv(args.output_dir / "execution_model_summary.csv", summary_rows)
    _write_csv(args.output_dir / "factorial_completeness.csv", completeness)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "planning_shards": [str(path) for path in shards],
        "execution_source": str(args.exec_dir / "execution_runs.csv"),
        "swapped_columns": EXECUTION_COLUMNS,
        "carried_planning_columns_dropped_from_report": list(CARRIED_COLUMNS),
        "bootstrap_samples": args.bootstrap_samples,
        "permutation_samples": args.permutation_samples,
        "runs": swapped,
        "note": (
            "Execution endpoints: representative re-evaluated in the shared Full "
            "environment; hypervolume/igd against the per-instance pooled "
            "reference of the full factorial replay. Holm family is per "
            "(case, metric) over the seven factor terms."
        ),
    }
    (args.output_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"wrote {len(effect_rows)} effect rows for {len(reported_metrics)} execution metrics")


if __name__ == "__main__":
    main()
