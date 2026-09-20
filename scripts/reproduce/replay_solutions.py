"""Re-evaluate stored decisions and report planning-versus-execution gaps.

Two execution models are supported:

``saved``
    Rebuild the exact instance and evaluation configuration a run was planned
    with, clear the cached objectives, and call the shared evaluator again.
    Any difference is a real reproducibility failure, not a model effect.

``full``
    Rebuild the common execution environment (v2 semantics, progressive
    recovery, heterogeneous vehicle thresholds, edge-capacity throughput) from
    the shared physical scenario and evaluate each saved planning decision in
    it. This is a unified replay of encoded decisions and priority policies: the
    executor regenerates vehicle types, routes and tonnages. It is not a
    verification that a fixed per-vehicle route plan stays unchanged.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.capacity_recovery import (
    CapacityExperimentInstance,
    EvaluationConfig,
    evaluate_capacity_solution_detailed,
)
from scripts.reproduce.solution_io import (
    RunStore,
    SolutionIOError,
    decision_from_json,
    physical_instance_hash,
    write_csv_atomic,
    write_json_atomic,
)


EXECUTION_MODELS = ("saved", "full")

DEFAULT_ABS_TOLERANCE = 1e-8
DEFAULT_REL_TOLERANCE = 1e-8

REPLAY_COLUMNS = (
    "run_key",
    "solution_id",
    "physical_instance_hash",
    "planning_model",
    "planning_model_fingerprint",
    "execution_model",
    "execution_model_fingerprint",
    "instance_seed",
    "solver_seed",
    "algorithm",
    "decision_hash",
    "planning_F1",
    "planning_F2",
    "planning_F3",
    "replay_F1",
    "replay_F2",
    "replay_F3",
    "replay_minus_planning_F1",
    "replay_minus_planning_F2",
    "replay_minus_planning_F3",
    "replay_final_total_satisfaction",
    "replay_final_min_satisfaction",
    "replay_zero_service_ratio",
    "replay_remaining_supply",
    "representative_selected_before_replay",
    "replay_success",
    "replay_error",
)


def main() -> None:
    args = _parse_args()
    input_root = Path(args.input_root)
    if not input_root.is_dir():
        raise SystemExit(f"input root does not exist: {input_root}")
    store = RunStore(input_root)
    records = store.load_all_runs()
    if not records:
        raise SystemExit(f"no complete run records found under {input_root}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    execution_cache: dict[str, CapacityExperimentInstance] = {}
    planning_cache: dict[str, CapacityExperimentInstance] = {}
    failures = 0

    for record in records:
        instance_file = record.get("instance_file")
        if not instance_file:
            raise SystemExit(
                f"run {record['run_key']} has no instance snapshot reference; "
                "it was written by an older format and cannot be replayed"
            )
        physical_hash = str(record["physical_instance_hash"])

        if args.execution_model == "saved":
            if instance_file not in planning_cache:
                planning_cache[instance_file] = store.load_instance(instance_file)
            execution_instance = planning_cache[instance_file]
        else:
            if physical_hash not in execution_cache:
                execution_cache[physical_hash] = store.load_execution_instance(physical_hash)
            execution_instance = execution_cache[physical_hash]
            expected = physical_instance_hash(execution_instance)
            if expected != physical_hash:
                raise SystemExit(
                    f"execution environment for {physical_hash} has physical hash "
                    f"{expected}; refusing to replay across physical scenarios"
                )

        for solution in record.get("pareto_front") or []:
            rows.append(
                _replay_solution(
                    record=record,
                    solution=solution,
                    execution_instance=execution_instance,
                    execution_model=args.execution_model,
                    abs_tolerance=args.abs_tolerance,
                    rel_tolerance=args.rel_tolerance,
                )
            )
            if not rows[-1]["replay_success"]:
                failures += 1

    write_csv_atomic(output_dir / "replay_results.csv", rows, list(REPLAY_COLUMNS))
    summary = _summarize(rows, args)
    write_json_atomic(output_dir / "replay_summary.json", summary)
    print(
        f"Replayed {len(rows)} solutions from {len(records)} runs "
        f"({failures} failures) -> {output_dir}"
    )
    if failures:
        # A mismatch is reported, never rounded away: the exit status is
        # non-zero so an automated caller cannot treat it as a clean replay.
        raise SystemExit(f"{failures} solution(s) failed to reproduce their stored objectives")


def _replay_solution(
    *,
    record: dict[str, Any],
    solution: dict[str, Any],
    execution_instance: CapacityExperimentInstance,
    execution_model: str,
    abs_tolerance: float,
    rel_tolerance: float,
) -> dict[str, Any]:
    planning_objectives = [float(value) for value in solution["objectives"]]
    row: dict[str, Any] = {
        "run_key": record["run_key"],
        "solution_id": solution["solution_id"],
        "physical_instance_hash": record["physical_instance_hash"],
        "planning_model": (record.get("evaluation") or {}).get("model_version"),
        "planning_model_fingerprint": record["model_fingerprint"],
        "execution_model": execution_model,
        "execution_model_fingerprint": None,
        "instance_seed": record["instance_seed"],
        "solver_seed": record["solver_seed"],
        "algorithm": record["algorithm"],
        "decision_hash": solution["decision_hash"],
        "planning_F1": planning_objectives[0],
        "planning_F2": planning_objectives[1],
        "planning_F3": planning_objectives[2],
        "replay_F1": None,
        "replay_F2": None,
        "replay_F3": None,
        "replay_minus_planning_F1": None,
        "replay_minus_planning_F2": None,
        "replay_minus_planning_F3": None,
        "replay_final_total_satisfaction": None,
        "replay_final_min_satisfaction": None,
        "replay_zero_service_ratio": None,
        "replay_remaining_supply": None,
        "representative_selected_before_replay": (
            solution["decision_hash"] == record.get("decision_hash")
        ),
        "replay_success": False,
        "replay_error": None,
    }
    try:
        # A clean individual with no cached objectives: the replay must go
        # through the shared evaluator rather than reuse stored numbers.
        decision = decision_from_json(solution["decision"], execution_instance)
        outcome = evaluate_capacity_solution_detailed(execution_instance, decision)
        replay_objectives = list(outcome.objectives)
        row["execution_model_fingerprint"] = _instance_model_fingerprint(execution_instance)
        row["replay_F1"] = replay_objectives[0]
        row["replay_F2"] = replay_objectives[1]
        row["replay_F3"] = replay_objectives[2]
        row["replay_minus_planning_F1"] = replay_objectives[0] - planning_objectives[0]
        row["replay_minus_planning_F2"] = replay_objectives[1] - planning_objectives[1]
        row["replay_minus_planning_F3"] = replay_objectives[2] - planning_objectives[2]
        row["replay_final_total_satisfaction"] = outcome.metrics["final_total_satisfaction"]
        row["replay_final_min_satisfaction"] = outcome.metrics["final_min_satisfaction"]
        row["replay_zero_service_ratio"] = outcome.metrics["zero_service_ratio"]
        row["replay_remaining_supply"] = outcome.metrics["remaining_supply"]
        if execution_model == "saved":
            row["replay_success"] = all(
                _close(planned, replayed, abs_tolerance, rel_tolerance)
                for planned, replayed in zip(planning_objectives, replay_objectives)
            )
        else:
            # Under a different execution model the objectives are expected to
            # move; the replay itself succeeded if it produced finite numbers.
            row["replay_success"] = all(math.isfinite(value) for value in replay_objectives)
    except (SolutionIOError, ValueError, KeyError) as error:
        row["replay_error"] = f"{type(error).__name__}: {error}"
    return row


def _instance_model_fingerprint(instance: CapacityExperimentInstance) -> str:
    from scripts.reproduce.solution_io import model_fingerprint

    return model_fingerprint(instance)


def _close(planned: float, replayed: float, abs_tolerance: float, rel_tolerance: float) -> bool:
    if math.isnan(planned) or math.isnan(replayed):
        return False
    if planned == replayed:
        return True
    return abs(planned - replayed) <= max(
        abs_tolerance,
        rel_tolerance * max(abs(planned), abs(replayed)),
    )


def _summarize(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    finite_rows = [
        row
        for row in rows
        if row["replay_minus_planning_F1"] is not None
        and all(
            math.isfinite(row[field])
            for field in (
                "replay_minus_planning_F1",
                "replay_minus_planning_F2",
                "replay_minus_planning_F3",
            )
        )
    ]
    summary: dict[str, Any] = {
        "input_root": str(args.input_root),
        "output_dir": str(args.output_dir),
        "execution_model": args.execution_model,
        "solutions": len(rows),
        "failures": sum(1 for row in rows if not row["replay_success"]),
        "abs_tolerance": args.abs_tolerance,
        "rel_tolerance": args.rel_tolerance,
    }
    if args.execution_model == "saved":
        summary["max_abs_error_F1"] = max(
            (abs(row["replay_minus_planning_F1"]) for row in finite_rows),
            default=None,
        )
        summary["max_abs_error_F2"] = max(
            (abs(row["replay_minus_planning_F2"]) for row in finite_rows),
            default=None,
        )
        summary["max_abs_error_F3"] = max(
            (abs(row["replay_minus_planning_F3"]) for row in finite_rows),
            default=None,
        )
        # A zero planned value has no percentage. Those rows are reported as
        # missing rather than being divided by an epsilon and inflated.
        ratios = [
            abs(row["replay_minus_planning_F1"]) / abs(row["planning_F1"])
            for row in finite_rows
            if abs(row["planning_F1"]) > 0.0
        ]
        summary["max_rel_error_F1"] = max(ratios, default=None)
        summary["max_rel_error_F1_missing_rows"] = len(finite_rows) - len(ratios)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay stored capacity-recovery decisions.",
    )
    parser.add_argument("--input-root", required=True, help="Directory written by a run entry point.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--execution-model",
        choices=list(EXECUTION_MODELS),
        default="saved",
        help=(
            "saved: re-evaluate in the planning model (must reproduce exactly). "
            "full: re-evaluate every planning decision in the shared v2 execution "
            "environment with progressive recovery, heterogeneous thresholds and "
            "edge-capacity throughput."
        ),
    )
    parser.add_argument("--abs-tolerance", type=float, default=DEFAULT_ABS_TOLERANCE)
    parser.add_argument("--rel-tolerance", type=float, default=DEFAULT_REL_TOLERANCE)
    args = parser.parse_args()
    if args.abs_tolerance < 0 or args.rel_tolerance < 0:
        parser.error("tolerances must be non-negative")
    return args


if __name__ == "__main__":
    main()
