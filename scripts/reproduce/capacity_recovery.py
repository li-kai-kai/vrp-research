from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.instance_generator import generate_random_instance
from scripts.reproduce.model import DamagedEdge, RandomInstance
from scripts.reproduce.objective_precision import (
    EXACT_PRECISION,
    ObjectivePrecision,
    V2_PRECISION,
    precision_for,
)


@dataclass(frozen=True)
class VehicleProfile:
    vehicle_type: int
    capacity_ton: float
    count: int
    occupied_od_pcu_h: float
    min_recovery_progress: float
    pcu_per_vehicle: float
    speed_factor: float = 1.0


@dataclass(frozen=True)
class RecoveryStage:
    lower: float
    upper: float
    capacity_ratio: float
    label: str
    speed_ratio: float


# Recovery-progress comparisons share one tolerance so a test exactly at a
# vehicle threshold is decided the same way everywhere.
PROGRESS_TOLERANCE = 1e-9


MODEL_VERSIONS = ("legacy", "v2")

FLEET_SEMANTICS_EXOGENOUS_PERIOD_TRIP_BUDGET = "exogenous_period_trip_budget"

_MODEL_PROFILES: dict[str, dict[str, Any]] = {
    "legacy": {
        "fair_share_cap": True,
        "dispatch_timing": "period_end_legacy",
        "enforce_within_period_arrival": False,
    },
    "v2": {
        "fair_share_cap": False,
        "dispatch_timing": "period_start",
        "enforce_within_period_arrival": True,
    },
}


@dataclass(frozen=True)
class EvaluationConfig:
    """Versioned evaluation semantics shared by every entry point.

    ``legacy`` keeps the original global supply/demand ratio cap and the
    end-of-period state semantics for historical regression. ``v2`` uses the
    semantics frozen in ``docs/model_v2_contract.md``. The flags that differ
    between versions cannot be mixed: a half-migrated configuration is rejected
    instead of being silently evaluated.
    """

    model_version: str = "legacy"
    fair_share_cap: bool = True
    dispatch_timing: str = "period_end_legacy"
    enforce_within_period_arrival: bool = False
    fleet_semantics: str = FLEET_SEMANTICS_EXOGENOUS_PERIOD_TRIP_BUDGET

    def __post_init__(self) -> None:
        if self.model_version not in _MODEL_PROFILES:
            raise ValueError(
                f"unknown model_version {self.model_version!r}; "
                f"expected one of {sorted(_MODEL_PROFILES)}"
            )
        if self.fleet_semantics != FLEET_SEMANTICS_EXOGENOUS_PERIOD_TRIP_BUDGET:
            raise ValueError(
                "fleet_semantics is fixed to "
                f"{FLEET_SEMANTICS_EXOGENOUS_PERIOD_TRIP_BUDGET!r} in the first round"
            )
        profile = _MODEL_PROFILES[self.model_version]
        inconsistent = [
            name for name, expected in profile.items() if getattr(self, name) != expected
        ]
        if inconsistent:
            details = ", ".join(
                f"{name}={getattr(self, name)!r} (expected {profile[name]!r})"
                for name in inconsistent
            )
            raise ValueError(
                f"model_version={self.model_version!r} requires a consistent "
                f"evaluation profile; got {details}"
            )

    @classmethod
    def for_version(cls, model_version: str) -> EvaluationConfig:
        try:
            profile = _MODEL_PROFILES[model_version]
        except KeyError:
            raise ValueError(
                f"unknown model_version {model_version!r}; "
                f"expected one of {sorted(_MODEL_PROFILES)}"
            ) from None
        return cls(model_version=model_version, **profile)

    @property
    def period_start_dispatch(self) -> bool:
        return self.dispatch_timing == "period_start"

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "fair_share_cap": self.fair_share_cap,
            "dispatch_timing": self.dispatch_timing,
            "enforce_within_period_arrival": self.enforce_within_period_arrival,
            "fleet_semantics": self.fleet_semantics,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def validate_instance_support(self, instance: CapacityExperimentInstance) -> None:
        """Reject settings the first v2 round does not implement.

        Crew transfer time and same-network crew accessibility are first-round
        simplifications, both pinned to zero. A non-zero value must be reported
        instead of being accepted and silently ignored.
        """
        if self.model_version != "v2":
            return
        unsupported: list[str] = []
        if instance.crew_transfer_time_scale != 0.0:
            unsupported.append("crew_transfer_time_scale")
        if instance.crew_min_access_progress != 0.0:
            unsupported.append("crew_min_access_progress")
        if unsupported:
            raise ValueError(
                "model_version='v2' does not support non-zero "
                + ", ".join(unsupported)
                + "; unified crew-transfer time and crew accessibility are not "
                "implemented in the first round"
            )


@dataclass
class CapacityExperimentInstance:
    base: RandomInstance
    vehicles: list[VehicleProfile]
    recovery_stages: list[RecoveryStage]
    capacity_scale: float = 1.0
    repair_time_weight: float = 0.05
    crew_transfer_time_scale: float = 0.0
    crew_min_access_progress: float = 0.0
    progressive_recovery: bool = True
    heterogeneous_vehicle_thresholds: bool = True
    edge_capacity_constraint: bool = True
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    # The scenario's declared Full recovery curve and thresholds, recorded by
    # the builders so a variant can be checked against, and restored from,
    # something other than its own possibly-reduced data.
    full_profile: FullExecutionProfile | None = None


@dataclass
class TimedRepairTask:
    damage_id: int
    team_id: int
    start_time: float
    finish_time: float
    repair_time: float
    transfer_time: float = 0.0
    transfer_path: tuple[int, ...] = ()


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
class ParetoSolution:
    solution_id: str
    objectives: tuple[float, float, float]
    metrics: dict[str, float]
    repair_order: list[int]
    team_assignment: list[int]
    dispatch_priority: list[tuple[int, int]]
    crowding_distance: float
    decision_hash: str

    def row(self) -> dict[str, Any]:
        return {
            "solution_id": self.solution_id,
            "decision_hash": self.decision_hash,
            "pareto_rank": 0,
            "crowding_distance": (
                self.crowding_distance
                if math.isfinite(self.crowding_distance)
                else None
            ),
            "unmet_area": self.objectives[0],
            "time_cost": self.objectives[1],
            "neg_min_satisfaction": self.objectives[2],
            "final_min_satisfaction": self.metrics["final_min_satisfaction"],
            "final_total_satisfaction": self.metrics["final_total_satisfaction"],
            "average_reachable_ratio": self.metrics["average_reachable_ratio"],
            "final_repaired_ratio": self.metrics["final_repaired_ratio"],
            "partial_recovery_edge_periods": self.metrics["partial_recovery_edge_periods"],
            "small_vehicle_share": self.metrics["small_vehicle_share"],
            "max_edge_utilization": self.metrics["max_edge_utilization"],
            "high_utilization_edge_periods": self.metrics["high_utilization_edge_periods"],
            "capacity_blocked_tons": self.metrics["capacity_blocked_tons"],
            "total_vehicle_trips": self.metrics["total_vehicle_trips"],
        }

    def to_jsonable(self) -> dict[str, Any]:
        return {
            **self.row(),
            "objectives": self.objectives,
            "metrics": self.metrics,
            "repair_order": self.repair_order,
            "team_assignment": self.team_assignment,
            "dispatch_priority": [
                {"supplier": supplier, "demand": demand}
                for supplier, demand in self.dispatch_priority
            ],
        }


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
    pareto_front: list[ParetoSolution] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    convergence: list[dict[str, float]] = field(default_factory=list)

    def summary_row(self) -> dict[str, Any]:
        return {
            "instance": self.instance_name,
            "scenario": self.scenario,
            "seed": self.seed,
            "algorithm": self.algorithm,
            "capacity_scale": self.metrics["capacity_scale"],
            "repair_time_weight": self.metrics["repair_time_weight"],
            "unmet_area": self.objectives[0],
            "time_cost": self.objectives[1],
            "neg_min_satisfaction": self.objectives[2],
            "final_total_satisfaction": self.metrics["final_total_satisfaction"],
            "final_min_satisfaction": self.metrics["final_min_satisfaction"],
            "average_reachable_ratio": self.metrics["average_reachable_ratio"],
            "final_repaired_ratio": self.metrics["final_repaired_ratio"],
            "partial_recovery_edge_periods": self.metrics["partial_recovery_edge_periods"],
            "small_vehicle_share": self.metrics["small_vehicle_share"],
            "max_edge_utilization": self.metrics["max_edge_utilization"],
            "high_utilization_edge_periods": self.metrics["high_utilization_edge_periods"],
            "capacity_blocked_tons": self.metrics["capacity_blocked_tons"],
            "total_vehicle_trips": self.metrics["total_vehicle_trips"],
            "pareto_solution_count": len(self.pareto_front),
            "runtime_seconds": self.runtime_seconds,
        }

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "summary": self.summary_row(),
            "repair_order": self.repair_order,
            "team_assignment": self.team_assignment,
            "objectives": self.objectives,
            "metrics": self.metrics,
            "parameters": self.parameters,
            "pareto_front": [solution.to_jsonable() for solution in self.pareto_front],
            "convergence": self.convergence,
        }


