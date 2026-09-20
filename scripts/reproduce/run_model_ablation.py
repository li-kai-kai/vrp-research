from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.benchmark_algorithms import (
    ALGORITHMS,
    BenchmarkBudget,
    solve_benchmark_algorithm,
)
from scripts.reproduce.benchmark_suite import (
    BenchmarkSpec,
    benchmark_specs,
    build_benchmark_instance,
    default_instance_seeds,
)
from scripts.reproduce.capacity_recovery import (
    MODEL_VERSIONS,
    UNIFORM_VEHICLE_RECOVERY_THRESHOLD,
    EvaluationConfig,
    model_factor_variant,
)
from scripts.reproduce.model_ablation_analysis import analyze_model_ablation
from scripts.reproduce.run_benchmark import (
    SOURCE_FILES,
    _default_evaluations,
    _default_population,
    _default_solver_repeats,
    _non_dominated,
    _select_specs,
    _write_csv,
    pooled_quality_indicators,
)
from scripts.reproduce.solution_io import (
    RunStore,
    build_run_record,
    make_run_key,
    model_fingerprint,
    physical_instance_hash,
    run_summary_row,
    source_fingerprint,
    write_store_indexes,
)


ALGORITHM = "nsga2_alns"

# The formal factorial design is the paired 2^3 block run with this algorithm.
FORMAL_ALGORITHM = "nsga2_alns"

# The entry point and its analysis also determine a run's numbers, so they are
# part of this experiment's source fingerprint.
ABLATION_SOURCE_FILES = SOURCE_FILES + (
    "scripts/reproduce/run_model_ablation.py",
    "scripts/reproduce/model_ablation_analysis.py",
)


@dataclass(frozen=True)
class ModelFactors:
    progressive_recovery: bool
    heterogeneous_vehicle_thresholds: bool
    edge_capacity_constraint: bool

    @property
    def model_id(self) -> str:
        return (
            f"PR{int(self.progressive_recovery)}_"
            f"HT{int(self.heterogeneous_vehicle_thresholds)}_"
            f"EC{int(self.edge_capacity_constraint)}"
        )

    def row(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "progressive_recovery": int(self.progressive_recovery),
            "heterogeneous_vehicle_thresholds": int(
                self.heterogeneous_vehicle_thresholds
            ),
            "edge_capacity_constraint": int(self.edge_capacity_constraint),
        }


MODEL_FACTOR_COMBINATIONS = tuple(
    ModelFactors(*levels)
    for levels in product((False, True), repeat=3)
)

MODEL_FACTORS_BY_ID = {factors.model_id: factors for factors in MODEL_FACTOR_COMBINATIONS}

# Full execution environment shared by every planning group in a replay.
FULL_EXECUTION_FACTORS = ModelFactors(
    progressive_recovery=True,
    heterogeneous_vehicle_thresholds=True,
    edge_capacity_constraint=True,
)


@dataclass(frozen=True)
class AblationRecord:
    spec: BenchmarkSpec
    instance_seed: int
    solver_seed: int
    factors: ModelFactors
    record: dict


def main() -> None:
    args = _parse_args()
    budget = BenchmarkBudget(
        max_evaluations=(
            args.max_evaluations
            if args.max_evaluations is not None
            else _default_evaluations(args.suite)
        ),
        pop_size=(
            args.pop_size
            if args.pop_size is not None
            else _default_population(args.suite)
        ),
        crossover_probability=args.crossover_probability,
        mutation_probability=args.mutation_probability,
        alns_probability=args.alns_probability,
        alns_iterations=args.alns_iterations,
    )
    run_model_ablation(
        suite=args.suite,
        output_dir=Path(args.output_dir),
        cases=args.cases,
        instance_seeds=args.instance_seeds,
        solver_repeats=args.solver_repeats,
        solver_repeat_start=args.solver_repeat_start,
        solver_seed_start=args.solver_seed_start,
        budget=budget,
        bootstrap_samples=args.bootstrap_samples,
        permutation_samples=args.permutation_samples,
        analysis_seed=args.analysis_seed,
        model_version=args.model_version,
        algorithm=args.algorithm,
        model_ids=args.model_ids,
        resume=args.resume,
    )


