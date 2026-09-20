"""When do the progressive-recovery, threshold and edge-capacity mechanisms bite?

This is a *diagnostic* module, not a model change. It answers one question for
each mechanism: under what physical and resource conditions does it actually
alter feasible routes, dispatch behaviour or the objectives?

The point is to keep all three zones in view -- non-binding, transitional and
binding -- instead of hunting for a parameter setting where a mechanism
"works". A mechanism that does nothing at a given calibration is a statement
about that calibration, and reporting it is the result, not a failure.

Nothing here modifies the approved model, search, replay, precision or
FullExecutionProfile logic. It reads them:

* the period loop below mirrors ``evaluate_capacity_solution_detailed`` so it
  can see per-period, per-edge detail the shared evaluator does not expose.
  ``assert_matches_evaluator`` proves the mirror agrees with the shared
  evaluator on the objectives, so a divergence cannot pass unnoticed.
* on/off deltas come from ``model_factor_variant``, the same variant builder
  the ablation uses.

Exposure is measured, not assumed: an edge-period is *exposed* only when the
mechanism could change an outcome there, and *material* only when it is on a
route that delivery actually uses.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

import networkx as nx

if __package__ == "" or __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.benchmark_algorithms import _greedy_individual
from scripts.reproduce.benchmark_suite import (
    BenchmarkSpec,
    benchmark_specs,
    build_benchmark_instance,
)
from scripts.reproduce.instance_generator import generate_random_instance
from scripts.reproduce.capacity_recovery import (
    DEFAULT_RECOVERY_STAGES,
    DEFAULT_VEHICLES,
    CapacityExperimentInstance,
    CapacityIndividual,
    EvaluationConfig,
    FullExecutionProfile,
    PROGRESS_TOLERANCE,
    _capacity_ratio,
    _decode_timed_schedule,
    _dispatch_with_vehicle_types,
    _edge_key,
    _period_edge_capacities,
    _repair_progress_by_damage,
    _shortest_paths_for_vehicle,
    _speed_ratio,
    evaluate_capacity_solution_detailed,
    model_factor_variant,
)
from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.solution_io import write_csv_atomic, write_json_atomic


# An edge-period counts as partially recovered when the road carries *some*
# capacity but is not yet fully open. That is exactly the state a binary curve
# cannot represent, so it is the precondition for progressive recovery to
# differ from binary at all.
def _is_partial_ratio(ratio: float) -> bool:
    return 0.0 < ratio < 1.0 - 1e-9


@dataclass
class PeriodSnapshot:
    period: int
    progress: dict[int, float]
    capacity_ratio: dict[int, float]
    speed_ratio: dict[int, float]
    edge_utilization: dict[Any, float]
    residual_capacity: dict[Any, float]
    delivered_total: float
    delivered_by_demand: dict[int, float]
    vehicle_trips: dict[int, int]
    allocations: list[dict[str, Any]]


@dataclass
class Trace:
    snapshots: list[PeriodSnapshot]
    objectives: tuple[float, float, float]
    total_delivered: float
    remaining_supply: float
    total_vehicle_trips: int
    time_infeasible_candidates: int
    # Trip budget that was available but never dispatched, summed over the
    # horizon. Zero means the fleet budget was fully used.
    unused_vehicle_trips: int = 0


def period_trace(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
) -> Trace:
    """Per-period state, mirroring the shared evaluator's period loop."""
    base = instance.base
    config = instance.evaluation
    schedule = _decode_timed_schedule(
        base,
        decision.repair_order,
        decision.team_assignment,
        instance.crew_transfer_time_scale,
    )
    remaining_supply = dict(base.supply_amounts)
    delivered = {demand: 0.0 for demand in base.demands}
    unmet_area = 0.0
    total_delivery_time = 0.0
    total_vehicle_trips = 0
    time_infeasible: set[tuple[int, int, int]] = set()
    unused_trips = 0
    snapshots: list[PeriodSnapshot] = []

    for period in range(1, base.periods + 1):
        progress_time = (
            (period - 1) * base.eta_minutes
            if config.period_start_dispatch
            else period * base.eta_minutes
        )
        progress = _repair_progress_by_damage(base, schedule, progress_time)
        remaining_demand = {
            demand: max(0.0, base.demand_amounts[demand] - delivered[demand])
            for demand in base.demands
        }
        initial_capacity = (
            _period_edge_capacities(instance, progress)
            if instance.edge_capacity_constraint
            else {}
        )
        result = _dispatch_with_vehicle_types(
            instance,
            decision.dispatch_priority,
            progress,
            remaining_supply,
            remaining_demand,
            config,
        )
        for demand, amount in result["delivered"].items():
            delivered[demand] += amount
        total_delivery_time += result["delivery_time"]
        total_vehicle_trips += sum(result["vehicle_trips"].values())
        time_infeasible.update(result["time_infeasible_candidates"])
        unused_trips += sum(
            max(0, vehicle.count - result["vehicle_trips"][vehicle.vehicle_type])
            for vehicle in instance.vehicles
        )

        # Rebuild the residual capacity the dispatcher left behind, so
        # utilisation can be reported per edge rather than as one maximum.
        residual = dict(initial_capacity)
        for allocation in result["allocations"]:
            vehicle = next(
                v for v in instance.vehicles
                if v.vehicle_type == allocation["vehicle_type"]
            )
            use = allocation["trips"] * vehicle.pcu_per_vehicle
            for u, v in zip(allocation["path"], allocation["path"][1:]):
                key = _edge_key(u, v)
                residual[key] = max(0.0, residual.get(key, 0.0) - use)
        utilization = {
            edge: (capacity - residual.get(edge, 0.0)) / capacity
            for edge, capacity in initial_capacity.items()
            if capacity > 1e-9
        }

        total_satisfaction = sum(
            min(delivered[d], base.demand_amounts[d]) for d in base.demands
        ) / max(base.total_demand, 1e-9)
        unmet_area += 1.0 - total_satisfaction

        snapshots.append(
            PeriodSnapshot(
                period=period,
                progress=progress,
                capacity_ratio={
                    damage_id: _capacity_ratio(instance.recovery_stages, value)
                    for damage_id, value in progress.items()
                },
                speed_ratio={
                    damage_id: _speed_ratio(instance.recovery_stages, value)
                    for damage_id, value in progress.items()
                },
                edge_utilization=utilization,
                residual_capacity=residual,
                delivered_total=sum(result["delivered"].values()),
                delivered_by_demand=dict(result["delivered"]),
                vehicle_trips=dict(result["vehicle_trips"]),
                allocations=list(result["allocations"]),
            )
        )

    satisfaction_values = [
        min(1.0, delivered[demand] / max(base.demand_amounts[demand], 1e-9))
        for demand in base.demands
    ]
    total_repair_work = sum(
        max(0.0, min(task.finish_time, base.horizon_minutes) - task.start_time)
        for task in schedule
        if task.start_time < base.horizon_minutes
    )
    objectives = (
        unmet_area,
        total_delivery_time + instance.repair_time_weight * total_repair_work,
        -(min(satisfaction_values) if satisfaction_values else 0.0),
    )
    return Trace(
        snapshots=snapshots,
        objectives=objectives,
        total_delivered=sum(
            min(delivered[d], base.demand_amounts[d]) for d in base.demands
        ),
        remaining_supply=sum(max(0.0, v) for v in remaining_supply.values()),
        total_vehicle_trips=total_vehicle_trips,
        time_infeasible_candidates=len(time_infeasible),
        unused_vehicle_trips=unused_trips,
    )