DEFAULT_RECOVERY_STAGES = [
    RecoveryStage(0.0, 0.30, 0.0, "blocked", 0.0),
    RecoveryStage(0.30, 0.60, 0.30, "temporary", 0.30),
    RecoveryStage(0.60, 0.80, 0.60, "one_lane", 0.60),
    RecoveryStage(0.80, 1.0, 0.80, "basic", 0.80),
    RecoveryStage(1.0, 1.01, 1.0, "full", 1.0),
]


BINARY_RECOVERY_STAGES = [
    RecoveryStage(0.0, 1.0, 0.0, "blocked", 0.0),
    RecoveryStage(1.0, 1.01, 1.0, "full", 1.0),
]


UNIFORM_VEHICLE_RECOVERY_THRESHOLD = 0.30


@dataclass(frozen=True)
class FullExecutionProfile:
    """A scenario's declared Full recovery curve and vehicle thresholds.

    The booleans on an instance say which factors are *supposed* to be in
    force; they cannot say whether the data underneath actually implements
    them. A binary stage table under ``progressive_recovery=True``, or a
    uniform threshold under ``heterogeneous_vehicle_thresholds=True``, is
    self-contradictory and still hashes consistently.

    This profile is the independent, traceable baseline those flags are
    checked against. It is recorded by the scenario builders, travels with
    every variant of the scenario, and is what ``model_factor_variant``
    restores from when a factor is switched back on.
    """

    label: str
    recovery_stages: tuple[RecoveryStage, ...]
    vehicle_thresholds: tuple[tuple[int, float], ...]

    @classmethod
    def from_instance(
        cls,
        instance: CapacityExperimentInstance,
        label: str,
    ) -> FullExecutionProfile:
        return cls(
            label=label,
            recovery_stages=tuple(instance.recovery_stages),
            vehicle_thresholds=tuple(
                (int(vehicle.vehicle_type), float(vehicle.min_recovery_progress))
                for vehicle in instance.vehicles
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "recovery_stages": [
                [float(s.lower), float(s.upper), float(s.capacity_ratio), float(s.speed_ratio)]
                for s in self.recovery_stages
            ],
            "vehicle_thresholds": [[int(t), float(v)] for t, v in self.vehicle_thresholds],
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def is_binary_recovery_curve(stages: Sequence[RecoveryStage]) -> bool:
    """True when the curve only distinguishes "blocked" from "fully open".

    Any intermediate partial-recovery state makes it non-binary. A single
    always-open stage is binary by this definition: it has no recovery
    dynamics to be progressive about.
    """
    if len(stages) > 2:
        return False
    ratios = {round(stage.capacity_ratio, 12) for stage in stages}
    return ratios <= {0.0, 1.0}


def full_execution_problems(
    instance: CapacityExperimentInstance,
    profile: FullExecutionProfile | None = None,
) -> list[str]:
    """Reasons this instance is not the agreed Full execution environment.

    ``physical_instance_hash`` deliberately excludes the planning-model
    factors, so two scenarios with the same physical hash can carry different
    recovery curves, vehicle thresholds or evaluation semantics. Checking that
    hash alone would let a legacy or reduced model be replayed while being
    labelled Full, so the factors themselves are checked here.

    Returns an empty list when the instance is a valid Full environment.
    """
    problems: list[str] = []
    evaluation = instance.evaluation
    if evaluation.model_version != "v2":
        problems.append(
            f"evaluation.model_version is {evaluation.model_version!r}, expected 'v2'"
        )
    if not evaluation.enforce_within_period_arrival:
        problems.append("within-period arrival is not enforced")
    if evaluation.dispatch_timing != "period_start":
        problems.append(
            f"dispatch_timing is {evaluation.dispatch_timing!r}, expected 'period_start'"
        )
    if not evaluation.fair_share_cap is False:
        problems.append("the v2 allocation policy is not in force")
    if not instance.progressive_recovery:
        problems.append("progressive recovery is disabled (binary recovery in force)")
    if not instance.heterogeneous_vehicle_thresholds:
        problems.append("heterogeneous vehicle thresholds are disabled")
    if not instance.edge_capacity_constraint:
        problems.append("edge-capacity throughput accounting is disabled")
    if instance.crew_transfer_time_scale != 0.0:
        problems.append(
            f"crew_transfer_time_scale is {instance.crew_transfer_time_scale}, "
            "which the first round does not implement"
        )
    if instance.crew_min_access_progress != 0.0:
        problems.append(
            f"crew_min_access_progress is {instance.crew_min_access_progress}, "
            "which the first round does not implement"
        )
    if not instance.vehicles:
        problems.append("the instance carries no vehicle profiles")
    if not instance.recovery_stages:
        problems.append("the instance carries no recovery stages")

    # The flags above describe intent; these describe whether the data under
    # them can actually implement it.
    if instance.progressive_recovery and instance.recovery_stages:
        if is_binary_recovery_curve(instance.recovery_stages):
            problems.append(
                "progressive_recovery is enabled but the recovery curve is binary "
                "(only blocked and fully open states); the flag does not make a "
                "non-progressive curve progressive"
            )

    declared = profile if profile is not None else instance.full_profile
    if declared is not None:
        actual_stages = tuple(
            (float(s.lower), float(s.upper), float(s.capacity_ratio), float(s.speed_ratio))
            for s in instance.recovery_stages
        )
        if actual_stages != tuple(
            (float(s.lower), float(s.upper), float(s.capacity_ratio), float(s.speed_ratio))
            for s in declared.recovery_stages
        ):
            problems.append(
                f"recovery stages do not match the declared Full profile "
                f"{declared.label!r}"
            )
        actual_thresholds = tuple(
            (int(vehicle.vehicle_type), float(vehicle.min_recovery_progress))
            for vehicle in instance.vehicles
        )
        # Only vehicle types present in both are comparable; a scenario is free
        # to differ in which vehicle types it carries.
        declared_thresholds = dict(declared.vehicle_thresholds)
        mismatched = [
            vehicle_type
            for vehicle_type, threshold in actual_thresholds
            if vehicle_type in declared_thresholds
            and abs(declared_thresholds[vehicle_type] - threshold) > 1e-12
        ]
        if mismatched:
            problems.append(
                f"vehicle thresholds for type(s) {sorted(mismatched)} do not match "
                f"the declared Full profile {declared.label!r}"
            )
    return problems


def is_full_execution_environment(
    instance: CapacityExperimentInstance,
    profile: FullExecutionProfile | None = None,
) -> bool:
    return not full_execution_problems(instance, profile)


DEFAULT_VEHICLES = [
    VehicleProfile(
        1,
        capacity_ton=5.0,
        count=150,
        occupied_od_pcu_h=300.0,
        min_recovery_progress=0.30,
        pcu_per_vehicle=1.0,
    ),
    VehicleProfile(
        2,
        capacity_ton=10.0,
        count=110,
        occupied_od_pcu_h=500.0,
        min_recovery_progress=0.50,
        pcu_per_vehicle=1.5,
    ),
    VehicleProfile(
        3,
        capacity_ton=15.0,
        count=70,
        occupied_od_pcu_h=800.0,
        min_recovery_progress=0.70,
        pcu_per_vehicle=2.0,
    ),
    VehicleProfile(
        4,
        capacity_ton=20.0,
        count=40,
        occupied_od_pcu_h=1000.0,
        min_recovery_progress=0.80,
        pcu_per_vehicle=2.5,
    ),
]


def model_factor_variant(
    instance: CapacityExperimentInstance,
    *,
    progressive_recovery: bool,
    heterogeneous_vehicle_thresholds: bool,
    edge_capacity_constraint: bool,
    uniform_vehicle_threshold: float = UNIFORM_VEHICLE_RECOVERY_THRESHOLD,
) -> CapacityExperimentInstance:
    """Create one orthogonal model-factor variant without changing the base instance.

    Binary recovery reuses the same stage-based capacity and speed functions as the
    progressive model. Disabling heterogeneous thresholds assigns one common
    passability threshold to every existing vehicle profile; it does not collapse
    fleet capacities, counts, PCU values, or speed factors.
    """
    if not 0.0 <= uniform_vehicle_threshold <= 1.0:
        raise ValueError("uniform_vehicle_threshold must be in [0, 1]")

    # Switching a factor back on must restore the scenario's declared Full
    # data, not simply re-label whatever the source instance happens to carry.
    # Otherwise a reduced instance re-labelled as Full would silently keep its
    # reduced curve and thresholds.
    profile = instance.full_profile
    if progressive_recovery:
        if profile is not None:
            stages = list(profile.recovery_stages)
        elif is_binary_recovery_curve(instance.recovery_stages):
            raise ValueError(
                "cannot build a progressive variant: the source instance "
                "carries a binary recovery curve and declares no Full profile "
                "to restore one from"
            )
        else:
            stages = list(instance.recovery_stages)
    else:
        stages = list(BINARY_RECOVERY_STAGES)

    declared_thresholds = (
        dict(profile.vehicle_thresholds) if profile is not None else {}
    )
    vehicles = []
    for vehicle in instance.vehicles:
        if heterogeneous_vehicle_thresholds:
            threshold = declared_thresholds.get(
                vehicle.vehicle_type,
                vehicle.min_recovery_progress,
            )
        else:
            threshold = uniform_vehicle_threshold
        vehicles.append(replace(vehicle, min_recovery_progress=threshold))
    return CapacityExperimentInstance(
        base=instance.base,
        vehicles=vehicles,
        recovery_stages=stages,
        capacity_scale=instance.capacity_scale,
        repair_time_weight=instance.repair_time_weight,
        crew_transfer_time_scale=instance.crew_transfer_time_scale,
        crew_min_access_progress=instance.crew_min_access_progress,
        progressive_recovery=progressive_recovery,
        heterogeneous_vehicle_thresholds=heterogeneous_vehicle_thresholds,
        edge_capacity_constraint=edge_capacity_constraint,
        # Version and evaluation configuration are inherited unchanged; the
        # variant only flips the requested model factor.
        evaluation=instance.evaluation,
        full_profile=instance.full_profile,
    )


def build_simulation_instance(
    seed: int,
    *,
    num_nodes: int = 25,
    model_version: str = "legacy",
) -> CapacityExperimentInstance:
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
    instance = CapacityExperimentInstance(
        base=base,
        vehicles=DEFAULT_VEHICLES,
        recovery_stages=DEFAULT_RECOVERY_STAGES,
        evaluation=EvaluationConfig.for_version(model_version),
    )
    instance.full_profile = FullExecutionProfile.from_instance(instance, "synthetic_full")
    return instance


def build_wenchuan_instance(
    seed: int = 0,
    *,
    model_version: str = "legacy",
) -> CapacityExperimentInstance:
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
    instance = CapacityExperimentInstance(
        base=base,
        vehicles=DEFAULT_VEHICLES,
        recovery_stages=DEFAULT_RECOVERY_STAGES,
        evaluation=EvaluationConfig.for_version(model_version),
    )
    instance.full_profile = FullExecutionProfile.from_instance(instance, "wenchuan_full")
    return instance


def solve_capacity_instance(
    instance: CapacityExperimentInstance,
    config: CapacityNSGAConfig,
    *,
    seed: int,
    scenario: str,
) -> CapacityExperimentResult:
    rng = random.Random(seed)
    precision = precision_for(instance)
    start = time.perf_counter()
    population = [_create_individual(instance, rng) for _ in range(config.pop_size)]
    pareto_archive: list[CapacityIndividual] = []
    convergence: list[dict[str, float]] = []

    for generation in range(config.generations):
        _evaluate_population(instance, population)
        pareto_archive = update_pareto_archive(pareto_archive, population, precision)
        fronts = _assign_rank_and_crowding(population, precision)
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
        pareto_archive = update_pareto_archive(
            pareto_archive,
            population + offspring,
            precision,
        )
        population = _select_next_generation(
            population + offspring,
            config.pop_size,
            precision,
        )

    _evaluate_population(instance, population)
    pareto_archive = update_pareto_archive(pareto_archive, population, precision)
    best_front = pareto_archive
    _assign_crowding(best_front, precision)
    best = min(best_front, key=lambda item: _representative_key(item, precision))
    pareto_front = _serialize_pareto_front(best_front)
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
        pareto_front=pareto_front,
        parameters=_experiment_parameters(instance, config),
        convergence=convergence,
    )


@dataclass
class EvaluationOutcome:
    """Full result of one shared-model evaluation."""

    objectives: tuple[float, float, float]
    metrics: dict[str, float]
    period_delivered: list[float] = field(default_factory=list)
    period_reachable_ratio: list[float] = field(default_factory=list)
    allocations: list[dict[str, Any]] = field(default_factory=list)


def evaluate_capacity_solution(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
) -> tuple[tuple[float, float, float], dict[str, float]]:
    outcome = evaluate_capacity_solution_detailed(instance, individual)
    return outcome.objectives, outcome.metrics


def evaluate_capacity_solution_detailed(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
) -> EvaluationOutcome:
    base = instance.base
    config = instance.evaluation
    config.validate_instance_support(instance)
    schedule = _decode_timed_schedule(
        base,
        individual.repair_order,
        individual.team_assignment,
        instance.crew_transfer_time_scale,
    )
    remaining_supply = dict(base.supply_amounts)
    delivered = {demand: 0.0 for demand in base.demands}
    total_delivery_time = 0.0
    total_repair_work = sum(
        max(0.0, min(task.finish_time, base.horizon_minutes) - task.start_time)
        for task in schedule
        if task.start_time < base.horizon_minutes
    )
    total_crew_transfer_time = sum(
        max(
            0.0,
            min(task.start_time, base.horizon_minutes)
            - max(0.0, task.start_time - task.transfer_time),
        )
        for task in schedule
        if task.start_time - task.transfer_time < base.horizon_minutes
    )
    unmet_area = 0.0
    reachable_ratios: list[float] = []
    partial_recovery_edge_periods = 0
    vehicle_ton_by_type = {vehicle.vehicle_type: 0.0 for vehicle in instance.vehicles}
    max_edge_utilizations: list[float] = []
    high_utilization_edge_periods = 0
    capacity_blocked_tons = 0.0
    total_vehicle_trips = 0
    period_delivered: list[float] = []
    time_infeasible_candidates: set[tuple[int, int, int]] = set()
    time_feasible_demand_periods = 0
    allocations: list[dict[str, Any]] = []

    for period in range(1, base.periods + 1):
        # v2 samples the state at the start of the period, so capacity built
        # during this period is only usable next period. legacy keeps the
        # original end-of-period sampling for historical regression.
        progress_time = (
            (period - 1) * base.eta_minutes
            if config.period_start_dispatch
            else period * base.eta_minutes
        )
        progress = _repair_progress_by_damage(base, schedule, progress_time)
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
            config,
        )
        period_amount = 0.0
        for demand, amount in period_result["delivered"].items():
            delivered[demand] += amount
            period_amount += amount
        period_delivered.append(period_amount)
        time_infeasible_candidates.update(period_result["time_infeasible_candidates"])
        time_feasible_demand_periods += len(period_result["time_feasible_demands"])
        allocations.extend(period_result["allocations"])
        total_delivery_time += period_result["delivery_time"]
        for vehicle_type, amount in period_result["vehicle_tons"].items():
            vehicle_ton_by_type[vehicle_type] += amount
        max_edge_utilizations.append(period_result["max_edge_utilization"])
        high_utilization_edge_periods += period_result["high_utilization_edges"]
        capacity_blocked_tons += period_result["capacity_blocked_tons"]
        total_vehicle_trips += sum(period_result["vehicle_trips"].values())
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
    time_cost = (
        total_delivery_time
        + instance.repair_time_weight
        * (total_repair_work + total_crew_transfer_time)
    )
    objectives = (
        unmet_area,
        time_cost,
        -final_min_satisfaction,
    )
    total_delivered_tons = sum(
        min(delivered[demand], base.demand_amounts[demand])
        for demand in base.demands
    )
    zero_service_demands = sum(
        1 for demand in base.demands if delivered[demand] <= 1e-9
    )
    remaining_supply_tons = sum(
        max(0.0, amount) for amount in remaining_supply.values()
    )
    metrics = {
        "capacity_scale": instance.capacity_scale,
        "repair_time_weight": instance.repair_time_weight,
        "crew_transfer_time_scale": instance.crew_transfer_time_scale,
        "progressive_recovery": float(instance.progressive_recovery),
        "heterogeneous_vehicle_thresholds": float(
            instance.heterogeneous_vehicle_thresholds
        ),
        "edge_capacity_constraint": float(instance.edge_capacity_constraint),
        "final_total_satisfaction": final_total_satisfaction,
        "final_min_satisfaction": final_min_satisfaction,
        "average_reachable_ratio": sum(reachable_ratios) / max(len(reachable_ratios), 1),
        "final_repaired_ratio": repaired_count / max(len(base.damaged_edges), 1),
        "total_delivery_time": total_delivery_time,
        "total_repair_work": total_repair_work,
        "total_crew_transfer_time": total_crew_transfer_time,
        "partial_recovery_edge_periods": float(partial_recovery_edge_periods),
        "small_vehicle_share": small_vehicle_tons / max(all_vehicle_tons, 1e-9),
        "max_edge_utilization": max(max_edge_utilizations, default=0.0),
        "high_utilization_edge_periods": float(high_utilization_edge_periods),
        "capacity_blocked_tons": capacity_blocked_tons,
        "total_vehicle_trips": float(total_vehicle_trips),
        # Discrete end-of-period sampling scaled by the period length. This is
        # not a continuous deprivation cost integrated over exact arrival times.
        "unmet_ratio_hours": unmet_area * base.eta_hours,
        "zero_service_ratio": zero_service_demands / max(len(base.demands), 1),
        "remaining_supply": remaining_supply_tons,
        "total_delivered": total_delivered_tons,
        "min_period_delivered": min(period_delivered, default=0.0),
        "max_period_delivered": max(period_delivered, default=0.0),
        # Demand connectivity separately named from the topology-based
        # average_reachable_ratio: a demand may be topologically reachable while
        # no single trip can arrive inside one period.
        "time_infeasible_candidates": float(len(time_infeasible_candidates)),
        "time_feasible_demand_periods": float(time_feasible_demand_periods),
    }
    return EvaluationOutcome(
        objectives=objectives,
        metrics=metrics,
        period_delivered=period_delivered,
        period_reachable_ratio=reachable_ratios,
        allocations=allocations,
    )


