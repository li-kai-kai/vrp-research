from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.instance_generator import generate_random_instance
from scripts.reproduce.model import DamagedEdge, RandomInstance


@dataclass(frozen=True)
class VehicleProfile:
    vehicle_type: int
    capacity_ton: float
    count: int
    pcu_impact: float
    min_recovery_progress: float
    speed_factor: float = 1.0


@dataclass(frozen=True)
class RecoveryStage:
    lower: float
    upper: float
    capacity_ratio: float
    label: str


@dataclass
class CapacityExperimentInstance:
    base: RandomInstance
    vehicles: list[VehicleProfile]
    recovery_stages: list[RecoveryStage]


@dataclass
class TimedRepairTask:
    damage_id: int
    team_id: int
    start_time: float
    finish_time: float
    repair_time: float


@dataclass
class CapacityIndividual:
    repair_order: list[int]
    team_assignment: list[int]
    dispatch_priority: list[tuple[int, int]]
    objectives: tuple[float, float, float] | None = None
    metrics: dict[str, float] | None = None
    rank: int = 0
    crowding: float = 0.0

    def clone(self) -> CapacityIndividual:
        return CapacityIndividual(
            repair_order=list(self.repair_order),
            team_assignment=list(self.team_assignment),
            dispatch_priority=list(self.dispatch_priority),
            objectives=self.objectives,
            metrics=dict(self.metrics) if self.metrics is not None else None,
            rank=self.rank,
            crowding=self.crowding,
        )


@dataclass(frozen=True)
class CapacityNSGAConfig:
    pop_size: int = 32
    generations: int = 30
    crossover_probability: float = 0.9
    mutation_probability: float = 0.2
    alns_probability: float = 0.35
    alns_iterations: int = 12


@dataclass
class CapacityExperimentResult:
    instance_name: str
    scenario: str
    seed: int
    algorithm: str
    objectives: tuple[float, float, float]
    metrics: dict[str, float]
    repair_order: list[int]
    team_assignment: list[int]
    runtime_seconds: float
    convergence: list[dict[str, float]] = field(default_factory=list)

    def summary_row(self) -> dict[str, Any]:
        return {
            "instance": self.instance_name,
            "scenario": self.scenario,
            "seed": self.seed,
            "algorithm": self.algorithm,
            "unmet_area": self.objectives[0],
            "time_cost": self.objectives[1],
            "neg_min_satisfaction": self.objectives[2],
            "final_total_satisfaction": self.metrics["final_total_satisfaction"],
            "final_min_satisfaction": self.metrics["final_min_satisfaction"],
            "average_reachable_ratio": self.metrics["average_reachable_ratio"],
            "final_repaired_ratio": self.metrics["final_repaired_ratio"],
            "partial_recovery_edge_periods": self.metrics["partial_recovery_edge_periods"],
            "small_vehicle_share": self.metrics["small_vehicle_share"],
            "runtime_seconds": self.runtime_seconds,
        }

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "summary": self.summary_row(),
            "repair_order": self.repair_order,
            "team_assignment": self.team_assignment,
            "objectives": self.objectives,
            "metrics": self.metrics,
            "convergence": self.convergence,
        }


DEFAULT_RECOVERY_STAGES = [
    RecoveryStage(0.0, 0.30, 0.0, "blocked"),
    RecoveryStage(0.30, 0.60, 0.30, "temporary"),
    RecoveryStage(0.60, 0.80, 0.60, "one_lane"),
    RecoveryStage(0.80, 1.0, 0.80, "basic"),
    RecoveryStage(1.0, 1.01, 1.0, "full"),
]


DEFAULT_VEHICLES = [
    VehicleProfile(1, capacity_ton=5.0, count=150, pcu_impact=300, min_recovery_progress=0.30),
    VehicleProfile(2, capacity_ton=10.0, count=110, pcu_impact=500, min_recovery_progress=0.50),
    VehicleProfile(3, capacity_ton=15.0, count=70, pcu_impact=800, min_recovery_progress=0.70),
    VehicleProfile(4, capacity_ton=20.0, count=40, pcu_impact=1000, min_recovery_progress=0.80),
]


def build_simulation_instance(seed: int, *, num_nodes: int = 25) -> CapacityExperimentInstance:
    base = generate_random_instance(
        num_nodes=num_nodes,
        gamma=3,
        damage_ratio=0.25,
        eta_hours=8,
        seed=seed,
        supply_ratio=0.9,
    )
    for _, _, data in base.graph.edges(data=True):
        data.setdefault("free_time", data.get("weight", 1.0))
        data.setdefault("capacity", 1500.0)
    return CapacityExperimentInstance(
        base=base,
        vehicles=DEFAULT_VEHICLES,
        recovery_stages=DEFAULT_RECOVERY_STAGES,
    )


