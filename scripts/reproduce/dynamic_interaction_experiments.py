from __future__ import annotations

import argparse
import csv
import random
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.capacity_recovery import (
    CapacityExperimentInstance,
    RecoveryStage,
    VehicleProfile,
    _crew_transfer,
    _decode_timed_schedule,
    _dispatch_with_vehicle_types,
    _repair_progress_by_damage,
    _shortest_paths_for_vehicle,
    build_simulation_instance,
    build_wenchuan_instance,
)


@dataclass(frozen=True)
class Mechanism:
    name: str
    progressive: bool
    repair_policy: str


@dataclass(frozen=True)
class RepairEfficiencyUncertainty:
    deviation: float = 0.0

    @property
    def lower(self) -> float:
        return 1.0 - self.deviation

    @property
    def upper(self) -> float:
        return 1.0 + self.deviation

    def validate(self) -> None:
        if not 0.0 <= self.deviation < 1.0:
            raise ValueError("repair efficiency deviation must be in [0, 1)")


MECHANISMS = (
    Mechanism("binary_static", False, "shortest_static"),
    Mechanism("progressive_static", True, "shortest_static"),
    Mechanism("progressive_openloop", True, "demand_openloop"),
    Mechanism("progressive_rolling", True, "demand_rolling"),
)