def run_model_ablation(
    *,
    suite: str,
    output_dir: Path,
    cases: list[str] | None = None,
    instance_seeds: list[int] | None = None,
    solver_repeats: int | None = None,
    solver_repeat_start: int = 0,
    solver_seed_start: int = 50_000,
    budget: BenchmarkBudget | None = None,
    bootstrap_samples: int = 5_000,
    permutation_samples: int = 20_000,
    analysis_seed: int = 202_608_31,
    model_version: str = "legacy",
    algorithm: str = ALGORITHM,
    model_ids: list[str] | None = None,
    resume: bool = False,
) -> list[dict[str, object]]:
    """Run the paired model-factor factorial with the unified benchmark solver.

    Selecting a strict subset of the eight combinations is supported and
    produces descriptive and replay summaries only: the formal main-effect and
    interaction analysis is reported as not applicable rather than computed on
    an incomplete design.
    """
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm: {algorithm}")
    specs = _select_specs(benchmark_specs(suite), cases)
    default_seeds = default_instance_seeds(suite)
    requested_seeds = instance_seeds if instance_seeds else None
    instance_seeds_by_case = {
        spec.case_id: (
            list(requested_seeds)
            if requested_seeds is not None
            else [1]
            if spec.source == "wenchuan"
            else list(default_seeds)
        )
        for spec in specs
    }
    selected_solver_repeats = (
        solver_repeats
        if solver_repeats is not None
        else _default_solver_repeats(suite)
    )
    selected_budget = budget or BenchmarkBudget(
        max_evaluations=_default_evaluations(suite),
        pop_size=_default_population(suite),
    )
    if selected_solver_repeats < 1:
        raise ValueError("solver_repeats must be positive")
    if solver_repeat_start < 0:
        raise ValueError("solver_repeat_start must be non-negative")

    selected_factors = _select_factors(model_ids)
    evaluation = EvaluationConfig.for_version(model_version)
    output_dir.mkdir(parents=True, exist_ok=True)
    store = RunStore(output_dir)
    budget_payload = asdict(selected_budget)
    source_fp = source_fingerprint(
        Path(__file__).resolve().parents[2], ABLATION_SOURCE_FILES
    )
    store.check_source_consistency(source_fp)

    records: list[AblationRecord] = []
    instance_rows: list[dict[str, object]] = []
    skipped = 0
    total = (
        sum(len(seeds) for seeds in instance_seeds_by_case.values())
        * selected_solver_repeats
        * len(selected_factors)
    )
    run_index = 0
    for spec in specs:
        for instance_seed in instance_seeds_by_case[spec.case_id]:
            base_instance = build_benchmark_instance(
                spec,
                instance_seed=instance_seed,
                model_version=model_version,
            )
            # The execution environment every planning group is replayed in.
            store.save_execution_instance(
                model_factor_variant(
                    base_instance,
                    progressive_recovery=FULL_EXECUTION_FACTORS.progressive_recovery,
                    heterogeneous_vehicle_thresholds=(
                        FULL_EXECUTION_FACTORS.heterogeneous_vehicle_thresholds
                    ),
                    edge_capacity_constraint=(
                        FULL_EXECUTION_FACTORS.edge_capacity_constraint
                    ),
                )
            )
            nominal_fleet_capacity = sum(
                vehicle.capacity_ton * vehicle.count for vehicle in base_instance.vehicles
            )
            instance_rows.append(
                {
                    **spec.row(),
                    "instance_seed": instance_seed,
                    "instance": base_instance.base.name,
                    "physical_instance_hash": physical_instance_hash(base_instance),
                    "model_version": model_version,
                    "edges": base_instance.base.graph.number_of_edges(),
                    "damaged_edges": len(base_instance.base.damaged_edges),
                    "suppliers": len(base_instance.base.suppliers),
                    "demands": len(base_instance.base.demands),
                    "repair_crews": base_instance.base.repair_crews,
                    "vehicles": sum(
                        vehicle.count for vehicle in base_instance.vehicles
                    ),
                    "nominal_fleet_capacity_per_period": nominal_fleet_capacity,
                    "realized_fleet_capacity_ratio": (
                        nominal_fleet_capacity
                        / max(base_instance.base.total_demand, 1e-9)
                    ),
                }
            )
            for repeat in range(
                solver_repeat_start,
                solver_repeat_start + selected_solver_repeats,
            ):
                solver_seed = solver_seed_start + instance_seed * 10_000 + repeat
                for factors in selected_factors:
                    run_index += 1
                    instance = model_factor_variant(
                        base_instance,
                        progressive_recovery=factors.progressive_recovery,
                        heterogeneous_vehicle_thresholds=(
                            factors.heterogeneous_vehicle_thresholds
                        ),
                        edge_capacity_constraint=factors.edge_capacity_constraint,
                    )
                    if physical_instance_hash(instance) != physical_instance_hash(
                        base_instance
                    ):
                        raise RuntimeError(
                            "model factor variant changed the shared physical scenario"
                        )
                    run_key = make_run_key(
                        case_id=spec.case_id,
                        instance_seed=instance_seed,
                        algorithm=algorithm,
                        model_id=factors.model_id,
                        solver_seed=solver_seed,
                        solver_repeat=repeat,
                        budget=budget_payload,
                        model_fingerprint_value=model_fingerprint(instance),
                        source_fingerprint=source_fp,
                    )
                    if resume and store.has_complete_run(run_key):
                        record = store.load_run(run_key)
                        skipped += 1
                        print(f"[{run_index}/{total}] {run_key} already complete, skipped",
                              flush=True)
                    else:
                        print(
                            f"[{run_index}/{total}] {spec.case_id}/instance={instance_seed} "
                            f"solver={solver_seed}/model={factors.model_id}",
                            flush=True,
                        )
                        result = solve_benchmark_algorithm(
                            algorithm,
                            instance,
                            selected_budget,
                            seed=solver_seed,
                        )
                        record = build_run_record(
                            run_key=run_key,
                            case_id=spec.case_id,
                            suite=suite,
                            source=spec.source,
                            size_group=spec.size_group,
                            num_nodes=spec.num_nodes,
                            instance_seed=instance_seed,
                            solver_seed=solver_seed,
                            solver_repeat=repeat,
                            algorithm=algorithm,
                            instance=instance,
                            front=result.front,
                            representative=result.representative,
                            evaluations=result.evaluations,
                            runtime_seconds=result.runtime_seconds,
                            convergence=result.convergence,
                            budget=budget_payload,
                            termination_reason=result.termination_reason,
                            source_fingerprint_value=source_fp,
                            extra={
                                "diagnostics": result.diagnostics,
                                **factors.row(),
                                "instance_file": model_fingerprint(instance),
                                "max_evaluations": selected_budget.max_evaluations,
                            },
                        )
                        store.save_run(record)
                    records.append(
                        AblationRecord(
                            spec=spec,
                            instance_seed=instance_seed,
                            solver_seed=solver_seed,
                            factors=factors,
                            record=record,
                        )
                    )

    reference_rows = _attach_pooled_quality(records)
    for entry in records:
        store.save_run(entry.record)

    # The analysis expects one flat row per run with F1/F2/F3, the quality
    # indicators and the model factor columns.
    ablation_rows = [_ablation_row(entry) for entry in records]
    pareto_rows = _pareto_rows(records)
    analysis = _formal_analysis(
        ablation_rows,
        selected_factors=selected_factors,
        algorithm=algorithm,
        bootstrap_samples=bootstrap_samples,
        permutation_samples=permutation_samples,
        analysis_seed=analysis_seed,
    )

    _write_csv(output_dir / "model_ablation.csv", ablation_rows)
    _write_csv(output_dir / "pareto_points.csv", pareto_rows)
    _write_csv(output_dir / "pooled_reference_front.csv", reference_rows)
    if analysis["status"] == "computed":
        _write_csv(output_dir / "model_summary.csv", analysis["model_summary"])
        _write_csv(output_dir / "factor_effects_raw.csv", analysis["raw_effects"])
        _write_csv(output_dir / "factor_effects.csv", analysis["effect_summary"])
        _write_csv(output_dir / "factorial_completeness.csv", analysis["completeness"])
    else:
        _write_not_applicable(output_dir, analysis["reason"])
    write_store_indexes(
        store,
        [entry.record for entry in records],
        reference_front_by_case=_reference_front_sizes(records),
    )
    _write_csv(
        output_dir / "aggregate_by_size.csv",
        _aggregate([run_summary_row(entry.record) for entry in records]),
    )
    _write_manifest(
        output_dir / "experiment_manifest.json",
        suite=suite,
        specs=specs,
        instance_seeds_by_case=instance_seeds_by_case,
        solver_repeats=selected_solver_repeats,
        solver_repeat_start=solver_repeat_start,
        solver_seed_start=solver_seed_start,
        budget=selected_budget,
        bootstrap_samples=bootstrap_samples,
        permutation_samples=permutation_samples,
        analysis_seed=analysis_seed,
        model_version=model_version,
        algorithm=algorithm,
        selected_factors=selected_factors,
        analysis=analysis,
        source_fp=source_fp,
        planned_runs=total,
        completed_runs=len(records),
        skipped_runs=skipped,
    )
    print(f"Done. Model ablation outputs written to {output_dir}")
    return ablation_rows