def build_wenchuan_instance(seed: int = 0) -> CapacityExperimentInstance:
    nodes = {
        1: ("Dujiangyan", "S", 3000), 2: ("Pengzhou", "S", 3000), 3: ("Shifang", "S", 3000),
        4: ("Yutang", "D", 342), 5: ("Zhongxing", "D", 360), 6: ("Qingchengshan", "D", 322),
        7: ("Daguang", "D", 361), 8: ("Anlong", "D", 382), 9: ("Shiyang", "D", 327),
        10: ("Cuiyuehu", "D", 361), 11: ("Zipingpu", "D", 344), 12: ("Longchi", "D", 321),
        13: ("Xingfu", "D", 363), 14: ("Juyuan", "D", 344), 15: ("Chongyi", "D", 384),
        16: ("Xujia", "D", 251), 17: ("Puyang", "D", 339), 18: ("Hongkou", "D", 358),
        19: ("Xiang'e", "D", 302), 20: ("Tianma", "D", 282), 21: ("Lichun", "D", 281),
        22: ("Guihua", "D", 205), 23: ("Longfeng", "D", 324), 24: ("Danjingshan", "D", 280),
        25: ("Cifeng", "D", 241), 26: ("Tongji", "D", 382), 27: ("Xinxing", "D", 320),
        28: ("Xiaoyudong", "D", 262), 29: ("Longmenshan", "D", 328), 30: ("Gexianshan", "D", 320),
        31: ("Hongyan", "D", 268), 32: ("Shigu", "D", 323), 33: ("Jiandi", "D", 300),
        34: ("Bailu", "D", 282), 35: ("Bajiao", "D", 359), 36: ("Luoshui", "D", 365),
        37: ("Yinghua", "D", 302), 38: ("Hongbai", "D", 403),
    }
    edge_rows = [
        (1, 4, 16, 1200), (1, 11, 36, 1200), (1, 13, 16, 1200), (1, 17, 28, 1200),
        (2, 23, 40, 1200), (2, 21, 36, 1200), (2, 3, 50, 1000), (3, 32, 52, 1000),
        (3, 36, 60, 1000), (4, 11, 40, 600), (4, 5, 22, 1000), (5, 6, 18, 1000),
        (6, 7, 24, 1000), (6, 10, 13, 1000), (7, 8, 34, 800), (8, 9, 50, 600),
        (9, 10, 50, 600), (11, 12, 64, 500), (11, 18, 74, 500), (13, 17, 24, 1000),
        (13, 16, 24, 1000), (13, 14, 22, 1000), (14, 15, 16, 1000), (16, 22, 42, 600),
        (16, 20, 28, 800), (17, 19, 28, 800), (17, 22, 36, 800), (18, 25, 180, 400),
        (19, 25, 32, 800), (20, 21, 56, 600), (21, 23, 48, 600), (22, 24, 28, 800),
        (22, 23, 34, 800), (23, 24, 16, 1000), (24, 27, 24, 1000), (24, 30, 64, 500),
        (25, 26, 50, 600), (26, 28, 32, 800), (26, 34, 46, 600), (26, 27, 20, 1000),
        (28, 29, 28, 800), (30, 31, 28, 800), (31, 32, 46, 600), (32, 33, 36, 800),
        (32, 36, 56, 600), (33, 34, 60, 500), (33, 36, 24, 1000), (34, 35, 100, 400),
        (35, 37, 32, 800), (36, 37, 56, 600), (37, 38, 52, 600),
    ]
    damaged_rows = [
        (0, 1, 17, 900), (1, 4, 5, 180), (2, 11, 12, 270), (3, 11, 18, 210),
        (4, 13, 14, 720), (5, 17, 19, 1080), (6, 17, 22, 180), (7, 18, 25, 270),
        (8, 22, 24, 810), (9, 24, 30, 270), (10, 26, 28, 720), (11, 26, 34, 1050),
        (12, 28, 29, 360), (13, 33, 34, 180), (14, 34, 35, 450), (15, 36, 37, 330),
    ]

    graph = nx.Graph()
    for node_id, (name, node_type, value) in nodes.items():
        graph.add_node(node_id, name=name, node_type=node_type, value=value)
    for edge_id, (u, v, free_time, capacity) in enumerate(edge_rows):
        graph.add_edge(
            u,
            v,
            edge_id=edge_id,
            free_time=float(free_time),
            weight=float(free_time),
            capacity=float(capacity),
            damaged=False,
        )

    damaged_edges: dict[int, DamagedEdge] = {}
    for damage_id, u, v, repair_time in damaged_rows:
        if not graph.has_edge(u, v):
            raise ValueError(f"Wenchuan damaged edge {(u, v)} is missing from base graph")
        graph[u][v]["damaged"] = True
        graph[u][v]["damage_id"] = damage_id
        graph[u][v]["repair_time"] = float(repair_time)
        damaged_edges[damage_id] = DamagedEdge(damage_id, u, v, float(repair_time))

    suppliers = [node_id for node_id, (_, node_type, _) in nodes.items() if node_type == "S"]
    demands = [node_id for node_id, (_, node_type, _) in nodes.items() if node_type == "D"]
    supply_amounts = {node_id: float(nodes[node_id][2]) for node_id in suppliers}
    demand_amounts = {node_id: float(nodes[node_id][2]) for node_id in demands}

    base = RandomInstance(
        name="wenchuan_capacity_recovery",
        seed=seed,
        num_nodes=len(nodes),
        gamma=0,
        damage_ratio=len(damaged_edges) / graph.number_of_edges(),
        eta_hours=8,
        horizon_hours=72,
        graph=graph,
        suppliers=suppliers,
        demands=demands,
        demand_amounts=demand_amounts,
        supply_amounts=supply_amounts,
        damaged_edges=damaged_edges,
        repair_crews=3,
        vehicle_capacity=100.0,
        vehicle_count=10,
    )
    return CapacityExperimentInstance(
        base=base,
        vehicles=DEFAULT_VEHICLES,
        recovery_stages=DEFAULT_RECOVERY_STAGES,
    )


