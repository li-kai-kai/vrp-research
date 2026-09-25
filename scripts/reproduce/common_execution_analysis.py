"""Paired descriptive comparisons in a validated common Full environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.capacity_recovery import EvaluationConfig, model_factor_variant
from scripts.reproduce.mechanism_zone_search import PLANNING_MODELS, FULL_MODEL
from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.replay_solutions import _replay_solution
from scripts.reproduce.run_benchmark import _non_dominated, pooled_quality_indicators
from scripts.reproduce.service_diagnostics import service_rows
from scripts.reproduce.solution_io import (
    RunStore, SolutionIOError, canonical_json, code_environment, decision_from_json,
    decision_hash, model_fingerprint, physical_instance_hash, source_hashes,
    write_csv_atomic, write_json_atomic, CONTRACT_FORMAT, CONTRACT_FORMAT_VERSION,
)

GROUP = ("case_id", "scenario_family", "zone")
LABELS = {FULL_MODEL: "Full", "PR0_HT1_EC1": "No-PR", "PR1_HT0_EC1": "No-HT", "PR1_HT1_EC0": "No-EC"}
FACTORS = dict(PLANNING_MODELS)
PAIR_METRICS = ("delta_hv", "delta_igd", "representative_delta_F1", "representative_delta_F2", "representative_delta_F3")


def require(condition, message):
    if not condition:
        raise SolutionIOError(message)


def objectives(values):
    require(isinstance(values, (list, tuple)) and len(values) == 3, "three objectives required")
    point = tuple(float(v) for v in values)
    require(all(math.isfinite(v) for v in point), "non-finite objectives")
    return point


def changed(left, right):
    return tuple(a != b for a, b in zip(V2_PRECISION.key(left), V2_PRECISION.key(right)))


def relation(full, other):
    if V2_PRECISION.equivalent(full, other):
        return "same"
    if V2_PRECISION.dominates(full, other):
        return "Full_dominates"
    if V2_PRECISION.dominates(other, full):
        return "simplified_dominates"
    return "tradeoff"


def aggregate(rows, keys):
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[k] for k in keys)].append(row)
    return [{**dict(zip(keys, key)), "members": len(values),
             **{m: statistics.fmean(v[m] for v in values) for m in PAIR_METRICS}}
            for key, values in sorted(grouped.items())]


def _check_contract(record, contract):
    require(contract.get("format") == CONTRACT_FORMAT and contract.get("format_version") == CONTRACT_FORMAT_VERSION,
            "unsupported directory contract")
    fixed = contract["fixed"]
    for field in ("suite", "budget", "source_fingerprint", "algorithm", "case_id", "evaluation", "evaluation_fingerprint"):
        if field in fixed:
            require(record.get(field) == fixed[field], f"run outside contract: {field}")
    require(fixed.get("model_version") == "v2", "only v2 contracts accepted")
    varying = contract.get("varying", {})
    for field, plural in (("case_id", "cases"), ("instance_seed", "instance_seeds"), ("model_id", "model_ids")):
        allowed = fixed.get(plural, varying.get(plural))
        if allowed is not None:
            require(record[field] in allowed, f"run outside contract: {plural}")
    for field in ("scenario",):
        if field in fixed:
            require(record.get("scenario_family") == fixed[field], "scenario outside contract")
    repeats = fixed.get("solver_repeats", varying.get("solver_repeats"))
    starts = fixed.get("solver_seed_start", varying.get("solver_seed_start"))
    repeat_start = varying.get("solver_repeat_start", 0)
    # RunStore represents extendable scalar values as lists.
    for name, value in (("repeats", repeats), ("starts", starts), ("repeat_start", repeat_start)):
        if isinstance(value, list):
            if name == "repeats": repeats = max(value)
            elif name == "starts": starts = value
            else: repeat_start = min(value)
    if repeats is not None:
        require(repeat_start <= record["solver_repeat"] < repeat_start + repeats, "repeat outside contract")
    if starts is not None:
        seeds = starts if isinstance(starts, list) else [starts]
        require(any(record["solver_seed"] == s + record["instance_seed"] * 10000 + record["solver_repeat"] for s in seeds),
                "solver seed outside contract")


def analyze(input_roots, output_dir, representative_traces=False):
    runs, fronts, replay, bias, periods, demands = [], [], [], [], [], []
    units = defaultdict(list)
    seen_runs, seen_slots = set(), set()
    physical_seeds, group_configs = {}, {}
    input_hashes = {}
    self_errors = [0.0, 0.0, 0.0]
    self_count = 0
    for root in map(Path, input_roots):
        store = RunStore(root)
        require(store.contract_path.is_file(), f"missing contract: {root}")
        contract = json.loads(store.contract_path.read_text())
        records = store.load_runs_for_experiment()
        require(records, f"empty run store: {root}")
        input_hashes[str(store.contract_path.resolve())] = hashlib.sha256(store.contract_path.read_bytes()).hexdigest()
        for record in records:
            _check_contract(record, contract)
            key = record["run_key"]
            require(key not in seen_runs, "duplicate input run")
            seen_runs.add(key)
            input_hashes[str(store.run_path(key).resolve())] = record["record_sha256"]
            require(record.get("model_id") in LABELS, "unexpected planning model")
            require(record.get("objective_precision") == V2_PRECISION.as_dict() and
                    record.get("objective_precision_fingerprint") == V2_PRECISION.fingerprint(), "incompatible precision")
            require(record.get("evaluation") == EvaluationConfig.for_version("v2").as_dict(), "incompatible evaluation")
            require(record.get("evaluation_fingerprint") == EvaluationConfig.for_version("v2").fingerprint(), "evaluation fingerprint mismatch")
            require(0 < record["evaluations"] <= record["budget"]["max_evaluations"], "invalid or exceeded budget")
            require(set(record["budget"]) == {"max_evaluations", "pop_size", "crossover_probability", "mutation_probability", "alns_probability", "alns_iterations"}, "incomplete budget")
            planning = store.load_instance(record["instance_file"])
            full = store.load_execution_instance(record["physical_instance_hash"], require_full=True)
            require(physical_instance_hash(planning) == record["physical_instance_hash"], "physical snapshot mismatch")
            for snapshot in (store.instance_path(record["instance_file"]),
                             store.execution_instance_path(record["physical_instance_hash"])):
                input_hashes[str(snapshot.resolve())] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            expected = model_factor_variant(full, **FACTORS[record["model_id"]])
            require(model_fingerprint(planning) == record["model_fingerprint"] == model_fingerprint(expected),
                    "planning label/snapshot/Full variant mismatch")
            identity = {"case_id": record["case_id"], "scenario_family": record.get("scenario_family", "benchmark"),
                        "zone": record.get("zone", "original"), "instance_seed": record["instance_seed"],
                        "solver_seed": record["solver_seed"], "solver_repeat": record["solver_repeat"],
                        "model_id": record["model_id"], "model": LABELS[record["model_id"]], "run_key": key,
                        "physical_instance_hash": record["physical_instance_hash"]}
            group = tuple(identity[k] for k in GROUP)
            unit = group + (record["instance_seed"],)
            slot = unit + (record["solver_seed"], record["solver_repeat"], record["model_id"])
            require(slot not in seen_slots, "duplicate planning model in pair")
            seen_slots.add(slot)
            physical_slot = (group, record["physical_instance_hash"])
            require(physical_slot not in physical_seeds or physical_seeds[physical_slot] == record["instance_seed"],
                    "same physical instance renamed to multiple seeds")
            physical_seeds[physical_slot] = record["instance_seed"]
            config = canonical_json([record["algorithm"], record["budget"], record["source_fingerprint"]])
            require(group not in group_configs or group_configs[group] == config, "incompatible group algorithm/source/budget")
            group_configs[group] = config
            stored = record.get("pareto_front")
            require(stored, "empty front")
            hashes = set()
            selected = None
            points = []
            for solution in stored:
                plan = objectives(solution["objectives"])
                decision = decision_from_json(solution["decision"], planning)
                require(decision_hash(decision) == solution["decision_hash"], "decision hash mismatch")
                require(solution["decision_hash"] not in hashes, "duplicate decision within run")
                hashes.add(solution["decision_hash"])
                saved = _replay_solution(record=record, solution=solution, execution_instance=planning,
                                         execution_model="saved", abs_tolerance=1e-8, rel_tolerance=1e-8)
                require(saved["replay_success"], "planning self-replay failed")
                for j in range(3):
                    self_errors[j] = max(self_errors[j], abs(saved[f"replay_minus_planning_F{j+1}"]))
                self_count += 1
                executed = _replay_solution(record=record, solution=solution, execution_instance=full,
                                            execution_model="full", abs_tolerance=1e-8, rel_tolerance=1e-8)
                require(executed["replay_success"], "Full replay failed")
                point = objectives([executed[f"replay_F{j}"] for j in (1, 2, 3)])
                points.append(point)
                replay.append({**identity, **executed})
                bias.append({**identity, "solution_id": solution["solution_id"], "decision_hash": solution["decision_hash"],
                             "is_representative": solution["decision_hash"] == record["decision_hash"],
                             **{f"execution_minus_planning_F{j+1}": point[j] - plan[j] for j in range(3)},
                             **{f"changed_F{j+1}": v for j, v in enumerate(changed(plan, point))}})
                if solution["decision_hash"] == record["decision_hash"]:
                    selected = (solution, point, executed)
            require(selected is not None, "missing preselected representative")
            rep, rep_point, rep_replay = selected
            require(decision_hash(decision_from_json(record["representative_decision"], planning)) == record["decision_hash"], "representative hash mismatch")
            require(objectives(record["objectives"]) == objectives(rep["objectives"]), "representative objectives mismatch")
            rep_key = lambda s: tuple(V2_PRECISION.key(s["objectives"])[j] for j in (2, 0, 1))
            require(rep_key(rep) == min(map(rep_key, stored)), "representative not selected in planning")
            front = _non_dominated(points, V2_PRECISION)
            for index, point in enumerate(front):
                fronts.append({**identity, "point_index": index, **{f"F{j+1}": point[j] for j in range(3)}})
            row = {**identity, "algorithm": record["algorithm"], "evaluations": record["evaluations"],
                   "termination_reason": record["termination_reason"], "saved_front_size": len(stored),
                   "execution_front_size": len(front), "representative_hash": record["decision_hash"],
                   **{f"representative_F{j+1}": rep_point[j] for j in range(3)},
                   **{m: rep_replay[f"replay_{m}"] for m in ("final_total_satisfaction", "final_min_satisfaction", "zero_service_ratio", "remaining_supply")}}
            runs.append(row)
            units[unit].append((row, front, model_fingerprint(full)))
            if representative_traces:
                p, d, _ = service_rows(full, decision_from_json(rep["decision"], full), identity)
                periods.extend(p)
                demands.extend(d)
    pairs, references = [], []
    for unit, entries in sorted(units.items()):
        require(len({(e[0]["physical_instance_hash"], e[2]) for e in entries}) == 1, "incompatible physical/execution instance")
        metrics, meta = pooled_quality_indicators([e[1] for e in entries], V2_PRECISION)
        references.append({**dict(zip(GROUP + ("instance_seed",), unit)), "physical_instance_hash": entries[0][0]["physical_instance_hash"], **meta})
        paired = defaultdict(dict)
        for (row, _, _), quality in zip(entries, metrics):
            row.update(quality)
            paired[(row["solver_seed"], row["solver_repeat"])][row["model_id"]] = row
        for _, models in sorted(paired.items()):
            require(set(models) == set(LABELS), "missing model in paired run")
            full = models[FULL_MODEL]
            for model_id, other in models.items():
                if model_id == FULL_MODEL:
                    continue
                f = tuple(full[f"representative_F{j}"] for j in (1, 2, 3))
                o = tuple(other[f"representative_F{j}"] for j in (1, 2, 3))
                pairs.append({**{k: other[k] for k in GROUP + ("instance_seed", "solver_seed", "solver_repeat", "model_id", "model")},
                              "full_run_key": full["run_key"], "simplified_run_key": other["run_key"],
                              "delta_hv": full["hypervolume"] - other["hypervolume"],
                              "delta_igd": other["igd"] - full["igd"], "representative_relation": relation(f, o),
                              **{f"representative_delta_F{j+1}": o[j] - f[j] for j in range(3)}})
    instance_summary = aggregate(pairs, GROUP + ("instance_seed", "model_id", "model"))
    group_summary = aggregate(instance_summary, GROUP + ("model_id", "model"))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = {"execution_runs": runs, "execution_fronts": fronts, "execution_pairs": pairs,
              "prediction_bias": bias, "instance_summary": instance_summary, "group_summary": group_summary,
              "replay_results": replay}
    if representative_traces:
        tables.update(representative_periods=periods, representative_demand_periods=demands)
    for name, rows in tables.items():
        write_csv_atomic(output_dir / f"{name}.csv", rows, list(dict.fromkeys(k for r in rows for k in r)))
    write_json_atomic(output_dir / "reference_metadata.json", references)
    manifest = {"environment": code_environment(), "input_record_hashes": input_hashes,
                "source_hashes": source_hashes(Path(__file__).resolve().parents[2], [str(p.relative_to(Path(__file__).resolve().parents[2])) for p in Path(__file__).resolve().parent.glob("*.py")]),
                "counts": {k: len(v) for k, v in tables.items()}, "self_replay_count": self_count,
                "self_replay_max_abs_error": self_errors, "full_identity_count": sum(r["identity_checked"] for r in replay),
                "full_identity_max_abs_error": [max((abs(r[f"replay_minus_planning_F{j}"]) for r in replay if r["identity_checked"]), default=0) for j in (1,2,3)],
                "failures": 0, "search_evaluations": sum(r["evaluations"] for r in runs),
                "budgets": [json.loads(c)[1] for c in sorted(set(group_configs.values()))],
                "precision": V2_PRECISION.as_dict(),
                "analysis": "Descriptive only. Average paired repeats within each instance, then weight instances equally. Per-physical-instance pooled reference; normalized HV is not absolute benefit across configurations. Representatives fixed before replay. Prediction bias is not decision benefit."}
    write_json_atomic(output_dir / "analysis_manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-roots", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--representative-traces", action="store_true")
    args = parser.parse_args()
    manifest = analyze(args.input_roots, args.output_dir, args.representative_traces)
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
