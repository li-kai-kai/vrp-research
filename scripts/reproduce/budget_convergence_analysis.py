"""Paired budget checks on one physical case, using fixed comparison frames.

Search progress is evaluated in each planning model separately. Decision
value is evaluated in the shared Full environment. All budgets enter their
respective reference frames together; budget-specific normalizations would
make an apparent convergence curve uninterpretable.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import math
from pathlib import Path
import statistics
import sys
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dataclasses import dataclass
import csv
import json
from tempfile import TemporaryDirectory

from scripts.reproduce.common_execution_analysis import analyze as analyze_common, LABELS, FULL_MODEL
from scripts.reproduce.solution_io import RunStore

EXPECTED_MODELS = tuple(LABELS)
MODEL_NAMES = LABELS
ANALYSIS_SOURCES = (
    "scripts/reproduce/common_execution_analysis.py",
    "scripts/reproduce/replay_solutions.py",
    "scripts/reproduce/service_diagnostics.py",
    "scripts/reproduce/mechanism_applicability.py",
    "scripts/reproduce/mechanism_zone_search.py",
)

@dataclass
class ReplayedRun:
    record: dict
    rows: list[dict]
    representative: dict
    group: tuple


def identity(run):
    record = run.record
    return {**{k: record[k] for k in ("run_key", "case_id", "instance_seed", "solver_seed", "solver_repeat", "model_id", "physical_instance_hash")},
            "scenario_family": record.get("scenario_family", "benchmark"),
            "zone": record.get("zone", "original"), "planning_model": LABELS[record["model_id"]]}


def objective(row, prefix):
    return tuple(float(row[f"{prefix}_F{i}"]) for i in (1, 2, 3))


def front_rows(run, space, front):
    return [{**identity(run), "max_evaluations": run.record["budget"]["max_evaluations"],
             "evaluation_space": space, "point_index": index,
             **{f"F{i+1}": value for i, value in enumerate(point)}} for index, point in enumerate(front)]


def _validate_group(runs, models):
    slots = defaultdict(list)
    for run in runs:
        slots[(run.record["solver_seed"], run.record["solver_repeat"])].append(run.record["model_id"])
    if any(len(v) != len(models) or set(v) != set(models) for v in slots.values()):
        raise ValueError("missing or duplicate planning model in paired block")


def _read_rows(path):
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key, value in row.items():
            if value in ("True", "False"):
                row[key] = value == "True"
            elif value == "":
                row[key] = None
            else:
                try:
                    row[key] = float(value) if any(c in value.lower() for c in (".", "e")) else int(value)
                except ValueError:
                    pass
    return rows


def collect_runs(input_roots):
    # Reuse the existing validated collector once per budget. Its per-budget
    # indicators are discarded; only replay rows and audited traces are reused.
    roots_by_budget = defaultdict(list)
    records_by_root = {}
    for root in map(Path, input_roots):
        records = RunStore(root).load_runs_for_experiment()
        levels = {r["budget"]["max_evaluations"] for r in records}
        if len(levels) != 1:
            raise ValueError("each RunStore must have one nonempty budget")
        roots_by_budget[next(iter(levels))].append(root)
        records_by_root[root] = records
    result, contexts = [], {}
    with TemporaryDirectory(prefix="vrp_budget_replay_") as temporary:
        for budget, roots in sorted(roots_by_budget.items()):
            out = Path(temporary) / str(budget)
            manifest = analyze_common(roots, out, representative_traces=True)
            replay = _read_rows(out / "replay_results.csv")
            periods = _read_rows(out / "representative_periods.csv")
            demands = _read_rows(out / "representative_demand_periods.csv")
            for root in roots:
                for record in records_by_root[root]:
                    key = record["run_key"]
                    if key in contexts:
                        raise ValueError("duplicate input run")
                    rows = [r for r in replay if r["run_key"] == key]
                    for row in rows:
                        row["planning_self_replay_max_abs_error"] = max(manifest["self_replay_max_abs_error"])
                    representative = next(r for r in rows if r["decision_hash"] == record["decision_hash"])
                    group = (record["case_id"], record.get("scenario_family", "benchmark"), record.get("zone", "original"))
                    result.append(ReplayedRun(record, rows, representative, group))
                    contexts[key] = (root, [r for r in periods if r["run_key"] == key],
                                     [r for r in demands if r["run_key"] == key], manifest)
    return result, contexts


def representative_traces(runs, contexts):
    periods, demands = [], []
    for run in runs:
        _, p, d, _ = contexts[run.record["run_key"]]
        periods.extend({**r, "planning_model": r["model"], "period_end_hours": r["end_hours"]} for r in p)
        demands.extend({**r, "planning_model": r["model"], "demand_node": r["demand"]} for r in d)
    return periods, demands

from scripts.reproduce.objective_precision import V2_PRECISION, safe_ratio
from scripts.reproduce.run_benchmark import _non_dominated, pooled_quality_indicators
from scripts.reproduce.run_model_ablation import ABLATION_SOURCE_FILES
from scripts.reproduce.solution_io import (
    canonical_json,
    code_environment,
    source_hashes,
    write_csv_atomic,
    write_json_atomic,
)

SOURCE_FILES = tuple(dict.fromkeys((
    *ABLATION_SOURCE_FILES, *ANALYSIS_SOURCES,
    "scripts/reproduce/budget_convergence_analysis.py",
)))
QUALITY_TIE_TOLERANCE = 1e-12


def validate_design(runs: list[ReplayedRun], protocol: dict) -> list[int]:
    """Allow only max_evaluations to change in the paired single-case design."""
    if not runs:
        raise ValueError("no budget runs")
    if set(protocol["model_ids"]) != set(EXPECTED_MODELS):
        raise ValueError("the protocol must include the four planning models")
    if len({r.record["run_key"] for r in runs}) != len(runs):
        raise ValueError("duplicate input run")
    for field in ("case_id", "instance_seed", "physical_instance_hash", "algorithm", "source_fingerprint"):
        values = {r.record[field] for r in runs}
        if len(values) != 1:
            raise ValueError(f"budget runs disagree on {field}")
        if field in protocol and next(iter(values)) != protocol[field]:
            raise ValueError(f"run {field} differs from the frozen protocol")
    if len({r.group for r in runs}) != 1:
        raise ValueError("budget checks require one scenario group")
    other_budgets = {
        canonical_json({k: v for k, v in r.record["budget"].items() if k != "max_evaluations"})
        for r in runs
    }
    if len(other_budgets) != 1:
        raise ValueError("only max_evaluations may change across budgets")
    if any(r.record["budget"]["pop_size"] != protocol["pop_size"] for r in runs):
        raise ValueError("population differs from the frozen protocol")
    levels: dict[int, list[ReplayedRun]] = defaultdict(list)
    for run in runs:
        limit = run.record["budget"]["max_evaluations"]
        if run.record["evaluations"] != limit or run.record["termination_reason"] != "budget_exhausted":
            raise ValueError("a budget run did not exhaust its declared evaluation allowance")
        levels[limit].append(run)
    initial = set(protocol["initial_budgets"])
    allowed = initial | {protocol["plateau_screen"]["confirmation_budget"]}
    if len(levels) < 2 or not initial <= set(levels) or not set(levels) <= allowed:
        raise ValueError("missing initial budget or undeclared extra budget")
    seeds = protocol["solver_seeds"]
    if len(set(seeds)) != len(seeds) or len(seeds) != protocol["solver_repeats"]:
        raise ValueError("invalid paired seeds in protocol")
    expected_blocks = {(seed, index + protocol.get("solver_repeat_start", 0)) for index, seed in enumerate(seeds)}
    for members in levels.values():
        _validate_group(members, EXPECTED_MODELS)
        actual = {(r.record["solver_seed"], r.record["solver_repeat"]) for r in members}
        if actual != expected_blocks:
            raise ValueError("paired solver blocks differ from the protocol")
    for model in EXPECTED_MODELS:
        if len({r.record["model_fingerprint"] for r in runs if r.record["model_id"] == model}) != 1:
            raise ValueError("a planning model changed between budgets")
    if len({row["execution_model_fingerprint"] for run in runs for row in run.rows}) != 1:
        raise ValueError("budgets do not share one Full execution environment")
    screen = protocol["plateau_screen"]
    if screen["pairs_per_model"] != len(seeds):
        raise ValueError("plateau screen has the wrong number of paired repeats")
    if not 1 <= screen["minimum_small_change_pairs"] <= len(seeds):
        raise ValueError("invalid minimum number of small-change pairs")
    for name in ("hv_relative_change_tolerance", "igd_absolute_change_tolerance"):
        if not math.isfinite(screen[name]) or screen[name] < 0:
            raise ValueError("screen tolerances must be finite and nonnegative")
    return sorted(levels)


def analyze_budgets(runs: list[ReplayedRun], protocol: dict) -> dict[str, Any]:
    budgets = validate_design(runs, protocol)
    runs = sorted(runs, key=lambda r: (
        r.record["budget"]["max_evaluations"], r.record["solver_seed"], r.record["model_id"]
    ))
    planning_fronts = {
        r.record["run_key"]: _non_dominated([objective(row, "planning") for row in r.rows], V2_PRECISION)
        for r in runs
    }
    execution_fronts = {
        r.record["run_key"]: _non_dominated([objective(row, "replay") for row in r.rows], V2_PRECISION)
        for r in runs
    }
    planning_quality, reference_metadata = {}, []
    for model in EXPECTED_MODELS:
        members = [r for r in runs if r.record["model_id"] == model]
        quality, metadata = pooled_quality_indicators(
            [planning_fronts[r.record["run_key"]] for r in members], V2_PRECISION
        )
        planning_quality.update({r.record["run_key"]: q for r, q in zip(members, quality)})
        reference_metadata.append({
            "evaluation_space": "planning", "planning_model": MODEL_NAMES[model],
            "budgets": budgets, "included_runs": len(members), **metadata,
        })
    execution_quality, metadata = pooled_quality_indicators(
        [execution_fronts[r.record["run_key"]] for r in runs], V2_PRECISION
    )
    reference_metadata.append({
        "evaluation_space": "execution", "planning_model": "all", "budgets": budgets,
        "included_runs": len(runs), **metadata,
    })
    reused = {r["run_key"] for r in protocol.get("reused_runs", [])}
    run_rows, planning_rows, execution_rows = [], [], []
    for run, executed_quality in zip(runs, execution_quality):
        record, representative = run.record, run.representative
        key = record["run_key"]
        run_rows.append({
            **identity(run), "max_evaluations": record["budget"]["max_evaluations"],
            "evaluations": record["evaluations"], "runtime_seconds": record["runtime_seconds"],
            "termination_reason": record["termination_reason"], "reused_from_pilot": key in reused,
            "saved_decisions": len(run.rows), "planning_front_size": len(planning_fronts[key]),
            "execution_front_size": len(execution_fronts[key]),
            **{f"planning_{k}": v for k, v in planning_quality[key].items()},
            **{f"execution_{k}": v for k, v in executed_quality.items()},
            "representative_decision_hash": representative["decision_hash"],
            **{f"representative_planning_F{i}": representative[f"planning_F{i}"] for i in (1, 2, 3)},
            **{f"representative_execution_F{i}": representative[f"replay_F{i}"] for i in (1, 2, 3)},
            "execution_min_satisfaction": representative["replay_final_min_satisfaction"],
            "execution_total_satisfaction": representative["replay_final_total_satisfaction"],
            "execution_zero_service_ratio": representative["replay_zero_service_ratio"],
            "execution_remaining_supply": representative["replay_remaining_supply"],
        })
        planning_rows.extend(front_rows(run, "planning", planning_fronts[key]))
        execution_rows.extend(front_rows(run, "replay", execution_fronts[key]))
    step_pairs = budget_step_pairs(run_rows, budgets, protocol["plateau_screen"])
    step_summary = summarize_steps(step_pairs, protocol["plateau_screen"])
    model_pairs = model_comparisons(run_rows)
    return {
        "run_quality": run_rows, "budget_summary": summarize_runs(run_rows),
        "budget_pairs": step_pairs, "step_summary": step_summary,
        "model_pairs": model_pairs, "model_summary": summarize_models(model_pairs),
        "planning_fronts": planning_rows, "execution_fronts": execution_rows,
        "reference_metadata": reference_metadata,
        "budget_decision": budget_decision(step_summary, budgets, protocol),
    }


def budget_step_pairs(rows: list[dict], budgets: list[int], screen: dict) -> list[dict]:
    grouped = defaultdict(dict)
    for row in rows:
        grouped[(row["model_id"], row["solver_seed"], row["solver_repeat"])][row["max_evaluations"]] = row
    pairs = []
    for (model, seed, repeat), levels in sorted(grouped.items()):
        for low_budget, high_budget in zip(budgets, budgets[1:]):
            low, high = levels[low_budget], levels[high_budget]
            entry = {
                "planning_model": MODEL_NAMES[model], "model_id": model,
                "solver_seed": seed, "solver_repeat": repeat,
                "low_budget": low_budget, "high_budget": high_budget,
                "low_run_key": low["run_key"], "high_run_key": high["run_key"],
            }
            for space in ("planning", "execution"):
                hv_gain = high[f"{space}_hypervolume"] - low[f"{space}_hypervolume"]
                entry[f"{space}_hv_gain"] = hv_gain
                entry[f"{space}_relative_hv_gain"] = safe_ratio(hv_gain, abs(low[f"{space}_hypervolume"]))
                entry[f"{space}_igd_gain"] = low[f"{space}_igd"] - high[f"{space}_igd"]
                for i in (1, 2, 3):
                    key = f"representative_{space}_F{i}"
                    entry[f"{key}_change"] = high[key] - low[key]
            entry["execution_min_satisfaction_change"] = high["execution_min_satisfaction"] - low["execution_min_satisfaction"]
            entry["execution_zero_service_ratio_change"] = high["execution_zero_service_ratio"] - low["execution_zero_service_ratio"]
            entry["runtime_ratio"] = safe_ratio(high["runtime_seconds"], low["runtime_seconds"])
            relative = entry["planning_relative_hv_gain"]
            entry["small_planning_change"] = (
                relative is not None and abs(relative) <= screen["hv_relative_change_tolerance"]
                and abs(entry["planning_igd_gain"]) <= screen["igd_absolute_change_tolerance"]
            )
            pairs.append(entry)
    return pairs


def _descriptive(entry: dict, rows: list[dict], fields: tuple[str, ...]) -> None:
    for field in fields:
        values = [r[field] for r in rows if r[field] is not None]
        for label, function in (("mean", statistics.fmean), ("median", statistics.median), ("min", min), ("max", max)):
            entry[f"{label}_{field}"] = function(values) if values else None


def summarize_runs(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["max_evaluations"], row["planning_model"])].append(row)
    result = []
    for (budget, model), members in sorted(groups.items()):
        entry = {"max_evaluations": budget, "planning_model": model, "solver_runs": len(members)}
        _descriptive(entry, members, (
            "planning_hypervolume", "planning_igd", "execution_hypervolume", "execution_igd",
            "runtime_seconds", "execution_front_size", "execution_min_satisfaction",
            "execution_zero_service_ratio", "representative_execution_F1", "representative_execution_F2",
        ))
        result.append(entry)
    return result


def summarize_steps(rows: list[dict], screen: dict) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["low_budget"], row["high_budget"], row["planning_model"])].append(row)
    result = []
    for (low, high, model), members in sorted(groups.items()):
        if len(members) != screen["pairs_per_model"]:
            raise ValueError("incomplete paired budget step")
        count = sum(r["small_planning_change"] for r in members)
        entry = {
            "low_budget": low, "high_budget": high, "planning_model": model,
            "solver_pairs": len(members), "small_change_pairs": count,
            "required_small_pairs": screen["minimum_small_change_pairs"],
            "planning_plateau_screen": count >= screen["minimum_small_change_pairs"],
        }
        _descriptive(entry, members, (
            "planning_hv_gain", "planning_relative_hv_gain", "planning_igd_gain",
            "execution_hv_gain", "execution_relative_hv_gain", "execution_igd_gain",
            "execution_min_satisfaction_change", "runtime_ratio",
        ))
        result.append(entry)
    return result


def budget_decision(steps: list[dict], budgets: list[int], protocol: dict) -> dict:
    flags = []
    for low, high in zip(budgets, budgets[1:]):
        rows = [r for r in steps if r["low_budget"] == low and r["high_budget"] == high]
        passed = sorted(r["planning_model"] for r in rows if r["planning_plateau_screen"])
        flags.append({"low_budget": low, "high_budget": high, "passed_models": passed,
                      "all_models_small": len(passed) == len(EXPECTED_MODELS)})
    confirm = protocol["plateau_screen"]["confirmation_budget"]
    initial_max = max(protocol["initial_budgets"])
    last = flags[-1]
    confirmation_required = last["all_models_small"] and budgets[-1] == initial_max and confirm not in budgets
    plateau = len(flags) >= 2 and all(r["all_models_small"] for r in flags[-2:])
    status = (
        "candidate_needs_confirmation" if confirmation_required
        else "empirical_plateau_subject_to_service_review" if plateau
        else "one_small_step_is_insufficient" if last["all_models_small"]
        else "no_common_plateau_in_tested_range"
    )
    return {
        "status": status, "steps": flags, "confirmation_required": confirmation_required,
        "confirmation_budget": confirm,
        "candidate_budget": budgets[-2] if plateau and not confirmation_required else None,
        "tested_budgets": budgets,
        "interpretation": "Predeclared descriptive search-stability screen, not a proof of optimality. Review service outcomes separately; model wins do not enter this screen.",
    }


def _direction(value: float) -> str:
    if abs(value) <= QUALITY_TIE_TOLERANCE:
        return "equal"
    return "Full" if value > 0 else "reduced"


def model_comparisons(rows: list[dict]) -> list[dict]:
    groups = defaultdict(dict)
    for row in rows:
        groups[(row["max_evaluations"], row["solver_seed"], row["solver_repeat"])][row["model_id"]] = row
    result = []
    for (budget, seed, repeat), models in sorted(groups.items()):
        full = models[FULL_MODEL]
        full_obj = tuple(full[f"representative_execution_F{i}"] for i in (1, 2, 3))
        for model in EXPECTED_MODELS:
            if model == FULL_MODEL:
                continue
            reduced = models[model]
            reduced_obj = tuple(reduced[f"representative_execution_F{i}"] for i in (1, 2, 3))
            hv = full["execution_hypervolume"] - reduced["execution_hypervolume"]
            igd = reduced["execution_igd"] - full["execution_igd"]
            relation = (
                "Full_dominates" if V2_PRECISION.dominates(full_obj, reduced_obj)
                else "reduced_dominates" if V2_PRECISION.dominates(reduced_obj, full_obj)
                else "equal" if V2_PRECISION.equivalent(full_obj, reduced_obj) else "tradeoff"
            )
            result.append({
                "max_evaluations": budget, "solver_seed": seed, "solver_repeat": repeat,
                "reduced_model": MODEL_NAMES[model],
                "full_run_key": full["run_key"], "reduced_run_key": reduced["run_key"],
                "full_hv_advantage": hv, "full_igd_advantage": igd,
                "hv_preferred_model": _direction(hv), "igd_preferred_model": _direction(igd),
                "representative_relation": relation,
                **{f"representative_reduced_minus_full_F{i+1}": b - a for i, (a, b) in enumerate(zip(full_obj, reduced_obj))},
            })
    return result


def summarize_models(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["max_evaluations"], row["reduced_model"])].append(row)
    result = []
    for (budget, model), members in sorted(groups.items()):
        entry = {"max_evaluations": budget, "reduced_model": model, "solver_pairs": len(members)}
        _descriptive(entry, members, ("full_hv_advantage", "full_igd_advantage"))
        for indicator in ("hv", "igd"):
            for direction in ("Full", "reduced", "equal"):
                entry[f"{indicator}_{direction}_pairs"] = sum(r[f"{indicator}_preferred_model"] == direction for r in members)
        for relation in ("Full_dominates", "reduced_dominates", "equal", "tradeoff"):
            entry[f"representative_{relation}_pairs"] = sum(r["representative_relation"] == relation for r in members)
        result.append(entry)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-roots", type=Path, nargs="+", required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--representative-traces", action="store_true")
    args = parser.parse_args()
    import hashlib
    import json

    protocol = json.loads(args.protocol.read_text())
    runs, contexts = collect_runs(args.input_roots)
    result = analyze_budgets(runs, protocol)
    if args.representative_traces:
        periods, demands = representative_traces(runs, contexts)
        budgets = {r.record["run_key"]: r.record["budget"]["max_evaluations"] for r in runs}
        result["representative_periods"] = [{"max_evaluations": budgets[r["run_key"]], **r} for r in periods]
        result["representative_demand_periods"] = [{"max_evaluations": budgets[r["run_key"]], **r} for r in demands]
    replay_rows = [
        {
            "max_evaluations": run.record["budget"]["max_evaluations"],
            "model_id": run.record["model_id"], **row,
        } for run in runs for row in run.rows
    ]
    result["replay_results"] = replay_rows
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in result.items():
        if name in ("reference_metadata", "budget_decision"):
            write_json_atomic(args.output_dir / f"{name}.json", data)
        else:
            write_csv_atomic(args.output_dir / f"{name}.csv", data, list(data[0]) if data else None)
    write_json_atomic(args.output_dir / "analysis_manifest.json", {
        "code": code_environment(), "source_hashes": source_hashes(Path(__file__).resolve().parents[2], SOURCE_FILES),
        "protocol": protocol, "protocol_sha256": hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        "input_roots": [str(p) for p in args.input_roots],
        "input_runs": [{"root": str(contexts[r.record["run_key"]][0]), "run_key": r.record["run_key"], "record_sha256": r.record["record_sha256"]} for r in runs],
        "runs": len(runs), "budgets": result["budget_decision"]["tested_budgets"],
        "actual_evaluations": sum(r.record["evaluations"] for r in runs),
        "replayed_decisions": len(replay_rows), "replay_failures": 0,
        "identity_checked_decisions": sum(r["identity_checked"] for r in replay_rows),
        "max_abs_identity_error": max((abs(r[f"replay_minus_planning_F{i}"]) for r in replay_rows if r["identity_checked"] for i in (1, 2, 3)), default=0.0),
        "max_abs_planning_self_replay_error": max(r["planning_self_replay_max_abs_error"] for r in replay_rows),
        "quality_reference": "Fixed across all included budgets. Planning frames separate by model; Full execution frame shared by all models.",
        "runtime_scope": protocol.get("runtime_scope", "Descriptive runtime; see protocol for search reuse and scheduling."),
        "validated_input_hashes": {key: value for ctx in contexts.values() for key, value in ctx[3]["input_record_hashes"].items()},
        "scope": "Five paired search repeats on one WEN38 case, no independent-network or statistical-significance claim.",
    })
    print(f"Analyzed {len(runs)} runs; budget decision: {result['budget_decision']['status']} -> {args.output_dir}")


if __name__ == "__main__":
    main()