def solve_capacity_instance(
    instance: CapacityExperimentInstance,
    config: CapacityNSGAConfig,
    *,
    seed: int,
    scenario: str,
) -> CapacityExperimentResult:
    rng = random.Random(seed)
    start = time.perf_counter()
    population = [_create_individual(instance, rng) for _ in range(config.pop_size)]
    convergence: list[dict[str, float]] = []

    for generation in range(config.generations):
        _evaluate_population(instance, population)
        fronts = _assign_rank_and_crowding(population)
        best_front = fronts[0] if fronts else []
        if best_front:
            best = min(best_front, key=_representative_key)
            convergence.append(_convergence_row(generation, best))

        offspring: list[CapacityIndividual] = []
        while len(offspring) < config.pop_size:
            parent_a = _tournament(population, rng)
            parent_b = _tournament(population, rng)
            if rng.random() < config.crossover_probability:
                child_a, child_b = _crossover(instance, parent_a, parent_b, rng)
            else:
                child_a, child_b = parent_a.clone(), parent_b.clone()
            _mutate(instance, child_a, config.mutation_probability, rng)
            _mutate(instance, child_b, config.mutation_probability, rng)
            if rng.random() < config.alns_probability:
                child_a = _alns_improve(instance, child_a, config.alns_iterations, rng)
            if rng.random() < config.alns_probability:
                child_b = _alns_improve(instance, child_b, config.alns_iterations, rng)
            offspring.append(child_a)
            if len(offspring) < config.pop_size:
                offspring.append(child_b)

        _evaluate_population(instance, offspring)
        population = _select_next_generation(population + offspring, config.pop_size)

    _evaluate_population(instance, population)
    fronts = _assign_rank_and_crowding(population)
    best_front = fronts[0]
    best = min(best_front, key=_representative_key)
    runtime = time.perf_counter() - start
    return CapacityExperimentResult(
        instance_name=instance.base.name,
        scenario=scenario,
        seed=seed,
        algorithm="NSGA-II-ALNS-prototype",
        objectives=best.objectives or (math.inf, math.inf, math.inf),
        metrics=best.metrics or {},
        repair_order=best.repair_order,
        team_assignment=best.team_assignment,
        runtime_seconds=runtime,
        convergence=convergence,
    )