def _decode_timed_schedule(
    base: RandomInstance,
    repair_order: list[int],
    team_assignment: list[int],
    crew_transfer_time_scale: float = 0.0,
) -> list[TimedRepairTask]:
    team_free = {team_id: 0.0 for team_id in range(base.repair_crews)}
    team_locations = {
        team_id: {
            "kind": "node",
            "node_id": base.suppliers[team_id % len(base.suppliers)],
        }
        for team_id in range(base.repair_crews)
    }
    tasks: list[TimedRepairTask] = []
    seen: set[int] = set()
    for idx, damage_id in enumerate(repair_order):
        if damage_id in seen or damage_id not in base.damaged_edges:
            continue
        seen.add(damage_id)
        team_id = team_assignment[idx] % base.repair_crews
        repair_time = base.damaged_edges[damage_id].repair_time
        transfer_time, transfer_path = _crew_transfer(
            base,
            team_locations[team_id],
            damage_id,
            crew_transfer_time_scale,
        )
        start_time = team_free[team_id] + transfer_time
        finish_time = start_time + repair_time
        team_free[team_id] = finish_time
        team_locations[team_id] = {"kind": "edge", "damage_id": damage_id}
        tasks.append(
            TimedRepairTask(
                damage_id=damage_id,
                team_id=team_id,
                start_time=start_time,
                finish_time=finish_time,
                repair_time=repair_time,
                transfer_time=transfer_time,
                transfer_path=tuple(transfer_path),
            )
        )
    return tasks


