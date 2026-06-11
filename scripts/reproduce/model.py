from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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


@dataclass(frozen=True)
class RepairTask:
    damage_id: int
    team_id: int
    start_time: float
    finish_time: float
    repaired: bool


@dataclass
class RepairSchedule:
    tasks: list[RepairTask]
    finish_times: dict[int, float]
    team_finish_times: dict[int, float]


@dataclass
class DispatchAllocation:
    supplier: int
    demand: int
    amount: float
    travel_time: float
    trips: int
    path: list[int]


@dataclass
class DispatchResult:
    allocations: list[DispatchAllocation]
    delivered_by_demand: dict[int, float]
    total_delivery_time: float
    reachable_demands: list[int]


@dataclass
class PeriodMetrics:
    instance: str
    seed: int
    num_nodes: int
    gamma: int
    damage_ratio: float
    eta_hours: int
    period: int
    time_hours: float
    accessibility: float
    accessibility_gain: float
    cumulative_accessibility: float
    total_satisfaction: float
    average_satisfaction: float
    minimum_satisfaction: float
    delivery_time: float
    repaired_ratio: float
    reachable_ratio: float


@dataclass
class SolutionResult:
    instance: RandomInstance
    repair_order: list[int]
    team_assignment: list[int]
    dispatch_priority: list[tuple[int, int]]
    repair_schedule: RepairSchedule
    period_metrics: list[PeriodMetrics]
    fitness: float
    runtime_seconds: float = 0.0
    convergence: list[float] = field(default_factory=list)

    def summary_row(self) -> dict[str, Any]:
        final = self.period_metrics[-1]
        return {
            "instance": self.instance.name,
            "seed": self.instance.seed,
            "num_nodes": self.instance.num_nodes,
            "gamma": self.instance.gamma,
            "damage_ratio": self.instance.damage_ratio,
            "eta_hours": self.instance.eta_hours,
            "damaged_edges": len(self.instance.damaged_edges),
            "repair_crews": self.instance.repair_crews,
            "fitness": self.fitness,
            "runtime_seconds": self.runtime_seconds,
            "final_accessibility": final.accessibility,
            "final_total_satisfaction": final.total_satisfaction,
            "final_average_satisfaction": final.average_satisfaction,
            "final_minimum_satisfaction": final.minimum_satisfaction,
            "final_repaired_ratio": final.repaired_ratio,
            "final_delivery_time": final.delivery_time,
        }

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "summary": self.summary_row(),
            "repair_order": self.repair_order,
            "team_assignment": self.team_assignment,
            "dispatch_priority": [
                {"supplier": supplier, "demand": demand}
                for supplier, demand in self.dispatch_priority
            ],
            "repair_schedule": [
                {
                    "damage_id": task.damage_id,
                    "team_id": task.team_id,
                    "start_time": task.start_time,
                    "finish_time": task.finish_time,
                    "repaired": task.repaired,
                }
                for task in self.repair_schedule.tasks
            ],
            "period_metrics": [metric.__dict__ for metric in self.period_metrics],
            "convergence": self.convergence,
        }

