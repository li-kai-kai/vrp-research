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
    AlgorithmRun,
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
    UNIFORM_VEHICLE_RECOVERY_THRESHOLD,
    model_factor_variant,
)
from scripts.reproduce.model_ablation_analysis import analyze_model_ablation
from scripts.reproduce.run_benchmark import (
    _decision_hash,
    _default_evaluations,
    _default_population,
    _default_solver_repeats,
    _non_dominated,
    _select_specs,
    _write_csv,
    pooled_quality_indicators,
)


ALGORITHM = "nsga2_alns"


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


@dataclass(frozen=True)
class AblationRecord:
    spec: BenchmarkSpec
    instance_seed: int
    solver_seed: int
    factors: ModelFactors
    result: AlgorithmRun


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
) -> list[dict[str, object]]:
    """Run the paired 2^3 model factorial with the unified benchmark solver."""
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

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[AblationRecord] = []
    total = (
        sum(len(instance_seeds_by_case[spec.case_id]) for spec in specs)
        * selected_solver_repeats
        * len(MODEL_FACTOR_COMBINATIONS)
    )
    run_index = 0
    for spec in specs:
        for instance_seed in instance_seeds_by_case[spec.case_id]:
            base_instance = build_benchmark_instance(
                spec,
                instance_seed=instance_seed,
            )
            for repeat in range(
                solver_repeat_start,
                solver_repeat_start + selected_solver_repeats,
            ):
                solver_seed = solver_seed_start + instance_seed * 10_000 + repeat
                for factors in MODEL_FACTOR_COMBINATIONS:
                    run_index += 1
                    print(
                        f"[{run_index}/{total}] {spec.case_id}/instance={instance_seed} "
                        f"solver={solver_seed}/model={factors.model_id}",
                        flush=True,
                    )
                    instance = model_factor_variant(
                        base_instance,
                        progressive_recovery=factors.progressive_recovery,
                        heterogeneous_vehicle_thresholds=(
                            factors.heterogeneous_vehicle_thresholds
                        ),
                        edge_capacity_constraint=factors.edge_capacity_constraint,
                    )
                    result = solve_benchmark_algorithm(
                        ALGORITHM,
                        instance,
                        selected_budget,
                        seed=solver_seed,
                    )
                    records.append(
                        AblationRecord(
                            spec=spec,
                            instance_seed=instance_seed,
                            solver_seed=solver_seed,
                            factors=factors,
                            result=result,
                        )
                    )

    run_rows, pareto_rows = _result_rows(
        records,
        max_evaluations=selected_budget.max_evaluations,
    )
    reference_rows = _attach_pooled_quality(records, run_rows)
    model_summary, raw_effects, effect_summary, completeness_rows = (
        analyze_model_ablation(
            run_rows,
            bootstrap_samples=bootstrap_samples,
            permutation_samples=permutation_samples,
            analysis_seed=analysis_seed,
        )
    )
    _write_csv(output_dir / "model_ablation.csv", run_rows)
    _write_csv(output_dir / "pareto_points.csv", pareto_rows)
    _write_csv(output_dir / "pooled_reference_front.csv", reference_rows)
    _write_csv(output_dir / "model_summary.csv", model_summary)
    _write_csv(output_dir / "factor_effects_raw.csv", raw_effects)
    _write_csv(output_dir / "factor_effects.csv", effect_summary)
    _write_csv(output_dir / "factorial_completeness.csv", completeness_rows)
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
    )
    print(f"Done. Model ablation outputs written to {output_dir}")
    return run_rows