def _crew_transfer(
    base: RandomInstance,
    origin: dict[str, Any],
    target_damage_id: int,
    time_scale: float,
    road_progress: dict[int, float] | None = None,
    min_access_progress: float = 0.30,
) -> tuple[float, list[int]]:
    """Approximate midpoint-to-midpoint crew transfer on the physical network."""
    if origin.get("kind") == "edge" and origin.get("damage_id") == target_damage_id:
        return 0.0, []

    target = base.damaged_edges[target_damage_id]
    target_endpoints = (target.u, target.v)
    target_half = 0.5 * float(
        base.graph[target.u][target.v].get(
            "free_time",
            base.graph[target.u][target.v].get("weight", 0.0),
        )
    )
    if origin.get("kind") == "edge":
        source = base.damaged_edges[int(origin["damage_id"])]
        if (
            road_progress is not None
            and road_progress.get(source.damage_id, 0.0)
            < min_access_progress - 1e-9
            and origin.get("access_node") is not None
        ):
            source_endpoints = (int(origin["access_node"]),)
        else:
            source_endpoints = (source.u, source.v)
        source_half = 0.5 * float(
            base.graph[source.u][source.v].get(
                "free_time",
                base.graph[source.u][source.v].get("weight", 0.0),
            )
        )
    else:
        source_endpoints = (int(origin["node_id"]),)
        source_half = 0.0

    transfer_graph = base.graph
    if road_progress is not None:
        transfer_graph = nx.Graph()
        transfer_graph.add_nodes_from(base.graph.nodes(data=True))
        for u, v, data in base.graph.edges(data=True):
            damage_id = data.get("damage_id")
            if (
                damage_id is None
                or road_progress.get(int(damage_id), 0.0)
                >= min_access_progress - 1e-9
            ):
                transfer_graph.add_edge(u, v, **data)

    best: tuple[float, list[int]] | None = None
    for source_node in source_endpoints:
        for target_node in target_endpoints:
            try:
                length, path = nx.single_source_dijkstra(
                    transfer_graph,
                    source_node,
                    target_node,
                    weight=lambda _u, _v, data: float(
                        data.get("free_time", data.get("weight", 1.0))
                    ),
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            candidate = (source_half + float(length) + target_half, list(path))
            if best is None or candidate[0] < best[0]:
                best = candidate
    if best is None:
        return math.inf, []
    return best[0] * max(time_scale, 0.0), best[1]


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
    config: EvaluationConfig | None = None,
) -> dict[str, Any]:
    base = instance.base
    config = config if config is not None else instance.evaluation
    period_minutes = float(base.eta_minutes)
    vehicle_trips_left = {
        vehicle.vehicle_type: vehicle.count
        for vehicle in instance.vehicles
    }
    edge_capacity = (
        _period_edge_capacities(instance, progress)
        if instance.edge_capacity_constraint
        else {}
    )
    residual_edge_capacity = dict(edge_capacity)
    shortest_by_vehicle = {
        vehicle.vehicle_type: _shortest_paths_for_vehicle(instance, progress, vehicle)
        for vehicle in instance.vehicles
    }
    reachable = set()
    for paths in shortest_by_vehicle.values():
        reachable.update(demand for _, demand in paths)

    # Topology reachability keeps its original meaning. Time feasibility is a
    # separate statistic: a demand can be reachable while no single trip can
    # arrive inside one period.
    time_infeasible_candidates: set[tuple[int, int, int]] = set()
    time_feasible: set[int] = set(reachable)
    if config.enforce_within_period_arrival:
        time_feasible = set()
        for vehicle in instance.vehicles:
            for (supplier, demand), (travel_time, _path) in shortest_by_vehicle[
                vehicle.vehicle_type
            ].items():
                if travel_time <= period_minutes + PROGRESS_TOLERANCE:
                    time_feasible.add(demand)
                else:
                    time_infeasible_candidates.add(
                        (supplier, demand, vehicle.vehicle_type)
                    )

    delivered = {demand: 0.0 for demand in base.demands}
    vehicle_tons = {vehicle.vehicle_type: 0.0 for vehicle in instance.vehicles}
    vehicle_trips = {vehicle.vehicle_type: 0 for vehicle in instance.vehicles}
    capacity_blocked_demands: set[int] = set()
    allocations: list[dict[str, Any]] = []
    delivery_time = 0.0
    serviceable_demands = [
        demand
        for demand in base.demands
        if demand in time_feasible and remaining_demand.get(demand, 0.0) > 1e-9
    ]
    available_supply = sum(max(0.0, remaining_supply.get(supplier, 0.0)) for supplier in base.suppliers)
    available_vehicle_capacity = sum(
        vehicle.capacity_ton * vehicle_trips_left[vehicle.vehicle_type]
        for vehicle in instance.vehicles
    )
    fair_resource = min(available_supply, available_vehicle_capacity)
    current_delivered = {
        demand: max(0.0, base.demand_amounts[demand] - remaining_demand.get(demand, 0.0))
        for demand in base.demands
    }
    # legacy caps every demand point by the global supply/demand ratio. v2
    # drops that cap: a demand point is limited only by its own requirement, so
    # a permanently unreachable demand no longer strands the rest of the
    # resources. Both rounds keep the fleet, passability and edge-capacity
    # constraints below.
    fair_ceiling = (
        min(1.0, base.total_supply / max(base.total_demand, 1e-9))
        if config.fair_share_cap
        else 1.0
    )
    target_level = min(
        fair_ceiling,
        _max_min_satisfaction_target(
            base,
            serviceable_demands,
            current_delivered,
            fair_resource,
        ),
    )
    # Both rounds pass period-total targets: _allocate_vehicle_aware subtracts
    # this period's delivered amount itself, so pre-subtracting here would
    # double-count the reduction.
    fair_targets = {
        demand: min(
            remaining_demand[demand],
            max(0.0, target_level * base.demand_amounts[demand] - current_delivered[demand]),
        )
        for demand in serviceable_demands
    }
    delivery_time += _allocate_vehicle_aware(
        instance,
        dispatch_priority,
        shortest_by_vehicle,
        progress,
        remaining_supply,
        vehicle_trips_left,
        residual_edge_capacity,
        delivered,
        vehicle_tons,
        vehicle_trips,
        fair_targets,
        capacity_blocked_demands,
        allocations,
        config=config,
        period_minutes=period_minutes,
        time_infeasible_candidates=time_infeasible_candidates,
    )
    residual_targets = {
        demand: min(
            remaining_demand.get(demand, 0.0),
            max(0.0, fair_ceiling * base.demand_amounts[demand] - current_delivered[demand]),
        )
        for demand in serviceable_demands
    }
    delivery_time += _allocate_vehicle_aware(
        instance,
        dispatch_priority,
        shortest_by_vehicle,
        progress,
        remaining_supply,
        vehicle_trips_left,
        residual_edge_capacity,
        delivered,
        vehicle_tons,
        vehicle_trips,
        residual_targets,
        capacity_blocked_demands,
        allocations,
        config=config,
        period_minutes=period_minutes,
        time_infeasible_candidates=time_infeasible_candidates,
    )

    max_edge_utilization, high_utilization_edges = _edge_utilization_stats(
        edge_capacity,
        residual_edge_capacity,
    )
    capacity_blocked_tons = sum(
        max(0.0, residual_targets.get(demand, 0.0) - delivered.get(demand, 0.0))
        for demand in capacity_blocked_demands
    )

    return {
        "delivered": delivered,
        "delivery_time": delivery_time,
        "reachable_count": len(reachable),
        "reachable_demands": sorted(reachable),
        "time_feasible_demands": sorted(time_feasible),
        "time_infeasible_candidates": time_infeasible_candidates,
        "allocations": allocations,
        "vehicle_tons": vehicle_tons,
        "vehicle_trips": vehicle_trips,
        "max_edge_utilization": max_edge_utilization,
        "high_utilization_edges": high_utilization_edges,
        "capacity_blocked_tons": capacity_blocked_tons,
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
    progress: dict[int, float],
    remaining_supply: dict[int, float],
    vehicle_trips_left: dict[int, int],
    residual_edge_capacity: dict[frozenset[Any], float],
    delivered: dict[int, float],
    vehicle_tons: dict[int, float],
    vehicle_trips: dict[int, int],
    targets: dict[int, float],
    capacity_blocked_demands: set[int],
    allocations: list[dict[str, Any]],
    *,
    config: EvaluationConfig | None = None,
    period_minutes: float = 0.0,
    time_infeasible_candidates: set[tuple[int, int, int]] | None = None,
) -> float:
    config = config if config is not None else instance.evaluation
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
            topology_exists_but_capacity_blocks = False
            for vehicle in instance.vehicles:
                if vehicle_trips_left[vehicle.vehicle_type] <= 0:
                    continue
                topology_path = shortest_by_vehicle[vehicle.vehicle_type].get((supplier, demand))
                if topology_path is None:
                    continue
                if (
                    config.enforce_within_period_arrival
                    and topology_path[0] > period_minutes + PROGRESS_TOLERANCE
                ):
                    # Even the topology shortest path needs more than one period.
                    # No capacity-feasible path can be shorter, so reject before
                    # computing one: nothing is deducted and nothing arrives.
                    if time_infeasible_candidates is not None:
                        time_infeasible_candidates.add(
                            (supplier, demand, vehicle.vehicle_type)
                        )
                    continue
                path_info = (
                    _capacity_feasible_shortest_path(
                        instance,
                        progress,
                        vehicle,
                        supplier,
                        demand,
                        residual_edge_capacity,
                    )
                    if instance.edge_capacity_constraint
                    else topology_path
                )
                if path_info is None:
                    topology_exists_but_capacity_blocks = True
                    continue
                travel_time, path = path_info
                if (
                    config.enforce_within_period_arrival
                    and travel_time > period_minutes + PROGRESS_TOLERANCE
                ):
                    # A capacity detour pushed the trip past the period length.
                    if time_infeasible_candidates is not None:
                        time_infeasible_candidates.add(
                            (supplier, demand, vehicle.vehicle_type)
                        )
                    continue
                path_capacity_trips = (
                    _path_trip_capacity(
                        path,
                        residual_edge_capacity,
                        vehicle.pcu_per_vehicle,
                    )
                    if instance.edge_capacity_constraint
                    else vehicle_trips_left[vehicle.vehicle_type]
                )
                available_trips = min(
                    vehicle_trips_left[vehicle.vehicle_type],
                    path_capacity_trips,
                )
                if available_trips <= 0:
                    topology_exists_but_capacity_blocks = True
                    continue
                max_tons = available_trips * vehicle.capacity_ton
                amount = min(
                    remaining_supply[supplier],
                    targets[demand] - delivered[demand],
                    max_tons,
                )
                if amount <= 1e-9:
                    continue
                trips = max(1, math.ceil(amount / vehicle.capacity_ton))
                candidates.append(
                    (travel_time, -vehicle.capacity_ton, vehicle, path, amount, trips)
                )
            if not candidates:
                if topology_exists_but_capacity_blocks:
                    capacity_blocked_demands.add(demand)
                break

            candidates.sort(key=lambda item: (item[0], item[1], item[2].vehicle_type))
            travel_time, _neg_capacity, vehicle, path, amount, trips = candidates[0]
            remaining_supply[supplier] -= amount
            vehicle_trips_left[vehicle.vehicle_type] -= trips
            delivered[demand] += amount
            vehicle_tons[vehicle.vehicle_type] += amount
            vehicle_trips[vehicle.vehicle_type] += trips
            allocations.append({
                "supplier": supplier,
                "demand": demand,
                "vehicle_type": vehicle.vehicle_type,
                "amount": amount,
                "trips": trips,
                "travel_time": travel_time,
                "path": list(path),
            })
            if instance.edge_capacity_constraint:
                capacity_use = trips * vehicle.pcu_per_vehicle
                for u, v in zip(path, path[1:]):
                    edge_key = _edge_key(u, v)
                    residual_edge_capacity[edge_key] = max(
                        0.0,
                        residual_edge_capacity.get(edge_key, 0.0) - capacity_use,
                    )
            delivery_time += travel_time * trips
    return delivery_time


