from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import sys
from collections import defaultdict
from itertools import product
from datetime import datetime, timezone
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.objective_precision import EXACT_PRECISION, V2_PRECISION
from scripts.reproduce.run_benchmark import (
    _non_dominated,
    _write_csv,
    pooled_quality_indicators,
)


FACTOR_COLUMNS = (
    "progressive_recovery",
    "heterogeneous_vehicle_thresholds",
    "edge_capacity_constraint",
)

FACTOR_TERMS = (
    ("progressive_recovery", ("progressive_recovery",)),
    (
        "heterogeneous_vehicle_thresholds",
        ("heterogeneous_vehicle_thresholds",),
    ),
    ("edge_capacity_constraint", ("edge_capacity_constraint",)),
    (
        "progressive_recovery:heterogeneous_vehicle_thresholds",
        ("progressive_recovery", "heterogeneous_vehicle_thresholds"),
    ),
    (
        "progressive_recovery:edge_capacity_constraint",
        ("progressive_recovery", "edge_capacity_constraint"),
    ),
    (
        "heterogeneous_vehicle_thresholds:edge_capacity_constraint",
        ("heterogeneous_vehicle_thresholds", "edge_capacity_constraint"),
    ),
)

PRIMARY_METRICS = (
    "hypervolume",
    "igd",
    "F1",
    "F2",
    "F3",
)

MECHANISM_METRICS = (
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

METRICS = PRIMARY_METRICS + MECHANISM_METRICS

HIGHER_IS_BETTER = frozenset(
    {
        "hypervolume",
        "final_total_satisfaction",
        "final_min_satisfaction",
        "average_reachable_ratio",
        "final_repaired_ratio",
    }
)

LOWER_IS_BETTER = frozenset(
    {
        "igd",
        "F1",
        "F2",
        "F3",
        "max_edge_utilization",
        "high_utilization_edge_periods",
        "capacity_blocked_tons",
        "total_delivery_time",
    }
)

EXPECTED_MODEL_IDS = frozenset(
    f"PR{progressive}_HT{heterogeneous}_EC{capacity}"
    for progressive, heterogeneous, capacity in product((0, 1), repeat=3)
)

POOLED_QUALITY_COLUMNS = frozenset(
    {
        "hypervolume",
        "igd",
        "pooled_reference_front_size",
        "pooled_ideal_F1",
        "pooled_ideal_F2",
        "pooled_ideal_F3",
        "pooled_nadir_F1",
        "pooled_nadir_F2",
        "pooled_nadir_F3",
    }
)


def analyze_model_ablation(
    run_rows: list[dict[str, object]],
    *,
    bootstrap_samples: int = 5_000,
    permutation_samples: int = 20_000,
    analysis_seed: int = 202_608_31,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Analyze a complete paired 2^3 factorial without treating repeats as instances."""
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")
    if permutation_samples < 1:
        raise ValueError("permutation_samples must be positive")
    completeness_rows = _validate_complete_blocks(run_rows)
    model_summary = _model_summary(
        run_rows,
        bootstrap_samples=bootstrap_samples,
        analysis_seed=analysis_seed,
    )
    raw_effects = _raw_factor_effects(run_rows)
    effect_summary = _factor_effect_summary(
        raw_effects,
        bootstrap_samples=bootstrap_samples,
        permutation_samples=permutation_samples,
        analysis_seed=analysis_seed,
    )
    return model_summary, raw_effects, effect_summary, completeness_rows


def merge_model_ablation_shards(
    input_paths: list[Path],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Merge shards and recompute per-instance pooled HV/IGD across all repeats."""
    by_run_key: dict[str, dict[str, object]] = {}
    by_point_key: dict[tuple[str, str], dict[str, object]] = {}
    for input_path in input_paths:
        with input_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                run_key = str(row["run_key"])
                if (
                    run_key in by_run_key
                    and not _run_rows_compatible(by_run_key[run_key], row)
                ):
                    raise ValueError(f"conflicting duplicate run_key: {run_key}")
                by_run_key.setdefault(run_key, row)
        pareto_path = input_path.with_name("pareto_points.csv")
        if not pareto_path.is_file():
            raise ValueError(f"missing paired Pareto file: {pareto_path}")
        with pareto_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                point_key = (str(row["run_key"]), str(row["decision_hash"]))
                if point_key in by_point_key and by_point_key[point_key] != row:
                    raise ValueError(
                        "conflicting duplicate Pareto point: " + ":".join(point_key)
                    )
                by_point_key[point_key] = row

    run_rows = sorted(by_run_key.values(), key=lambda row: str(row["run_key"]))
    pareto_rows = sorted(
        by_point_key.values(),
        key=lambda row: (str(row["run_key"]), str(row["decision_hash"])),
    )
    fronts_by_run: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for row in pareto_rows:
        fronts_by_run[str(row["run_key"])].append(
            (
                _finite_float(row, "F1"),
                _finite_float(row, "F2"),
                _finite_float(row, "F3"),
            )
        )
    missing_fronts = [
        str(row["run_key"])
        for row in run_rows
        if not fronts_by_run[str(row["run_key"])]
    ]
    if missing_fronts:
        raise ValueError("runs without Pareto points: " + ", ".join(missing_fronts[:10]))

    groups: dict[tuple[str, int], list[int]] = defaultdict(list)
    for index, row in enumerate(run_rows):
        groups[(str(row["case_id"]), int(row["instance_seed"]))].append(index)
    reference_rows: list[dict[str, object]] = []
    for (case_id, instance_seed), indices in sorted(groups.items()):
        fronts = [
            fronts_by_run[str(run_rows[index]["run_key"])]
            for index in indices
        ]
        # The resolution is not optional here: pooling must use the same
        # comparison coordinates the runs were searched under, never the
        # exact-float default.
        versions = {
            (run_rows[index].get("model_version") or "legacy") for index in indices
        }
        if len(versions) != 1:
            raise ValueError(
                f"cannot pool quality indicators across model versions "
                f"{sorted(versions)} for {case_id}/instance={instance_seed}"
            )
        precision = V2_PRECISION if versions == {"v2"} else EXACT_PRECISION
        qualities, metadata = pooled_quality_indicators(fronts, precision)
        ideal = metadata["ideal"]
        nadir = metadata["nadir"]
        for index, quality in zip(indices, qualities):
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
                    "pooled_quality_precision": metadata["precision"]["label"],
                    "pooled_effective_dimensions": metadata["effective_dimensions"],
                    "pooled_key_span_F1": metadata["key_spans"][0],
                    "pooled_key_span_F2": metadata["key_spans"][1],
                    "pooled_key_span_F3": metadata["key_spans"][2],
                }
            )
        pooled_points = [point for front in fronts for point in front]
        for point_id, point in enumerate(
            _non_dominated(pooled_points, precision), start=1
        ):
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
    return run_rows, pareto_rows, reference_rows


