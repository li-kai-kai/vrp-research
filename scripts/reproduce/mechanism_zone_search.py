"""Stage 2 and 3 of the mechanism applicability diagnostic.

Stage 2 asks a narrow question: once the zones are known, does a planner that
*knows* about a mechanism find different decisions in a binding zone than in an
inactive one? Stage 3 puts every saved planning decision back into one common
Full execution environment and measures what ignoring the mechanism costs.

This is a diagnostic harness, not a new benchmark. It reuses
``solve_benchmark_algorithm``, ``model_factor_variant`` and the shared
evaluator unchanged, and it does not touch the approved entry points. Its
scenarios are stress configurations whose zones are *measured* here and
reported, never assumed: ``zone_exposure.csv`` records where each zone
actually landed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ == "" or __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.benchmark_algorithms import (
    BenchmarkBudget,
    solve_benchmark_algorithm,
)
from scripts.reproduce.benchmark_suite import benchmark_specs
from scripts.reproduce.capacity_recovery import (
    CapacityIndividual,
    evaluate_capacity_solution_detailed,
    model_factor_variant,
)
from scripts.reproduce.mechanism_applicability import (
    DIAGNOSTIC_SOURCES,
    bridge_diagnostics,
    corridor_stress_instance,
    fixed_decisions,
    mechanism_report,
    require_corridor_scenario,
    scale_capacity,
    stress_topology_instance,
)
from scripts.reproduce.solution_io import (
    code_environment,
    decision_hash,
    decision_to_json,
    source_hashes,
    write_csv_atomic,
    write_json_atomic,
)


# The three zones differ only in the road-throughput calibration, so the
# physical scenario -- network, damage, demands, fleet, repairs -- is shared
# and the comparison across zones stays paired.
#
# The numbers are *targets*, not settings: the capacity scale that reaches
# each one is found by measuring. A fixed scale cannot work across scenarios
# because utilization is not a function of the scale alone -- on a single
# corridor it is close to proportional to 1/scale, so the 0.85-0.97 band spans
# a few percent of scale and different instance seeds land on different sides
# of it. Fixing the scale instead would put a cell labelled "transition"
# anywhere from 0.25 to 0.95.
ZONE_TARGETS = (
    ("inactive", 0.20),
    ("transition", 0.91),
    ("binding", 0.99),
)

# The scale a zone may end up with, and how close the measured utilization has
# to get to the target before the search is accepted.
ZONE_SCALE_BOUNDS = (1e-5, 0.5)
ZONE_UTILIZATION_TOLERANCE = 0.01

PLANNING_MODELS = (
    ("PR1_HT1_EC1", dict(progressive_recovery=True,
                         heterogeneous_vehicle_thresholds=True,
                         edge_capacity_constraint=True)),
    ("PR0_HT1_EC1", dict(progressive_recovery=False,
                         heterogeneous_vehicle_thresholds=True,
                         edge_capacity_constraint=True)),
    ("PR1_HT0_EC1", dict(progressive_recovery=True,
                         heterogeneous_vehicle_thresholds=False,
                         edge_capacity_constraint=True)),
    ("PR1_HT1_EC0", dict(progressive_recovery=True,
                         heterogeneous_vehicle_thresholds=True,
                         edge_capacity_constraint=False)),
)

FULL_MODEL = "PR1_HT1_EC1"


SCAN_POINTS = 25


def _probe_utilization(scenario, instance_seed: int, capacity_scale: float) -> float:
    """Measured maximum edge utilization of a reference (SPT) decision."""
    instance = scale_capacity(scenario, capacity_scale)
    probe = fixed_decisions(instance, random_decisions=0, seed=instance_seed)["spt"]
    return mechanism_report(instance, probe, "spt")["max_edge_utilization"]


def calibrate_zones(scenario, instance_seed: int) -> list[tuple[str, float, float]]:
    """Find, for each zone, the capacity scale whose *measured* utilization
    lands nearest the zone's target.

    Utilization is **not** monotonic in the capacity scale. Shrinking capacity
    first raises utilization and then, once nothing can be dispatched at all,
    collapses it to zero -- so a bisection over the whole range would converge
    on the infeasible tail. The search is therefore a log scan first, then a
    bisection only on the branch above the peak, where utilization really does
    fall as capacity grows.

    Returns ``(zone, scale, achieved)`` triples so the caller reports where a
    zone actually landed instead of trusting the number it asked for.
    """
    low, high = ZONE_SCALE_BOUNDS
    scales = [low * (high / low) ** (index / (SCAN_POINTS - 1)) for index in range(SCAN_POINTS)]
    scan = [(scale, _probe_utilization(scenario, instance_seed, scale)) for scale in scales]
    peak = max(range(len(scan)), key=lambda index: scan[index][1])
    peak_scale, peak_utilization = scan[peak]

    # Above the peak utilization is decreasing, so index it for bracketing.
    descending = [scan[index] for index in range(peak, len(scan))]

    placements: list[tuple[str, float, float]] = []
    for zone, target in ZONE_TARGETS:
        if target >= peak_utilization:
            # Not reachable: report the most binding point that exists rather
            # than a scale that would only pretend to be in the band.
            placements.append((zone, peak_scale, peak_utilization))
            continue
        scale, achieved = _bracket_utilization(scenario, instance_seed, descending, target)
        placements.append((zone, scale, achieved))
    return placements


def _bracket_utilization(
    scenario,
    instance_seed: int,
    descending: list[tuple[float, float]],
    target: float,
) -> tuple[float, float]:
    for index in range(1, len(descending)):
        above_scale, above = descending[index - 1]
        below_scale, below = descending[index]
        if below <= target:
            low, high = above_scale, below_scale
            best = (below_scale, below)
            for _ in range(40):
                middle = (low + high) / 2.0
                achieved = _probe_utilization(scenario, instance_seed, middle)
                if abs(achieved - target) < ZONE_UTILIZATION_TOLERANCE:
                    return middle, achieved
                best = min(
                    (best, (middle, achieved)),
                    key=lambda pair: abs(pair[1] - target),
                )
                if achieved > target:
                    low = middle
                else:
                    high = middle
            return best
    return descending[-1]


def _scenario(spec, instance_seed: int, args) -> Any:
    """Build the shared physical scenario for every zone.

    The corridor scenario is built explicitly and asserted to have a damaged
    bridge; the stress topology keeps its generator flags but is never
    *described* as bridge damage unless the damage really is on a bridge.
    """
    if args.scenario == "corridor":
        instance = corridor_stress_instance(spec, instance_seed=instance_seed)
        require_corridor_scenario(instance, f"corridor seed={instance_seed}")
        return instance
    return stress_topology_instance(
        spec,
        instance_seed=instance_seed,
        damage_strategy=args.damage_strategy,
        node_role_strategy=args.node_role_strategy,
    )


def main() -> None:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = {spec.case_id: spec for spec in benchmark_specs(args.suite)}
    if args.case not in specs:
        raise SystemExit(f"unknown case {args.case!r} for suite {args.suite}")
    spec = specs[args.case]
    budget = BenchmarkBudget(
        max_evaluations=args.max_evaluations,
        pop_size=args.pop_size,
        alns_probability=args.alns_probability,
        alns_iterations=args.alns_iterations,
    )

    exposure_rows: list[dict[str, Any]] = []
    zone_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    replay_rows: list[dict[str, Any]] = []
    # Every replayed solution keeps its full three-part decision, so a
    # representative or an outlier can be rebuilt and re-evaluated without
    # re-running the search. Keyed by decision hash; the CSV carries the hash.
    decisions: dict[str, dict[str, Any]] = {}

    for instance_seed in args.instance_seeds:
        scenario = _scenario(spec, instance_seed, args)
        # Taken from the scenario itself, not from the flags that built it: a
        # scenario may only be described as a bridge/corridor stress if a
        # damaged bridge actually exists in it.
        diagnostics = bridge_diagnostics(scenario)
        # The zone scales are found by measuring this scenario, once per seed,
        # so the three zones really are the three zones.
        for (zone, capacity_scale, achieved), (_, target_utilization) in zip(
            calibrate_zones(scenario, instance_seed), ZONE_TARGETS
        ):
            instance = scale_capacity(scenario, capacity_scale)

            # Measure the zone instead of trusting its label.
            probe = fixed_decisions(instance, random_decisions=0, seed=instance_seed)["spt"]
            exposure = mechanism_report(instance, probe, "spt")
            exposure_rows.append(
                {
                    "zone": zone,
                    "case_id": spec.case_id,
                    "instance_seed": instance_seed,
                    "capacity_scale": capacity_scale,
                    "scenario": args.scenario,
                    "target_utilization": target_utilization,
                    "in_target_band": abs(achieved - target_utilization)
                    <= ZONE_UTILIZATION_TOLERANCE,
                    **diagnostics,
                    "max_edge_utilization": exposure["max_edge_utilization"],
                    "capacity_reroutes": exposure["capacity_reroutes"],
                    "EC_same_decision_changed": exposure["EC_same_decision_changed"],
                    "HT_same_decision_changed": exposure["HT_same_decision_changed"],
                    "PR_same_decision_changed": exposure["PR_same_decision_changed"],
                    "partial_edge_used_periods": exposure["partial_edge_used_periods"],
                    "threshold_sensitive_od_periods": exposure[
                        "threshold_sensitive_od_periods"
                    ],
                }
            )

            for repeat in range(args.solver_repeats):
                solver_seed = args.solver_seed_start + instance_seed * 10_000 + repeat
                for model_id, factors in PLANNING_MODELS:
                    planning_instance = model_factor_variant(instance, **factors)
                    result = solve_benchmark_algorithm(
                        args.algorithm, planning_instance, budget, seed=solver_seed
                    )
                    run_row: dict[str, Any] = {
                        "zone": zone,
                        "capacity_scale": capacity_scale,
                        "case_id": spec.case_id,
                        "instance_seed": instance_seed,
                        "solver_seed": solver_seed,
                        "solver_repeat": repeat,
                        "algorithm": args.algorithm,
                        "model_id": model_id,
                        "evaluations": result.evaluations,
                        "termination_reason": result.termination_reason,
                        "pareto_size": len(result.front),
                        "planning_F1": result.representative.objectives[0],
                        "planning_F2": result.representative.objectives[1],
                        "planning_F3": result.representative.objectives[2],
                    }
                    run_rows.append(run_row)

                    # Stage 3: every saved decision goes back into the SAME
                    # Full environment, regardless of which model planned it.
                    full_instance = model_factor_variant(
                        instance, **dict(PLANNING_MODELS)[FULL_MODEL]
                    )
                    for solution_index, individual in enumerate(result.front):
                        decisions[decision_hash(individual)] = decision_to_json(individual)
                        replay_rows.append(
                            _replay(
                                zone=zone,
                                capacity_scale=capacity_scale,
                                case_id=spec.case_id,
                                instance_seed=instance_seed,
                                solver_seed=solver_seed,
                                solver_repeat=repeat,
                                model_id=model_id,
                                solution_index=solution_index,
                                individual=individual,
                                full_instance=full_instance,
                            )
                        )

    write_csv_atomic(output_dir / "zone_exposure.csv", exposure_rows, list(exposure_rows[0]))
    write_csv_atomic(output_dir / "zone_runs.csv", run_rows, list(run_rows[0]))
    write_csv_atomic(output_dir / "zone_replay.csv", replay_rows, list(replay_rows[0]))
    write_json_atomic(output_dir / "zone_decisions.json", decisions)
    write_json_atomic(
        output_dir / "zone_search_manifest.json",
        {
            "scope": (
                "stage 2/3 mechanism diagnostic; scenarios are stress "
                "configurations whose zones are measured, not assumed"
            ),
            "case_id": spec.case_id,
            "suite": args.suite,
            "instance_seeds": list(args.instance_seeds),
            "zone_targets": [{"zone": z, "target_utilization": t} for z, t in ZONE_TARGETS],
            "zone_calibration": {
                "method": (
                    "capacity_scale bisected per (scenario, instance seed) until "
                    "the measured maximum edge utilization reaches the target"
                ),
                "scale_bounds": list(ZONE_SCALE_BOUNDS),
                "utilization_tolerance": ZONE_UTILIZATION_TOLERANCE,
                "zones_are_measured": True,
            },
            "zone_landing": [
                {
                    "zone": row["zone"],
                    "instance_seed": row["instance_seed"],
                    "capacity_scale": row["capacity_scale"],
                    "measured_utilization": row["max_edge_utilization"],
                    "in_target_band": row["in_target_band"],
                }
                for row in exposure_rows
            ],
            "scenario": args.scenario,
            "damage_strategy": args.damage_strategy,
            "node_role_strategy": args.node_role_strategy,
            "network_strategy": {
                "scenario": args.scenario,
                "damage_strategy": (
                    "corridor" if args.scenario == "corridor" else args.damage_strategy
                ),
                "node_role_strategy": (
                    "corridor" if args.scenario == "corridor" else args.node_role_strategy
                ),
            },
            "bridge_diagnostics": diagnostics,
            "algorithm": args.algorithm,
            "budget": {"max_evaluations": args.max_evaluations, "pop_size": args.pop_size},
            "solver_repeats": args.solver_repeats,
            "solver_seed_start": args.solver_seed_start,
            "execution_model": FULL_MODEL,
            "decisions_file": "zone_decisions.json",
            "decisions_are_complete": True,
            "decision_encoding": (
                "repair_order + team_assignment + dispatch_priority; rebuildable "
                "with solution_io.decision_from_json and validated per instance"
            ),
            "replayed_decisions": len(replay_rows),
            "distinct_decisions": len(decisions),
            "code": code_environment(),
            "source_hashes": source_hashes(
                Path(__file__).resolve().parents[2], DIAGNOSTIC_SOURCES
            ),
        },
    )
    print(
        f"Wrote {len(exposure_rows)} zone rows, {len(run_rows)} runs, "
        f"{len(replay_rows)} replayed decisions ({len(decisions)} distinct, "
        f"stored in full) to {output_dir}"
    )


def _replay(
    *,
    zone: str,
    capacity_scale: float,
    case_id: str,
    instance_seed: int,
    solver_seed: int,
    solver_repeat: int,
    model_id: str,
    solution_index: int,
    individual: CapacityIndividual,
    full_instance,
) -> dict[str, Any]:
    planning_objectives = individual.objectives or (0.0, 0.0, 0.0)
    full_objectives = evaluate_capacity_solution_detailed(
        full_instance,
        CapacityIndividual(
            list(individual.repair_order),
            list(individual.team_assignment),
            list(individual.dispatch_priority),
        ),
    ).objectives
    return {
        "zone": zone,
        "capacity_scale": capacity_scale,
        "case_id": case_id,
        "instance_seed": instance_seed,
        "solver_seed": solver_seed,
        "solver_repeat": solver_repeat,
        "model_id": model_id,
        "solution_index": solution_index,
        "decision_hash": decision_hash(individual),
        "is_full_planning_model": model_id == FULL_MODEL,
        "planning_F1": planning_objectives[0],
        "planning_F2": planning_objectives[1],
        "planning_F3": planning_objectives[2],
        "execution_F1": full_objectives[0],
        "execution_F2": full_objectives[1],
        "execution_F3": full_objectives[2],
        "execution_minus_planning_F1": full_objectives[0] - planning_objectives[0],
        "execution_minus_planning_F2": full_objectives[1] - planning_objectives[1],
        "execution_minus_planning_F3": full_objectives[2] - planning_objectives[2],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 2/3: small search per zone and common-execution replay.",
    )
    parser.add_argument("--suite", choices=["smoke", "benchmark", "publication"], default="benchmark")
    parser.add_argument("--case", default="S025")
    parser.add_argument("--instance-seeds", type=int, nargs="+", default=[101, 102])
    parser.add_argument(
        "--scenario",
        choices=["corridor", "critical", "benchmark"],
        default="corridor",
        help=(
            "corridor builds a network with exactly one damaged bridge (asserted); "
            "critical/benchmark use the suite generator, whose damage may fall "
            "back to random and is then never described as bridge damage"
        ),
    )
    parser.add_argument("--damage-strategy", choices=["random", "critical"], default="critical")
    parser.add_argument("--node-role-strategy", choices=["random", "separated"], default="separated")
    parser.add_argument("--algorithm", default="nsga2")
    parser.add_argument("--max-evaluations", type=int, default=200)
    parser.add_argument("--pop-size", type=int, default=16)
    parser.add_argument("--alns-probability", type=float, default=0.35)
    parser.add_argument("--alns-iterations", type=int, default=4)
    parser.add_argument("--solver-repeats", type=int, default=2)
    parser.add_argument("--solver-seed-start", type=int, default=50_000)
    parser.add_argument("--output-dir", default="outputs/mechanism_probe/zone_search")
    args = parser.parse_args()
    if args.solver_repeats < 1:
        parser.error("--solver-repeats must be positive")
    return args


if __name__ == "__main__":
    main()