def _select_factors(model_ids: list[str] | None) -> list[ModelFactors]:
    if not model_ids:
        return list(MODEL_FACTOR_COMBINATIONS)
    unknown = sorted(set(model_ids) - set(MODEL_FACTORS_BY_ID))
    if unknown:
        raise ValueError(
            f"unknown model ids {unknown}; expected a subset of "
            f"{sorted(MODEL_FACTORS_BY_ID)}"
        )
    ordered: list[ModelFactors] = []
    for model_id in model_ids:
        factors = MODEL_FACTORS_BY_ID[model_id]
        if factors not in ordered:
            ordered.append(factors)
    return ordered


def _formal_analysis(
    run_rows: list[dict[str, object]],
    *,
    selected_factors: list[ModelFactors],
    algorithm: str,
    bootstrap_samples: int,
    permutation_samples: int,
    analysis_seed: int,
) -> dict[str, object]:
    """Run the formal factorial only on a complete design that supports it."""
    if len(selected_factors) != len(MODEL_FACTOR_COMBINATIONS):
        return {
            "status": "not_applicable",
            "reason": (
                "subset model selection: only a descriptive and replay summary is "
                "produced, no main-effect or interaction significance results"
            ),
        }
    if algorithm != FORMAL_ALGORITHM:
        return {
            "status": "not_applicable",
            "reason": (
                f"the formal paired design is defined for {FORMAL_ALGORITHM}; "
                f"algorithm {algorithm!r} is reported descriptively only"
            ),
        }
    try:
        model_summary, raw_effects, effect_summary, completeness_rows = (
            analyze_model_ablation(
                run_rows,
                bootstrap_samples=bootstrap_samples,
                permutation_samples=permutation_samples,
                analysis_seed=analysis_seed,
            )
        )
    except ValueError as error:
        return {
            "status": "blocked",
            "reason": f"incomplete or unpaired 2^3 block: {error}",
        }
    return {
        "status": "computed",
        "model_summary": model_summary,
        "raw_effects": raw_effects,
        "effect_summary": effect_summary,
        "completeness": completeness_rows,
        "reason": None,
    }


