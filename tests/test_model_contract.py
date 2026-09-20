"""Versioned evaluation-contract tests (M01-M11).

These build minimal, fully explicit instances instead of sampling the random
generator, so each acceptance criterion pins one mechanism at a time. They are
the acceptance cases named in the v2 task book; they are not a substitute for
the historical legacy regression suite in tests/test_capacity_recovery.py.
"""

from __future__ import annotations

import unittest

import networkx as nx

from scripts.reproduce.capacity_recovery import (
    BINARY_RECOVERY_STAGES,
    PROGRESS_TOLERANCE,
    CapacityExperimentInstance,
    CapacityIndividual,
    EvaluationConfig,
    RecoveryStage,
    VehicleProfile,
    _build_vehicle_graph,
    _dispatch_with_vehicle_types,
    evaluate_capacity_solution,
    evaluate_capacity_solution_detailed,
    model_factor_variant,
)
from scripts.reproduce.model import DamagedEdge, RandomInstance


TRUCK_WITH_AMPLE_QUOTA = VehicleProfile(
    vehicle_type=1,
    capacity_ton=500.0,
    count=10,
    occupied_od_pcu_h=0.0,
    min_recovery_progress=0.0,
    pcu_per_vehicle=1.0,
)

PASS_THROUGH_STAGES = [
    RecoveryStage(0.0, 1.0, 1.0, "full", 1.0),
]


def _make_instance(
    *,
    model_version: str = "legacy",
    suppliers: list[int],
    demands: list[int],
    supply_amounts: dict[int, float],
    demand_amounts: dict[int, float],
    edges: list[tuple[int, int, float, float]],
    damaged: list[tuple[int, int, float]] | None = None,
    repair_crews: int = 1,
    eta_hours: int = 8,
    horizon_hours: int = 72,
    vehicles: list[VehicleProfile] | None = None,
    recovery_stages: list[RecoveryStage] | None = None,
    capacity_scale: float = 1.0,
    crew_transfer_time_scale: float = 0.0,
    crew_min_access_progress: float = 0.0,
) -> CapacityExperimentInstance:
    """Build a minimal instance with an exactly specified physical graph."""
    graph = nx.Graph()
    for node_id in sorted({*suppliers, *demands}):
        graph.add_node(node_id)
    for edge_id, (u, v, free_time, capacity) in enumerate(edges):
        graph.add_node(u)
        graph.add_node(v)
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
    for damage_id, (u, v, repair_time) in enumerate(damaged or []):
        if not graph.has_edge(u, v):
            raise ValueError(f"damaged edge {(u, v)} must exist in the base graph")
        graph[u][v]["damaged"] = True
        graph[u][v]["damage_id"] = damage_id
        graph[u][v]["repair_time"] = float(repair_time)
        damaged_edges[damage_id] = DamagedEdge(damage_id, u, v, float(repair_time))

    base = RandomInstance(
        name=f"contract_{model_version}",
        seed=0,
        num_nodes=graph.number_of_nodes(),
        gamma=0,
        damage_ratio=0.0,
        eta_hours=eta_hours,
        horizon_hours=horizon_hours,
        graph=graph,
        suppliers=list(suppliers),
        demands=list(demands),
        demand_amounts=dict(demand_amounts),
        supply_amounts=dict(supply_amounts),
        damaged_edges=damaged_edges,
        repair_crews=repair_crews,
    )
    return CapacityExperimentInstance(
        base=base,
        vehicles=list(vehicles) if vehicles is not None else [TRUCK_WITH_AMPLE_QUOTA],
        recovery_stages=(
            list(recovery_stages) if recovery_stages is not None else list(PASS_THROUGH_STAGES)
        ),
        capacity_scale=capacity_scale,
        crew_transfer_time_scale=crew_transfer_time_scale,
        crew_min_access_progress=crew_min_access_progress,
        evaluation=EvaluationConfig.for_version(model_version),
    )


def _decision(
    instance: CapacityExperimentInstance,
    *,
    repair_order: list[int] | None = None,
    team_assignment: list[int] | None = None,
    dispatch_priority: list[tuple[int, int]] | None = None,
) -> CapacityIndividual:
    base = instance.base
    order = list(repair_order if repair_order is not None else base.damaged_edges)
    return CapacityIndividual(
        repair_order=order,
        team_assignment=list(
            team_assignment if team_assignment is not None else [0] * len(order)
        ),
        dispatch_priority=list(
            dispatch_priority
            if dispatch_priority is not None
            else [(s, d) for s in base.suppliers for d in base.demands]
        ),
    )


