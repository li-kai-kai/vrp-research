from __future__ import annotations

import math

import networkx as nx

from scripts.reproduce.model import DispatchAllocation, DispatchResult, RandomInstance


def dispatch_relief(
    instance: RandomInstance,
    available_graph: nx.Graph,
    dispatch_priority: list[tuple[int, int]],
    *,
    remaining_supply: dict[int, float] | None = None,
    remaining_demand: dict[int, float] | None = None,
    period_transport_capacity: float | None = None,
) -> DispatchResult:
    """Allocate relief using a max-relative-satisfaction style water-fill heuristic."""
    supply_state = remaining_supply if remaining_supply is not None else dict(instance.supply_amounts)
    demand_state = (
        remaining_demand
        if remaining_demand is not None
        else dict(instance.demand_amounts)
    )
    remaining_transport_capacity = {
        "value": (
            period_transport_capacity
            if period_transport_capacity is not None
            else instance.vehicle_capacity * instance.vehicle_count
        )
    }
    delivered = {node: 0.0 for node in instance.demands}
    allocations: list[DispatchAllocation] = []
    shortest_cache = _shortest_paths(instance, available_graph)
    reachable_demands = [
        demand
        for demand in instance.demands
        if demand_state.get(demand, 0.0) > 1e-9
        if any((supplier, demand) in shortest_cache for supplier in instance.suppliers)
    ]

    if not reachable_demands:
        return DispatchResult(
            allocations=[],
            delivered_by_demand=delivered,
            total_delivery_time=0.0,
            reachable_demands=[],
        )

    reachable_demand_total = sum(demand_state[node] for node in reachable_demands)
    effective_supply = min(sum(supply_state.values()), remaining_transport_capacity["value"])
    target_satisfaction = min(1.0, effective_supply / reachable_demand_total)
    target_amounts = {
        demand: demand_state[demand] * target_satisfaction
        for demand in reachable_demands
    }

    _allocate_by_priority(
        instance,
        dispatch_priority,
        shortest_cache,
        supply_state,
        remaining_transport_capacity,
        delivered,
        target_amounts,
        allocations,
    )

    full_demand_targets = {
        demand: demand_state[demand]
        for demand in reachable_demands
    }
    _allocate_by_priority(
        instance,
        dispatch_priority,
        shortest_cache,
        supply_state,
        remaining_transport_capacity,
        delivered,
        full_demand_targets,
        allocations,
    )

    total_delivery_time = sum(item.travel_time * item.trips for item in allocations)
    return DispatchResult(
        allocations=allocations,
        delivered_by_demand=delivered,
        total_delivery_time=total_delivery_time,
        reachable_demands=reachable_demands,
    )


def _shortest_paths(
    instance: RandomInstance,
    available_graph: nx.Graph,
) -> dict[tuple[int, int], tuple[float, list[int]]]:
    paths: dict[tuple[int, int], tuple[float, list[int]]] = {}
    for supplier in instance.suppliers:
        lengths, path_map = nx.single_source_dijkstra(
            available_graph,
            supplier,
            weight="weight",
        )
        for demand in instance.demands:
            if demand in lengths:
                paths[(supplier, demand)] = (float(lengths[demand]), path_map[demand])
    return paths


def _allocate_by_priority(
    instance: RandomInstance,
    dispatch_priority: list[tuple[int, int]],
    shortest_cache: dict[tuple[int, int], tuple[float, list[int]]],
    remaining_supply: dict[int, float],
    remaining_transport_capacity: dict[str, float],
    delivered: dict[int, float],
    target_amounts: dict[int, float],
    allocations: list[DispatchAllocation],
) -> None:
    for supplier, demand in dispatch_priority:
        if demand not in target_amounts:
            continue
        if (supplier, demand) not in shortest_cache:
            continue
        available = remaining_supply.get(supplier, 0.0)
        need = target_amounts[demand] - delivered[demand]
        capacity = remaining_transport_capacity["value"]
        if available <= 1e-9 or need <= 1e-9 or capacity <= 1e-9:
            continue

        amount = min(available, need, capacity)
        travel_time, path = shortest_cache[(supplier, demand)]
        trips = max(1, math.ceil(amount / instance.vehicle_capacity))
        remaining_supply[supplier] -= amount
        remaining_transport_capacity["value"] -= amount
        delivered[demand] += amount
        allocations.append(
            DispatchAllocation(
                supplier=supplier,
                demand=demand,
                amount=amount,
                travel_time=travel_time,
                trips=trips,
                path=path,
            )
        )
