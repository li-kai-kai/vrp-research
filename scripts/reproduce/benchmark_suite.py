from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from scripts.reproduce.capacity_recovery import (
    DEFAULT_RECOVERY_STAGES,
    DEFAULT_VEHICLES,
    CapacityExperimentInstance,
    build_wenchuan_instance,
)
from scripts.reproduce.instance_generator import generate_random_instance


DEFAULT_SYNTHETIC_FLEET_CAPACITY_RATIO = 0.14


@dataclass(frozen=True)
class BenchmarkSpec:
    case_id: str
    size_group: str
    num_nodes: int
    gamma: int
    damage_ratio: float
    eta_hours: int = 8
    capacity_scale: float = 0.05
    supply_ratio: float = 0.90
    source: str = "synthetic"
    fleet_capacity_ratio: float | None = DEFAULT_SYNTHETIC_FLEET_CAPACITY_RATIO

    def row(self) -> dict[str, object]:
        return asdict(self)


_CORE_SPECS = (
    BenchmarkSpec(
        "WEN38",
        "case_study",
        38,
        0,
        16 / 51,
        capacity_scale=1.0,
        supply_ratio=9000 / 11288,
        source="wenchuan",
        fleet_capacity_ratio=None,
    ),
    BenchmarkSpec("S025", "small", 25, 3, 0.15),
    BenchmarkSpec("S050", "small", 50, 4, 0.30),
    BenchmarkSpec("M100", "medium", 100, 3, 0.15),
    BenchmarkSpec("M200", "medium", 200, 4, 0.30),
    BenchmarkSpec("L400", "large", 400, 3, 0.15),
    BenchmarkSpec("L800", "large", 800, 4, 0.30),
)


def benchmark_specs(suite: str) -> list[BenchmarkSpec]:
    """Return an explicit, interpretable size-stratified benchmark suite."""
    if suite == "smoke":
        return [
            BenchmarkSpec("S020", "small", 20, 3, 0.15),
            BenchmarkSpec("M060", "medium", 60, 3, 0.20),
            BenchmarkSpec("L120", "large", 120, 4, 0.25),
        ]
    if suite in {"benchmark", "publication"}:
        return list(_CORE_SPECS)
    raise ValueError(f"unknown benchmark suite: {suite}")


def default_instance_seeds(suite: str) -> list[int]:
    if suite == "smoke":
        return [1]
    if suite == "benchmark":
        return [1, 2, 3, 4, 5]
    if suite == "publication":
        return list(range(1, 31))
    raise ValueError(f"unknown benchmark suite: {suite}")


def build_benchmark_instance(
    spec: BenchmarkSpec,
    *,
    instance_seed: int,
) -> CapacityExperimentInstance:
    if spec.source == "wenchuan":
        instance = build_wenchuan_instance(seed=instance_seed)
        instance.base.name = f"{spec.case_id}_seed{instance_seed}"
        instance.capacity_scale = spec.capacity_scale
        return instance

    base = generate_random_instance(
        num_nodes=spec.num_nodes,
        gamma=spec.gamma,
        damage_ratio=spec.damage_ratio,
        eta_hours=spec.eta_hours,
        seed=instance_seed,
        supply_ratio=spec.supply_ratio,
        topology="random",
        damage_strategy="random",
        node_role_strategy="random",
    )
    base.name = f"{spec.case_id}_seed{instance_seed}"

    if spec.fleet_capacity_ratio is None or spec.fleet_capacity_ratio <= 0:
        raise ValueError("synthetic fleet_capacity_ratio must be positive")
    # Each vehicle can make one trip per decision period. Calibrate the fleet's
    # nominal tonnage to demand so relief cannot be exhausted in the first period.
    reference_capacity = sum(
        vehicle.capacity_ton * vehicle.count for vehicle in DEFAULT_VEHICLES
    )
    target_period_capacity = base.total_demand * spec.fleet_capacity_ratio
    fleet_scale = target_period_capacity / reference_capacity
    vehicles = [
        replace(vehicle, count=max(1, round(vehicle.count * fleet_scale)))
        for vehicle in DEFAULT_VEHICLES
    ]
    return CapacityExperimentInstance(
        base=base,
        vehicles=vehicles,
        recovery_stages=list(DEFAULT_RECOVERY_STAGES),
        capacity_scale=spec.capacity_scale,
    )
