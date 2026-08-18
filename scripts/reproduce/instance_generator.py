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
    topology: str = "random",
    damage_strategy: str = "random",
    node_role_strategy: str = "random",
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
    if topology not in {"random", "clustered"}:
        raise ValueError("topology must be 'random' or 'clustered'")
    if damage_strategy not in {"random", "critical"}:
        raise ValueError("damage_strategy must be 'random' or 'critical'")
    if node_role_strategy not in {"random", "separated"}:
        raise ValueError("node_role_strategy must be 'random' or 'separated'")

    rng = random.Random(seed)
    edge_count = math.ceil(gamma * num_nodes)
    if topology == "clustered":
        graph = _clustered_random_graph(num_nodes, edge_count, rng)
    else:
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
    if node_role_strategy == "separated":
        supplier_pool = all_nodes[: max(supplier_count, num_nodes // 4)]
        suppliers = sorted(rng.sample(supplier_pool, supplier_count))
    else:
        suppliers = sorted(rng.sample(all_nodes, supplier_count))
    remaining = [node for node in all_nodes if node not in suppliers]
    if node_role_strategy == "separated":
        remote_pool = [node for node in remaining if node >= num_nodes // 4]
        demand_pool = remote_pool if len(remote_pool) >= demand_count else remaining
        demands = sorted(rng.sample(demand_pool, demand_count))
    else:
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
    if damage_strategy == "critical":
        bridges = sorted(nx.bridges(graph))
        bridge_keys = {frozenset(edge) for edge in bridges}
        remaining_edges = [
            edge for edge in graph.edges() if frozenset(edge) not in bridge_keys
        ]
        damaged_pairs = bridges[:damaged_count]
        damaged_pairs.extend(
            rng.sample(
                remaining_edges,
                min(damaged_count - len(damaged_pairs), len(remaining_edges)),
            )
        )
    else:
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
    topology_suffix = "" if topology == "random" else f"_{topology}"
    name = f"N{num_nodes}_g{gamma}_d{damage_ratio:.2f}_eta{eta_hours}{topology_suffix}_seed{seed}"
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


def _clustered_random_graph(
    num_nodes: int,
    target_edges: int,
    rng: random.Random,
) -> nx.Graph:
    """Build internally dense regions connected by bridge-like relief corridors."""
    cluster_count = min(4, max(2, num_nodes // 40 + 2))
    clusters = [
        list(range(start, num_nodes, cluster_count))
        for start in range(cluster_count)
    ]
    graph = nx.Graph()
    graph.add_nodes_from(range(num_nodes))

    for cluster in clusters:
        shuffled = list(cluster)
        rng.shuffle(shuffled)
        for idx in range(1, len(shuffled)):
            graph.add_edge(shuffled[idx], shuffled[rng.randrange(idx)])

    corridor_edges: set[frozenset[int]] = set()
    for idx in range(cluster_count - 1):
        edge = (rng.choice(clusters[idx]), rng.choice(clusters[idx + 1]))
        graph.add_edge(*edge)
        corridor_edges.add(frozenset(edge))

    max_internal_edges = sum(len(cluster) * (len(cluster) - 1) // 2 for cluster in clusters)
    feasible_target = min(target_edges, max_internal_edges + len(corridor_edges))
    while graph.number_of_edges() < feasible_target:
        cluster = rng.choice(clusters)
        if len(cluster) < 2:
            continue
        u, v = rng.sample(cluster, 2)
        graph.add_edge(u, v)
    return graph