def _write_not_applicable(output_dir: Path, reason: str | None) -> None:
    header = [{"formal_analysis": "not_applicable", "reason": reason or ""}]
    for name in (
        "model_summary.csv",
        "factor_effects_raw.csv",
        "factor_effects.csv",
        "factorial_completeness.csv",
    ):
        _write_csv(output_dir / name, header)


def _ablation_row(entry: AblationRecord) -> dict[str, object]:
    record = entry.record
    objectives = record.get("objectives") or [None, None, None]
    metrics = record.get("metrics") or {}
    row: dict[str, object] = {
        "run_key": record["run_key"],
        "case_id": entry.spec.case_id,
        "source": entry.spec.source,
        "size_group": entry.spec.size_group,
        "num_nodes": entry.spec.num_nodes,
        "instance_seed": entry.instance_seed,
        "solver_seed": entry.solver_seed,
        "algorithm": record["algorithm"],
        "model_version": (record.get("evaluation") or {}).get("model_version"),
        "physical_instance_hash": record["physical_instance_hash"],
        "model_fingerprint": record["model_fingerprint"],
        **entry.factors.row(),
        "max_evaluations": record.get("max_evaluations")
        or (record.get("budget") or {}).get("max_evaluations"),
        "evaluations": record.get("evaluations"),
        "termination_reason": record.get("termination_reason"),
        "runtime_seconds": record.get("runtime_seconds"),
        "pareto_size": len(record.get("pareto_front") or []),
        "F1": objectives[0],
        "F2": objectives[1],
        "F3": objectives[2],
        "hypervolume": record.get("hypervolume"),
        "igd": record.get("igd"),
    }
    for metric in _MECHANISM_METRICS:
        row[metric] = metrics.get(metric, 0.0)
    return row


