from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.benchmark_algorithms import (
    ALGORITHMS,
    STOCHASTIC_ALGORITHMS,
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
    MODEL_VERSIONS,
    CapacityIndividual,
    EvaluationConfig,
    _dominates,
)
from scripts.reproduce.objective_precision import (
    EXACT_PRECISION,
    V2_PRECISION,
    ObjectivePrecision,
    effective_span,
    key_bounds,
    key_front,
    narrow_coordinates,
)
from scripts.reproduce.solution_io import (
    RunStore,
    SolutionIOError,
    build_run_record,
    decision_hash as solution_decision_hash,
    make_run_key,
    model_fingerprint,
    physical_instance_hash,
    run_summary_row,
    source_fingerprint,
    source_hashes,
    write_store_indexes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

# Files whose contents determine a run's numerical behaviour; hashed into the
# run key so a code change cannot silently reuse an older record.
SOURCE_FILES = (
    "scripts/reproduce/run_benchmark.py",
    "scripts/reproduce/benchmark_suite.py",
    "scripts/reproduce/benchmark_algorithms.py",
    "scripts/reproduce/capacity_recovery.py",
    "scripts/reproduce/instance_generator.py",
    "scripts/reproduce/model.py",
    "scripts/reproduce/solution_io.py",
    "scripts/reproduce/objective_precision.py",
    # A dependency change can move the last bits of every objective, so the
    # lock and the project declaration are part of the source fingerprint.
    "pyproject.toml",
    "uv.lock",
)


def main() -> None:
    args = _parse_args()
    specs = _select_specs(benchmark_specs(args.suite), args.cases)
    instance_seeds = args.instance_seeds or default_instance_seeds(args.suite)
    solver_repeats = args.solver_repeats or _default_solver_repeats(args.suite)
    budget = BenchmarkBudget(
        max_evaluations=args.max_evaluations or _default_evaluations(args.suite),
        pop_size=args.pop_size or _default_population(args.suite),
        crossover_probability=args.crossover_probability,
        mutation_probability=args.mutation_probability,
        alns_probability=args.alns_probability,
        alns_iterations=args.alns_iterations,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    evaluation = EvaluationConfig.for_version(args.model_version)
    store = RunStore(output_dir)
    budget_payload = asdict(budget)
    source_fp = source_fingerprint(REPO_ROOT, SOURCE_FILES)
    # Both checks run before any snapshot write: a rejected run must not have
    # already overwritten a stored instance or execution environment.
    store.check_source_consistency(source_fp)
    store.enforce_contract(
        entry_point="run_benchmark",
        fixed={
            "suite": args.suite,
            "model_version": args.model_version,
            "evaluation": evaluation.as_dict(),
            "evaluation_fingerprint": evaluation.fingerprint(),
            "budget": budget_payload,
            "source_fingerprint": source_fp,
        },
        varying={
            "algorithms": list(args.algorithms),
            "cases": [spec.case_id for spec in specs],
            "instance_seeds": list(instance_seeds),
            "solver_seed_start": args.solver_seed_start,
            "solver_repeats": solver_repeats,
        },
    )

    records: list[dict[str, object]] = []
    instance_rows: list[dict[str, object]] = []
    skipped = 0
    total = sum(
        1 if algorithm not in STOCHASTIC_ALGORITHMS else solver_repeats
        for _spec in specs
        for _instance_seed in instance_seeds
        for algorithm in args.algorithms
    )
    run_idx = 0
    for spec in specs:
        for instance_seed in instance_seeds:
            instance = build_benchmark_instance(
                spec,
                instance_seed=instance_seed,
                model_version=args.model_version,
            )
            instance_file = store.save_instance(instance)
            physical_hash = physical_instance_hash(instance)
            # A benchmark run plans and executes under the same model, so the
            # shared execution environment is the instance itself.
            store.save_execution_instance(instance)
            nominal_fleet_capacity = sum(
                vehicle.capacity_ton * vehicle.count for vehicle in instance.vehicles
            )
            instance_rows.append(
                {
                    **spec.row(),
                    "instance_seed": instance_seed,
                    "instance": instance.base.name,
                    "physical_instance_hash": physical_hash,
                    "edges": instance.base.graph.number_of_edges(),
                    "damaged_edges": len(instance.base.damaged_edges),
                    "suppliers": len(instance.base.suppliers),
                    "demands": len(instance.base.demands),
                    "repair_crews": instance.base.repair_crews,
                    "vehicles": sum(vehicle.count for vehicle in instance.vehicles),
                    "nominal_fleet_capacity_per_period": nominal_fleet_capacity,
                    "realized_fleet_capacity_ratio": (
                        nominal_fleet_capacity / max(instance.base.total_demand, 1e-9)
                    ),
                }
            )
            for algorithm in args.algorithms:
                repeats = solver_repeats if algorithm in STOCHASTIC_ALGORITHMS else 1
                for repeat in range(repeats):
                    run_idx += 1
                    solver_seed = args.solver_seed_start + instance_seed * 10_000 + repeat
                    run_key = make_run_key(
                        case_id=spec.case_id,
                        instance_seed=instance_seed,
                        algorithm=algorithm,
                        solver_seed=solver_seed,
                        solver_repeat=repeat,
                        budget=budget_payload,
                        model_fingerprint_value=model_fingerprint(instance),
                        source_fingerprint=source_fp,
                    )
                    if args.resume and store.has_complete_run(run_key):
                        records.append(store.load_run(run_key))
                        skipped += 1
                        print(
                            f"[{run_idx}/{total}] {run_key} already complete, skipped",
                            flush=True,
                        )
                        continue
                    print(
                        f"[{run_idx}/{total}] {spec.case_id}/instance={instance_seed} "
                        f"algorithm={algorithm}/solver={solver_seed}",
                        flush=True,
                    )
                    result = solve_benchmark_algorithm(
                        algorithm,
                        instance,
                        budget,
                        seed=solver_seed,
                    )
                    record = build_run_record(
                        run_key=run_key,
                        case_id=spec.case_id,
                        suite=args.suite,
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
                            "instance_file": instance_file,
                        },
                    )
                    store.save_run(record)
                    records.append(record)
                    objectives = result.representative.objectives or (math.inf,) * 3
                    print(
                        f"  front={len(result.front)} evals={result.evaluations} "
                        f"unmet={objectives[0]:.4f} min_sat={-objectives[2]:.4f} "
                        f"runtime={result.runtime_seconds:.3f}s "
                        f"stop={result.termination_reason}",
                        flush=True,
                    )

    # Summaries, the manifest and replay must cover exactly the same runs.
    # Deriving the run set from the directory rather than from this invocation
    # is what stops a resumed or extended experiment from hiding records that
    # replay would still read.
    directory_records = store.load_runs_for_experiment()
    reference_faces = _attach_pooled_quality(directory_records)
    for record in directory_records:
        # Rewrite each run once with its pooled quality indicators so a resumed
        # run does not need the whole directory to be re-scored.
        store.save_run(record)

    _write_csv(output_dir / "instances.csv", _unique_rows(instance_rows))
    write_store_indexes(
        store,
        directory_records,
        reference_front_by_case=reference_faces,
    )
    _write_csv(
        output_dir / "aggregate_by_size.csv",
        _aggregate_rows([run_summary_row(record) for record in directory_records]),
    )
    _write_manifest(
        output_dir / "experiment_manifest.json",
        args=args,
        specs=specs,
        instance_seeds=instance_seeds,
        solver_repeats=solver_repeats,
        budget=budget,
        evaluation=evaluation,
        source_fp=source_fp,
        planned_runs=total,
        completed_runs=len(directory_records),
        skipped_runs=skipped,
        runs_this_invocation=len(records),
    )
    print(
        f"Done. {len(records)} run records this invocation ({skipped} resumed); "
        f"{len(directory_records)} in {output_dir}"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the unified multi-scale capacity-recovery benchmark.",
    )
    parser.add_argument("--suite", choices=["smoke", "benchmark", "publication"], default="smoke")
    parser.add_argument(
        "--model-version",
        choices=list(MODEL_VERSIONS),
        default="legacy",
        help=(
            "Evaluation semantics. legacy keeps the historical global "
            "supply/demand cap and end-of-period dispatch; v2 uses the frozen "
            "period-start semantics in docs/model_v2_contract.md."
        ),
    )
    parser.add_argument("--cases", nargs="*", help="Optional case IDs, e.g. S025 M100 L400.")
    parser.add_argument("--instance-seeds", type=int, nargs="*")
    parser.add_argument("--solver-repeats", type=int)
    parser.add_argument("--solver-seed-start", type=int, default=50_000)
    parser.add_argument("--algorithms", nargs="+", choices=ALGORITHMS, default=list(ALGORITHMS))
    parser.add_argument("--max-evaluations", type=int)
    parser.add_argument("--pop-size", type=int)
    parser.add_argument("--crossover-probability", type=float, default=0.90)
    parser.add_argument("--mutation-probability", type=float, default=0.20)
    parser.add_argument("--alns-probability", type=float, default=0.35)
    parser.add_argument("--alns-iterations", type=int, default=4)
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Skip runs whose complete record already exists with exactly "
            "matching instance, model, algorithm, budget and source fingerprint."
        ),
    )
    parser.add_argument("--output-dir", default="outputs/benchmark")
    args = parser.parse_args()
    if args.solver_repeats is not None and args.solver_repeats < 1:
        parser.error("--solver-repeats must be positive")
    if args.max_evaluations is not None and args.max_evaluations < 1:
        parser.error("--max-evaluations must be positive")
    if args.pop_size is not None and args.pop_size < 2:
        parser.error("--pop-size must be at least 2")
    if args.alns_iterations < 0:
        parser.error("--alns-iterations must be non-negative")
    for value, name in (
        (args.crossover_probability, "--crossover-probability"),
        (args.mutation_probability, "--mutation-probability"),
        (args.alns_probability, "--alns-probability"),
    ):
        if not 0.0 <= value <= 1.0:
            parser.error(f"{name} must be in [0, 1]")
    return args