def run_mechanism(
    instance,
    mechanism,
    seed,
    repair_efficiency_deviation=0.0,
    state_callback: Callable[[dict[str, Any]], None] | None = None,
):
    uncertainty = RepairEfficiencyUncertainty(repair_efficiency_deviation)
    uncertainty.validate()
    variant = _variant(instance, mechanism.progressive)
    base = variant.base
    priority = [(s, d) for s in base.suppliers for d in base.demands]
    priority.sort(key=lambda pair: (-base.demand_amounts[pair[1]], pair))
    order = sorted(
        base.damaged_edges,
        key=lambda edge_id: (base.damaged_edges[edge_id].repair_time, edge_id),
    )
    schedule = _decode_timed_schedule(
        base,
        order,
        [idx % base.repair_crews for idx in range(len(order))],
        variant.crew_transfer_time_scale,
    )
    efficiency_realization = _sample_repair_efficiencies(
        base,
        seed,
        uncertainty,
    )
    static_plan = _build_static_plan(base, schedule)
    openloop_plan = None
    if mechanism.repair_policy == "demand_openloop":
        openloop_plan = _build_openloop_plan(variant, priority)
    progress = {edge_id: 0.0 for edge_id in base.damaged_edges}
    remaining_supply = dict(base.supply_amounts)
    delivered = {demand: 0.0 for demand in base.demands}
    previous_paths = {}
    rows = []
    unmet_area = 0.0
    path_switches = 0
    observed_efficiencies = []
    progress_forecast_errors = []
    crew_locations = {
        crew_id: {
            "kind": "node",
            "node_id": base.suppliers[crew_id % len(base.suppliers)],
        }
        for crew_id in range(base.repair_crews)
    }

    if state_callback is not None:
        state_callback(
            _state_snapshot(
                variant,
                mechanism,
                period=0,
                progress=progress,
                delivered=delivered,
                selected=[],
                crew_locations=crew_locations,
                reachable_demands=_reachable_demands(variant, progress),
                period_delivery={},
                shipments=[],
                vehicle_trips={},
                crew_transfers={},
                crew_activity={},
                road_progress_before=progress,
                counterfactual_delivery={},
                counterfactual_reachable=_reachable_demands(variant, progress),
            )
        )

    for period in range(1, base.periods + 1):
        period_start_progress = dict(progress)
        period_efficiency = {
            edge_id: efficiency_realization[(period, edge_id)]
            for edge_id in base.damaged_edges
        }
        if mechanism.repair_policy == "demand_rolling":
            expected_progress = dict(progress)
            crew_activity: dict[int, list[int]] = {}
            crew_transfers: dict[int, list[dict[str, Any]]] = {}
            selected = _objective_aligned_step(
                variant,
                expected_progress,
                delivered,
                remaining_supply,
                priority,
                base.eta_minutes,
                crew_activity=crew_activity,
                crew_locations=crew_locations,
                crew_transfers=crew_transfers,
            )
            planned_increment = _progress_increment(progress, expected_progress)
        elif mechanism.repair_policy == "demand_openloop":
            selected, planned_increment, crew_activity, crew_transfers = (
                openloop_plan[period - 1]
            )
        else:
            selected, planned_increment, crew_activity, crew_transfers = (
                static_plan[period - 1]
            )

        for crew_id, damage_ids in crew_activity.items():
            if damage_ids:
                current_location = crew_locations.get(crew_id, {})
                transfer_items = crew_transfers.get(crew_id, [])
                last_path = transfer_items[-1].get("path", []) if transfer_items else []
                crew_locations[crew_id] = {
                    "kind": "edge",
                    "damage_id": damage_ids[-1],
                    "access_node": (
                        last_path[-1]
                        if last_path
                        else current_location.get("access_node")
                    ),
                }

        before_realization = dict(progress)
        expected_after_repair = _apply_repair_efficiency(
            before_realization,
            planned_increment,
            {edge_id: 1.0 for edge_id in base.damaged_edges},
        )
        progress = _apply_repair_efficiency(
            before_realization,
            planned_increment,
            period_efficiency,
        )
        progress_forecast_mae = sum(
            abs(progress[edge_id] - expected_after_repair[edge_id])
            for edge_id in base.damaged_edges
        ) / max(len(base.damaged_edges), 1)
        progress_forecast_errors.append(progress_forecast_mae)
        worked_efficiencies = [
            period_efficiency[edge_id]
            for edge_id, increment in planned_increment.items()
            if increment > 1e-9
        ]
        observed_efficiencies.extend(worked_efficiencies)

        remaining_demand = {
            d: max(0.0, base.demand_amounts[d] - delivered[d])
            for d in base.demands
        }
        counterfactual = _dispatch_with_vehicle_types(
            variant,
            priority,
            period_start_progress,
            dict(remaining_supply),
            dict(remaining_demand),
        )
        dispatch = _dispatch_with_vehicle_types(
            variant, priority, progress, remaining_supply, remaining_demand
        )
        for demand, amount in dispatch["delivered"].items():
            delivered[demand] += amount

        paths = _best_paths(variant, progress)
        switches = sum(
            previous_paths.get(demand) != path
            for demand, path in paths.items()
            if demand in previous_paths
        )
        previous_paths = paths
        path_switches += switches
        total_sat = sum(
            min(delivered[d], base.demand_amounts[d]) for d in base.demands
        ) / base.total_demand
        min_sat = min(
            delivered[d] / base.demand_amounts[d] for d in base.demands
        )
        unmet_area += 1.0 - total_sat
        rows.append({
            "mechanism": mechanism.name,
            "seed": seed,
            "period": period,
            "selected_repairs": "|".join(map(str, selected)),
            "mean_progress": sum(progress.values()) / len(progress),
            "partial_edges": sum(1 for p in progress.values() if 1e-9 < p < 1 - 1e-9),
            "reachable_ratio": dispatch["reachable_count"] / len(base.demands),
            "total_satisfaction": total_sat,
            "min_satisfaction": min_sat,
            "path_switches": switches,
            "delivered": sum(dispatch["delivered"].values()),
            "vehicle_trips": sum(dispatch["vehicle_trips"].values()),
            "max_edge_utilization": dispatch["max_edge_utilization"],
            "high_utilization_edges": dispatch["high_utilization_edges"],
            "capacity_blocked_tons": dispatch["capacity_blocked_tons"],
            "repair_efficiency_scenario_seed": seed,
            "repair_efficiency_deviation": uncertainty.deviation,
            "crew_transfer_time_scale": variant.crew_transfer_time_scale,
            "period_mean_repair_efficiency": (
                sum(worked_efficiencies) / len(worked_efficiencies)
                if worked_efficiencies else 1.0
            ),
            "repair_progress_forecast_mae": progress_forecast_mae,
            "crew_transfer_minutes": sum(
                transfer["minutes"]
                for transfers in crew_transfers.values()
                for transfer in transfers
            ),
            "repair_enabled_delivery_tons": (
                sum(dispatch["delivered"].values())
                - sum(counterfactual["delivered"].values())
            ),
            "repair_enabled_reachable_demands": len(
                set(dispatch["reachable_demands"])
                - set(counterfactual["reachable_demands"])
            ),
        })
        if state_callback is not None:
            state_callback(
                _state_snapshot(
                    variant,
                    mechanism,
                    period=period,
                    progress=progress,
                    delivered=delivered,
                    selected=selected,
                    crew_locations=crew_locations,
                    reachable_demands=set(dispatch["reachable_demands"]),
                    period_delivery=dispatch["delivered"],
                    shipments=dispatch["allocations"],
                    vehicle_trips=dispatch["vehicle_trips"],
                    crew_transfers=crew_transfers,
                    crew_activity=crew_activity,
                    road_progress_before=period_start_progress,
                    counterfactual_delivery=counterfactual["delivered"],
                    counterfactual_reachable=set(
                        counterfactual["reachable_demands"]
                    ),
                )
            )

    summary = {
        "mechanism": mechanism.name,
        "seed": seed,
        "cumulative_unmet_area": unmet_area,
        "final_total_satisfaction": rows[-1]["total_satisfaction"],
        "final_min_satisfaction": rows[-1]["min_satisfaction"],
        "average_reachable_ratio": sum(r["reachable_ratio"] for r in rows) / len(rows),
        "first_delivery_period": next(
            (r["period"] for r in rows if r["delivered"] > 1e-9), None
        ),
        "path_switches": path_switches,
        "partial_edge_periods": sum(r["partial_edges"] for r in rows),
        "max_edge_utilization": max(r["max_edge_utilization"] for r in rows),
        "high_utilization_edge_periods": sum(r["high_utilization_edges"] for r in rows),
        "capacity_blocked_tons": sum(r["capacity_blocked_tons"] for r in rows),
        "total_vehicle_trips": sum(r["vehicle_trips"] for r in rows),
        "total_crew_transfer_minutes": sum(
            r["crew_transfer_minutes"] for r in rows
        ),
        "repair_efficiency_scenario_seed": seed,
        "repair_efficiency_deviation": uncertainty.deviation,
        "crew_transfer_time_scale": variant.crew_transfer_time_scale,
        "mean_observed_repair_efficiency": (
            sum(observed_efficiencies) / len(observed_efficiencies)
            if observed_efficiencies else 1.0
        ),
        "mean_repair_progress_forecast_mae": (
            sum(progress_forecast_errors) / len(progress_forecast_errors)
        ),
    }
    return summary, rows