_MECHANISM_METRICS = (
    "final_total_satisfaction",
    "final_min_satisfaction",
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


def _pareto_rows(records: list[AblationRecord]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entry in records:
        record = entry.record
        for solution in record.get("pareto_front") or []:
            objectives = solution["objectives"]
            metrics = solution.get("metrics") or {}
            rows.append(
                {
                    "run_key": record["run_key"],
                    "case_id": entry.spec.case_id,
                    "instance_seed": entry.instance_seed,
                    "solver_seed": entry.solver_seed,
                    **entry.factors.row(),
                    "point_id": solution["solution_id"],
                    "decision_hash": solution["decision_hash"],
                    "F1": objectives[0],
                    "F2": objectives[1],
                    "F3": objectives[2],
                    "final_total_satisfaction": metrics.get(
                        "final_total_satisfaction", 0.0
                    ),
                    "final_min_satisfaction": metrics.get("final_min_satisfaction", 0.0),
                }
            )
    return rows


def _attach_pooled_quality(records: list[AblationRecord]) -> list[dict[str, object]]:
    """Pool all selected factor levels and repeats within each instance."""
    groups: dict[tuple[str, int], list[int]] = defaultdict(list)
    for index, entry in enumerate(records):
        groups[(entry.spec.case_id, entry.instance_seed)].append(index)

    reference_rows: list[dict[str, object]] = []
    for (case_id, instance_seed), indices in groups.items():
        fronts = [
            [
                tuple(solution["objectives"])
                for solution in (records[index].record.get("pareto_front") or [])
            ]
            for index in indices
        ]
        quality_rows, metadata = pooled_quality_indicators(fronts)
        ideal = metadata["ideal"]
        nadir = metadata["nadir"]
        for index, quality in zip(indices, quality_rows):
            records[index].record.update(quality)
            records[index].record.update(
                {
                    "reference_front_size": metadata["reference_front_size"],
                    "pooled_ideal_F1": ideal[0],
                    "pooled_ideal_F2": ideal[1],
                    "pooled_ideal_F3": ideal[2],
                    "pooled_nadir_F1": nadir[0],
                    "pooled_nadir_F2": nadir[1],
                    "pooled_nadir_F3": nadir[2],
                }
            )
        pooled_points = [point for front in fronts for point in front]
        for point_id, point in enumerate(_non_dominated(pooled_points), start=1):
            reference_rows.append(
                {
                    "case_id": case_id,
                    "instance_seed": instance_seed,
                    "point_id": point_id,
                    "F1": point[0],
                    "F2": point[1],
                    "F3": point[2],
                }
            )
    return reference_rows


def _reference_front_sizes(
    records: list[AblationRecord],
) -> dict[tuple[str, int], dict[str, object]]:
    return {
        (entry.spec.case_id, entry.instance_seed): {
            "size": entry.record.get("reference_front_size")
        }
        for entry in records
    }


def _aggregate(run_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    import statistics

    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in run_rows:
        groups[(str(row.get("size_group")), str(row["algorithm"]))].append(row)
    metrics = ("hypervolume", "igd", "runtime_seconds", "evaluations", "F1", "F2", "F3")
    output: list[dict[str, object]] = []
    for (size_group, algorithm), rows in sorted(groups.items()):
        aggregate: dict[str, object] = {
            "size_group": size_group,
            "algorithm": algorithm,
            "runs": len(rows),
        }
        for metric in metrics:
            values = [
                float(row[metric]) for row in rows if row.get(metric) is not None
            ]
            if not values:
                continue
            aggregate[f"{metric}_mean"] = statistics.fmean(values)
            aggregate[f"{metric}_sd"] = (
                statistics.stdev(values) if len(values) > 1 else 0.0
            )
        output.append(aggregate)
    return output


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the paired 2^3 model-mechanism ablation factorial.",
    )
    parser.add_argument(
        "--suite",
        choices=["smoke", "benchmark", "publication"],
        default="smoke",
    )
    parser.add_argument("--cases", nargs="*", help="Optional case IDs, e.g. S025 M100.")
    parser.add_argument("--instance-seeds", type=int, nargs="*")
    parser.add_argument("--solver-repeats", type=int)
    parser.add_argument("--solver-repeat-start", type=int, default=0)
    parser.add_argument("--solver-seed-start", type=int, default=50_000)
    parser.add_argument("--max-evaluations", type=int)
    parser.add_argument("--pop-size", type=int)
    parser.add_argument("--crossover-probability", type=float, default=0.90)
    parser.add_argument("--mutation-probability", type=float, default=0.20)
    parser.add_argument("--alns-probability", type=float, default=0.35)
    parser.add_argument("--alns-iterations", type=int, default=4)
    parser.add_argument(
        "--model-version",
        choices=list(MODEL_VERSIONS),
        default="legacy",
        help=(
            "Evaluation semantics shared by all planning groups. legacy keeps "
            "the historical cap and end-of-period dispatch; v2 uses the frozen "
            "semantics in docs/model_v2_contract.md."
        ),
    )
    parser.add_argument(
        "--algorithm",
        choices=list(ALGORITHMS),
        default=ALGORITHM,
        help="Solver used for every planning group in the paired design.",
    )
    parser.add_argument(
        "--model-ids",
        nargs="*",
        help=(
            "Optional subset of planning models, e.g. "
            "PR1_HT1_EC1 PR0_HT1_EC1 PR1_HT0_EC1 PR1_HT1_EC0. "
            "A subset produces descriptive and replay summaries only."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip runs whose complete record already matches exactly.",
    )
    parser.add_argument("--bootstrap-samples", type=int, default=5_000)
    parser.add_argument("--permutation-samples", type=int, default=20_000)
    parser.add_argument("--analysis-seed", type=int, default=202_608_31)
    parser.add_argument("--output-dir", default="outputs/model_ablation")
    args = parser.parse_args()
    if args.solver_repeats is not None and args.solver_repeats < 1:
        parser.error("--solver-repeats must be positive")
    if args.solver_repeat_start < 0:
        parser.error("--solver-repeat-start must be non-negative")
    if args.max_evaluations is not None and args.max_evaluations < 1:
        parser.error("--max-evaluations must be positive")
    if args.pop_size is not None and args.pop_size < 2:
        parser.error("--pop-size must be at least 2")
    if args.alns_iterations < 0:
        parser.error("--alns-iterations must be non-negative")
    if args.bootstrap_samples < 1:
        parser.error("--bootstrap-samples must be positive")
    if args.permutation_samples < 1:
        parser.error("--permutation-samples must be positive")
    if args.model_ids:
        try:
            _select_factors(args.model_ids)
        except ValueError as error:
            parser.error(str(error))
    for value, name in (
        (args.crossover_probability, "--crossover-probability"),
        (args.mutation_probability, "--mutation-probability"),
        (args.alns_probability, "--alns-probability"),
    ):
        if not 0.0 <= value <= 1.0:
            parser.error(f"{name} must be in [0, 1]")
    return args


def _write_manifest(
    path: Path,
    *,
    suite: str,
    specs: list[BenchmarkSpec],
    instance_seeds_by_case: dict[str, list[int]],
    solver_repeats: int,
    solver_repeat_start: int,
    solver_seed_start: int,
    budget: BenchmarkBudget,
    bootstrap_samples: int,
    permutation_samples: int,
    analysis_seed: int,
    model_version: str,
    algorithm: str,
    selected_factors: list[ModelFactors],
    analysis: dict[str, object],
    source_fp: str,
    planned_runs: int,
    completed_runs: int,
    skipped_runs: int,
) -> None:
    evaluation = EvaluationConfig.for_version(model_version)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "source_files_sha256": _source_hashes(),
        "source_fingerprint": source_fp,
        "python": sys.version,
        "platform": platform.platform(),
        "suite": suite,
        "cases": [spec.row() for spec in specs],
        "instance_seeds_by_case": instance_seeds_by_case,
        "solver_seed_start": solver_seed_start,
        "solver_repeats": solver_repeats,
        "solver_repeat_start": solver_repeat_start,
        "algorithm": algorithm,
        "model_version": model_version,
        "evaluation": evaluation.as_dict(),
        "evaluation_fingerprint": evaluation.fingerprint(),
        "budget": asdict(budget),
        "planned_runs": planned_runs,
        "completed_runs": completed_runs,
        "resumed_runs": skipped_runs,
        "planned_max_objective_evaluations": planned_runs * budget.max_evaluations,
        "model_factor_order": [
            "progressive_recovery",
            "heterogeneous_vehicle_thresholds",
            "edge_capacity_constraint",
        ],
        "selected_model_ids": [factors.model_id for factors in selected_factors],
        "model_combinations": [factors.row() for factors in selected_factors],
        "full_execution_environment": {
            **FULL_EXECUTION_FACTORS.row(),
            "model_version": "v2",
            "note": (
                "planning groups are replayed in this environment by "
                "replay_solutions.py --execution-model full"
            ),
        },
        "uniform_vehicle_recovery_threshold_when_disabled": (
            UNIFORM_VEHICLE_RECOVERY_THRESHOLD
        ),
        "objectives": {
            "F1": "min_unmet_area",
            "F2": "min_time_cost",
            "F3": "min_neg_min_satisfaction",
        },
        "representative_rule": (
            "lexicographic min of (F3, F1, F2), applied before any replay and "
            "recorded per solution as representative_selected_before_replay"
        ),
        "formal_analysis": {
            "status": analysis["status"],
            "reason": analysis["reason"],
            "required_algorithm": FORMAL_ALGORITHM,
            "requires_all_eight_combinations": True,
            "synthetic_analysis_unit": (
                "instance seed after averaging paired solver repeats"
            ),
            "wenchuan_analysis_unit": (
                "solver run on the single fixed case-study instance"
            ),
            "factorial_terms": (
                "three main effects and three second-order interactions"
            ),
            "confidence_interval": "95% BCa bootstrap interval of analysis-unit means",
            "test": "two-sided paired sign-flip randomization test",
            "multiple_comparison_correction": (
                "Holm correction across six factorial terms within case and metric"
            ),
            "bootstrap_samples": bootstrap_samples,
            "permutation_samples": permutation_samples,
            "analysis_seed": analysis_seed,
        },
        "quality_indicators": {
            "pooling": (
                "one pooled non-dominated reference front per case_id and "
                "instance_seed across the selected model combinations and repeats"
            ),
            "normalization": "pooled observed ideal/nadir per objective",
            "hypervolume": "exact normalized 3D HV; reference point (1.1, 1.1, 1.1)",
            "igd": "normalized Euclidean IGD to the pooled non-dominated front",
            "caveat": (
                "per-planning-model hypervolume is not evidence of model value; "
                "use the common-execution replay table for that"
            ),
        },
    }
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_dirty() -> bool | None:
    try:
        return bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    paths = tuple(ABLATION_SOURCE_FILES)
    return {
        str(relative_path): hashlib.sha256((root / relative_path).read_bytes()).hexdigest()
        for relative_path in paths
        if (root / relative_path).is_file()
    }


if __name__ == "__main__":
    main()
