from __future__ import annotations

import statistics

import networkx as nx

from scripts.reproduce.dispatch import dispatch_relief
from scripts.reproduce.model import (
    PeriodMetrics,
    RandomInstance,
    RepairSchedule,
    RepairTask,
    SolutionResult,
)


def decode_repair_schedule(
    instance: RandomInstance,
    repair_order: list[int],
    team_assignment: list[int],
) -> RepairSchedule:
    team_finish_times = {team_id: 0.0 for team_id in range(instance.repair_crews)}
    tasks: list[RepairTask] = []
    finish_times: dict[int, float] = {}
    seen: set[int] = set()

    for idx, damage_id in enumerate(repair_order):
        if damage_id in seen:
            continue
        seen.add(damage_id)
        if damage_id not in instance.damaged_edges:
            continue
        team_id = team_assignment[idx] % instance.repair_crews
        edge = instance.damaged_edges[damage_id]
        start_time = team_finish_times[team_id]
        finish_time = start_time + edge.repair_time
        repaired = finish_time <= instance.horizon_minutes
        if repaired:
            team_finish_times[team_id] = finish_time
            finish_times[damage_id] = finish_time
        tasks.append(
            RepairTask(
                damage_id=damage_id,
                team_id=team_id,
                start_time=start_time,
                finish_time=finish_time,
                repaired=repaired,
            )
        )
    return RepairSchedule(
        tasks=tasks,
        finish_times=finish_times,
        team_finish_times=team_finish_times,
    )


def evaluate_solution(
    instance: RandomInstance,
    repair_order: list[int],
    team_assignment: list[int],
    dispatch_priority: list[tuple[int, int]],
) -> SolutionResult:
    schedule = decode_repair_schedule(instance, repair_order, team_assignment)
    baseline_graph = instance.graph.copy()
    baseline_accessibility = _compute_accessibility(instance, baseline_graph)
    previous_accessibility = _compute_accessibility(
        instance,
        build_available_graph(instance, schedule, 0.0),
    )
    cumulative_accessibility = 0.0
    period_metrics: list[PeriodMetrics] = []
    remaining_supply = dict(instance.supply_amounts)
    cumulative_delivered = {node: 0.0 for node in instance.demands}

    for period in range(1, instance.periods + 1):
        time_minutes = period * instance.eta_minutes
        available_graph = build_available_graph(instance, schedule, time_minutes)
        accessibility = _compute_accessibility(instance, available_graph)
        accessibility_gain = max(0.0, accessibility - previous_accessibility)
        cumulative_accessibility += (
            accessibility_gain
            * max(instance.periods - period, 0)
            * instance.eta_hours
        )
        remaining_demand = {
            demand: max(
                0.0,
                instance.demand_amounts[demand] - cumulative_delivered[demand],
            )
            for demand in instance.demands
        }
        dispatch = dispatch_relief(
            instance,
            available_graph,
            dispatch_priority,
            remaining_supply=remaining_supply,
            remaining_demand=remaining_demand,
        )
        for demand, amount in dispatch.delivered_by_demand.items():
            cumulative_delivered[demand] += amount
        satisfaction_values = [
            min(
                1.0,
                cumulative_delivered[demand]
                / max(instance.demand_amounts[demand], 1e-9),
            )
            for demand in instance.demands
        ]
        total_satisfaction = sum(
            min(cumulative_delivered[demand], instance.demand_amounts[demand])
            for demand in instance.demands
        ) / max(instance.total_demand, 1e-9)
        repaired_ratio = _repaired_ratio(instance, schedule, time_minutes)
        reachable_ratio = len(dispatch.reachable_demands) / max(len(instance.demands), 1)

        period_metrics.append(
            PeriodMetrics(
                instance=instance.name,
                seed=instance.seed,
                num_nodes=instance.num_nodes,
                gamma=instance.gamma,
                damage_ratio=instance.damage_ratio,
                eta_hours=instance.eta_hours,
                period=period,
                time_hours=time_minutes / 60,
                accessibility=accessibility / max(baseline_accessibility, 1e-9),
                accessibility_gain=accessibility_gain,
                cumulative_accessibility=cumulative_accessibility,
                total_satisfaction=total_satisfaction,
                average_satisfaction=statistics.fmean(satisfaction_values),
                minimum_satisfaction=min(satisfaction_values),
                delivery_time=dispatch.total_delivery_time,
                repaired_ratio=repaired_ratio,
                reachable_ratio=reachable_ratio,
            )
        )
        previous_accessibility = accessibility

    fitness = _fitness(period_metrics)
    return SolutionResult(
        instance=instance,
        repair_order=list(repair_order),
        team_assignment=list(team_assignment),
        dispatch_priority=list(dispatch_priority),
        repair_schedule=schedule,
        period_metrics=period_metrics,
        fitness=fitness,
    )


def build_available_graph(
    instance: RandomInstance,
    schedule: RepairSchedule,
    time_minutes: float,
) -> nx.Graph:
    graph = instance.graph.copy()
    for damage_id, damaged_edge in instance.damaged_edges.items():
        if schedule.finish_times.get(damage_id, float("inf")) > time_minutes:
            if graph.has_edge(damaged_edge.u, damaged_edge.v):
                graph.remove_edge(damaged_edge.u, damaged_edge.v)
    return graph


def _compute_accessibility(instance: RandomInstance, graph: nx.Graph) -> float:
    total = 0.0
    penalty = 1_000_000.0
    for supplier in instance.suppliers:
        lengths = nx.single_source_dijkstra_path_length(graph, supplier, weight="weight")
        for demand in instance.demands:
            demand_weight = instance.demand_amounts[demand]
            total += demand_weight / max(float(lengths.get(demand, penalty)), 1e-9)
    return total


def _repaired_ratio(
    instance: RandomInstance,
    schedule: RepairSchedule,
    time_minutes: float,
) -> float:
    repaired = sum(
        1
        for damage_id in instance.damaged_edges
        if schedule.finish_times.get(damage_id, float("inf")) <= time_minutes
    )
    return repaired / max(len(instance.damaged_edges), 1)


def _fitness(period_metrics: list[PeriodMetrics]) -> float:
    if not period_metrics:
        return float("-inf")
    avg_total_sat = statistics.fmean(m.total_satisfaction for m in period_metrics)
    avg_min_sat = statistics.fmean(m.minimum_satisfaction for m in period_metrics)
    avg_reachable = statistics.fmean(m.reachable_ratio for m in period_metrics)
    final = period_metrics[-1]
    delivery_scale = max(1.0, final.num_nodes * final.eta_hours * 60)
    avg_delivery_penalty = statistics.fmean(m.delivery_time for m in period_metrics) / delivery_scale
    cumulative_accessibility = final.cumulative_accessibility / max(
        1.0,
        final.eta_hours * len(period_metrics),
    )
    return (
        3.0 * cumulative_accessibility
        + 4.0 * avg_total_sat
        + 2.0 * avg_min_sat
        + 1.0 * avg_reachable
        + 1.0 * final.repaired_ratio
        - 0.25 * avg_delivery_penalty
    )