def evaluate_capacity_solution(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
) -> tuple[tuple[float, float, float], dict[str, float]]:
    base = instance.base
    schedule = _decode_timed_schedule(base, individual.repair_order, individual.team_assignment)
    remaining_supply = dict(base.supply_amounts)
    delivered = {demand: 0.0 for demand in base.demands}
    total_delivery_time = 0.0
    total_repair_work = sum(
        max(0.0, min(task.finish_time, base.horizon_minutes) - task.start_time)
        for task in schedule
        if task.start_time < base.horizon_minutes
    )
    unmet_area = 0.0
    reachable_ratios: list[float] = []
    partial_recovery_edge_periods = 0
    vehicle_ton_by_type = {vehicle.vehicle_type: 0.0 for vehicle in instance.vehicles}

    for period in range(1, base.periods + 1):
        time_minutes = period * base.eta_minutes
        progress = _repair_progress_by_damage(base, schedule, time_minutes)
        for value in progress.values():
            if 1e-9 < value < 1.0 - 1e-9:
                partial_recovery_edge_periods += 1

        remaining_demand = {
            demand: max(0.0, base.demand_amounts[demand] - delivered[demand])
            for demand in base.demands
        }
        period_result = _dispatch_with_vehicle_types(
            instance,
            individual.dispatch_priority,
            progress,
            remaining_supply,
            remaining_demand,
        )
        for demand, amount in period_result["delivered"].items():
            delivered[demand] += amount
        total_delivery_time += period_result["delivery_time"]
        for vehicle_type, amount in period_result["vehicle_tons"].items():
            vehicle_ton_by_type[vehicle_type] += amount
        reachable_ratios.append(period_result["reachable_count"] / max(len(base.demands), 1))
        total_delivered = sum(min(delivered[d], base.demand_amounts[d]) for d in base.demands)
        total_satisfaction = total_delivered / max(base.total_demand, 1e-9)
        unmet_area += 1.0 - total_satisfaction

    satisfaction_values = [
        min(1.0, delivered[demand] / max(base.demand_amounts[demand], 1e-9))
        for demand in base.demands
    ]
    final_total_satisfaction = sum(
        min(delivered[demand], base.demand_amounts[demand])
        for demand in base.demands
    ) / max(base.total_demand, 1e-9)
    final_min_satisfaction = min(satisfaction_values) if satisfaction_values else 0.0
    repaired_count = sum(
        1
        for task in schedule
        if task.finish_time <= base.horizon_minutes
    )
    small_vehicle_tons = sum(
        amount
        for vehicle_type, amount in vehicle_ton_by_type.items()
        if vehicle_type <= 2
    )
    all_vehicle_tons = sum(vehicle_ton_by_type.values())
    time_cost = total_delivery_time + 0.05 * total_repair_work
    objectives = (
        unmet_area,
        time_cost,
        -final_min_satisfaction,
    )
    metrics = {
        "final_total_satisfaction": final_total_satisfaction,
        "final_min_satisfaction": final_min_satisfaction,
        "average_reachable_ratio": sum(reachable_ratios) / max(len(reachable_ratios), 1),
        "final_repaired_ratio": repaired_count / max(len(base.damaged_edges), 1),
        "total_delivery_time": total_delivery_time,
        "total_repair_work": total_repair_work,
        "partial_recovery_edge_periods": float(partial_recovery_edge_periods),
        "small_vehicle_share": small_vehicle_tons / max(all_vehicle_tons, 1e-9),
    }
    return objectives, metrics


def _decode_timed_schedule(
    base: RandomInstance,
    repair_order: list[int],
    team_assignment: list[int],
) -> list[TimedRepairTask]:
    team_free = {team_id: 0.0 for team_id in range(base.repair_crews)}
    tasks: list[TimedRepairTask] = []
    seen: set[int] = set()
    for idx, damage_id in enumerate(repair_order):
        if damage_id in seen or damage_id not in base.damaged_edges:
            continue
        seen.add(damage_id)
        team_id = team_assignment[idx] % base.repair_crews
        repair_time = base.damaged_edges[damage_id].repair_time
        start_time = team_free[team_id]
        finish_time = start_time + repair_time
        team_free[team_id] = finish_time
        tasks.append(
            TimedRepairTask(
                damage_id=damage_id,
                team_id=team_id,
                start_time=start_time,
                finish_time=finish_time,
                repair_time=repair_time,
            )
        )
    return tasks


def _repair_progress_by_damage(
    base: RandomInstance,
    schedule: list[TimedRepairTask],
    time_minutes: float,
) -> dict[int, float]:
    progress = {damage_id: 0.0 for damage_id in base.damaged_edges}
    for task in schedule:
        if time_minutes <= task.start_time:
            value = 0.0
        elif time_minutes >= task.finish_time:
            value = 1.0
        else:
            value = (time_minutes - task.start_time) / max(task.repair_time, 1e-9)
        progress[task.damage_id] = min(1.0, max(0.0, value))
    return progress


