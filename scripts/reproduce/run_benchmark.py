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
from scripts.reproduce.capacity_recovery import CapacityIndividual, _dominates


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

    records: list[tuple[BenchmarkSpec, int, int, AlgorithmRun]] = []
    instance_rows: list[dict[str, object]] = []
    total = sum(
        1 if algorithm not in STOCHASTIC_ALGORITHMS else solver_repeats
        for _spec in specs
        for _instance_seed in instance_seeds
        for algorithm in args.algorithms
    )
    run_idx = 0
    for spec in specs:
        for instance_seed in instance_seeds:
            instance = build_benchmark_instance(spec, instance_seed=instance_seed)
            nominal_fleet_capacity = sum(
                vehicle.capacity_ton * vehicle.count for vehicle in instance.vehicles
            )
            instance_rows.append(
                {
                    **spec.row(),
                    "instance_seed": instance_seed,
                    "instance": instance.base.name,
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
                    records.append((spec, instance_seed, solver_seed, result))
                    objectives = result.representative.objectives or (math.inf,) * 3
                    print(
                        f"  front={len(result.front)} evals={result.evaluations} "
                        f"unmet={objectives[0]:.4f} min_sat={-objectives[2]:.4f} "
                        f"runtime={result.runtime_seconds:.3f}s",
                        flush=True,
                    )

    run_rows, pareto_rows, convergence_rows = _result_rows(records)
    _attach_quality_indicators(records, run_rows)
    _write_csv(output_dir / "instances.csv", _unique_rows(instance_rows))
    _write_csv(output_dir / "runs.csv", run_rows)
    _write_csv(output_dir / "pareto_points.csv", pareto_rows)
    _write_csv(output_dir / "convergence.csv", convergence_rows)
    _write_csv(output_dir / "aggregate_by_size.csv", _aggregate_rows(run_rows))
    _write_manifest(
        output_dir / "experiment_manifest.json",
        args=args,
        specs=specs,
        instance_seeds=instance_seeds,
        solver_repeats=solver_repeats,
        budget=budget,
    )
    print(f"Done. Benchmark outputs written to {output_dir}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the unified multi-scale capacity-recovery benchmark.",
    )
    parser.add_argument("--suite", choices=["smoke", "benchmark", "publication"], default="smoke")
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


def _result_rows(
    records: list[tuple[BenchmarkSpec, int, int, AlgorithmRun]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    run_rows: list[dict[str, object]] = []
    pareto_rows: list[dict[str, object]] = []
    convergence_rows: list[dict[str, object]] = []
    for spec, instance_seed, solver_seed, result in records:
        representative = result.representative
        objectives = representative.objectives or (math.inf,) * 3
        metrics = representative.metrics or {}
        key = _run_key(spec.case_id, instance_seed, result.algorithm, solver_seed)
        run_rows.append(
            {
                "run_key": key,
                "case_id": spec.case_id,
                "source": spec.source,
                "size_group": spec.size_group,
                "num_nodes": spec.num_nodes,
                "instance_seed": instance_seed,
                "solver_seed": solver_seed,
                "algorithm": result.algorithm,
                "evaluations": result.evaluations,
                "runtime_seconds": result.runtime_seconds,
                "pareto_size": len(result.front),
                "unmet_area": objectives[0],
                "time_cost": objectives[1],
                "neg_min_satisfaction": objectives[2],
                "final_total_satisfaction": metrics.get("final_total_satisfaction", 0.0),
                "final_min_satisfaction": metrics.get("final_min_satisfaction", 0.0),
                "average_reachable_ratio": metrics.get("average_reachable_ratio", 0.0),
                "final_repaired_ratio": metrics.get("final_repaired_ratio", 0.0),
            }
        )
        for point_idx, individual in enumerate(result.front, start=1):
            point_objectives = individual.objectives or (math.inf,) * 3
            point_metrics = individual.metrics or {}
            pareto_rows.append(
                {
                    "run_key": key,
                    "case_id": spec.case_id,
                    "size_group": spec.size_group,
                    "instance_seed": instance_seed,
                    "solver_seed": solver_seed,
                    "algorithm": result.algorithm,
                    "point_id": point_idx,
                    "decision_hash": _decision_hash(individual),
                    "unmet_area": point_objectives[0],
                    "time_cost": point_objectives[1],
                    "neg_min_satisfaction": point_objectives[2],
                    "final_total_satisfaction": point_metrics.get("final_total_satisfaction", 0.0),
                    "final_min_satisfaction": point_metrics.get("final_min_satisfaction", 0.0),
                }
            )
        for row in result.convergence:
            convergence_rows.append(
                {
                    "run_key": key,
                    "case_id": spec.case_id,
                    "size_group": spec.size_group,
                    "instance_seed": instance_seed,
                    "solver_seed": solver_seed,
                    "algorithm": result.algorithm,
                    **row,
                }
            )
    return run_rows, pareto_rows, convergence_rows


def _attach_quality_indicators(
    records: list[tuple[BenchmarkSpec, int, int, AlgorithmRun]],
    run_rows: list[dict[str, object]],
) -> None:
    groups: dict[tuple[str, int], list[tuple[int, AlgorithmRun]]] = defaultdict(list)
    for idx, (spec, instance_seed, _solver_seed, result) in enumerate(records):
        groups[(spec.case_id, instance_seed)].append((idx, result))

    for grouped in groups.values():
        all_points = [
            individual.objectives
            for _idx, result in grouped
            for individual in result.front
            if individual.objectives is not None
        ]
        reference_front = _non_dominated(all_points)
        # Scale by the full observed objective range. A singleton pooled front
        # can otherwise create a zero range and numerically meaningless IGD.
        ideal, nadir = _bounds(all_points)
        normalized_reference = [_normalize(point, ideal, nadir) for point in reference_front]
        for row_idx, result in grouped:
            normalized = [
                _normalize(individual.objectives, ideal, nadir)
                for individual in result.front
                if individual.objectives is not None
            ]
            run_rows[row_idx]["hypervolume"] = hypervolume_3d(normalized, (1.1, 1.1, 1.1))
            run_rows[row_idx]["igd"] = inverted_generational_distance(
                normalized,
                normalized_reference,
            )
            run_rows[row_idx]["reference_front_size"] = len(reference_front)


def _non_dominated(points: Iterable[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    unique = sorted(set(points))
    return [
        point
        for idx, point in enumerate(unique)
        if not any(_dominates(other, point) for other_idx, other in enumerate(unique) if idx != other_idx)
    ]


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
) -> tuple[float, float, float]:
    return tuple(
        (point[idx] - ideal[idx]) / max(nadir[idx] - ideal[idx], 1e-12)
        for idx in range(3)
    )


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


def _aggregate_rows(run_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in run_rows:
        groups[(str(row["size_group"]), str(row["algorithm"]))].append(row)
    metrics = (
        "hypervolume",
        "igd",
        "runtime_seconds",
        "evaluations",
        "unmet_area",
        "time_cost",
        "final_total_satisfaction",
        "final_min_satisfaction",
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
            values = [float(row[metric]) for row in rows]
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
) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
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
    root = Path(__file__).resolve().parents[2]
    paths = (
        Path("scripts/reproduce/run_benchmark.py"),
        Path("scripts/reproduce/benchmark_suite.py"),
        Path("scripts/reproduce/benchmark_algorithms.py"),
        Path("scripts/reproduce/instance_generator.py"),
        Path("scripts/reproduce/capacity_recovery.py"),
    )
    hashes: dict[str, str] = {}
    for relative_path in paths:
        path = root / relative_path
        if path.is_file():
            hashes[str(relative_path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _run_key(case_id: str, instance_seed: int, algorithm: str, solver_seed: int) -> str:
    return f"{case_id}:i{instance_seed}:{algorithm}:s{solver_seed}"


def _decision_hash(individual: CapacityIndividual) -> str:
    payload = repr(
        (
            tuple(individual.repair_order),
            tuple(individual.team_assignment),
            tuple(individual.dispatch_priority),
        )
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


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
