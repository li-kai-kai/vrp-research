"""Summarize a replay table without treating Pareto points as replicates.

A replay CSV has one row per stored non-dominated decision. Runs that
explored more of the front therefore contribute more rows, so averaging over
all rows would silently weight a run by how many points it happened to keep.

This script therefore reduces *within each run first*: per run it counts the
solutions whose change exceeds the pinned service resolution, and takes the
mean, median and maximum absolute change. The across-run figures are then
means of those run-level statistics with equal weight per run, and the largest
change anywhere is reported separately together with the run key and solution
id it came from.

Fixed-decision diagnostics, whole-front replay and the pre-selected
representative are separate questions and are reported in separate tables.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if __package__ == "" or __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.solution_io import write_csv_atomic, write_json_atomic


# A change is called real only when it exceeds the resolution the objectives
# are compared at, so rounding noise is never reported as an effect.
TOLERANCES = {
    "F1": V2_PRECISION.resolutions[0],
    "F2": V2_PRECISION.resolutions[1],
    "F3": V2_PRECISION.resolutions[2],
}

GROUP_ORDER = ("PR1_HT1_EC1", "PR0_HT1_EC1", "PR1_HT0_EC1", "PR1_HT1_EC0")


def main() -> None:
    args = _parse_args()
    rows = _read_replay(Path(args.replay_results))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    group_rows, run_rows, representative_rows = summarize(rows)

    write_csv_atomic(
        output_dir / "replay_by_model_group.csv",
        group_rows,
        list(group_rows[0]) if group_rows else None,
    )
    write_csv_atomic(
        output_dir / "replay_per_run.csv",
        run_rows,
        list(run_rows[0]) if run_rows else None,
    )
    write_csv_atomic(
        output_dir / "replay_representatives.csv",
        representative_rows,
        list(representative_rows[0]) if representative_rows else None,
    )
    write_json_atomic(
        output_dir / "replay_summary.json",
        {
            "replay_results": str(args.replay_results),
            "solutions": len(rows),
            "runs": len({row["run_key"] for row in rows}),
            "tolerances": TOLERANCES,
            "pooling_rule": (
                "reduced within each run first; across-run figures are means of "
                "run-level statistics with equal weight per run"
            ),
        },
    )
    print(f"Summarized {len(rows)} solutions from {len(run_rows)} runs -> {output_dir}")


def _model_group(run_key: str, planning_model: str | None) -> str:
    """The planning model id encoded in the run key, e.g. PR1_HT1_EC1."""
    for group in GROUP_ORDER:
        if f":{group}:" in run_key or run_key.endswith(f":{group}"):
            return group
    return planning_model or "unknown"


def _read_replay(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"missing replay results: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("replay_minus_planning_F1") not in (None, "")
        ]
    if not rows:
        raise SystemExit(f"no replayed solutions in {path}")
    return rows


def summarize(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Per-run reduction, then across-run aggregation, plus the representative view."""
    by_run: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_run[row["run_key"]].append(row)

    per_run_rows: list[dict[str, Any]] = []
    for run_key, members in sorted(by_run.items()):
        entry: dict[str, Any] = {
            "run_key": run_key,
            "model_group": _model_group(run_key, members[0].get("planning_model")),
            "case_id": members[0].get("case_id") or "",
            "instance_seed": members[0].get("instance_seed"),
            "solutions": len(members),
        }
        for name in ("F1", "F2", "F3"):
            column = f"replay_minus_planning_{name}"
            deltas = [float(row[column]) for row in members]
            abs_deltas = [abs(value) for value in deltas]
            worst = max(members, key=lambda row: abs(float(row[column])))
            tolerance = TOLERANCES[name]
            entry[f"nonzero_solutions_{name}"] = sum(
                1 for value in abs_deltas if value > tolerance
            )
            entry[f"mean_delta_{name}"] = statistics.fmean(deltas)
            entry[f"median_delta_{name}"] = statistics.median(deltas)
            entry[f"max_abs_delta_{name}"] = max(abs_deltas)
            entry[f"max_abs_delta_{name}_solution"] = worst["solution_id"]
        per_run_rows.append(entry)

    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in per_run_rows:
        by_group[str(entry["model_group"])].append(entry)

    group_rows: list[dict[str, Any]] = []
    for group in sorted(by_group, key=lambda name: (GROUP_ORDER.index(name) if name in GROUP_ORDER else 99, name)):
        runs = by_group[group]
        aggregate: dict[str, Any] = {
            "model_group": group,
            "runs": len(runs),
            "solutions": sum(int(entry["solutions"]) for entry in runs),
        }
        for name in ("F1", "F2", "F3"):
            # Run-level statistics averaged with one vote per run. The absolute
            # worst case is reported separately with its provenance, never as
            # an average over points.
            aggregate[f"runs_with_any_{name}_change"] = sum(
                1 for entry in runs if int(entry[f"nonzero_solutions_{name}"]) > 0
            )
            aggregate[f"mean_of_run_mean_delta_{name}"] = statistics.fmean(
                float(entry[f"mean_delta_{name}"]) for entry in runs
            )
            aggregate[f"mean_of_run_median_delta_{name}"] = statistics.fmean(
                float(entry[f"median_delta_{name}"]) for entry in runs
            )
            worst_run = max(runs, key=lambda entry: float(entry[f"max_abs_delta_{name}"]))
            aggregate[f"worst_run_max_abs_delta_{name}"] = float(
                worst_run[f"max_abs_delta_{name}"]
            )
            aggregate[f"worst_run_{name}"] = worst_run["run_key"]
            aggregate[f"worst_run_{name}_solution"] = worst_run[f"max_abs_delta_{name}_solution"]
        group_rows.append(aggregate)

    representative_rows = _representative_table(rows)
    return group_rows, per_run_rows, representative_rows


def _representative_table(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """The pre-selected representative solution, reported on its own.

    The representative is chosen before any replay by the lexicographic
    (F3, F1, F2) rule, so it is a single decision per run rather than a front
    statistic and must not be mixed into the front-wide numbers.
    """
    table: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("representative_selected_before_replay")).lower() not in ("true", "1"):
            continue
        table.append(
            {
                "run_key": row["run_key"],
                "model_group": _model_group(row["run_key"], row.get("planning_model")),
                "solution_id": row["solution_id"],
                "decision_hash": row["decision_hash"],
                "planning_F1": float(row["planning_F1"]),
                "planning_F2": float(row["planning_F2"]),
                "planning_F3": float(row["planning_F3"]),
                "replay_F1": float(row["replay_F1"]),
                "replay_F2": float(row["replay_F2"]),
                "replay_F3": float(row["replay_F3"]),
                "replay_minus_planning_F1": float(row["replay_minus_planning_F1"]),
                "replay_minus_planning_F2": float(row["replay_minus_planning_F2"]),
                "replay_minus_planning_F3": float(row["replay_minus_planning_F3"]),
            }
        )
    return sorted(table, key=lambda entry: entry["run_key"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize a replay table with one vote per run.",
    )
    parser.add_argument(
        "--replay-results",
        default="outputs/claude_v2/pilot_common_execution/replay_results.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/claude_v2/pilot_common_execution/summary",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