def _dispatch_with_vehicle_types(
    instance: CapacityExperimentInstance,
    dispatch_priority: list[tuple[int, int]],
    progress: dict[int, float],
    remaining_supply: dict[int, float],
    remaining_demand: dict[int, float],
) -> dict[str, Any]:
    base = instance.base
    vehicle_capacity_left = {
        vehicle.vehicle_type: vehicle.capacity_ton * vehicle.count
        for vehicle in instance.vehicles
    }
    shortest_by_vehicle = {
        vehicle.vehicle_type: _shortest_paths_for_vehicle(instance, progress, vehicle)
        for vehicle in instance.vehicles
    }
    reachable = set()
    for paths in shortest_by_vehicle.values():
        reachable.update(demand for _, demand in paths)

    delivered = {demand: 0.0 for demand in base.demands}
    vehicle_tons = {vehicle.vehicle_type: 0.0 for vehicle in instance.vehicles}
    delivery_time = 0.0
    reachable_demands = [
        demand
        for demand in base.demands
        if demand in reachable and remaining_demand.get(demand, 0.0) > 1e-9
    ]
    available_supply = sum(max(0.0, remaining_supply.get(supplier, 0.0)) for supplier in base.suppliers)
    available_vehicle_capacity = sum(max(0.0, value) for value in vehicle_capacity_left.values())
    fair_resource = min(available_supply, available_vehicle_capacity)
    current_delivered = {
        demand: max(0.0, base.demand_amounts[demand] - remaining_demand.get(demand, 0.0))
        for demand in base.demands
    }
    fair_ceiling = min(1.0, base.total_supply / max(base.total_demand, 1e-9))
    target_level = min(
        fair_ceiling,
        _max_min_satisfaction_target(
            base,
            reachable_demands,
            current_delivered,
            fair_resource,
        ),
    )
    fair_targets = {
        demand: min(
            remaining_demand[demand],
            max(0.0, target_level * base.demand_amounts[demand] - current_delivered[demand]),
        )
        for demand in reachable_demands
    }
    delivery_time += _allocate_vehicle_aware(
        instance,
        dispatch_priority,
        shortest_by_vehicle,
        remaining_supply,
        vehicle_capacity_left,
        delivered,
        vehicle_tons,
        fair_targets,
    )
    residual_targets = {
        demand: min(
            remaining_demand.get(demand, 0.0),
            max(0.0, fair_ceiling * base.demand_amounts[demand] - current_delivered[demand]),
        )
        for demand in reachable_demands
    }
    delivery_time += _allocate_vehicle_aware(
        instance,
        dispatch_priority,
        shortest_by_vehicle,
        remaining_supply,
        vehicle_capacity_left,
        delivered,
        vehicle_tons,
        residual_targets,
    )

    return {
        "delivered": delivered,
        "delivery_time": delivery_time,
        "reachable_count": len(reachable),
        "vehicle_tons": vehicle_tons,
    }


def _max_min_satisfaction_target(
    base: RandomInstance,
    reachable_demands: list[int],
    current_delivered: dict[int, float],
    available_resource: float,
) -> float:
    if not reachable_demands or available_resource <= 1e-9:
        return 0.0
    low = min(
        current_delivered[demand] / max(base.demand_amounts[demand], 1e-9)
        for demand in reachable_demands
    )
    high = 1.0
    for _ in range(40):
        mid = (low + high) / 2.0
        needed = sum(
            max(0.0, mid * base.demand_amounts[demand] - current_delivered[demand])
            for demand in reachable_demands
        )
        if needed <= available_resource:
            low = mid
        else:
            high = mid
    return low


def _allocate_vehicle_aware(
    instance: CapacityExperimentInstance,
    dispatch_priority: list[tuple[int, int]],
    shortest_by_vehicle: dict[int, dict[tuple[int, int], tuple[float, list[int]]]],
    remaining_supply: dict[int, float],
    vehicle_capacity_left: dict[int, float],
    delivered: dict[int, float],
    vehicle_tons: dict[int, float],
    targets: dict[int, float],
) -> float:
    delivery_time = 0.0
    for supplier, demand in dispatch_priority:
        if targets.get(demand, 0.0) <= delivered.get(demand, 0.0) + 1e-9:
            continue
        if remaining_supply.get(supplier, 0.0) <= 1e-9:
            continue

        while (
            targets.get(demand, 0.0) > delivered.get(demand, 0.0) + 1e-9
            and remaining_supply.get(supplier, 0.0) > 1e-9
        ):
            candidates = []
            for vehicle in instance.vehicles:
                if vehicle_capacity_left[vehicle.vehicle_type] <= 1e-9:
                    continue
                path_info = shortest_by_vehicle[vehicle.vehicle_type].get((supplier, demand))
                if path_info is None:
                    continue
                candidates.append((path_info[0], vehicle, path_info[1]))
            if not candidates:
                break

            candidates.sort(key=lambda item: (item[0], -item[1].capacity_ton))
            travel_time, vehicle, _path = candidates[0]
            amount = min(
                remaining_supply[supplier],
                targets[demand] - delivered[demand],
                vehicle_capacity_left[vehicle.vehicle_type],
            )
            if amount <= 1e-9:
                break
            trips = max(1, math.ceil(amount / vehicle.capacity_ton))
            remaining_supply[supplier] -= amount
            vehicle_capacity_left[vehicle.vehicle_type] -= amount
            delivered[demand] += amount
            vehicle_tons[vehicle.vehicle_type] += amount
            delivery_time += travel_time * trips
    return delivery_time