def _variant(instance, progressive):
    if progressive:
        return instance
    vehicles = [
        VehicleProfile(
            vehicle_type=v.vehicle_type,
            capacity_ton=v.capacity_ton,
            count=v.count,
            occupied_od_pcu_h=v.occupied_od_pcu_h,
            min_recovery_progress=1.0,
            pcu_per_vehicle=v.pcu_per_vehicle,
            speed_factor=v.speed_factor,
        )
        for v in instance.vehicles
    ]
    stages = [
        RecoveryStage(0.0, 1.0, 0.0, "blocked", 0.0),
        RecoveryStage(1.0, 1.01, 1.0, "full", 1.0),
    ]
    return CapacityExperimentInstance(
        instance.base,
        vehicles,
        stages,
        capacity_scale=instance.capacity_scale,
        repair_time_weight=instance.repair_time_weight,
        crew_transfer_time_scale=instance.crew_transfer_time_scale,
        crew_min_access_progress=instance.crew_min_access_progress,
    )


def _build_openloop_plan(instance, dispatch_priority):
    """Plan the full horizon once using expected repair efficiency and state."""
    base = instance.base
    planned_progress = {edge_id: 0.0 for edge_id in base.damaged_edges}
    planned_delivered = {demand: 0.0 for demand in base.demands}
    planned_supply = dict(base.supply_amounts)
    crew_locations = {
        crew_id: {
            "kind": "node",
            "node_id": base.suppliers[crew_id % len(base.suppliers)],
        }
        for crew_id in range(base.repair_crews)
    }
    plan = []
    for _period in range(base.periods):
        before_progress = dict(planned_progress)
        crew_activity: dict[int, list[int]] = {}
        crew_transfers: dict[int, list[dict[str, Any]]] = {}
        selected = _objective_aligned_step(
            instance,
            planned_progress,
            planned_delivered,
            planned_supply,
            dispatch_priority,
            base.eta_minutes,
            crew_activity=crew_activity,
            crew_locations=crew_locations,
            crew_transfers=crew_transfers,
        )
        plan.append(
            (
                selected,
                _progress_increment(before_progress, planned_progress),
                crew_activity,
                crew_transfers,
            )
        )
        remaining_demand = {
            demand: max(
                0.0,
                base.demand_amounts[demand] - planned_delivered[demand],
            )
            for demand in base.demands
        }
        dispatch = _dispatch_with_vehicle_types(
            instance,
            dispatch_priority,
            planned_progress,
            planned_supply,
            remaining_demand,
        )
        for demand, amount in dispatch["delivered"].items():
            planned_delivered[demand] += amount
    return plan


