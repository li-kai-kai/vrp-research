from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class DamagedEdge:
    damage_id: int
    u: int
    v: int
    repair_time: float


@dataclass
class RandomInstance:
    name: str
    seed: int
    num_nodes: int
    gamma: int
    damage_ratio: float
    eta_hours: int
    horizon_hours: int
    graph: nx.Graph
    suppliers: list[int]
    demands: list[int]
    demand_amounts: dict[int, float]
    supply_amounts: dict[int, float]
    damaged_edges: dict[int, DamagedEdge]
    repair_crews: int
    vehicle_capacity: float = 100.0
    vehicle_count: int = 10

    @property
    def periods(self) -> int:
        return self.horizon_hours // self.eta_hours

    @property
    def eta_minutes(self) -> int:
        return self.eta_hours * 60

    @property
    def horizon_minutes(self) -> int:
        return self.horizon_hours * 60

    @property
    def total_demand(self) -> float:
        return sum(self.demand_amounts.values())

    @property
    def total_supply(self) -> float:
        return sum(self.supply_amounts.values())
