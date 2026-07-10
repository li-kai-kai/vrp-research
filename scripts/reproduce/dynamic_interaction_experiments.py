from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from dataclasses import dataclass, replace
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.capacity_recovery import (
    CapacityExperimentInstance,
    RecoveryStage,
    VehicleProfile,
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
    rolling_feedback: bool


MECHANISMS = (
    Mechanism("binary_static", False, False),
    Mechanism("progressive_static", True, False),
    Mechanism("progressive_rolling", True, True),
)


def run_mechanism(instance, mechanism, seed):
    rng = random.Random(seed)
    variant = _variant(instance, mechanism.progressive)
    base = variant.base
    priority = [(s, d) for s in base.suppliers for d in base.demands]
    priority.sort(key=lambda pair: (-base.demand_amounts[pair[1]], pair))
    order = sorted(
        base.damaged_edges,
        key=lambda edge_id: (base.damaged_edges[edge_id].repair_time, edge_id),
    )
    schedule = _decode_timed_schedule(
        base, order, [idx % base.repair_crews for idx in range(len(order))]
    )
    progress = {edge_id: 0.0 for edge_id in base.damaged_edges}
    remaining_supply = dict(base.supply_amounts)
    delivered = {demand: 0.0 for demand in base.demands}
    previous_paths = {}
    rows = []
    unmet_area = 0.0
    path_switches = 0

    for period in range(1, base.periods + 1):
        if mechanism.rolling_feedback:
            selected = _rolling_step(
                variant, progress, delivered, base.eta_minutes, rng
            )
        else:
            progress = _repair_progress_by_damage(
                base, schedule, period * base.eta_minutes
            )
            selected = [
                task.damage_id for task in schedule
                if task.start_time < period * base.eta_minutes
                and task.finish_time > (period - 1) * base.eta_minutes
            ]

        remaining_demand = {
            d: max(0.0, base.demand_amounts[d] - delivered[d])
            for d in base.demands
        }
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
        })

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
    }
    return summary, rows


def _variant(instance, progressive):
    if progressive:
        return instance
    vehicles = [
        VehicleProfile(
            v.vehicle_type, v.capacity_ton, v.count, v.pcu_impact, 1.0, v.speed_factor
        )
        for v in instance.vehicles
    ]
    stages = [
        RecoveryStage(0.0, 1.0, 0.0, "blocked"),
        RecoveryStage(1.0, 1.01, 1.0, "full"),
    ]
    return CapacityExperimentInstance(instance.base, vehicles, stages)


def _rolling_step(instance, progress, delivered, work_minutes, rng):
    base = instance.base
    chosen = []
    active = set()
    for _crew in range(base.repair_crews):
        budget = float(work_minutes)
        while budget > 1e-9:
            candidates = [
                edge_id for edge_id, value in progress.items()
                if value < 1 - 1e-9 and edge_id not in active
            ]
            if not candidates:
                break
            remaining = {
                d: max(0.0, base.demand_amounts[d] - delivered[d])
                for d in base.demands
            }
            scored = [
                (_marginal_score(instance, progress, remaining, edge_id, budget),
                 rng.random(), edge_id)
                for edge_id in candidates
            ]
            best = max(scored)[2]
            if best not in chosen:
                chosen.append(best)
            active.add(best)
            edge = base.damaged_edges[best]
            work_needed = (1.0 - progress[best]) * edge.repair_time
            work = min(budget, work_needed)
            progress[best] += work / max(edge.repair_time, 1e-9)
            budget -= work
            if progress[best] >= 1 - 1e-9:
                active.remove(best)
    return chosen


def _apply_stress(instance, repair_scale, crews):
    base = instance.base
    base.repair_crews = crews
    base.damaged_edges = {
        edge_id: replace(edge, repair_time=edge.repair_time * repair_scale)
        for edge_id, edge in base.damaged_edges.items()
    }
    for edge in base.damaged_edges.values():
        base.graph[edge.u][edge.v]["repair_time"] = edge.repair_time
    return instance


def _marginal_score(instance, progress, remaining, edge_id, work_minutes):
    before = _access_value(instance, progress, remaining)
    after_progress = dict(progress)
    edge = instance.base.damaged_edges[edge_id]
    after_progress[edge_id] = min(
        1.0, after_progress[edge_id] + work_minutes / edge.repair_time
    )
    after = _access_value(instance, after_progress, remaining)
    threshold_gain = sum(
        v.capacity_ton * v.count for v in instance.vehicles
        if progress[edge_id] < v.min_recovery_progress <= after_progress[edge_id]
    )
    return after - before + 1e-4 * threshold_gain - 1e-6 * edge.repair_time


def _access_value(instance, progress, remaining):
    best = {}
    for vehicle in instance.vehicles:
        for (_, demand), (time_value, _) in _shortest_paths_for_vehicle(
            instance, progress, vehicle
        ).items():
            best[demand] = min(best.get(demand, math.inf), time_value)
    return sum(
        remaining[d] / (1.0 + best[d]) for d in best if remaining[d] > 1e-9
    )


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
    parser.add_argument("--output-dir", default="outputs/dynamic_interaction")
    args = parser.parse_args()
    summaries, periods = [], []
    for seed in range(args.seed_start, args.seed_start + args.seeds):
        instance = (
            build_wenchuan_instance(seed) if args.scenario == "wenchuan"
            else build_simulation_instance(seed, num_nodes=args.sim_nodes)
        )
        instance = _apply_stress(instance, args.repair_scale, args.crews)
        for mechanism in MECHANISMS:
            summary, rows = run_mechanism(instance, mechanism, seed + 40000)
            summary["scenario"] = args.scenario
            summary["repair_scale"] = args.repair_scale
            summary["crews"] = args.crews
            for row in rows:
                row["scenario"] = args.scenario
                row["repair_scale"] = args.repair_scale
                row["crews"] = args.crews
            summaries.append(summary)
            periods.extend(rows)
            print(mechanism.name, seed, summary)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "mechanism_summary.csv", summaries)
    _write_csv(output / "period_dynamics.csv", periods)


if __name__ == "__main__":
    run_cli()