def assert_matches_evaluator(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
    trace: Trace,
) -> None:
    """The mirror must agree with the shared evaluator, or it is not a mirror."""
    outcome = evaluate_capacity_solution_detailed(
        instance, CapacityIndividual(
            list(decision.repair_order),
            list(decision.team_assignment),
            list(decision.dispatch_priority),
        )
    )
    for index, (ours, theirs) in enumerate(zip(trace.objectives, outcome.objectives)):
        if abs(ours - theirs) > 1e-9:
            raise AssertionError(
                f"period trace diverged from the shared evaluator on objective "
                f"{index}: {ours!r} != {theirs!r}"
            )


# --------------------------------------------------------------------------
# PR: is a damaged road partially recovered while delivery decisions are made?
# --------------------------------------------------------------------------


def pr_exposure(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
    trace: Trace,
) -> dict[str, Any]:
    base = instance.base
    partial_edge_periods = 0
    route_exposed = 0
    used_partial = 0
    stage_histogram = {"blocked": 0, "partial": 0, "full": 0}
    per_edge_partial: dict[int, int] = {d: 0 for d in base.damaged_edges}

    for snapshot in trace.snapshots:
        # Which damaged edges carry a supply-demand route at this state?
        on_route = _damaged_edges_on_routes(instance, snapshot.progress)
        used_edges = _damaged_edges_in_allocations(instance, snapshot.allocations)
        for damage_id, ratio in snapshot.capacity_ratio.items():
            if _is_partial_ratio(ratio):
                partial_edge_periods += 1
                per_edge_partial[damage_id] += 1
                stage_histogram["partial"] += 1
                if damage_id in on_route:
                    route_exposed += 1
                if damage_id in used_edges:
                    used_partial += 1
            elif ratio <= 1e-9:
                stage_histogram["blocked"] += 1
            else:
                stage_histogram["full"] += 1

    repair_times = [edge.repair_time for edge in base.damaged_edges.values()]
    eta = base.eta_minutes
    return {
        "repair_crews": base.repair_crews,
        "periods": base.periods,
        "damaged_edges": len(base.damaged_edges),
        "repair_time_over_eta_min": min(repair_times) / eta if repair_times else 0.0,
        "repair_time_over_eta_median": (
            sorted(repair_times)[len(repair_times) // 2] / eta if repair_times else 0.0
        ),
        "repair_time_over_eta_max": max(repair_times) / eta if repair_times else 0.0,
        "partial_edge_periods": partial_edge_periods,
        "partial_route_exposure": route_exposed,
        "partial_edge_used_periods": used_partial,
        "edges_with_any_partial": sum(1 for v in per_edge_partial.values() if v > 0),
        "stage_blocked_edge_periods": stage_histogram["blocked"],
        "stage_partial_edge_periods": stage_histogram["partial"],
        "stage_full_edge_periods": stage_histogram["full"],
    }


def _damaged_edges_on_routes(
    instance: CapacityExperimentInstance,
    progress: dict[int, float],
) -> set[int]:
    """Damaged edges lying on some supplier-demand shortest path at this state.

    A partially recovered road only matters if a delivery route would use it.
    """
    base = instance.base
    graph = nx.Graph()
    graph.add_nodes_from(base.graph.nodes())
    for u, v, data in base.graph.edges(data=True):
        damage_id = data.get("damage_id")
        if damage_id is None:
            ratio, speed = 1.0, 1.0
        else:
            p = progress.get(damage_id, 0.0)
            ratio = _capacity_ratio(instance.recovery_stages, p)
            speed = _speed_ratio(instance.recovery_stages, p)
        if ratio <= 0.0 or speed <= 0.0:
            continue
        free_time = float(data.get("free_time", data.get("weight", 1.0)))
        graph.add_edge(u, v, weight=free_time / max(speed, 0.1), damage_id=damage_id)

    used: set[int] = set()
    for supplier in base.suppliers:
        try:
            _lengths, paths = nx.single_source_dijkstra(graph, supplier, weight="weight")
        except nx.NodeNotFound:
            continue
        for demand in base.demands:
            path = paths.get(demand)
            if not path:
                continue
            for a, b in zip(path, path[1:]):
                damage_id = base.graph[a][b].get("damage_id")
                if damage_id is not None:
                    used.add(int(damage_id))
    return used


def _damaged_edges_in_allocations(
    instance: CapacityExperimentInstance,
    allocations: Sequence[dict[str, Any]],
) -> set[int]:
    base = instance.base
    used: set[int] = set()
    for allocation in allocations:
        path = allocation["path"]
        for a, b in zip(path, path[1:]):
            damage_id = base.graph[a][b].get("damage_id")
            if damage_id is not None:
                used.add(int(damage_id))
    return used


# --------------------------------------------------------------------------
# HT: does a road's progress fall between two vehicle types' thresholds?
# --------------------------------------------------------------------------


def ht_exposure(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
    trace: Trace,
) -> dict[str, Any]:
    base = instance.base
    thresholds = sorted(
        {v.min_recovery_progress for v in instance.vehicles}
    )
    types = sorted({v.vehicle_type for v in instance.vehicles})
    sensitive_edge_periods = 0
    access_set_changes = 0
    per_edge_sensitive: dict[int, int] = {d: 0 for d in base.damaged_edges}
    previous_access: dict[int, frozenset[int]] = {}

    for snapshot in trace.snapshots:
        for damage_id in base.damaged_edges:
            p = snapshot.progress.get(damage_id, 0.0)
            access = frozenset(
                vehicle.vehicle_type
                for vehicle in instance.vehicles
                if _passable(instance, p, vehicle)
            )
            # Sensitive: the road is open to some vehicle types but not all, so
            # the threshold set -- not just the recovery curve -- decides who
            # gets through.
            if 0 < len(access) < len(types):
                sensitive_edge_periods += 1
                per_edge_sensitive[damage_id] += 1
            if damage_id in previous_access and previous_access[damage_id] != access:
                access_set_changes += 1
            previous_access[damage_id] = access

    od_sensitive = _threshold_sensitive_od_periods(instance, trace)
    return {
        "vehicle_types": len(types),
        "distinct_thresholds": len(thresholds),
        "threshold_sensitive_edge_periods": sensitive_edge_periods,
        "threshold_sensitive_od_periods": od_sensitive,
        "vehicle_access_set_changes": access_set_changes,
        "edges_with_any_threshold_sensitivity": sum(
            1 for v in per_edge_sensitive.values() if v > 0
        ),
    }


def _passable(
    instance: CapacityExperimentInstance,
    progress: float,
    vehicle,
) -> bool:
    ratio = _capacity_ratio(instance.recovery_stages, progress)
    speed = _speed_ratio(instance.recovery_stages, progress)
    return (
        progress >= vehicle.min_recovery_progress - PROGRESS_TOLERANCE
        and ratio > 0.0
        and speed > 0.0
    )


def _threshold_sensitive_od_periods(
    instance: CapacityExperimentInstance,
    trace: Trace,
) -> int:
    """Supplier-demand-period triples where the threshold set changes anything.

    Reachability alone is too narrow a test. In a network with alternatives,
    every vehicle type can usually *reach* every demand by some path, so the
    access set stays "all types" even though the threshold set changed which
    route each type finds. What a threshold actually buys is a shorter path for
    a narrower vehicle, and that is what this counts: a triple is sensitive
    when some vehicle type's best travel time to a demand differs between the
    declared thresholds and a uniform threshold.
    """
    base = instance.base
    uniform = model_factor_variant(
        instance,
        progressive_recovery=instance.progressive_recovery,
        heterogeneous_vehicle_thresholds=False,
        edge_capacity_constraint=instance.edge_capacity_constraint,
    )
    count = 0
    for snapshot in trace.snapshots:
        declared_paths = {
            vehicle.vehicle_type: _shortest_paths_for_vehicle(
                instance, snapshot.progress, vehicle
            )
            for vehicle in instance.vehicles
        }
        uniform_paths = {
            vehicle.vehicle_type: _shortest_paths_for_vehicle(
                uniform, snapshot.progress, vehicle
            )
            for vehicle in uniform.vehicles
        }
        for supplier in base.suppliers:
            for demand in base.demands:
                for vehicle_type in declared_paths:
                    here = declared_paths[vehicle_type].get((supplier, demand))
                    there = uniform_paths[vehicle_type].get((supplier, demand))
                    here_time = here[0] if here else None
                    there_time = there[0] if there else None
                    if here_time is None or there_time is None:
                        if (here_time is None) != (there_time is None):
                            count += 1
                            break
                        continue
                    if abs(here_time - there_time) > 1e-9:
                        count += 1
                        break
    return count


# --------------------------------------------------------------------------
# EC: is road throughput actually the binding resource?
# --------------------------------------------------------------------------


def ec_exposure(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
    trace: Trace,
) -> dict[str, Any]:
    base = instance.base
    max_utilization = 0.0
    binding_edge_periods = 0
    high_edge_periods = 0
    utilization_values: list[float] = []

    for snapshot in trace.snapshots:
        for value in snapshot.edge_utilization.values():
            utilization_values.append(value)
            max_utilization = max(max_utilization, value)
            if value >= 0.999:
                binding_edge_periods += 1
            elif value >= 0.80:
                high_edge_periods += 1

    return {
        "max_edge_utilization": max_utilization,
        "binding_edge_periods": binding_edge_periods,
        "high_utilization_edge_periods": high_edge_periods,
        "mean_edge_utilization_of_used": (
            sum(v for v in utilization_values if v > 0.0)
            / max(sum(1 for v in utilization_values if v > 0.0), 1)
        ),
        "capacity_reroutes": _capacity_reroutes(instance, trace),
        "edge_periods_observed": len(utilization_values),
        "unused_vehicle_trips": trace.unused_vehicle_trips,
        "remaining_supply": trace.remaining_supply,
    }


def _capacity_reroutes(
    instance: CapacityExperimentInstance,
    trace: Trace,
) -> int:
    """Allocations whose path is not the unrestricted shortest path.

    A capacity detour is direct evidence that throughput, not reachability,
    changed the dispatch decision.
    """
    base = instance.base
    count = 0
    for snapshot in trace.snapshots:
        if not snapshot.allocations:
            continue
        topology = {
            vehicle.vehicle_type: _shortest_paths_for_vehicle(
                instance, snapshot.progress, vehicle
            )
            for vehicle in instance.vehicles
        }
        for allocation in snapshot.allocations:
            key = (allocation["supplier"], allocation["demand"])
            reference = topology.get(allocation["vehicle_type"], {}).get(key)
            if reference is None:
                count += 1
                continue
            if list(reference[1]) != list(allocation["path"]):
                count += 1
    return count


# --------------------------------------------------------------------------
# Same-decision on/off deltas: does the mechanism change the objective at all?
# --------------------------------------------------------------------------


def _delta(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
    **variant: bool,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    variant_instance = model_factor_variant(instance, **variant)

    def evaluate(target) -> tuple[float, float, float]:
        # A fresh individual each time: the shared evaluator must not be handed
        # a cached objective from the other arm of the comparison.
        return evaluate_capacity_solution_detailed(
            target,
            CapacityIndividual(
                list(decision.repair_order),
                list(decision.team_assignment),
                list(decision.dispatch_priority),
            ),
        ).objectives

    return evaluate(instance), evaluate(variant_instance)


def same_decision_deltas(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
) -> dict[str, Any]:
    """Effect of switching each mechanism off, on one fixed decision."""
    row: dict[str, Any] = {}
    for label, variant in (
        ("PR", {"progressive_recovery": False,
                "heterogeneous_vehicle_thresholds": instance.heterogeneous_vehicle_thresholds,
                "edge_capacity_constraint": instance.edge_capacity_constraint}),
        ("HT", {"progressive_recovery": instance.progressive_recovery,
                "heterogeneous_vehicle_thresholds": False,
                "edge_capacity_constraint": instance.edge_capacity_constraint}),
        ("EC", {"progressive_recovery": instance.progressive_recovery,
                "heterogeneous_vehicle_thresholds": instance.heterogeneous_vehicle_thresholds,
                "edge_capacity_constraint": False}),
    ):
        full, off = _delta(instance, decision, **variant)
        for index, name in enumerate(("F1", "F2", "F3")):
            row[f"{label}_same_decision_delta_{name}"] = off[index] - full[index]
        row[f"{label}_same_decision_changed"] = any(
            abs(off[index] - full[index]) > V2_PRECISION.resolutions[index]
            for index in range(3)
        )
    return row


def material_dispatch_changes(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
    trace: Trace,
    **variant: bool,
) -> int:
    """Allocations that differ when a mechanism is switched off.

    Exposure says a mechanism *could* matter somewhere; this says whether the
    dispatcher's actual choices changed. Counting (period, supplier, demand)
    triples whose vehicle type or route differs keeps it a dispatch diagnostic
    rather than a restatement of the objective delta.
    """
    off_instance = model_factor_variant(instance, **variant)
    off_trace = period_trace(off_instance, decision)
    changes = 0
    for on_snapshot, off_snapshot in zip(trace.snapshots, off_trace.snapshots):
        on_map = {
            (a["supplier"], a["demand"]): (a["vehicle_type"], tuple(a["path"]))
            for a in on_snapshot.allocations
        }
        off_map = {
            (a["supplier"], a["demand"]): (a["vehicle_type"], tuple(a["path"]))
            for a in off_snapshot.allocations
        }
        for key in set(on_map) | set(off_map):
            if on_map.get(key) != off_map.get(key):
                changes += 1
    return changes


def mechanism_report(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
    label: str,
) -> dict[str, Any]:
    trace = period_trace(instance, decision)
    assert_matches_evaluator(instance, decision, trace)
    row: dict[str, Any] = {
        "decision": label,
        "model_version": instance.evaluation.model_version,
        "physical_instance_hash_prefix": None,  # filled by the caller if needed
        "F1": trace.objectives[0],
        "F2": trace.objectives[1],
        "F3": trace.objectives[2],
        "total_delivered": trace.total_delivered,
    }
    row.update(pr_exposure(instance, decision, trace))
    row.update(ht_exposure(instance, decision, trace))
    row.update(ec_exposure(instance, decision, trace))
    row.update(same_decision_deltas(instance, decision))
    # Material exposure, one per mechanism: did the dispatch actually change?
    row["PR_allocations_changed"] = material_dispatch_changes(
        instance, decision, trace,
        progressive_recovery=False,
        heterogeneous_vehicle_thresholds=instance.heterogeneous_vehicle_thresholds,
        edge_capacity_constraint=instance.edge_capacity_constraint,
    )
    row["HT_allocations_changed"] = material_dispatch_changes(
        instance, decision, trace,
        progressive_recovery=instance.progressive_recovery,
        heterogeneous_vehicle_thresholds=False,
        edge_capacity_constraint=instance.edge_capacity_constraint,
    )
    row["EC_allocations_changed"] = material_dispatch_changes(
        instance, decision, trace,
        progressive_recovery=instance.progressive_recovery,
        heterogeneous_vehicle_thresholds=instance.heterogeneous_vehicle_thresholds,
        edge_capacity_constraint=False,
    )
    return row


def stress_topology_instance(
    spec: BenchmarkSpec,
    *,
    instance_seed: int,
    damage_strategy: str,
    node_role_strategy: str,
) -> CapacityExperimentInstance:
    """A stress network with damage on bridges and demands pushed to the rim.

    The benchmark generator damages edges at random, which leaves alternative
    routes almost everywhere and therefore no corridor that a *single* damaged
    road gates. Thresholds can only restrict a vehicle set if such a corridor
    exists, so this scenario builds one on purpose. It is a diagnostic
    scenario, not a calibration and not a new benchmark case.

    The fleet scaling mirrors ``benchmark_suite.build_benchmark_instance`` so
    the only thing that differs from the benchmark instance is the topology and
    which edges are damaged.
    """
    base = generate_random_instance(
        num_nodes=spec.num_nodes,
        gamma=spec.gamma,
        damage_ratio=spec.damage_ratio,
        eta_hours=spec.eta_hours,
        seed=instance_seed,
        supply_ratio=spec.supply_ratio,
        topology="random",
        damage_strategy=damage_strategy,
        node_role_strategy=node_role_strategy,
    )
    base.name = f"{spec.case_id}_seed{instance_seed}_{damage_strategy}"
    reference_capacity = sum(
        vehicle.capacity_ton * vehicle.count for vehicle in DEFAULT_VEHICLES
    )
    target = base.total_demand * (spec.fleet_capacity_ratio or 0.14)
    scale = target / reference_capacity
    vehicles = [
        replace(vehicle, count=max(1, round(vehicle.count * scale)))
        for vehicle in DEFAULT_VEHICLES
    ]
    instance = CapacityExperimentInstance(
        base=base,
        vehicles=vehicles,
        recovery_stages=list(DEFAULT_RECOVERY_STAGES),
        capacity_scale=spec.capacity_scale,
        evaluation=EvaluationConfig.for_version("v2"),
    )
    instance.full_profile = FullExecutionProfile.from_instance(instance, "synthetic_full")
    return instance


# --------------------------------------------------------------------------
# B4: fleet budget versus road throughput
# --------------------------------------------------------------------------


def scale_fleet(
    instance: CapacityExperimentInstance,
    multiplier: float,
) -> CapacityExperimentInstance:
    """A stress variant with a different fleet size. Not a calibration."""
    if multiplier <= 0:
        raise ValueError("fleet multiplier must be positive")
    vehicles = [
        replace(vehicle, count=max(1, round(vehicle.count * multiplier)))
        for vehicle in instance.vehicles
    ]
    return replace(instance, vehicles=vehicles, full_profile=None)


def scale_capacity(
    instance: CapacityExperimentInstance,
    capacity_scale: float,
) -> CapacityExperimentInstance:
    if capacity_scale <= 0:
        raise ValueError("capacity_scale must be positive")
    return replace(instance, capacity_scale=capacity_scale, full_profile=None)


def resource_grid(
    instance: CapacityExperimentInstance,
    decision: CapacityIndividual,
    *,
    fleet_multipliers: Sequence[float],
    capacity_scales: Sequence[float],
) -> list[dict[str, Any]]:
    """Two-axis stress grid separating "fleet-bound" from "road-bound"."""
    rows: list[dict[str, Any]] = []
    for fleet in fleet_multipliers:
        for capacity in capacity_scales:
            variant = scale_capacity(scale_fleet(instance, fleet), capacity)
            trace = period_trace(variant, decision)
            assert_matches_evaluator(variant, decision, trace)
            exposure = ec_exposure(variant, decision, trace)
            # The decisive question in a cell is not whether capacity is tight
            # but whether removing the accounting changes the dispatch outcome.
            ec_off = model_factor_variant(
                variant,
                progressive_recovery=variant.progressive_recovery,
                heterogeneous_vehicle_thresholds=variant.heterogeneous_vehicle_thresholds,
                edge_capacity_constraint=False,
            )
            ec_off_objectives = evaluate_capacity_solution_detailed(
                ec_off,
                CapacityIndividual(
                    list(decision.repair_order),
                    list(decision.team_assignment),
                    list(decision.dispatch_priority),
                ),
            ).objectives
            rows.append(
                {
                    "fleet_multiplier": fleet,
                    "capacity_scale": capacity,
                    "F1": trace.objectives[0],
                    "F2": trace.objectives[1],
                    "F3": trace.objectives[2],
                    "total_delivered": trace.total_delivered,
                    "remaining_supply": trace.remaining_supply,
                    "unused_vehicle_trips": trace.unused_vehicle_trips,
                    "total_vehicle_trips": trace.total_vehicle_trips,
                    "max_edge_utilization": exposure["max_edge_utilization"],
                    "binding_edge_periods": exposure["binding_edge_periods"],
                    "high_utilization_edge_periods": exposure[
                        "high_utilization_edge_periods"
                    ],
                    "capacity_reroutes": exposure["capacity_reroutes"],
                    "EC_same_decision_delta_F1": ec_off_objectives[0] - trace.objectives[0],
                    "EC_same_decision_delta_F2": ec_off_objectives[1] - trace.objectives[1],
                    "EC_same_decision_delta_F3": ec_off_objectives[2] - trace.objectives[2],
                    "EC_same_decision_changed": any(
                        abs(ec_off_objectives[i] - trace.objectives[i])
                        > V2_PRECISION.resolutions[i]
                        for i in range(3)
                    ),
                }
            )
    return rows


# --------------------------------------------------------------------------
# B5: repair duration relative to the decision period
# --------------------------------------------------------------------------


def scale_repair_times(
    instance: CapacityExperimentInstance,
    multiplier: float,
) -> CapacityExperimentInstance:
    """A stress variant with longer repairs. Not Wenchuan calibration."""
    if multiplier <= 0:
        raise ValueError("repair time multiplier must be positive")
    base = instance.base
    scaled_edges = {
        damage_id: replace(edge, repair_time=edge.repair_time * multiplier)
        for damage_id, edge in base.damaged_edges.items()
    }
    graph = base.graph.copy()
    for damage_id, edge in scaled_edges.items():
        graph[edge.u][edge.v]["repair_time"] = edge.repair_time
        graph[edge.u][edge.v]["damage_id"] = damage_id
        graph[edge.u][edge.v]["damaged"] = True
    return replace(
        instance,
        base=replace(base, graph=graph, damaged_edges=scaled_edges),
        full_profile=None,
    )


def repair_time_sweep(
    instance: CapacityExperimentInstance,
    decisions: dict[str, CapacityIndividual],
    *,
    multipliers: Sequence[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for multiplier in multipliers:
        variant = scale_repair_times(instance, multiplier)
        for label, decision in decisions.items():
            trace = period_trace(variant, decision)
            assert_matches_evaluator(variant, decision, trace)
            row: dict[str, Any] = {
                "repair_time_multiplier": multiplier,
                "decision": label,
                "F1": trace.objectives[0],
                "F2": trace.objectives[1],
                "F3": trace.objectives[2],
            }
            row.update(pr_exposure(variant, decision, trace))
            row.update(ht_exposure(variant, decision, trace))
            rows.append(row)
    return rows


# --------------------------------------------------------------------------
# fixed decision sets
# --------------------------------------------------------------------------


def fixed_decisions(
    instance: CapacityExperimentInstance,
    *,
    random_decisions: int,
    seed: int,
) -> dict[str, CapacityIndividual]:
    """SPT plus a few fixed random decisions. No optimizer is involved."""
    import random

    base = instance.base
    decisions = {"spt": _greedy_individual(instance)}
    rng = random.Random(seed)
    for index in range(random_decisions):
        order = list(base.damaged_edges)
        rng.shuffle(order)
        teams = [rng.randrange(base.repair_crews) for _ in order]
        priority = [
            (supplier, demand)
            for supplier in base.suppliers
            for demand in base.demands
        ]
        rng.shuffle(priority)
        decisions[f"random_{index}"] = CapacityIndividual(order, teams, priority)
    return decisions


def main() -> None:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = {spec.case_id: spec for spec in benchmark_specs(args.suite)}
    if args.case not in specs:
        raise SystemExit(f"unknown case {args.case!r} for suite {args.suite}")
    spec = specs[args.case]

    summary_rows: list[dict[str, Any]] = []
    grid_rows: list[dict[str, Any]] = []
    sweep_rows: list[dict[str, Any]] = []

    for instance_seed in args.instance_seeds:
        if args.damage_strategy == "random" and args.node_role_strategy == "random":
            instance = build_benchmark_instance(
                spec, instance_seed=instance_seed, model_version="v2"
            )
        else:
            instance = stress_topology_instance(
                spec,
                instance_seed=instance_seed,
                damage_strategy=args.damage_strategy,
                node_role_strategy=args.node_role_strategy,
            )
        decisions = fixed_decisions(
            instance,
            random_decisions=args.random_decisions,
            seed=instance_seed,
        )
        for label, decision in decisions.items():
            row = mechanism_report(instance, decision, label)
            row["case_id"] = spec.case_id
            row["instance_seed"] = instance_seed
            summary_rows.append(row)

        if args.grid:
            grid_rows.extend(
                {
                    "case_id": spec.case_id,
                    "instance_seed": instance_seed,
                    "decision": "spt",
                    **entry,
                }
                for entry in resource_grid(
                    instance,
                    decisions["spt"],
                    fleet_multipliers=args.fleet_multipliers,
                    capacity_scales=args.capacity_scales,
                )
            )

        if args.sweep:
            sweep_rows.extend(
                {
                    "case_id": spec.case_id,
                    "instance_seed": instance_seed,
                    **entry,
                }
                for entry in repair_time_sweep(
                    instance,
                    decisions,
                    multipliers=args.repair_time_multipliers,
                )
            )

    write_csv_atomic(output_dir / "mechanism_exposure.csv", summary_rows, list(summary_rows[0]))
    if grid_rows:
        write_csv_atomic(output_dir / "resource_grid.csv", grid_rows, list(grid_rows[0]))
    if sweep_rows:
        write_csv_atomic(
            output_dir / "repair_time_sweep.csv", sweep_rows, list(sweep_rows[0])
        )
    write_json_atomic(
        output_dir / "mechanism_probe_manifest.json",
        {
            "scope": (
                "fixed-decision mechanism applicability diagnostic; no optimizer "
                "is run and no approved model/search/replay logic is modified"
            ),
            "case_id": spec.case_id,
            "suite": args.suite,
            "instance_seeds": list(args.instance_seeds),
            "random_decisions": args.random_decisions,
            "damage_strategy": args.damage_strategy,
            "node_role_strategy": args.node_role_strategy,
            "fleet_multipliers": list(args.fleet_multipliers),
            "capacity_scales": list(args.capacity_scales),
            "repair_time_multipliers": list(args.repair_time_multipliers),
            "stress_scenario_note": (
                "fleet multipliers, capacity scales and repair-time multipliers "
                "are stress diagnostics, not measured Wenchuan parameters"
            ),
        },
    )
    print(
        f"Wrote {len(summary_rows)} exposure rows, {len(grid_rows)} grid rows, "
        f"{len(sweep_rows)} sweep rows to {output_dir}"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose when PR / HT / EC actually change outcomes.",
    )
    parser.add_argument("--suite", choices=["smoke", "benchmark", "publication"], default="benchmark")
    parser.add_argument("--case", default="S025")
    parser.add_argument("--instance-seeds", type=int, nargs="+", default=[101])
    parser.add_argument("--random-decisions", type=int, default=4)
    parser.add_argument("--grid", action="store_true", help="run the fleet/capacity resource grid")
    parser.add_argument("--sweep", action="store_true", help="run the repair-time exposure sweep")
    parser.add_argument(
        "--fleet-multipliers", type=float, nargs="+", default=[0.5, 1.0, 2.0, 4.0]
    )
    parser.add_argument(
        "--capacity-scales", type=float, nargs="+", default=[0.05, 0.01, 0.005, 0.002]
    )
    parser.add_argument(
        "--repair-time-multipliers", type=float, nargs="+", default=[1.0, 2.0, 4.0]
    )
    parser.add_argument(
        "--damage-strategy",
        choices=["random", "critical"],
        default="random",
        help=(
            "random mirrors the benchmark suite; critical puts damage on bridges "
            "and pushes demands to the rim, creating corridors a single damaged "
            "road gates. A stress diagnostic, not a calibration."
        ),
    )
    parser.add_argument(
        "--node-role-strategy", choices=["random", "separated"], default="random"
    )
    parser.add_argument("--output-dir", default="outputs/mechanism_probe/S025")
    args = parser.parse_args()
    if args.random_decisions < 0:
        parser.error("--random-decisions must be non-negative")
    return args


if __name__ == "__main__":
    main()
