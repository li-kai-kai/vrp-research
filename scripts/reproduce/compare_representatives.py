"""Compare representative selection before and after the resolution change.

Three different questions, reported separately because they have different
evidentiary weight:

``post_hoc``
    Take the *stored* front from the old run and re-select its representative
    under the new resolution rule. Nothing is re-evaluated, so this shows only
    how much of the change was a reporting artefact.

``researched``
    The new run searched with the new rule in force, so its front is different
    from the old one. This is what the corrected pipeline actually reports.

``front_size``
    How many points each front kept, since quantizing merges sub-resolution
    distinctions and a smaller front is the expected consequence.

Runs are matched on their semantic identity (case, instance seed, algorithm,
solver seed and repeat), not on the run key, because the run key includes the
source fingerprint and therefore changes whenever the code does.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ == "" or __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.benchmark_algorithms import _representative_key
from scripts.reproduce.capacity_recovery import CapacityIndividual
from scripts.reproduce.objective_precision import (
    EXACT_PRECISION,
    V2_PRECISION,
)
from scripts.reproduce.solution_io import (
    RunStore,
    decision_hash,
    write_csv_atomic,
    write_json_atomic,
)


IDENTITY_FIELDS = ("case_id", "instance_seed", "algorithm", "solver_seed", "solver_repeat")


def main() -> None:
    args = _parse_args()
    old_root = Path(args.old_root)
    new_root = Path(args.new_root)
    if not old_root.is_dir() or not new_root.is_dir():
        raise SystemExit("both --old-root and --new-root must be existing directories")

    old_by_identity = {_identity(record): record for record in RunStore(old_root).load_all_runs()}
    new_by_identity = {_identity(record): record for record in RunStore(new_root).load_all_runs()}
    if not old_by_identity or not new_by_identity:
        raise SystemExit("one of the run sets is empty")

    rows: list[dict[str, Any]] = []
    for identity in sorted(set(old_by_identity) & set(new_by_identity), key=str):
        rows.append(_compare(old_by_identity[identity], new_by_identity[identity]))

    missing_new = sorted(set(old_by_identity) - set(new_by_identity), key=str)
    missing_old = sorted(set(new_by_identity) - set(old_by_identity), key=str)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(output_dir / "representative_comparison.csv", rows, list(rows[0]))
    write_json_atomic(
        output_dir / "representative_summary.json",
        {
            "old_root": str(old_root),
            "new_root": str(new_root),
            "runs_compared": len(rows),
            "stored_representative_changed": sum(
                1 for row in rows if row["stored_representative_changed"]
            ),
            "exact_rule_vs_v2_rule_on_old_front_changed": sum(
                1 for row in rows if row["post_hoc_changed"]
            ),
            "researched_representative_changed": sum(
                1 for row in rows if row["researched_changed"]
            ),
            "front_size_shrank": sum(
                1 for row in rows if row["new_front_size"] < row["old_front_size"]
            ),
            "runs_only_in_old": [list(entry) for entry in missing_new],
            "runs_only_in_new": [list(entry) for entry in missing_old],
        },
    )
    print(f"Compared {len(rows)} matched runs -> {output_dir}")


def _identity(record: dict[str, Any]) -> tuple:
    return tuple(record.get(field) for field in IDENTITY_FIELDS)


def _compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_front = _rebuild_front(old)
    new_front = _rebuild_front(new)

    # Post-hoc: the stored front, re-selected under the new rule only.
    old_representative = _select(old_front, EXACT_PRECISION)
    post_hoc_representative = _select(old_front, V2_PRECISION)
    researched_representative = _select(new_front, V2_PRECISION)

    # What each run actually reported, as stored. This is the clean
    # run-to-run comparison; the rule comparisons below answer a different
    # question (how much the resolution rule alone moves the choice).
    stored_old = old.get("decision_hash")
    stored_new = new.get("decision_hash")

    return {
        **{field: old.get(field) for field in IDENTITY_FIELDS},
        "old_run_key": old["run_key"],
        "new_run_key": new["run_key"],
        "stored_representative_hash_old": stored_old,
        "stored_representative_hash_new": stored_new,
        "stored_representative_changed": stored_old != stored_new,
        "stored_objectives_old": list(old.get("objectives") or []),
        "stored_objectives_new": list(new.get("objectives") or []),
        "old_front_size": len(old_front),
        "new_front_size": len(new_front),
        "old_representative_hash": old_representative,
        "post_hoc_representative_hash": post_hoc_representative,
        "researched_representative_hash": researched_representative,
        "post_hoc_changed": post_hoc_representative != old_representative,
        "researched_changed": researched_representative != old_representative,
        "old_objectives": _objectives_of(old_front, old_representative),
        "post_hoc_objectives": _objectives_of(old_front, post_hoc_representative),
        "researched_objectives": _objectives_of(new_front, researched_representative),
    }


def _rebuild_front(record: dict[str, Any]) -> list[CapacityIndividual]:
    """Stored decisions with their stored objectives, as individuals.

    The instance is not needed: the objectives are read from the record, which
    is exactly what makes this a post-hoc re-selection rather than a re-run.
    """
    front: list[CapacityIndividual] = []
    for solution in record.get("pareto_front") or []:
        decision = solution["decision"]
        front.append(
            CapacityIndividual(
                repair_order=list(decision["repair_order"]),
                team_assignment=list(decision["team_assignment"]),
                dispatch_priority=[
                    (int(pair[0]), int(pair[1])) for pair in decision["dispatch_priority"]
                ],
                objectives=tuple(float(value) for value in solution["objectives"]),
            )
        )
    return front


def _select(front: list[CapacityIndividual], precision) -> str | None:
    if not front:
        return None
    winner = min(front, key=lambda item: _representative_key(item, precision))
    return decision_hash(winner)


def _objectives_of(front: list[CapacityIndividual], wanted: str | None):
    for individual in front:
        if decision_hash(individual) == wanted:
            return list(individual.objectives or ())
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare representative selection across a resolution change.",
    )
    parser.add_argument("--old-root", required=True)
    parser.add_argument("--new-root", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