def _result_rows(
    records: list[AblationRecord],
    *,
    max_evaluations: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    run_rows: list[dict[str, object]] = []
    pareto_rows: list[dict[str, object]] = []
    mechanism_metrics = (
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
    for record in records:
        result = record.result
        representative = result.representative
        objectives = representative.objectives or (float("inf"),) * 3
        metrics = representative.metrics or {}
        run_key = (
            f"{record.spec.case_id}:i{record.instance_seed}:"
            f"s{record.solver_seed}:{record.factors.model_id}"
        )
        row: dict[str, object] = {
            "run_key": run_key,
            "case_id": record.spec.case_id,
            "source": record.spec.source,
            "size_group": record.spec.size_group,
            "num_nodes": record.spec.num_nodes,
            "instance_seed": record.instance_seed,
            "solver_seed": record.solver_seed,
            "algorithm": result.algorithm,
            **record.factors.row(),
            "max_evaluations": max_evaluations,
            "evaluations": result.evaluations,
            "runtime_seconds": result.runtime_seconds,
            "pareto_size": len(result.front),
            "F1": objectives[0],
            "F2": objectives[1],
            "F3": objectives[2],
        }
        row.update({metric: metrics.get(metric, 0.0) for metric in mechanism_metrics})
        run_rows.append(row)

        for point_id, individual in enumerate(result.front, start=1):
            point = individual.objectives or (float("inf"),) * 3
            point_metrics = individual.metrics or {}
            pareto_rows.append(
                {
                    "run_key": run_key,
                    "case_id": record.spec.case_id,
                    "instance_seed": record.instance_seed,
                    "solver_seed": record.solver_seed,
                    **record.factors.row(),
                    "point_id": point_id,
                    "decision_hash": _decision_hash(individual),
                    "F1": point[0],
                    "F2": point[1],
                    "F3": point[2],
                    "final_total_satisfaction": point_metrics.get(
                        "final_total_satisfaction", 0.0
                    ),
                    "final_min_satisfaction": point_metrics.get(
                        "final_min_satisfaction", 0.0
                    ),
                }
            )
    return run_rows, pareto_rows


def _attach_pooled_quality(
    records: list[AblationRecord],
    run_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Pool all factor levels and repeats within each benchmark instance."""
    groups: dict[tuple[str, int], list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[(record.spec.case_id, record.instance_seed)].append(index)

    reference_rows: list[dict[str, object]] = []
    for (case_id, instance_seed), indices in groups.items():
        fronts = [
            [
                individual.objectives
                for individual in records[index].result.front
                if individual.objectives is not None
            ]
            for index in indices
        ]
        quality_rows, metadata = pooled_quality_indicators(fronts)
        ideal = metadata["ideal"]
        nadir = metadata["nadir"]
        for index, quality in zip(indices, quality_rows):
            run_rows[index].update(quality)
            run_rows[index].update(
                {
                    "pooled_reference_front_size": metadata[
                        "reference_front_size"
                    ],
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
) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "source_files_sha256": _source_hashes(),
        "python": sys.version,
        "platform": platform.platform(),
        "suite": suite,
        "cases": [spec.row() for spec in specs],
        "instance_seeds_by_case": instance_seeds_by_case,
        "solver_seed_start": solver_seed_start,
        "solver_repeats": solver_repeats,
        "solver_repeat_start": solver_repeat_start,
        "algorithm": ALGORITHM,
        "budget": asdict(budget),
        "planned_runs": (
            sum(len(seeds) for seeds in instance_seeds_by_case.values())
            * solver_repeats
            * len(MODEL_FACTOR_COMBINATIONS)
        ),
        "planned_max_objective_evaluations": (
            sum(len(seeds) for seeds in instance_seeds_by_case.values())
            * solver_repeats
            * len(MODEL_FACTOR_COMBINATIONS)
            * budget.max_evaluations
        ),
        "model_factor_order": [
            "progressive_recovery",
            "heterogeneous_vehicle_thresholds",
            "edge_capacity_constraint",
        ],
        "model_combinations": [factors.row() for factors in MODEL_FACTOR_COMBINATIONS],
        "uniform_vehicle_recovery_threshold_when_disabled": (
            UNIFORM_VEHICLE_RECOVERY_THRESHOLD
        ),
        "objectives": {
            "F1": "min_unmet_area",
            "F2": "min_time_cost",
            "F3": "min_neg_min_satisfaction",
        },
        "quality_indicators": {
            "pooling": (
                "one pooled non-dominated reference front per case_id and "
                "instance_seed across all 8 factor combinations and solver repeats"
            ),
            "normalization": "pooled observed ideal/nadir per objective",
            "hypervolume": "exact normalized 3D HV; reference point (1.1, 1.1, 1.1)",
            "igd": "normalized Euclidean IGD to the pooled non-dominated front",
        },
        "formal_analysis": {
            "synthetic_analysis_unit": (
                "instance seed after averaging paired solver repeats"
            ),
            "wenchuan_analysis_unit": (
                "solver run on the single fixed case-study instance"
            ),
            "factorial_terms": (
                "three main effects and three second-order interactions"
            ),
            "effect_contrast": (
                "mean response at positive effect-coded term minus mean response "
                "at negative effect-coded term within each paired block"
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
    paths = (
        Path("scripts/reproduce/run_model_ablation.py"),
        Path("scripts/reproduce/model_ablation_analysis.py"),
        Path("scripts/reproduce/run_benchmark.py"),
        Path("scripts/reproduce/benchmark_suite.py"),
        Path("scripts/reproduce/benchmark_algorithms.py"),
        Path("scripts/reproduce/capacity_recovery.py"),
        Path("scripts/reproduce/dynamic_interaction_experiments.py"),
    )
    return {
        str(relative_path): hashlib.sha256((root / relative_path).read_bytes()).hexdigest()
        for relative_path in paths
    }


if __name__ == "__main__":
    main()