def _build_static_plan(base, schedule):
    plan = []
    previous = {edge_id: 0.0 for edge_id in base.damaged_edges}
    for period in range(1, base.periods + 1):
        planned = _repair_progress_by_damage(
            base,
            schedule,
            period * base.eta_minutes,
        )
        selected = [
            task.damage_id for task in schedule
            if task.start_time < period * base.eta_minutes
            and task.finish_time > (period - 1) * base.eta_minutes
        ]
        crew_activity = {
            crew_id: [
                task.damage_id
                for task in sorted(schedule, key=lambda item: item.start_time)
                if task.team_id == crew_id
                and task.start_time < period * base.eta_minutes
                and task.finish_time > (period - 1) * base.eta_minutes
            ]
            for crew_id in range(base.repair_crews)
        }
        period_start = (period - 1) * base.eta_minutes
        period_end = period * base.eta_minutes
        crew_transfers = {crew_id: [] for crew_id in range(base.repair_crews)}
        for task in schedule:
            transfer_start = task.start_time - task.transfer_time
            overlap = max(
                0.0,
                min(task.start_time, period_end) - max(transfer_start, period_start),
            )
            if overlap > 1e-9:
                crew_transfers[task.team_id].append({
                    "to_damage_id": task.damage_id,
                    "minutes": overlap,
                    "path": list(task.transfer_path),
                })
        plan.append(
            (
                selected,
                _progress_increment(previous, planned),
                crew_activity,
                crew_transfers,
            )
        )
        previous = planned
    return plan


def _reachable_demands(instance, progress):
    reachable = set()
    for vehicle in instance.vehicles:
        reachable.update(
            demand
            for _supplier, demand in _shortest_paths_for_vehicle(
                instance,
                progress,
                vehicle,
            )
        )
    return reachable


def _state_snapshot(
    instance,
    mechanism,
    *,
    period,
    progress,
    delivered,
    selected,
    crew_locations,
    reachable_demands,
    period_delivery,
    shipments,
    vehicle_trips,
    crew_transfers,
    crew_activity,
    road_progress_before,
    counterfactual_delivery,
    counterfactual_reachable,
):
    base = instance.base
    total_delivered = sum(
        min(delivered[demand], base.demand_amounts[demand])
        for demand in base.demands
    )
    actual_period_tons = sum(period_delivery.values())
    counterfactual_period_tons = sum(counterfactual_delivery.values())
    newly_reachable = sorted(set(reachable_demands) - set(counterfactual_reachable))
    return {
        "mechanism": mechanism.name,
        "period": period,
        "time_hours": period * base.eta_hours,
        "road_progress": dict(progress),
        "road_progress_before": dict(road_progress_before),
        "delivered_by_demand": dict(delivered),
        "period_delivery_by_demand": dict(period_delivery),
        "period_delivered_tons": sum(period_delivery.values()),
        "shipments": [dict(item) for item in shipments],
        "vehicle_trips": dict(vehicle_trips),
        "reachable_demands": sorted(reachable_demands),
        "selected_repairs": list(selected),
        "crew_locations": {
            crew_id: dict(location)
            for crew_id, location in crew_locations.items()
        },
        "crew_transfers": {
            crew_id: [dict(item) for item in transfers]
            for crew_id, transfers in crew_transfers.items()
        },
        "crew_activity": {
            crew_id: list(damage_ids)
            for crew_id, damage_ids in crew_activity.items()
        },
        "repair_impact": {
            "actual_period_delivery_tons": actual_period_tons,
            "no_current_repair_delivery_tons": counterfactual_period_tons,
            "enabled_delivery_tons": actual_period_tons - counterfactual_period_tons,
            "newly_reachable_demands": newly_reachable,
            "counterfactual_reachable_demands": sorted(counterfactual_reachable),
        },
        "total_satisfaction": total_delivered / max(base.total_demand, 1e-9),
    }


