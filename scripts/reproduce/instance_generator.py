from __future__ import annotations

import math
import random

import networkx as nx

from scripts.reproduce.model import DamagedEdge, RandomInstance


def generate_random_instance(
    *,
    num_nodes: int,
    gamma: int,
    damage_ratio: float,
    eta_hours: int,
    seed: int,
    horizon_hours: int = 72,
    supply_ratio: float = 0.8,
    supplier_ratio: float = 0.08,
    demand_ratio: float = 0.35,
) -> RandomInstance:
    """Generate a connected random road-network instance following the paper's setup."""
    if num_nodes < 8:
        raise ValueError("num_nodes must be at least 8")
    if gamma < 1:
        raise ValueError("gamma must be positive")
    if not 0 < damage_ratio <= 1:
        raise ValueError("damage_ratio must be in (0, 1]")
    if eta_hours <= 0 or horizon_hours % eta_hours != 0:
        raise ValueError("eta_hours must divide horizon_hours")

    rng = random.Random(seed)
    edge_count = math.ceil(gamma * num_nodes)
    graph = _connected_random_graph(num_nodes, edge_count, rng)
    for edge_id, (u, v) in enumerate(sorted(graph.edges())):
        graph[u][v]["edge_id"] = edge_id
        graph[u][v]["free_time"] = rng.uniform(1.0, 30.0)
        graph[u][v]["weight"] = graph[u][v]["free_time"]
        graph[u][v]["capacity"] = rng.uniform(1000.0, 3000.0)
        graph[u][v]["damaged"] = False

    all_nodes = list(range(num_nodes))
    supplier_count = max(1, round(num_nodes * supplier_ratio))
    demand_count = max(3, round(num_nodes * demand_ratio))
    supplier_count = min(supplier_count, num_nodes - demand_count)
    suppliers = sorted(rng.sample(all_nodes, supplier_count))
    remaining = [node for node in all_nodes if node not in suppliers]
    demands = sorted(rng.sample(remaining, demand_count))

    demand_amounts = {node: float(rng.randint(50, 200)) for node in demands}
    total_demand = sum(demand_amounts.values())
    total_supply = total_demand * supply_ratio
    supplier_weights = [rng.random() + 0.1 for _ in suppliers]
    weight_sum = sum(supplier_weights)
    supply_amounts = {
        node: total_supply * supplier_weights[idx] / weight_sum
        for idx, node in enumerate(suppliers)
    }

    damaged_count = max(1, math.ceil(damage_ratio * graph.number_of_edges()))
    damaged_pairs = rng.sample(list(graph.edges()), damaged_count)
    damaged_edges: dict[int, DamagedEdge] = {}
    for damage_id, (u, v) in enumerate(damaged_pairs):
        # The paper gives repair time in the same planning-horizon scale as eta/T.
        # Internally we use minutes, so [10, 60] hours is converted here.
        repair_time = rng.uniform(10.0, 60.0) * 60.0
        graph[u][v]["damaged"] = True
        graph[u][v]["damage_id"] = damage_id
        graph[u][v]["repair_time"] = repair_time
        damaged_edges[damage_id] = DamagedEdge(
            damage_id=damage_id,
            u=u,
            v=v,
            repair_time=repair_time,
        )

    repair_crews = math.ceil(num_nodes / 30) + 1
    vehicle_count = max(3, math.ceil(num_nodes / 10))
    name = (
        f"N{num_nodes}_g{gamma}_d{damage_ratio:.2f}_"
        f"eta{eta_hours}_seed{seed}"
    )
    return RandomInstance(
        name=name,
        seed=seed,
        num_nodes=num_nodes,
        gamma=gamma,
        damage_ratio=damage_ratio,
        eta_hours=eta_hours,
        horizon_hours=horizon_hours,
        graph=graph,
        suppliers=suppliers,
        demands=demands,
        demand_amounts=demand_amounts,
        supply_amounts=supply_amounts,
        damaged_edges=damaged_edges,
        repair_crews=repair_crews,
        vehicle_capacity=100.0,
        vehicle_count=vehicle_count,
    )


def _connected_random_graph(
    num_nodes: int,
    target_edges: int,
    rng: random.Random,
) -> nx.Graph:
    max_edges = num_nodes * (num_nodes - 1) // 2
    target_edges = min(max(target_edges, num_nodes - 1), max_edges)
    graph = nx.Graph()
    graph.add_nodes_from(range(num_nodes))

    nodes = list(range(num_nodes))
    rng.shuffle(nodes)
    for idx in range(1, num_nodes):
        u = nodes[idx]
        v = nodes[rng.randrange(idx)]
        graph.add_edge(u, v)

    while graph.number_of_edges() < target_edges:
        u, v = rng.sample(range(num_nodes), 2)
        if u != v:
            graph.add_edge(u, v)
    return graph