def _run_rows_compatible(
    left: dict[str, object],
    right: dict[str, object],
) -> bool:
    keys = (set(left) | set(right)) - POOLED_QUALITY_COLUMNS
    return all(str(left.get(key, "")) == str(right.get(key, "")) for key in keys)


def _validate_complete_blocks(
    run_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not run_rows:
        raise ValueError("model ablation contains no run rows")
    blocks: dict[tuple[str, int, int], list[dict[str, object]]] = defaultdict(list)
    for row in run_rows:
        key = (
            str(row["case_id"]),
            int(row["instance_seed"]),
            int(row["solver_seed"]),
        )
        blocks[key].append(row)

    completeness_rows: list[dict[str, object]] = []
    errors = []
    for (case_id, instance_seed, solver_seed), rows in sorted(blocks.items()):
        model_ids = [str(row["model_id"]) for row in rows]
        unique_ids = set(model_ids)
        missing = sorted(EXPECTED_MODEL_IDS - unique_ids)
        duplicates = sorted(
            model_id
            for model_id in unique_ids
            if model_ids.count(model_id) > 1
        )
        evaluation_counts = {int(row["evaluations"]) for row in rows}
        evaluation_budgets = {int(row["max_evaluations"]) for row in rows}
        algorithms = {str(row["algorithm"]) for row in rows}
        complete = (
            not missing
            and not duplicates
            and len(rows) == 8
            and len(evaluation_counts) == 1
            and len(evaluation_budgets) == 1
            and len(algorithms) == 1
            and algorithms == {"nsga2_alns"}
        )
        completeness_rows.append(
            {
                "case_id": case_id,
                "instance_seed": instance_seed,
                "solver_seed": solver_seed,
                "rows": len(rows),
                "unique_models": len(unique_ids),
                "missing_models": " ".join(missing),
                "duplicate_models": " ".join(duplicates),
                "algorithms": " ".join(sorted(algorithms)),
                "evaluation_counts": " ".join(
                    str(value) for value in sorted(evaluation_counts)
                ),
                "evaluation_budgets": " ".join(
                    str(value) for value in sorted(evaluation_budgets)
                ),
                "complete": int(complete),
            }
        )
        if not complete:
            errors.append(
                f"{case_id}/instance={instance_seed}/solver={solver_seed}"
            )
    if errors:
        raise ValueError(
            "incomplete or unpaired 2^3 blocks: " + ", ".join(errors[:10])
        )
    return completeness_rows


def _model_summary(
    run_rows: list[dict[str, object]],
    *,
    bootstrap_samples: int,
    analysis_seed: int,
) -> list[dict[str, object]]:
    unit_values: dict[
        tuple[str, str, str, str, str],
        list[float],
    ] = defaultdict(list)
    for row in run_rows:
        case_id = str(row["case_id"])
        source = str(row["source"])
        model_id = str(row["model_id"])
        if source == "wenchuan":
            analysis_unit = "solver_run"
            unit_id = f"s{int(row['solver_seed'])}"
        else:
            analysis_unit = "instance_mean"
            unit_id = f"i{int(row['instance_seed'])}"
        for metric in METRICS:
            value = _finite_float(row, metric)
            unit_values[(case_id, model_id, metric, analysis_unit, unit_id)].append(value)

    grouped: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for (case_id, model_id, metric, analysis_unit, _unit_id), values in unit_values.items():
        grouped[(case_id, model_id, metric, analysis_unit)].append(
            statistics.fmean(values)
        )

    output = []
    for key, values in sorted(grouped.items()):
        case_id, model_id, metric, analysis_unit = key
        seed = _stable_seed(analysis_seed, "model", *key)
        summary = _distribution_summary(
            values,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )
        output.append(
            {
                "case_id": case_id,
                "model_id": model_id,
                "metric": metric,
                "direction": _metric_direction(metric),
                "analysis_unit": analysis_unit,
                **summary,
            }
        )
    return output


def _raw_factor_effects(
    run_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    blocks: dict[tuple[str, str, int, int], list[dict[str, object]]] = defaultdict(list)
    for row in run_rows:
        key = (
            str(row["case_id"]),
            str(row["source"]),
            int(row["instance_seed"]),
            int(row["solver_seed"]),
        )
        blocks[key].append(row)

    output = []
    for (case_id, source, instance_seed, solver_seed), rows in sorted(blocks.items()):
        for term_name, factors in FACTOR_TERMS:
            signs = [
                math.prod(
                    1 if int(row[factor]) == 1 else -1
                    for factor in factors
                )
                for row in rows
            ]
            for metric in METRICS:
                values = [_finite_float(row, metric) for row in rows]
                positive = [value for value, sign in zip(values, signs) if sign > 0]
                negative = [value for value, sign in zip(values, signs) if sign < 0]
                effect = statistics.fmean(positive) - statistics.fmean(negative)
                direction = _metric_direction(metric)
                output.append(
                    {
                        "case_id": case_id,
                        "source": source,
                        "instance_seed": instance_seed,
                        "solver_seed": solver_seed,
                        "term": term_name,
                        "term_order": len(factors),
                        "metric": metric,
                        "direction": direction,
                        "effect_high_minus_low": effect,
                        "oriented_effect": (
                            effect
                            if direction == "higher"
                            else -effect
                            if direction == "lower"
                            else None
                        ),
                    }
                )
    return output


def _factor_effect_summary(
    raw_effects: list[dict[str, object]],
    *,
    bootstrap_samples: int,
    permutation_samples: int,
    analysis_seed: int,
) -> list[dict[str, object]]:
    units: dict[
        tuple[str, str, str, int, str, str],
        list[float],
    ] = defaultdict(list)
    for row in raw_effects:
        source = str(row["source"])
        if source == "wenchuan":
            analysis_unit = "solver_run"
            unit_id = f"s{int(row['solver_seed'])}"
        else:
            analysis_unit = "instance_mean"
            unit_id = f"i{int(row['instance_seed'])}"
        key = (
            str(row["case_id"]),
            str(row["term"]),
            str(row["metric"]),
            int(row["term_order"]),
            str(row["direction"]),
            analysis_unit + ":" + unit_id,
        )
        units[key].append(float(row["effect_high_minus_low"]))

    grouped: dict[
        tuple[str, str, str, int, str, str],
        list[float],
    ] = defaultdict(list)
    for key, values in units.items():
        case_id, term, metric, term_order, direction, unit = key
        analysis_unit, _unit_id = unit.split(":", 1)
        grouped[(case_id, term, metric, term_order, direction, analysis_unit)].append(
            statistics.fmean(values)
        )

    output = []
    for key, values in sorted(grouped.items()):
        case_id, term, metric, term_order, direction, analysis_unit = key
        seed = _stable_seed(analysis_seed, "effect", *key)
        summary = _distribution_summary(
            values,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )
        mean_effect = float(summary["mean"])
        sd = float(summary["sd"])
        p_value = _sign_flip_p_value(
            values,
            samples=permutation_samples,
            seed=seed + 1,
        )
        output.append(
            {
                "case_id": case_id,
                "term": term,
                "term_order": term_order,
                "metric": metric,
                "direction": direction,
                "analysis_unit": analysis_unit,
                **summary,
                "oriented_mean_effect": (
                    mean_effect
                    if direction == "higher"
                    else -mean_effect
                    if direction == "lower"
                    else None
                ),
                "standardized_paired_effect_dz": (
                    mean_effect / sd if sd > 1e-12 else None
                ),
                "sign_flip_p_value": p_value,
                "holm_adjusted_p_value": None,
            }
        )
    _attach_holm_adjustment(output)
    return output


def _distribution_summary(
    values: list[float],
    *,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, object]:
    ordered = sorted(values)
    mean = statistics.fmean(ordered)
    ci_low, ci_high = _bca_mean_ci(
        ordered,
        samples=bootstrap_samples,
        seed=seed,
    )
    return {
        "n_units": len(ordered),
        "mean": mean,
        "sd": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "median": statistics.median(ordered),
        "q1": _percentile(ordered, 0.25),
        "q3": _percentile(ordered, 0.75),
        "ci95_bca_low": ci_low,
        "ci95_bca_high": ci_high,
        "minimum": ordered[0],
        "maximum": ordered[-1],
    }


def _bca_mean_ci(
    values: list[float],
    *,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    if len(values) < 2 or max(values) - min(values) <= 1e-15:
        value = statistics.fmean(values)
        return value, value
    rng = random.Random(seed)
    observed = statistics.fmean(values)
    count = len(values)
    boot = sorted(
        statistics.fmean(rng.choices(values, k=count))
        for _ in range(samples)
    )
    proportion_less = (
        sum(value < observed for value in boot)
        + 0.5 * sum(value == observed for value in boot)
    ) / samples
    epsilon = 0.5 / samples
    proportion_less = min(max(proportion_less, epsilon), 1.0 - epsilon)
    normal = statistics.NormalDist()
    bias = normal.inv_cdf(proportion_less)

    jackknife = [
        statistics.fmean(values[:idx] + values[idx + 1 :])
        for idx in range(count)
    ]
    jack_mean = statistics.fmean(jackknife)
    numerator = sum((jack_mean - value) ** 3 for value in jackknife)
    denominator = 6.0 * (
        sum((jack_mean - value) ** 2 for value in jackknife) ** 1.5
    )
    acceleration = numerator / denominator if denominator > 1e-15 else 0.0

    adjusted = []
    for alpha in (0.025, 0.975):
        z_alpha = normal.inv_cdf(alpha)
        denominator_term = 1.0 - acceleration * (bias + z_alpha)
        if abs(denominator_term) <= 1e-12:
            probability = alpha
        else:
            probability = normal.cdf(
                bias + (bias + z_alpha) / denominator_term
            )
        adjusted.append(min(max(probability, 0.0), 1.0))
    return _percentile(boot, adjusted[0]), _percentile(boot, adjusted[1])


def _sign_flip_p_value(
    values: list[float],
    *,
    samples: int,
    seed: int,
) -> float | None:
    if len(values) < 2:
        return None
    observed = abs(statistics.fmean(values))
    if max(abs(value) for value in values) <= 1e-15:
        return 1.0
    tolerance = 1e-15
    if len(values) <= 16:
        extreme = 0
        total = 1 << len(values)
        for mask in range(total):
            permuted = statistics.fmean(
                value if mask & (1 << idx) else -value
                for idx, value in enumerate(values)
            )
            if abs(permuted) >= observed - tolerance:
                extreme += 1
        return extreme / total
    rng = random.Random(seed)
    extreme = 0
    for _ in range(samples):
        permuted = statistics.fmean(
            value if rng.random() < 0.5 else -value
            for value in values
        )
        if abs(permuted) >= observed - tolerance:
            extreme += 1
    return (extreme + 1) / (samples + 1)


def _attach_holm_adjustment(rows: list[dict[str, object]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row["sign_flip_p_value"] is not None:
            groups[(str(row["case_id"]), str(row["metric"]))].append(row)
    for grouped in groups.values():
        ordered = sorted(grouped, key=lambda row: float(row["sign_flip_p_value"]))
        running = 0.0
        count = len(ordered)
        for index, row in enumerate(ordered):
            adjusted = min(
                1.0,
                (count - index) * float(row["sign_flip_p_value"]),
            )
            running = max(running, adjusted)
            row["holm_adjusted_p_value"] = running


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot calculate a percentile of an empty sequence")
    if len(values) == 1:
        return values[0]
    position = min(max(probability, 0.0), 1.0) * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _finite_float(row: dict[str, object], key: str) -> float:
    value = float(row[key])
    if not math.isfinite(value):
        raise ValueError(f"non-finite {key} in run {row.get('run_key')}")
    return value


def _metric_direction(metric: str) -> str:
    if metric in HIGHER_IS_BETTER:
        return "higher"
    if metric in LOWER_IS_BETTER:
        return "lower"
    return "descriptive"


def _stable_seed(base: int, *parts: object) -> int:
    payload = "|".join(str(part) for part in (base, *parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze a complete paired 2^3 model-ablation result file.",
    )
    parser.add_argument(
        "--input",
        nargs="*",
        help="One or more model_ablation.csv shard files.",
    )
    parser.add_argument(
        "--input-root",
        help="Recursively discover model_ablation.csv shard files below this directory.",
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--bootstrap-samples", type=int, default=5_000)
    parser.add_argument("--permutation-samples", type=int, default=20_000)
    parser.add_argument("--analysis-seed", type=int, default=202_608_31)
    args = parser.parse_args()
    input_paths = [Path(value) for value in (args.input or [])]
    if args.input_root:
        input_paths.extend(sorted(Path(args.input_root).rglob("model_ablation.csv")))
    input_paths = sorted(set(path.resolve() for path in input_paths))
    if not input_paths:
        parser.error("provide --input or --input-root")
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else input_paths[0].parent
    )
    rows, pareto_rows, reference_rows = merge_model_ablation_shards(input_paths)
    model_summary, raw_effects, effect_summary, completeness = analyze_model_ablation(
        rows,
        bootstrap_samples=args.bootstrap_samples,
        permutation_samples=args.permutation_samples,
        analysis_seed=args.analysis_seed,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "model_ablation.csv", rows)
    _write_csv(output_dir / "pareto_points.csv", pareto_rows)
    _write_csv(output_dir / "pooled_reference_front.csv", reference_rows)
    _write_csv(output_dir / "model_summary.csv", model_summary)
    _write_csv(output_dir / "factor_effects_raw.csv", raw_effects)
    _write_csv(output_dir / "factor_effects.csv", effect_summary)
    _write_csv(output_dir / "factorial_completeness.csv", completeness)
    _write_analysis_manifest(
        output_dir / "analysis_manifest.json",
        input_paths=input_paths,
        run_rows=rows,
        bootstrap_samples=args.bootstrap_samples,
        permutation_samples=args.permutation_samples,
        analysis_seed=args.analysis_seed,
    )


def _write_analysis_manifest(
    path: Path,
    *,
    input_paths: list[Path],
    run_rows: list[dict[str, object]],
    bootstrap_samples: int,
    permutation_samples: int,
    analysis_seed: int,
) -> None:
    source_path = Path(__file__).resolve()
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "source_file_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "input_files_sha256": {
            str(input_path): hashlib.sha256(input_path.read_bytes()).hexdigest()
            for input_path in input_paths
        },
        "run_rows": len(run_rows),
        "cases": sorted({str(row["case_id"]) for row in run_rows}),
        "instance_seeds_by_case": {
            case_id: sorted(
                {
                    int(row["instance_seed"])
                    for row in run_rows
                    if str(row["case_id"]) == case_id
                }
            )
            for case_id in sorted({str(row["case_id"]) for row in run_rows})
        },
        "pooled_quality_recomputed_from_all_input_pareto_points": True,
        "bootstrap_samples": bootstrap_samples,
        "permutation_samples": permutation_samples,
        "analysis_seed": analysis_seed,
        "analysis_units": {
            "synthetic": "instance mean across paired solver repeats",
            "wenchuan": "solver run on one fixed case-study instance",
        },
        "multiple_comparison_correction": (
            "Holm across six factorial terms within case and metric"
        ),
    }
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