def _shortest_paths_for_vehicle(
    instance: CapacityExperimentInstance,
    progress: dict[int, float],
    vehicle: VehicleProfile,
) -> dict[tuple[int, int], tuple[float, list[int]]]:
    graph = _build_vehicle_graph(instance, progress, vehicle)
    paths: dict[tuple[int, int], tuple[float, list[int]]] = {}
    for supplier in instance.base.suppliers:
        lengths, path_map = nx.single_source_dijkstra(graph, supplier, weight="weight")
        for demand in instance.base.demands:
            if demand in lengths:
                paths[(supplier, demand)] = (float(lengths[demand]), path_map[demand])
    return paths


def _build_vehicle_graph(
    instance: CapacityExperimentInstance,
    progress: dict[int, float],
    vehicle: VehicleProfile,
) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(instance.base.graph.nodes(data=True))
    for u, v, data in instance.base.graph.edges(data=True):
        damage_id = data.get("damage_id")
        if damage_id is None:
            ratio = 1.0
            passable = True
        else:
            p = progress.get(damage_id, 0.0)
            ratio = _capacity_ratio(instance.recovery_stages, p)
            passable = p >= vehicle.min_recovery_progress and ratio > 0.0
        if not passable:
            continue
        free_time = float(data.get("free_time", data.get("weight", 1.0)))
        weight = free_time / max(ratio, 0.1) / max(vehicle.speed_factor, 1e-9)
        graph.add_edge(
            u,
            v,
            weight=weight,
            capacity=float(data.get("capacity", 1000.0)) * ratio,
        )
    return graph


def _capacity_ratio(stages: list[RecoveryStage], progress: float) -> float:
    if progress >= 1.0:
        return 1.0
    for stage in stages:
        if stage.lower <= progress < stage.upper:
            return stage.capacity_ratio
    return 0.0


def _representative_key(individual: CapacityIndividual) -> tuple[float, float, float]:
    objectives = individual.objectives or (math.inf, math.inf, math.inf)
    return (
        objectives[2],
        objectives[0],
        objectives[1],
    )


def _create_individual(
    instance: CapacityExperimentInstance,
    rng: random.Random,
) -> CapacityIndividual:
    repair_order = list(instance.base.damaged_edges)
    rng.shuffle(repair_order)
    team_assignment = [rng.randrange(instance.base.repair_crews) for _ in repair_order]
    dispatch_priority = [
        (supplier, demand)
        for supplier in instance.base.suppliers
        for demand in instance.base.demands
    ]
    rng.shuffle(dispatch_priority)
    return CapacityIndividual(repair_order, team_assignment, dispatch_priority)


def _evaluate_population(
    instance: CapacityExperimentInstance,
    population: list[CapacityIndividual],
) -> None:
    for individual in population:
        if individual.objectives is None:
            individual.objectives, individual.metrics = evaluate_capacity_solution(instance, individual)