class ModelContractTest(unittest.TestCase):
    def test_m01_permanently_isolated_demand_does_not_strand_resources(self):
        """legacy caps the reachable point at 25 t, v2 delivers 50 t."""
        observation: dict[str, dict[str, float]] = {}
        for version in ("legacy", "v2"):
            instance = _make_instance(
                model_version=version,
                suppliers=[0],
                demands=[1, 2],
                supply_amounts={0: 50.0},
                demand_amounts={1: 50.0, 2: 50.0},
                # Node 2 carries demand but has no incident edge at all.
                edges=[(0, 1, 10.0, 10_000.0)],
            )
            _objectives, metrics = evaluate_capacity_solution(
                instance,
                _decision(instance),
            )
            observation[version] = metrics

            # Conservation holds in both rounds.
            self.assertLessEqual(metrics["total_delivered"], 50.0 + 1e-9)
            self.assertGreaterEqual(metrics["remaining_supply"], -1e-9)
            self.assertAlmostEqual(
                metrics["total_delivered"] + metrics["remaining_supply"],
                50.0,
                places=6,
            )

        self.assertAlmostEqual(observation["legacy"]["total_delivered"], 25.0, places=6)
        self.assertAlmostEqual(observation["v2"]["total_delivered"], 50.0, places=6)
        self.assertAlmostEqual(observation["v2"]["remaining_supply"], 0.0, places=6)
        self.assertAlmostEqual(observation["legacy"]["remaining_supply"], 25.0, places=6)

    def test_m02_period_targets_are_not_double_subtracted(self):
        """Both stages pass period-total targets and never over/under-allocate."""
        instance = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1, 2],
            supply_amounts={0: 120.0},
            demand_amounts={1: 100.0, 2: 100.0},
            edges=[(0, 1, 10.0, 10_000.0), (0, 2, 10.0, 10_000.0)],
        )
        remaining_supply = dict(instance.base.supply_amounts)
        remaining_demand = dict(instance.base.demand_amounts)
        result = _dispatch_with_vehicle_types(
            instance,
            [(0, 1), (0, 2)],
            {},
            remaining_supply,
            remaining_demand,
        )

        delivered = result["delivered"]
        for demand, amount in delivered.items():
            self.assertLessEqual(
                amount,
                remaining_demand[demand] + 1e-9,
                f"demand {demand} received more than it still requires",
            )
        # Ample trips and edge capacity: every unit of the binding resource is
        # placed, so no reachable supply is stranded by the two-stage split.
        self.assertAlmostEqual(sum(delivered.values()), 120.0, places=6)
        self.assertAlmostEqual(
            sum(remaining_supply.values()) + sum(delivered.values()),
            120.0,
            places=6,
        )

        # The dispatch is idempotent on its own output state: nothing is
        # double-counted, so a repeat pass has nothing left to move.
        follow_up = _dispatch_with_vehicle_types(
            instance,
            [(0, 1), (0, 2)],
            {},
            remaining_supply,
            {
                demand: max(0.0, remaining_demand[demand] - delivered[demand])
                for demand in remaining_demand
            },
        )
        self.assertAlmostEqual(sum(follow_up["delivered"].values()), 0.0, places=6)

    def test_m02_vehicle_quota_bounds_two_stage_allocation(self):
        """A binding fleet budget is respected without over-allocation.

        The period budget bounds *trips*, and one trip is charged per
        allocation whatever the load, so a single 60-ton vehicle serves one
        demand point and the second stage cannot reuse its spare tonnage.
        """
        instance = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1, 2],
            supply_amounts={0: 200.0},
            demand_amounts={1: 100.0, 2: 100.0},
            edges=[(0, 1, 10.0, 10_000.0), (0, 2, 10.0, 10_000.0)],
            vehicles=[
                VehicleProfile(
                    vehicle_type=1,
                    capacity_ton=60.0,
                    count=1,
                    occupied_od_pcu_h=0.0,
                    min_recovery_progress=0.0,
                    pcu_per_vehicle=1.0,
                )
            ],
        )
        result = _dispatch_with_vehicle_types(
            instance,
            [(0, 1), (0, 2)],
            {},
            dict(instance.base.supply_amounts),
            dict(instance.base.demand_amounts),
        )
        delivered = result["delivered"]

        self.assertLessEqual(sum(result["vehicle_trips"].values()), 1)
        self.assertEqual(result["vehicle_trips"][1], 1)
        # Never more than the fleet could carry, and never more than asked for.
        self.assertLessEqual(sum(delivered.values()), 60.0 + 1e-9)
        for demand, amount in delivered.items():
            self.assertLessEqual(amount, instance.base.demand_amounts[demand] + 1e-9)
        # The one trip went to the first open target; the spent budget leaves
        # nothing for the second demand rather than silently exceeding it.
        self.assertGreater(delivered[1], 0.0)
        self.assertAlmostEqual(delivered[2], 0.0, places=9)

    def test_m03_cross_period_conservation(self):
        """Cumulative delivery never exceeds supply and stock never goes negative."""
        instance = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1, 2],
            supply_amounts={0: 90.0},
            demand_amounts={1: 120.0, 2: 120.0},
            edges=[(0, 1, 10.0, 10_000.0), (0, 2, 10.0, 10_000.0)],
            vehicles=[
                VehicleProfile(
                    vehicle_type=1,
                    capacity_ton=10.0,
                    count=1,
                    occupied_od_pcu_h=0.0,
                    min_recovery_progress=0.0,
                    pcu_per_vehicle=1.0,
                )
            ],
        )
        objectives, metrics = evaluate_capacity_solution(
            instance,
            _decision(instance),
        )

        self.assertLessEqual(metrics["total_delivered"], 90.0 + 1e-9)
        self.assertAlmostEqual(
            metrics["total_delivered"] + metrics["remaining_supply"],
            90.0,
            places=6,
        )
        self.assertGreaterEqual(metrics["remaining_supply"], -1e-9)
        # A ten-ton-per-period fleet cannot finish 240 tons inside one horizon.
        self.assertLess(metrics["total_delivered"], 90.0)
        self.assertGreater(metrics["zero_service_ratio"], 0.0)
        self.assertAlmostEqual(metrics["unmet_ratio_hours"], objectives[0] * 8)

    def test_m04_road_repaired_late_in_a_period_is_usable_only_next_period(self):
        """Binary recovery, 479-minute repair, 480-minute period."""
        outcomes = {}
        for version in ("legacy", "v2"):
            instance = _make_instance(
                model_version=version,
                suppliers=[0],
                demands=[1],
                supply_amounts={0: 100.0},
                demand_amounts={1: 50.0},
                edges=[(0, 1, 10.0, 10_000.0)],
                damaged=[(0, 1, 479.0)],
                recovery_stages=BINARY_RECOVERY_STAGES,
                vehicles=[
                    VehicleProfile(
                        vehicle_type=1,
                        capacity_ton=100.0,
                        count=10,
                        occupied_od_pcu_h=0.0,
                        min_recovery_progress=1.0,
                        pcu_per_vehicle=1.0,
                    )
                ],
            )
            outcomes[version] = evaluate_capacity_solution_detailed(
                instance,
                _decision(instance, repair_order=[0], team_assignment=[0]),
            )

        # v2 samples the state at the start of the period, so the first period
        # is still blocked and the first delivery can only happen in period two.
        self.assertAlmostEqual(outcomes["v2"].period_delivered[0], 0.0, places=9)
        self.assertGreater(outcomes["v2"].period_delivered[1], 0.0)
        # legacy keeps its historical end-of-period sampling and delivers early.
        self.assertGreater(outcomes["legacy"].period_delivered[0], 0.0)

    def test_m05_edge_finished_exactly_on_the_period_boundary(self):
        """A 480-minute repair is usable in period two and never backfills period one."""
        instance = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 100.0},
            demand_amounts={1: 50.0},
            edges=[(0, 1, 10.0, 10_000.0)],
            damaged=[(0, 1, 480.0)],
            recovery_stages=BINARY_RECOVERY_STAGES,
            vehicles=[
                VehicleProfile(
                    vehicle_type=1,
                    capacity_ton=100.0,
                    count=10,
                    occupied_od_pcu_h=0.0,
                    min_recovery_progress=1.0,
                    pcu_per_vehicle=1.0,
                )
            ],
        )
        outcome = evaluate_capacity_solution_detailed(
            instance,
            _decision(instance, repair_order=[0], team_assignment=[0]),
        )

        self.assertAlmostEqual(outcome.period_delivered[0], 0.0, places=9)
        self.assertGreater(outcome.period_delivered[1], 0.0)

    def test_m06_over_period_trip_consumes_nothing(self):
        """A 540-minute one-way trip cannot count as an arrival inside 480 minutes."""
        kwargs = dict(
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 100.0},
            demand_amounts={1: 50.0},
            edges=[(0, 1, 540.0, 10_000.0)],
        )
        v2_instance = _make_instance(model_version="v2", **kwargs)
        v2_outcome = evaluate_capacity_solution_detailed(
            v2_instance,
            _decision(v2_instance),
        )

        self.assertAlmostEqual(v2_outcome.metrics["total_delivered"], 0.0, places=9)
        self.assertAlmostEqual(v2_outcome.metrics["remaining_supply"], 100.0, places=6)
        self.assertAlmostEqual(v2_outcome.metrics["total_vehicle_trips"], 0.0)
        self.assertAlmostEqual(v2_outcome.metrics["max_edge_utilization"], 0.0)
        self.assertGreater(v2_outcome.metrics["time_infeasible_candidates"], 0.0)

        # legacy keeps its historical behaviour: the trip is dispatched even
        # though it cannot arrive inside one period.
        legacy_instance = _make_instance(model_version="legacy", **kwargs)
        _objectives, legacy_metrics = evaluate_capacity_solution(
            legacy_instance,
            _decision(legacy_instance),
        )
        self.assertGreater(legacy_metrics["total_delivered"], 0.0)
        self.assertGreater(legacy_metrics["total_vehicle_trips"], 0.0)

    def test_m07_vehicle_threshold_boundary_uses_one_tolerance(self):
        stages = [
            RecoveryStage(0.0, 0.30, 0.30, "temporary", 0.30),
            RecoveryStage(0.30, 1.0, 0.60, "one_lane", 0.60),
            RecoveryStage(1.0, 1.01, 1.0, "full", 1.0),
        ]
        instance = _make_instance(
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 100.0},
            demand_amounts={1: 50.0},
            edges=[(0, 1, 10.0, 1000.0)],
            damaged=[(0, 1, 60.0)],
            recovery_stages=stages,
            vehicles=[
                VehicleProfile(
                    vehicle_type=1,
                    capacity_ton=100.0,
                    count=10,
                    occupied_od_pcu_h=0.0,
                    min_recovery_progress=0.30,
                    pcu_per_vehicle=1.0,
                )
            ],
        )
        vehicle = instance.vehicles[0]

        def passable(progress: float) -> bool:
            graph = _build_vehicle_graph(instance, {0: progress}, vehicle)
            return graph.has_edge(0, 1)

        self.assertTrue(passable(0.30))
        self.assertTrue(passable(0.30 + 1e-12))
        self.assertTrue(passable(0.30 - 0.5 * PROGRESS_TOLERANCE))
        self.assertFalse(passable(0.30 - 1e-6))

    def test_m08_fleet_quota_is_shared_and_edge_capacity_is_charged_per_trip(self):
        """Trips x PCU are charged to edges; the quota is not copied per supplier."""
        instance = _make_instance(
            model_version="v2",
            suppliers=[0, 1],
            demands=[2, 3],
            supply_amounts={0: 1000.0, 1: 1000.0},
            demand_amounts={2: 500.0, 3: 500.0},
            edges=[
                (0, 2, 10.0, 1000.0),
                (0, 3, 10.0, 1000.0),
                (1, 2, 10.0, 1000.0),
                (1, 3, 10.0, 1000.0),
            ],
            vehicles=[
                VehicleProfile(
                    vehicle_type=1,
                    capacity_ton=50.0,
                    count=2,
                    occupied_od_pcu_h=0.0,
                    min_recovery_progress=0.0,
                    pcu_per_vehicle=5.0,
                )
            ],
            capacity_scale=0.001,
        )
        result = _dispatch_with_vehicle_types(
            instance,
            [(0, 2), (0, 3), (1, 2), (1, 3)],
            {},
            dict(instance.base.supply_amounts),
            dict(instance.base.demand_amounts),
        )

        # One shared period budget, not one budget per supply point: with four
        # supplier-demand pairs a per-supplier copy would allow up to eight.
        self.assertLessEqual(sum(result["vehicle_trips"].values()), 2)
        self.assertLessEqual(result["max_edge_utilization"], 1.0 + 1e-9)
        self.assertAlmostEqual(
            sum(item["amount"] for item in result["allocations"]),
            sum(result["delivered"].values()),
        )
        # Each edge period holds capacity * eta_hours * capacity_scale = 8 PCU,
        # so a five-PCU vehicle fits exactly once per edge.
        for vehicle_type, trips in result["vehicle_trips"].items():
            self.assertLessEqual(
                trips * instance.vehicles[0].pcu_per_vehicle,
                8 * 2 + 1e-9,
                f"vehicle type {vehicle_type} overran the period throughput",
            )

    def test_m09_model_factor_variant_inherits_evaluation_config(self):
        source = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 100.0},
            demand_amounts={1: 50.0},
            edges=[(0, 1, 10.0, 1000.0)],
            damaged=[(0, 1, 60.0)],
        )
        original_thresholds = [v.min_recovery_progress for v in source.vehicles]
        original_stages = list(source.recovery_stages)

        variant = model_factor_variant(
            source,
            progressive_recovery=False,
            heterogeneous_vehicle_thresholds=False,
            edge_capacity_constraint=False,
        )

        # The version and evaluation configuration are inherited unchanged.
        self.assertEqual(variant.evaluation, source.evaluation)
        self.assertEqual(variant.evaluation.model_version, "v2")
        self.assertFalse(variant.evaluation.fair_share_cap)
        self.assertEqual(variant.evaluation.dispatch_timing, "period_start")
        self.assertTrue(variant.evaluation.enforce_within_period_arrival)
        self.assertNotEqual(
            variant.evaluation.fingerprint(),
            EvaluationConfig.for_version("legacy").fingerprint(),
        )

        # Only the requested model factors moved, and the base is untouched.
        self.assertFalse(variant.progressive_recovery)
        self.assertFalse(variant.heterogeneous_vehicle_thresholds)
        self.assertFalse(variant.edge_capacity_constraint)
        self.assertTrue(source.progressive_recovery)
        self.assertTrue(source.heterogeneous_vehicle_thresholds)
        self.assertTrue(source.edge_capacity_constraint)
        self.assertEqual([v.min_recovery_progress for v in source.vehicles], original_thresholds)
        self.assertEqual(list(source.recovery_stages), original_stages)

    def test_m10_illegal_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            EvaluationConfig(model_version="unknown")
        with self.assertRaises(ValueError):
            # A half-migrated profile must not evaluate a silent mixture.
            EvaluationConfig(model_version="v2", fair_share_cap=True)
        with self.assertRaises(ValueError):
            EvaluationConfig(
                model_version="legacy",
                dispatch_timing="period_start",
            )
        with self.assertRaises(ValueError):
            EvaluationConfig(
                model_version="legacy",
                fleet_semantics="per_supplier_fleet",
            )

        for field_name in ("crew_transfer_time_scale", "crew_min_access_progress"):
            instance = _make_instance(
                model_version="v2",
                suppliers=[0],
                demands=[1],
                supply_amounts={0: 100.0},
                demand_amounts={1: 50.0},
                edges=[(0, 1, 10.0, 1000.0)],
                **{field_name: 0.5},
            )
            with self.assertRaises(ValueError):
                evaluate_capacity_solution(instance, _decision(instance))

        # legacy is unaffected: it still accepts these settings.
        legacy = _make_instance(
            model_version="legacy",
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 100.0},
            demand_amounts={1: 50.0},
            edges=[(0, 1, 10.0, 1000.0)],
            crew_transfer_time_scale=0.5,
        )
        evaluate_capacity_solution(legacy, _decision(legacy))

    def test_m11_objective_units_and_signs(self):
        instance = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1, 2],
            supply_amounts={0: 60.0},
            demand_amounts={1: 80.0, 2: 80.0},
            edges=[(0, 1, 10.0, 10_000.0), (0, 2, 10.0, 10_000.0)],
        )
        objectives, metrics = evaluate_capacity_solution(
            instance,
            _decision(instance),
        )
        f1, f2, f3 = objectives

        self.assertAlmostEqual(
            metrics["unmet_ratio_hours"],
            f1 * instance.base.eta_hours,
            places=9,
        )
        self.assertAlmostEqual(f3, -metrics["final_min_satisfaction"], places=9)
        self.assertLessEqual(f3, 0.0)
        self.assertGreaterEqual(f1, 0.0)
        self.assertLessEqual(f1, float(instance.base.periods))
        self.assertGreaterEqual(f2, 0.0)
        # Repair work is reported separately and is never called a makespan.
        self.assertIn("total_repair_work", metrics)
        self.assertNotIn("makespan", metrics)


if __name__ == "__main__":
    unittest.main()