def _sample_repair_efficiencies(base, seed, uncertainty):
    rng = random.Random(seed)
    return {
        (period, edge_id): rng.uniform(uncertainty.lower, uncertainty.upper)
        for period in range(1, base.periods + 1)
        for edge_id in sorted(base.damaged_edges)
    }


def _repair_efficiency_rows(base, scenario_seed, uncertainty):
    realization = _sample_repair_efficiencies(base, scenario_seed, uncertainty)
    return [
        {
            "repair_efficiency_scenario_seed": scenario_seed,
            "period": period,
            "damage_id": edge_id,
            "repair_efficiency": realization[(period, edge_id)],
            "repair_efficiency_deviation": uncertainty.deviation,
            "distribution": "uniform",
            "lower_bound": uncertainty.lower,
            "upper_bound": uncertainty.upper,
        }
        for period in range(1, base.periods + 1)
        for edge_id in sorted(base.damaged_edges)
    ]


def _progress_increment(before, after):
    return {
        edge_id: max(0.0, after.get(edge_id, 0.0) - before.get(edge_id, 0.0))
        for edge_id in before
    }


def _apply_repair_efficiency(progress, planned_increment, efficiency):
    return {
        edge_id: min(
            1.0,
            progress.get(edge_id, 0.0)
            + planned_increment.get(edge_id, 0.0) * efficiency[edge_id],
        )
        for edge_id in progress
    }


def _objective_aligned_step(
    instance,
    progress,
    delivered,
    remaining_supply,
    dispatch_priority,
    work_minutes,
    *,
    crew_activity=None,
    crew_locations=None,
    crew_transfers=None,
):
    base = instance.base
    chosen = []
    active = set()
    access_progress = dict(progress)
    if crew_locations is None:
        crew_locations = {
            crew_id: {
                "kind": "node",
                "node_id": base.suppliers[crew_id % len(base.suppliers)],
            }
            for crew_id in range(base.repair_crews)
        }
    for crew_id in range(base.repair_crews):
        if crew_activity is not None:
            crew_activity.setdefault(crew_id, [])
        if crew_transfers is not None:
            crew_transfers.setdefault(crew_id, [])
        budget = float(work_minutes)
        while budget > 1e-9:
            candidate_ids = [
                edge_id for edge_id, value in progress.items()
                if value < 1 - 1e-9 and edge_id not in active
            ]
            candidates = []
            for edge_id in candidate_ids:
                transfer_minutes, transfer_path = _crew_transfer(
                    base,
                    crew_locations[crew_id],
                    edge_id,
                    instance.crew_transfer_time_scale,
                    access_progress,
                    instance.crew_min_access_progress,
                )
                repair_budget = budget - transfer_minutes
                if repair_budget <= 1e-9:
                    continue
                candidates.append(
                    (
                        _candidate_objective_gain(
                            instance,
                            progress,
                            delivered,
                            remaining_supply,
                            dispatch_priority,
                            edge_id,
                            repair_budget,
                        ),
                        -transfer_minutes,
                        -edge_id,
                        edge_id,
                        transfer_minutes,
                        transfer_path,
                    )
                )
            if not candidates:
                break
            best_item = max(candidates)
            best = best_item[3]
            transfer_minutes = best_item[4]
            transfer_path = best_item[5]
            if best not in chosen:
                chosen.append(best)
            if crew_activity is not None:
                crew_activity[crew_id].append(best)
            if crew_transfers is not None and transfer_minutes > 1e-9:
                crew_transfers[crew_id].append({
                    "to_damage_id": best,
                    "minutes": transfer_minutes,
                    "path": list(transfer_path),
                })
            budget -= transfer_minutes
            previous_location = crew_locations[crew_id]
            access_node = (
                transfer_path[-1]
                if transfer_path
                else previous_location.get("access_node")
            )
            crew_locations[crew_id] = {
                "kind": "edge",
                "damage_id": best,
                "access_node": access_node,
            }
            active.add(best)
            edge = base.damaged_edges[best]
            work_needed = (1.0 - progress[best]) * edge.repair_time
            work = min(budget, work_needed)
            progress[best] += work / max(edge.repair_time, 1e-9)
            budget -= work
            if progress[best] >= 1 - 1e-9:
                active.remove(best)
    return chosen