def _dominates(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> bool:
    return all(a <= b for a, b in zip(left, right)) and any(a < b for a, b in zip(left, right))


def _assign_rank_and_crowding(
    population: list[CapacityIndividual],
) -> list[list[CapacityIndividual]]:
    fronts = _fast_non_dominated_sort(population)
    for rank, front in enumerate(fronts):
        for individual in front:
            individual.rank = rank
            individual.crowding = 0.0
        _assign_crowding(front)
    return fronts


def _fast_non_dominated_sort(
    population: list[CapacityIndividual],
) -> list[list[CapacityIndividual]]:
    dominates_map: dict[int, list[int]] = {idx: [] for idx in range(len(population))}
    dominated_count = {idx: 0 for idx in range(len(population))}
    fronts_idx: list[list[int]] = [[]]
    objectives = [individual.objectives or (math.inf, math.inf, math.inf) for individual in population]

    for p in range(len(population)):
        for q in range(len(population)):
            if p == q:
                continue
            if _dominates(objectives[p], objectives[q]):
                dominates_map[p].append(q)
            elif _dominates(objectives[q], objectives[p]):
                dominated_count[p] += 1
        if dominated_count[p] == 0:
            fronts_idx[0].append(p)

    idx = 0
    while idx < len(fronts_idx) and fronts_idx[idx]:
        next_front: list[int] = []
        for p in fronts_idx[idx]:
            for q in dominates_map[p]:
                dominated_count[q] -= 1
                if dominated_count[q] == 0:
                    next_front.append(q)
        idx += 1
        if next_front:
            fronts_idx.append(next_front)
    return [[population[idx] for idx in front] for front in fronts_idx if front]


def _assign_crowding(front: list[CapacityIndividual]) -> None:
    if len(front) <= 2:
        for individual in front:
            individual.crowding = math.inf
        return
    for obj_idx in range(3):
        front.sort(key=lambda item: (item.objectives or (math.inf, math.inf, math.inf))[obj_idx])
        front[0].crowding = math.inf
        front[-1].crowding = math.inf
        min_value = (front[0].objectives or (0, 0, 0))[obj_idx]
        max_value = (front[-1].objectives or (0, 0, 0))[obj_idx]
        scale = max(max_value - min_value, 1e-9)
        for idx in range(1, len(front) - 1):
            previous_value = (front[idx - 1].objectives or (0, 0, 0))[obj_idx]
            next_value = (front[idx + 1].objectives or (0, 0, 0))[obj_idx]
            front[idx].crowding += (next_value - previous_value) / scale


def _select_next_generation(
    combined: list[CapacityIndividual],
    pop_size: int,
) -> list[CapacityIndividual]:
    fronts = _assign_rank_and_crowding(combined)
    selected: list[CapacityIndividual] = []
    for front in fronts:
        if len(selected) + len(front) <= pop_size:
            selected.extend(item.clone() for item in front)
        else:
            front.sort(key=lambda item: item.crowding, reverse=True)
            selected.extend(item.clone() for item in front[: pop_size - len(selected)])
            break
    return selected


def _tournament(
    population: list[CapacityIndividual],
    rng: random.Random,
) -> CapacityIndividual:
    a, b = rng.sample(population, 2)
    if (a.rank, -a.crowding) < (b.rank, -b.crowding):
        return a
    return b


def _crossover(
    instance: CapacityExperimentInstance,
    parent_a: CapacityIndividual,
    parent_b: CapacityIndividual,
    rng: random.Random,
) -> tuple[CapacityIndividual, CapacityIndividual]:
    child_a_order = _ordered_crossover(parent_a.repair_order, parent_b.repair_order, rng)
    child_b_order = _ordered_crossover(parent_b.repair_order, parent_a.repair_order, rng)
    child_a_priority = _ordered_crossover(parent_a.dispatch_priority, parent_b.dispatch_priority, rng)
    child_b_priority = _ordered_crossover(parent_b.dispatch_priority, parent_a.dispatch_priority, rng)
    child_a_team = _uniform_crossover(parent_a.team_assignment, parent_b.team_assignment, rng)
    child_b_team = _uniform_crossover(parent_b.team_assignment, parent_a.team_assignment, rng)
    crews = instance.base.repair_crews
    return (
        CapacityIndividual(child_a_order, [team % crews for team in child_a_team], child_a_priority),
        CapacityIndividual(child_b_order, [team % crews for team in child_b_team], child_b_priority),
    )


def _ordered_crossover(values_a: list[Any], values_b: list[Any], rng: random.Random) -> list[Any]:
    size = len(values_a)
    if size < 2:
        return list(values_a)
    left, right = sorted(rng.sample(range(size), 2))
    child = [None] * size
    child[left:right] = values_a[left:right]
    fill = [value for value in values_b if value not in child]
    fill_idx = 0
    for idx, value in enumerate(child):
        if value is None:
            child[idx] = fill[fill_idx]
            fill_idx += 1
    return list(child)


def _uniform_crossover(values_a: list[int], values_b: list[int], rng: random.Random) -> list[int]:
    return [a if rng.random() < 0.5 else b for a, b in zip(values_a, values_b)]


def _mutate(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
    probability: float,
    rng: random.Random,
) -> None:
    changed = False
    if rng.random() < probability:
        _swap_two(individual.repair_order, rng)
        changed = True
    if rng.random() < probability:
        _swap_two(individual.dispatch_priority, rng)
        changed = True
    if rng.random() < probability and individual.team_assignment:
        idx = rng.randrange(len(individual.team_assignment))
        individual.team_assignment[idx] = rng.randrange(instance.base.repair_crews)
        changed = True
    if changed:
        individual.objectives = None
        individual.metrics = None


def _alns_improve(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
    iterations: int,
    rng: random.Random,
) -> CapacityIndividual:
    _ensure_evaluated(instance, individual)
    current = individual.clone()
    current_score = _weighted_score(current)
    for _ in range(iterations):
        candidate = current.clone()
        operator = rng.choice([
            _swap_two_repairs,
            _insert_repair,
            _rebalance_team,
            _swap_two_dispatches,
            _move_high_demand_priority,
        ])
        operator(instance, candidate, rng)
        candidate.objectives = None
        candidate.metrics = None
        _ensure_evaluated(instance, candidate)
        candidate_score = _weighted_score(candidate)
        if _dominates(candidate.objectives, current.objectives) or candidate_score < current_score:
            current = candidate
            current_score = candidate_score
        elif rng.random() < 0.05:
            current = candidate
            current_score = candidate_score
    return current


def _ensure_evaluated(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
) -> None:
    if individual.objectives is None:
        individual.objectives, individual.metrics = evaluate_capacity_solution(instance, individual)


def _weighted_score(individual: CapacityIndividual) -> float:
    objectives = individual.objectives or (math.inf, math.inf, math.inf)
    return objectives[0] + 0.001 * objectives[1] + objectives[2]


def _swap_two_repairs(
    _instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
    rng: random.Random,
) -> None:
    _swap_two(individual.repair_order, rng)


def _insert_repair(
    _instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
    rng: random.Random,
) -> None:
    if len(individual.repair_order) < 2:
        return
    src, dst = rng.sample(range(len(individual.repair_order)), 2)
    value = individual.repair_order.pop(src)
    individual.repair_order.insert(dst, value)


def _rebalance_team(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
    rng: random.Random,
) -> None:
    if not individual.team_assignment:
        return
    idx = rng.randrange(len(individual.team_assignment))
    individual.team_assignment[idx] = rng.randrange(instance.base.repair_crews)


def _swap_two_dispatches(
    _instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
    rng: random.Random,
) -> None:
    _swap_two(individual.dispatch_priority, rng)


def _move_high_demand_priority(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
    rng: random.Random,
) -> None:
    if not individual.dispatch_priority:
        return
    high_demands = sorted(
        instance.base.demands,
        key=lambda demand: instance.base.demand_amounts[demand],
        reverse=True,
    )
    demand = rng.choice(high_demands[: max(1, min(5, len(high_demands)))])
    matches = [idx for idx, (_, d) in enumerate(individual.dispatch_priority) if d == demand]
    if not matches:
        return
    idx = rng.choice(matches)
    value = individual.dispatch_priority.pop(idx)
    individual.dispatch_priority.insert(0, value)


def _swap_two(values: list[Any], rng: random.Random) -> None:
    if len(values) < 2:
        return
    left, right = rng.sample(range(len(values)), 2)
    values[left], values[right] = values[right], values[left]


def _convergence_row(generation: int, individual: CapacityIndividual) -> dict[str, float]:
    objectives = individual.objectives or (math.inf, math.inf, math.inf)
    metrics = individual.metrics or {}
    return {
        "generation": float(generation),
        "unmet_area": objectives[0],
        "time_cost": objectives[1],
        "neg_min_satisfaction": objectives[2],
        "final_total_satisfaction": metrics.get("final_total_satisfaction", 0.0),
        "final_min_satisfaction": metrics.get("final_min_satisfaction", 0.0),
    }


def run_cli() -> None:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = CapacityNSGAConfig(
        pop_size=args.pop_size,
        generations=args.generations,
        alns_iterations=args.alns_iterations,
        alns_probability=args.alns_probability,
    )
    results: list[CapacityExperimentResult] = []
    scenarios = ["simulation", "wenchuan"] if args.scenario == "both" else [args.scenario]
    for scenario in scenarios:
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            if scenario == "simulation":
                instance = build_simulation_instance(seed, num_nodes=args.sim_nodes)
            else:
                instance = build_wenchuan_instance(seed)
            print(
                f"Solving {scenario} seed={seed} "
                f"nodes={instance.base.num_nodes} damaged={len(instance.base.damaged_edges)}"
            )
            result = solve_capacity_instance(instance, config, seed=seed + 30_000, scenario=scenario)
            results.append(result)
            summary = result.summary_row()
            print(
                "  "
                f"sat={summary['final_total_satisfaction']:.3f}, "
                f"min_sat={summary['final_min_satisfaction']:.3f}, "
                f"repair={summary['final_repaired_ratio']:.3f}, "
                f"partial={summary['partial_recovery_edge_periods']:.0f}, "
                f"time={summary['runtime_seconds']:.2f}s"
            )
    _write_outputs(results, output_dir)
    print(f"Done. Results written to {output_dir}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run capacity-recovery NSGA-II + ALNS prototype experiments.",
    )
    parser.add_argument("--scenario", choices=["simulation", "wenchuan", "both"], default="both")
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--sim-nodes", type=int, default=25)
    parser.add_argument("--pop-size", type=int, default=32)
    parser.add_argument("--generations", type=int, default=30)
    parser.add_argument("--alns-iterations", type=int, default=12)
    parser.add_argument("--alns-probability", type=float, default=0.35)
    parser.add_argument(
        "--output-dir",
        default="outputs/capacity_recovery",
        help="Directory for CSV and JSON outputs.",
    )
    return parser.parse_args()


def _write_outputs(results: list[CapacityExperimentResult], output_dir: Path) -> None:
    _write_csv(output_dir / "runs.csv", [result.summary_row() for result in results])
    with (output_dir / "solutions.json").open("w", encoding="utf-8") as fh:
        json.dump([result.to_jsonable() for result in results], fh, indent=2, ensure_ascii=False)
    convergence_rows = [
        {"instance": result.instance_name, "scenario": result.scenario, "seed": result.seed, **row}
        for result in results
        for row in result.convergence
    ]
    _write_csv(output_dir / "convergence.csv", convergence_rows)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    run_cli()