def _capacity_feasible_shortest_path(
    instance: CapacityExperimentInstance,
    progress: dict[int, float],
    vehicle: VehicleProfile,
    supplier: int,
    demand: int,
    residual_edge_capacity: dict[frozenset[Any], float],
) -> tuple[float, list[int]] | None:
    graph = _build_vehicle_graph(
        instance,
        progress,
        vehicle,
        residual_edge_capacity=residual_edge_capacity,
    )
    try:
        travel_time, path = nx.single_source_dijkstra(
            graph,
            supplier,
            demand,
            weight="weight",
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    return float(travel_time), path


def _path_trip_capacity(
    path: list[int],
    residual_edge_capacity: dict[frozenset[Any], float],
    pcu_per_vehicle: float,
) -> int:
    if len(path) < 2 or pcu_per_vehicle <= 0:
        return 0
    return max(
        0,
        math.floor(
            min(
                residual_edge_capacity.get(_edge_key(u, v), 0.0)
                for u, v in zip(path, path[1:])
            )
            / pcu_per_vehicle
            + 1e-9
        ),
    )


def _period_edge_capacities(
    instance: CapacityExperimentInstance,
    progress: dict[int, float],
) -> dict[frozenset[Any], float]:
    if instance.capacity_scale <= 0:
        raise ValueError("capacity_scale must be greater than zero")
    capacities: dict[frozenset[Any], float] = {}
    for u, v, data in instance.base.graph.edges(data=True):
        damage_id = data.get("damage_id")
        ratio = (
            1.0
            if damage_id is None
            else _capacity_ratio(instance.recovery_stages, progress.get(damage_id, 0.0))
        )
        capacities[_edge_key(u, v)] = (
            float(data.get("capacity", 1000.0))
            * ratio
            * instance.base.eta_hours
            * instance.capacity_scale
        )
    return capacities


def _edge_utilization_stats(
    initial: dict[frozenset[Any], float],
    residual: dict[frozenset[Any], float],
) -> tuple[float, int]:
    utilizations = [
        (capacity - residual.get(edge, 0.0)) / capacity
        for edge, capacity in initial.items()
        if capacity > 1e-9
    ]
    return (
        max(utilizations, default=0.0),
        sum(value >= 0.80 - 1e-9 for value in utilizations),
    )


def _edge_key(u: Any, v: Any) -> frozenset[Any]:
    return frozenset((u, v))


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
    *,
    residual_edge_capacity: dict[frozenset[Any], float] | None = None,
) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(instance.base.graph.nodes(data=True))
    for u, v, data in instance.base.graph.edges(data=True):
        damage_id = data.get("damage_id")
        if damage_id is None:
            ratio = 1.0
            speed_ratio = 1.0
            passable = True
        else:
            p = progress.get(damage_id, 0.0)
            ratio = _capacity_ratio(instance.recovery_stages, p)
            speed_ratio = _speed_ratio(instance.recovery_stages, p)
            passable = (
                p >= vehicle.min_recovery_progress - PROGRESS_TOLERANCE
                and ratio > 0.0
                and speed_ratio > 0.0
            )
        if not passable:
            continue
        edge_key = _edge_key(u, v)
        if (
            residual_edge_capacity is not None
            and residual_edge_capacity.get(edge_key, 0.0)
            < vehicle.pcu_per_vehicle - 1e-9
        ):
            continue
        free_time = float(data.get("free_time", data.get("weight", 1.0)))
        weight = free_time / max(speed_ratio, 0.1) / max(vehicle.speed_factor, 1e-9)
        graph.add_edge(
            u,
            v,
            weight=weight,
            period_capacity_pcu=(
                float(data.get("capacity", 1000.0))
                * ratio
                * instance.base.eta_hours
                * instance.capacity_scale
            ),
        )
    return graph