def _apply_stress(
    instance,
    repair_scale,
    crews,
    capacity_scale=1.0,
    crew_transfer_time_scale=None,
    crew_min_access_progress=None,
):
    base = instance.base
    base.repair_crews = crews
    instance.capacity_scale = capacity_scale
    if crew_transfer_time_scale is not None:
        instance.crew_transfer_time_scale = crew_transfer_time_scale
    if crew_min_access_progress is not None:
        instance.crew_min_access_progress = crew_min_access_progress
    base.damaged_edges = {
        edge_id: replace(edge, repair_time=edge.repair_time * repair_scale)
        for edge_id, edge in base.damaged_edges.items()
    }
    for edge in base.damaged_edges.values():
        base.graph[edge.u][edge.v]["repair_time"] = edge.repair_time
    return instance


def _candidate_objective_gain(
    instance,
    progress,
    delivered,
    remaining_supply,
    dispatch_priority,
    edge_id,
    work_minutes,
):
    """Return lexicographic gains aligned with F1, F3, then delivery-time F2."""
    base = instance.base
    remaining_demand = {
        demand: max(0.0, base.demand_amounts[demand] - delivered[demand])
        for demand in base.demands
    }
    before_dispatch = _dispatch_with_vehicle_types(
        instance,
        dispatch_priority,
        progress,
        dict(remaining_supply),
        remaining_demand,
    )
    after_progress = dict(progress)
    edge = base.damaged_edges[edge_id]
    available_work = min(
        float(work_minutes),
        (1.0 - progress[edge_id]) * edge.repair_time,
    )
    after_progress[edge_id] = min(
        1.0,
        after_progress[edge_id] + available_work / max(edge.repair_time, 1e-9),
    )
    after_dispatch = _dispatch_with_vehicle_types(
        instance,
        dispatch_priority,
        after_progress,
        dict(remaining_supply),
        remaining_demand,
    )

    before_unmet, before_min = _post_dispatch_service_metrics(
        base, delivered, before_dispatch["delivered"]
    )
    after_unmet, after_min = _post_dispatch_service_metrics(
        base, delivered, after_dispatch["delivered"]
    )
    return (
        before_unmet - after_unmet,
        after_min - before_min,
        before_dispatch["delivery_time"] - after_dispatch["delivery_time"],
    )


def _post_dispatch_service_metrics(base, delivered, period_delivery):
    cumulative = {
        demand: min(
            base.demand_amounts[demand],
            delivered[demand] + period_delivery.get(demand, 0.0),
        )
        for demand in base.demands
    }
    unmet = sum(
        base.demand_amounts[demand] - cumulative[demand]
        for demand in base.demands
    )
    minimum_satisfaction = min(
        cumulative[demand] / max(base.demand_amounts[demand], 1e-9)
        for demand in base.demands
    )
    return unmet, minimum_satisfaction