def _select_specs(specs: list[BenchmarkSpec], case_ids: list[str] | None) -> list[BenchmarkSpec]:
    if not case_ids:
        return specs
    requested = set(case_ids)
    selected = [spec for spec in specs if spec.case_id in requested]
    missing = requested - {spec.case_id for spec in selected}
    if missing:
        raise SystemExit(f"Unknown case IDs: {', '.join(sorted(missing))}")
    return selected


def _default_evaluations(suite: str) -> int:
    return {"smoke": 12, "benchmark": 500, "publication": 10_000}[suite]


def _default_population(suite: str) -> int:
    return {"smoke": 4, "benchmark": 32, "publication": 100}[suite]


def _default_solver_repeats(suite: str) -> int:
    return {"smoke": 1, "benchmark": 10, "publication": 30}[suite]


def _attach_pooled_quality(
    records: list[dict[str, object]],
) -> dict[tuple[str, int], dict[str, object]]:
    """Score every run against one pooled front per benchmark instance.

    Pooling across algorithms and repeats keeps a single normalization and a
    single reference front, so no run is scored against a reference it chose.
    """
    groups: dict[tuple[str, int], list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[(str(record["case_id"]), int(record["instance_seed"]))].append(index)

    reference_faces: dict[tuple[str, int], dict[str, object]] = {}
    for key, indices in groups.items():
        fronts = [
            [
                tuple(solution["objectives"])
                for solution in (records[index].get("pareto_front") or [])
            ]
            for index in indices
        ]
        # Every run pooling into one reference front shares one model version,
        # so the resolution is unambiguous; assert it rather than assume it.
        versions = {
            (records[index].get("evaluation") or {}).get("model_version")
            for index in indices
        }
        if len(versions) != 1:
            raise SolutionIOError(
                f"cannot pool quality indicators across model versions {sorted(versions)} "
                f"for {key}"
            )
        precision = (
            V2_PRECISION if versions == {"v2"} else EXACT_PRECISION
        )
        quality_rows, metadata = pooled_quality_indicators(fronts, precision)
        for index, quality in zip(indices, quality_rows):
            records[index].update(quality)
            records[index]["quality_precision"] = metadata["precision"]["label"]
            records[index]["quality_effective_dimensions"] = metadata[
                "effective_dimensions"
            ]
        reference_faces[key] = {
            "size": metadata["reference_front_size"],
            "degenerate_dimensions": metadata["degenerate_dimensions"],
            "effective_dimensions": metadata["effective_dimensions"],
        }
    return reference_faces


def _non_dominated(
    points: Iterable[tuple[float, float, float]],
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> list[tuple[float, float, float]]:
    """One representative raw point per surviving comparison key.

    De-duplication is by comparison key, not by raw tuple: two points that are
    the same point at the pinned resolution must yield one entry, and the
    survivor is the lowest raw tuple so input order cannot change the result.
    """
    candidates = list(points)
    surviving = set(key_front(candidates, precision))
    chosen: dict[tuple, tuple[float, float, float]] = {}
    for point in sorted(candidates):
        key = precision.key(point)
        if key in surviving:
            chosen.setdefault(key, point)
    return [chosen[key] for key in sorted(chosen)]


def _bounds(
    points: list[tuple[float, float, float]],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    ideal = tuple(min(point[idx] for point in points) for idx in range(3))
    nadir = tuple(max(point[idx] for point in points) for idx in range(3))
    return ideal, nadir


def _normalize(
    point: tuple[float, float, float],
    ideal: tuple[float, ...],
    nadir: tuple[float, ...],
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> tuple[float, float, float]:
    """Min-max normalize against one shared reference frame.

    Each dimension is divided by its *effective* span: a dimension whose
    observed range is below the pinned resolution is floored at the resolution
    instead of being divided by a near-zero range, which would otherwise turn
    rounding noise into the dominant component of the distance.
    """
    normalized = []
    for idx in range(3):
        span, _floored = effective_span(
            ideal[idx],
            nadir[idx],
            precision.resolutions[idx],
        )
        normalized.append((point[idx] - ideal[idx]) / max(span, 1e-12))
    return tuple(normalized)


def hypervolume_3d(
    points: list[tuple[float, float, float]],
    reference: tuple[float, float, float],
) -> float:
    """Exact dominated hypervolume for a minimization problem in three dimensions."""
    clipped = sorted(
        {
            tuple(min(max(value, 0.0), reference[idx]) for idx, value in enumerate(point))
            for point in points
            if all(point[idx] <= reference[idx] for idx in range(3))
        }
    )
    if not clipped:
        return 0.0
    volume = 0.0
    x_values = sorted({point[0] for point in clipped})
    for idx, x_value in enumerate(x_values):
        next_x = x_values[idx + 1] if idx + 1 < len(x_values) else reference[0]
        active_yz = [(point[1], point[2]) for point in clipped if point[0] <= x_value]
        volume += max(0.0, next_x - x_value) * _hypervolume_2d(
            active_yz,
            (reference[1], reference[2]),
        )
    return volume


def _hypervolume_2d(
    points: list[tuple[float, float]],
    reference: tuple[float, float],
) -> float:
    area = 0.0
    best_y = reference[1]
    for x_value, y_value in sorted(set(points)):
        if y_value < best_y:
            area += max(0.0, reference[0] - x_value) * (best_y - y_value)
            best_y = y_value
    return area


def inverted_generational_distance(
    points: list[tuple[float, float, float]],
    reference_front: list[tuple[float, float, float]],
) -> float:
    if not points or not reference_front:
        return math.inf
    distances = [
        min(math.dist(reference, point) for point in points)
        for reference in reference_front
    ]
    return statistics.fmean(distances)


def pooled_quality_indicators(
    fronts: list[list[tuple[float, float, float]]],
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> tuple[list[dict[str, float]], dict[str, object]]:
    """Calculate normalized HV/IGD against one front pooled across all runs.

    Raw objectives are never overwritten; the normalized values are derived
    here and the metadata records the raw range of every dimension and which
    dimensions were too flat to carry information at the pinned resolution.
    """
    all_points = [point for front in fronts for point in front]
    if not all_points:
        raise ValueError("at least one objective point is required")

    # Everything below happens in comparison coordinates: the integer grid the
    # resolution defines. Raw objectives are only ever read, never rewritten.
    all_keys = [precision.key(point) for point in all_points]
    reference_keys = key_front(all_points, precision)
    # Use the full observed key range, not only the non-dominated points, so
    # every compared run uses exactly the same normalization.
    ideal_key, nadir_key = key_bounds(all_keys)
    key_spans = tuple(nadir_key[idx] - ideal_key[idx] for idx in range(3))
    degenerate = [idx for idx in range(3) if key_spans[idx] <= 0]
    normalized_reference = narrow_coordinates(reference_keys, ideal_key, nadir_key)

    quality_rows = []
    for front in fronts:
        coordinates = narrow_coordinates(
            [precision.key(point) for point in front],
            ideal_key,
            nadir_key,
        )
        quality_rows.append(
            {
                "hypervolume": hypervolume_3d(coordinates, (1.1, 1.1, 1.1)),
                "igd": inverted_generational_distance(
                    coordinates,
                    normalized_reference,
                ),
            }
        )

    # Raw bounds are reported for auditing; they are not what distances are
    # measured in.
    raw_ideal, raw_nadir = _bounds(all_points)
    metadata: dict[str, object] = {
        "reference_front_size": len(reference_keys),
        "ideal": raw_ideal,
        "nadir": raw_nadir,
        "raw_ranges": tuple(raw_nadir[idx] - raw_ideal[idx] for idx in range(3)),
        "ideal_key": ideal_key,
        "nadir_key": nadir_key,
        "key_spans": key_spans,
        "degenerate_dimensions": degenerate,
        "effective_dimensions": 3 - len(degenerate),
        "coordinate_space": "quantized comparison keys",
        "precision": precision.as_dict(),
        "precision_fingerprint": precision.fingerprint(),
        "reference_point_normalized": (1.1, 1.1, 1.1),
    }
    return quality_rows, metadata


def _aggregate_rows(run_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in run_rows:
        groups[(str(row["size_group"]), str(row["algorithm"]))].append(row)
    metrics = (
        "hypervolume",
        "igd",
        "runtime_seconds",
        "evaluations",
        "pareto_size",
        "F1",
        "F2",
        "F3",
        "final_total_satisfaction",
        "final_min_satisfaction",
        "zero_service_ratio",
    )
    output: list[dict[str, object]] = []
    for (size_group, algorithm), rows in sorted(groups.items()):
        aggregate: dict[str, object] = {
            "size_group": size_group,
            "algorithm": algorithm,
            "runs": len(rows),
            "instances": len({(row["case_id"], row["instance_seed"]) for row in rows}),
        }
        for metric in metrics:
            values = [
                float(row[metric])
                for row in rows
                if row.get(metric) is not None
            ]
            if not values:
                continue
            aggregate[f"{metric}_mean"] = statistics.fmean(values)
            aggregate[f"{metric}_sd"] = statistics.stdev(values) if len(values) > 1 else 0.0
            aggregate[f"{metric}_median"] = statistics.median(values)
        output.append(aggregate)
    return output


def _write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    specs: list[BenchmarkSpec],
    instance_seeds: list[int],
    solver_repeats: int,
    budget: BenchmarkBudget,
    evaluation: EvaluationConfig,
    source_fp: str,
    planned_runs: int,
    completed_runs: int,
    skipped_runs: int,
    runs_this_invocation: int,
) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_version": evaluation.model_version,
        "evaluation": evaluation.as_dict(),
        "evaluation_fingerprint": evaluation.fingerprint(),
        "source_fingerprint": source_fp,
        "planned_runs": planned_runs,
        "runs_in_directory": completed_runs,
        "runs_this_invocation": runs_this_invocation,
        "resumed_runs": skipped_runs,
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "source_files_sha256": _source_hashes(),
        "python": sys.version,
        "platform": platform.platform(),
        "suite": args.suite,
        "cases": [spec.row() for spec in specs],
        "instance_seeds": instance_seeds,
        "solver_seed_start": args.solver_seed_start,
        "solver_repeats_stochastic": solver_repeats,
        "deterministic_repeats": 1,
        "algorithms": args.algorithms,
        "budget": asdict(budget),
        "objectives": ["min_unmet_area", "min_time_cost", "min_neg_min_satisfaction"],
        "representative_rule": (
            "lexicographic min of (F3, F1, F2), applied before any replay and "
            "recorded per solution as representative_selected_before_replay"
        ),
        "quality_indicators": {
            "hypervolume": "exact normalized 3D HV; pooled reference point (1.1, 1.1, 1.1)",
            "igd": "normalized Euclidean IGD to pooled non-dominated front per instance",
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
    return source_hashes(REPO_ROOT, SOURCE_FILES)


def _decision_hash(individual: CapacityIndividual) -> str:
    return solution_decision_hash(individual)


def _unique_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[tuple[str, object], ...]] = set()
    output: list[dict[str, object]] = []
    for row in rows:
        signature = tuple(row.items())
        if signature not in seen:
            seen.add(signature)
            output.append(row)
    return output


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