def _capacity_ratio(stages: list[RecoveryStage], progress: float) -> float:
    if progress >= 1.0:
        return 1.0
    for stage in stages:
        if stage.lower <= progress < stage.upper:
            return stage.capacity_ratio
    return 0.0


def _speed_ratio(stages: list[RecoveryStage], progress: float) -> float:
    if progress >= 1.0:
        return 1.0
    for stage in stages:
        if stage.lower <= progress < stage.upper:
            return stage.speed_ratio
    return 0.0


def _representative_key(
    individual: CapacityIndividual,
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> tuple[float, float, float]:
    """Lexicographic (F3, F1, F2), compared on the quantized key.

    Quantizing here is what stops a 1e-13 fairness difference from outranking an
    11% difference in cumulative unmet demand.
    """
    objectives = individual.objectives or (math.inf, math.inf, math.inf)
    if precision.is_exact:
        return (objectives[2], objectives[0], objectives[1])
    f1, f2, f3 = precision.key(objectives)
    return (f3, f1, f2)


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
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> bool:
    """Dominance under a pinned resolution.

    Defaults to the historical exact rule so legacy callers are unchanged; v2
    callers pass the instance's precision.
    """
    return precision.dominates(left, right)


def _assign_rank_and_crowding(
    population: list[CapacityIndividual],
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> list[list[CapacityIndividual]]:
    fronts = _fast_non_dominated_sort(population, precision)
    for rank, front in enumerate(fronts):
        for individual in front:
            individual.rank = rank
            individual.crowding = 0.0
        _assign_crowding(front, precision)
    return fronts


def _fast_non_dominated_sort(
    population: list[CapacityIndividual],
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> list[list[CapacityIndividual]]:
    dominates_map: dict[int, list[int]] = {idx: [] for idx in range(len(population))}
    dominated_count = {idx: 0 for idx in range(len(population))}
    fronts_idx: list[list[int]] = [[]]
    objectives = [individual.objectives or (math.inf, math.inf, math.inf) for individual in population]

    for p in range(len(population)):
        for q in range(len(population)):
            if p == q:
                continue
            if precision.dominates(objectives[p], objectives[q]):
                dominates_map[p].append(q)
            elif precision.dominates(objectives[q], objectives[p]):
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


def _assign_crowding(
    front: list[CapacityIndividual],
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> None:
    """Crowding distance, with resolution-dead dimensions contributing nothing.

    A dimension whose spread across the front is smaller than the resolution
    carries no service information. Letting min-max normalization amplify it
    would make rounding noise look like the most important source of diversity,
    so that dimension is skipped and its endpoints are not marked infinite.
    """
    if len(front) <= 2:
        for individual in front:
            individual.crowding = math.inf
        return
    exact = precision.is_exact
    for obj_idx in range(3):
        if exact:
            # Historical rule, preserved: sort on the raw value and keep the
            # original endpoint handling for a constant dimension.
            front.sort(
                key=lambda item: (
                    item.objectives or (math.inf, math.inf, math.inf)
                )[obj_idx]
            )
        else:
            # v2 sorts on the comparison coordinate, with the decision
            # signature breaking ties, so a raw float tail can never decide
            # which point becomes an endpoint.
            front.sort(
                key=lambda item: (
                    precision.key(item.objectives or (math.inf, math.inf, math.inf))[obj_idx],
                    _decision_signature(item),
                )
            )
        min_coordinate = _crowding_coordinate(front[0], obj_idx, precision)
        max_coordinate = _crowding_coordinate(front[-1], obj_idx, precision)
        span = max_coordinate - min_coordinate
        if span <= 0:
            # The dimension is constant in the comparison coordinates: it is
            # not a source of diversity, so it contributes nothing and its
            # points are not endpoints.
            if not exact:
                continue
        front[0].crowding = math.inf
        front[-1].crowding = math.inf
        scale = max(span, 1e-9)
        for idx in range(1, len(front) - 1):
            previous_value = _crowding_coordinate(front[idx - 1], obj_idx, precision)
            next_value = _crowding_coordinate(front[idx + 1], obj_idx, precision)
            front[idx].crowding += (next_value - previous_value) / scale


def _crowding_coordinate(
    individual: CapacityIndividual,
    obj_idx: int,
    precision: ObjectivePrecision,
) -> float:
    """The value crowding distances are measured in.

    Exact precision measures raw objectives; every other precision measures the
    quantized comparison coordinate, so raw jitter that does not change a key
    cannot change a distance.
    """
    objectives = individual.objectives or (math.inf, math.inf, math.inf)
    if precision.is_exact:
        return float(objectives[obj_idx])
    return float(precision.key(objectives)[obj_idx])


def _decision_signature(individual: CapacityIndividual) -> tuple[Any, ...]:
    return (
        tuple(individual.repair_order),
        tuple(individual.team_assignment),
        tuple(individual.dispatch_priority),
    )


def _update_pareto_archive(
    archive: list[CapacityIndividual],
    candidates: list[CapacityIndividual],
) -> list[CapacityIndividual]:
    return update_pareto_archive(archive, candidates, EXACT_PRECISION)


def update_pareto_archive(
    archive: list[CapacityIndividual],
    candidates: list[CapacityIndividual],
    precision: ObjectivePrecision,
) -> list[CapacityIndividual]:
    """Non-dominated set over `archive + candidates` under one resolution.

    De-duplication keeps one decision per *quantized objective key*, not per
    exact objective triple: two decisions that are indistinguishable at the
    service resolution are one point on the front, and the survivor is chosen
    deterministically by decision signature so the result does not depend on
    input order.
    """
    unique: dict[tuple[Any, ...], CapacityIndividual] = {}
    for individual in archive + candidates:
        if individual.objectives is None:
            continue
        signature = _decision_signature(individual)
        unique.setdefault(signature, individual.clone())

    # Collapse decisions with the same resolution-equivalent objectives,
    # keeping the lowest decision signature so the choice is order-independent.
    by_objective: dict[Any, CapacityIndividual] = {}
    for individual in sorted(unique.values(), key=_decision_signature):
        objectives = individual.objectives or (math.inf, math.inf, math.inf)
        by_objective.setdefault(precision.key(objectives), individual)
    values = list(by_objective.values())

    non_dominated = [
        individual
        for idx, individual in enumerate(values)
        if not any(
            precision.dominates(other.objectives, individual.objectives)
            for other_idx, other in enumerate(values)
            if idx != other_idx and other.objectives is not None
        )
    ]
    non_dominated.sort(
        key=lambda item: (
            precision.key(item.objectives or (math.inf, math.inf, math.inf)),
            _decision_signature(item),
        )
    )
    return non_dominated


def _serialize_pareto_front(front: list[CapacityIndividual]) -> list[ParetoSolution]:
    solutions: list[ParetoSolution] = []
    for idx, individual in enumerate(front, start=1):
        objectives = individual.objectives or (math.inf, math.inf, math.inf)
        metrics = individual.metrics or {}
        signature = repr(_decision_signature(individual)).encode("utf-8")
        solutions.append(
            ParetoSolution(
                solution_id=f"p{idx:04d}",
                objectives=objectives,
                metrics=dict(metrics),
                repair_order=list(individual.repair_order),
                team_assignment=list(individual.team_assignment),
                dispatch_priority=list(individual.dispatch_priority),
                crowding_distance=(
                    individual.crowding if math.isfinite(individual.crowding) else math.inf
                ),
                decision_hash=hashlib.sha256(signature).hexdigest()[:16],
            )
        )
    return solutions


def _select_next_generation(
    combined: list[CapacityIndividual],
    pop_size: int,
    precision: ObjectivePrecision = EXACT_PRECISION,
) -> list[CapacityIndividual]:
    fronts = _assign_rank_and_crowding(combined, precision)
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


def _experiment_parameters(
    instance: CapacityExperimentInstance,
    config: CapacityNSGAConfig,
) -> dict[str, Any]:
    base = instance.base
    return {
        "algorithm": asdict(config),
        "instance": {
            "name": base.name,
            "instance_seed": base.seed,
            "nodes": base.num_nodes,
            "edges": base.graph.number_of_edges(),
            "damaged_edges": len(base.damaged_edges),
            "repair_crews": base.repair_crews,
            "eta_hours": base.eta_hours,
            "horizon_hours": base.horizon_hours,
            "periods": base.periods,
            "total_supply_ton": base.total_supply,
            "total_demand_ton": base.total_demand,
            "theoretical_supply_ceiling": base.total_supply / max(base.total_demand, 1e-9),
        },
        "model": {
            "capacity_scale": instance.capacity_scale,
            "repair_time_weight": instance.repair_time_weight,
            "crew_transfer_time_scale": instance.crew_transfer_time_scale,
            "crew_min_access_progress": instance.crew_min_access_progress,
            "progressive_recovery": instance.progressive_recovery,
            "heterogeneous_vehicle_thresholds": (
                instance.heterogeneous_vehicle_thresholds
            ),
            "edge_capacity_constraint": instance.edge_capacity_constraint,
            "evaluation": instance.evaluation.as_dict(),
            "evaluation_fingerprint": instance.evaluation.fingerprint(),
            "vehicles": [asdict(vehicle) for vehicle in instance.vehicles],
            "recovery_stages": [asdict(stage) for stage in instance.recovery_stages],
        },
    }


def run_cli() -> None:
    args = _parse_args()
    if args.capacity_scale <= 0:
        raise SystemExit("--capacity-scale must be greater than zero")
    if args.repair_time_weight < 0:
        raise SystemExit("--repair-time-weight must be non-negative")
    if args.crew_transfer_time_scale < 0:
        raise SystemExit("--crew-transfer-time-scale must be non-negative")
    if not 0.0 <= args.crew_min_access_progress <= 1.0:
        raise SystemExit("--crew-min-access-progress must be in [0, 1]")
    if args.pop_size < 2:
        raise SystemExit("--pop-size must be at least 2")
    if args.generations <= 0:
        raise SystemExit("--generations must be greater than zero")
    if args.alns_iterations < 0:
        raise SystemExit("--alns-iterations must be non-negative")
    for name in (
        "crossover_probability",
        "mutation_probability",
        "alns_probability",
    ):
        if not 0.0 <= getattr(args, name) <= 1.0:
            raise SystemExit(f"--{name.replace('_', '-')} must be in [0, 1]")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = CapacityNSGAConfig(
        pop_size=args.pop_size,
        generations=args.generations,
        crossover_probability=args.crossover_probability,
        mutation_probability=args.mutation_probability,
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
            instance.capacity_scale = args.capacity_scale
            instance.repair_time_weight = args.repair_time_weight
            instance.crew_transfer_time_scale = args.crew_transfer_time_scale
            instance.crew_min_access_progress = args.crew_min_access_progress
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
                f"max_util={summary['max_edge_utilization']:.3f}, "
                f"time={summary['runtime_seconds']:.2f}s"
            )
    _write_outputs(results, output_dir, config)
    _plot_pareto_front(results, output_dir / "pareto_front.png")
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
    parser.add_argument("--crossover-probability", type=float, default=0.9)
    parser.add_argument("--mutation-probability", type=float, default=0.2)
    parser.add_argument("--alns-iterations", type=int, default=12)
    parser.add_argument("--alns-probability", type=float, default=0.35)
    parser.add_argument(
        "--capacity-scale",
        type=float,
        default=1.0,
        help="Multiplier applied to every edge-period throughput capacity.",
    )
    parser.add_argument(
        "--repair-time-weight",
        type=float,
        default=0.05,
        help="Weight lambda_R applied to repair work in the time objective.",
    )
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
        help="Minimum recovery progress usable by a moving repair crew.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/capacity_recovery",
        help="Directory for CSV and JSON outputs.",
    )
    return parser.parse_args()


def _write_outputs(
    results: list[CapacityExperimentResult],
    output_dir: Path,
    config: CapacityNSGAConfig,
) -> None:
    _write_csv(output_dir / "runs.csv", [result.summary_row() for result in results])
    with (output_dir / "solutions.json").open("w", encoding="utf-8") as fh:
        json.dump([result.to_jsonable() for result in results], fh, indent=2, ensure_ascii=False)
    convergence_rows = [
        {"instance": result.instance_name, "scenario": result.scenario, "seed": result.seed, **row}
        for result in results
        for row in result.convergence
    ]
    _write_csv(output_dir / "convergence.csv", convergence_rows)
    run_pareto_rows = [
        {
            "instance": result.instance_name,
            "scenario": result.scenario,
            "solver_seed": result.seed,
            **solution.row(),
        }
        for result in results
        for solution in result.pareto_front
    ]
    _write_csv(output_dir / "pareto_front_runs.csv", run_pareto_rows)
    global_points = _global_pareto_points(results)
    global_rows = [
        {
            "instance": result.instance_name,
            "scenario": result.scenario,
            "solver_seed": result.seed,
            **solution.row(),
        }
        for result, solution in global_points
    ]
    _write_csv(output_dir / "pareto_front.csv", global_rows)
    with (output_dir / "pareto_solutions.json").open("w", encoding="utf-8") as fh:
        json.dump(
            [
                {
                    "instance": result.instance_name,
                    "scenario": result.scenario,
                    "solver_seed": result.seed,
                    "solutions": [
                        solution.to_jsonable() for solution in result.pareto_front
                    ],
                }
                for result in results
            ],
            fh,
            indent=2,
            ensure_ascii=False,
        )
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "python_version": sys.version,
        "platform": platform.platform(),
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "source_file": str(Path(__file__).resolve()),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "algorithm_config": asdict(config),
        "runs": [
            {
                "scenario": result.scenario,
                "instance": result.instance_name,
                "solver_seed": result.seed,
                "parameters": result.parameters,
            }
            for result in results
        ],
    }
    with (output_dir / "experiment_manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)


def _git_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _git_dirty() -> bool | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return bool(completed.stdout.strip())


def _global_pareto_points(
    results: list[CapacityExperimentResult],
) -> list[tuple[CapacityExperimentResult, ParetoSolution]]:
    unique: dict[
        tuple[str, tuple[float, float, float]],
        tuple[CapacityExperimentResult, ParetoSolution],
    ] = {}
    for result in results:
        for solution in result.pareto_front:
            key = (solution.decision_hash, solution.objectives)
            unique.setdefault(key, (result, solution))

    points = list(unique.values())
    non_dominated = [
        point
        for idx, point in enumerate(points)
        if not any(
            _dominates(other[1].objectives, point[1].objectives)
            for other_idx, other in enumerate(points)
            if idx != other_idx
        )
    ]
    non_dominated.sort(
        key=lambda point: (
            point[1].objectives,
            point[1].decision_hash,
            point[0].seed,
        )
    )
    return non_dominated


def _plot_pareto_front(
    results: list[CapacityExperimentResult],
    output_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points = _global_pareto_points(results)
    if not points:
        return

    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8), constrained_layout=True)
    unmet = [solution.objectives[0] for _, solution in points]
    time_cost = [solution.objectives[1] for _, solution in points]
    min_sat = [solution.metrics["final_min_satisfaction"] for _, solution in points]
    colors = min_sat

    first = axes[0].scatter(unmet, time_cost, c=colors, cmap="viridis", s=42, alpha=0.85)
    axes[0].set_xlabel("F1: cumulative unmet fraction-period")
    axes[0].set_ylabel("F2: weighted time cost (minutes)")
    axes[0].set_title("Efficiency trade-off")
    colorbar = figure.colorbar(first, ax=axes[0])
    colorbar.set_label("Final minimum satisfaction")

    axes[1].scatter(unmet, min_sat, c=time_cost, cmap="plasma", s=42, alpha=0.85)
    axes[1].set_xlabel("F1: cumulative unmet fraction-period")
    axes[1].set_ylabel("Final minimum satisfaction")
    axes[1].set_title("Service versus fairness")

    axes[2].scatter(time_cost, min_sat, c=unmet, cmap="cividis", s=42, alpha=0.85)
    axes[2].set_xlabel("F2: weighted time cost (minutes)")
    axes[2].set_ylabel("Final minimum satisfaction")
    axes[2].set_title("Cost versus fairness")

    for axis in axes:
        axis.grid(alpha=0.22, linewidth=0.7)
    run_text = ", ".join(
        f"{result.scenario}/seed={result.seed}: n={len(result.pareto_front)}"
        for result in results
    )
    figure.suptitle(
        f"Global approximate Pareto front: n={len(points)} | {run_text}",
        fontsize=11,
    )
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


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