def _best_paths(instance, progress):
    best = {}
    for vehicle in instance.vehicles:
        for (_, demand), (time_value, path) in _shortest_paths_for_vehicle(
            instance, progress, vehicle
        ).items():
            candidate = (time_value, tuple(path))
            if demand not in best or candidate < best[demand]:
                best[demand] = candidate
    return {demand: item[1] for demand, item in best.items()}


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["wenchuan", "simulation"], default="wenchuan")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--sim-nodes", type=int, default=25)
    parser.add_argument("--repair-scale", type=float, default=1.0)
    parser.add_argument("--crews", type=int, default=3)
    parser.add_argument("--capacity-scale", type=float, default=1.0)
    parser.add_argument(
        "--crew-transfer-time-scale",
        type=float,
        default=0.0,
        help=(
            "Multiplier for midpoint-to-midpoint repair-crew transfer time; "
            "0 preserves the original no-transfer assumption."
        ),
    )
    parser.add_argument(
        "--crew-min-access-progress",
        type=float,
        default=0.0,
        help="Minimum road recovery progress usable by a moving repair crew.",
    )
    parser.add_argument(
        "--repair-efficiency-deviation",
        type=float,
        default=0.30,
        help="Uniform repair-efficiency deviation around 1.0; 0.30 means U[0.7, 1.3].",
    )
    parser.add_argument("--output-dir", default="outputs/dynamic_interaction")
    args = parser.parse_args()
    if args.capacity_scale <= 0:
        parser.error("--capacity-scale must be greater than zero")
    if args.crew_transfer_time_scale < 0:
        parser.error("--crew-transfer-time-scale must be non-negative")
    if not 0.0 <= args.crew_min_access_progress <= 1.0:
        parser.error("--crew-min-access-progress must be in [0, 1]")
    if args.seeds <= 0:
        parser.error("--seeds must be greater than zero")
    if not 0.0 <= args.repair_efficiency_deviation < 1.0:
        parser.error("--repair-efficiency-deviation must be in [0, 1)")
    uncertainty = RepairEfficiencyUncertainty(args.repair_efficiency_deviation)
    summaries, periods, efficiency_rows = [], [], []
    for seed in range(args.seed_start, args.seed_start + args.seeds):
        instance = (
            build_wenchuan_instance(seed) if args.scenario == "wenchuan"
            else build_simulation_instance(seed, num_nodes=args.sim_nodes)
        )
        instance = _apply_stress(
            instance,
            args.repair_scale,
            args.crews,
            args.capacity_scale,
            args.crew_transfer_time_scale,
            args.crew_min_access_progress,
        )
        efficiency_seed = seed + 40000
        for row in _repair_efficiency_rows(instance.base, efficiency_seed, uncertainty):
            row["scenario"] = args.scenario
            row["scenario_seed"] = seed
            row["repair_scale"] = args.repair_scale
            row["crews"] = args.crews
            row["capacity_scale"] = args.capacity_scale
            efficiency_rows.append(row)
        for mechanism in MECHANISMS:
            summary, rows = run_mechanism(
                instance,
                mechanism,
                efficiency_seed,
                args.repair_efficiency_deviation,
            )
            summary["scenario"] = args.scenario
            summary["scenario_seed"] = seed
            summary["repair_scale"] = args.repair_scale
            summary["crews"] = args.crews
            summary["capacity_scale"] = args.capacity_scale
            summary["crew_transfer_time_scale"] = args.crew_transfer_time_scale
            summary["crew_min_access_progress"] = args.crew_min_access_progress
            summary["repair_efficiency_deviation"] = args.repair_efficiency_deviation
            for row in rows:
                row["scenario"] = args.scenario
                row["scenario_seed"] = seed
                row["repair_scale"] = args.repair_scale
                row["crews"] = args.crews
                row["capacity_scale"] = args.capacity_scale
                row["crew_transfer_time_scale"] = args.crew_transfer_time_scale
                row["crew_min_access_progress"] = args.crew_min_access_progress
                row["repair_efficiency_deviation"] = args.repair_efficiency_deviation
            summaries.append(summary)
            periods.extend(rows)
            print(mechanism.name, seed, summary)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "mechanism_summary.csv", summaries)
    _write_csv(output / "period_dynamics.csv", periods)
    _write_csv(output / "repair_efficiency_realizations.csv", efficiency_rows)


if __name__ == "__main__":
    run_cli()
