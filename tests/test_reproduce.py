import unittest

import networkx as nx

from scripts.reproduce.dispatch import dispatch_relief
from scripts.reproduce.instance_generator import generate_random_instance
from scripts.reproduce.metrics import evaluate_solution
from scripts.reproduce.capacity_recovery import (
    _dispatch_with_vehicle_types,
    build_wenchuan_instance,
)
from scripts.reproduce.dynamic_interaction_experiments import (
    MECHANISMS,
    _apply_stress,
    _variant,
    run_mechanism,
)


class ReproductionFrameworkTest(unittest.TestCase):
    def test_instance_generation_counts_and_seed_reproducibility(self):
        first = generate_random_instance(
            num_nodes=25,
            gamma=3,
            damage_ratio=0.3,
            eta_hours=12,
            seed=7,
        )
        second = generate_random_instance(
            num_nodes=25,
            gamma=3,
            damage_ratio=0.3,
            eta_hours=12,
            seed=7,
        )

        self.assertEqual(first.graph.number_of_nodes(), 25)
        self.assertEqual(first.graph.number_of_edges(), 75)
        self.assertEqual(len(first.damaged_edges), 23)
        self.assertEqual(first.suppliers, second.suppliers)
        self.assertEqual(first.demands, second.demands)
        self.assertEqual(first.demand_amounts, second.demand_amounts)
        self.assertEqual(
            [(edge.u, edge.v, edge.repair_time) for edge in first.damaged_edges.values()],
            [(edge.u, edge.v, edge.repair_time) for edge in second.damaged_edges.values()],
        )

    def test_unreachable_demands_do_not_receive_allocations(self):
        instance = generate_random_instance(
            num_nodes=25,
            gamma=3,
            damage_ratio=0.1,
            eta_hours=12,
            seed=3,
        )
        disconnected = nx.Graph()
        disconnected.add_nodes_from(instance.graph.nodes)
        priority = [(supplier, demand) for supplier in instance.suppliers for demand in instance.demands]

        result = dispatch_relief(instance, disconnected, priority)

        self.assertEqual(result.allocations, [])
        self.assertTrue(all(amount == 0 for amount in result.delivered_by_demand.values()))

    def test_evaluation_satisfaction_bounds_and_unique_repairs(self):
        instance = generate_random_instance(
            num_nodes=25,
            gamma=3,
            damage_ratio=0.1,
            eta_hours=12,
            seed=11,
        )
        repair_order = list(instance.damaged_edges)
        team_assignment = [0 for _ in repair_order]
        priority = [(supplier, demand) for supplier in instance.suppliers for demand in instance.demands]

        result = evaluate_solution(instance, repair_order, team_assignment, priority)

        repaired_ids = [task.damage_id for task in result.repair_schedule.tasks if task.repaired]
        self.assertEqual(len(repaired_ids), len(set(repaired_ids)))
        for metric in result.period_metrics:
            self.assertGreaterEqual(metric.total_satisfaction, 0.0)
            self.assertLessEqual(metric.total_satisfaction, 1.0)
            self.assertGreaterEqual(metric.minimum_satisfaction, 0.0)
            self.assertLessEqual(metric.minimum_satisfaction, 1.0)
        totals = [metric.total_satisfaction for metric in result.period_metrics]
        self.assertEqual(totals, sorted(totals))

    def test_wenchuan_capacity_case_supply_ceiling(self):
        instance = build_wenchuan_instance(seed=1).base

        self.assertEqual(instance.graph.number_of_nodes(), 38)
        self.assertEqual(instance.graph.number_of_edges(), 51)
        self.assertEqual(len(instance.damaged_edges), 16)
        self.assertEqual(instance.total_supply, 9000)
        self.assertEqual(instance.total_demand, 11288)
        self.assertAlmostEqual(instance.total_supply / instance.total_demand, 0.7973068745570517)

    def test_binary_mechanism_requires_full_recovery(self):
        instance = _variant(build_wenchuan_instance(seed=1), progressive=False)

        self.assertTrue(all(vehicle.min_recovery_progress == 1.0 for vehicle in instance.vehicles))
        self.assertEqual([stage.capacity_ratio for stage in instance.recovery_stages], [0.0, 1.0])

    def test_edge_period_capacity_is_enforced(self):
        instance = build_wenchuan_instance(seed=1)
        instance.capacity_scale = 0.001
        progress = {edge_id: 1.0 for edge_id in instance.base.damaged_edges}
        priority = [
            (supplier, demand)
            for supplier in instance.base.suppliers
            for demand in instance.base.demands
        ]
        result = _dispatch_with_vehicle_types(
            instance,
            priority,
            progress,
            dict(instance.base.supply_amounts),
            dict(instance.base.demand_amounts),
        )

        self.assertLessEqual(result["max_edge_utilization"], 1.0 + 1e-9)
        self.assertGreater(result["max_edge_utilization"], 0.0)
        self.assertGreater(result["capacity_blocked_tons"], 0.0)
        for vehicle in instance.vehicles:
            self.assertLessEqual(
                result["vehicle_trips"][vehicle.vehicle_type],
                vehicle.count,
            )

    def test_stress_grid_exposes_dynamic_feedback_benefit(self):
        instance = _apply_stress(build_wenchuan_instance(seed=1), 2.0, 2)
        results = {
            mechanism.name: run_mechanism(instance, mechanism, 40001)[0]
            for mechanism in MECHANISMS
        }

        self.assertEqual(
            set(results),
            {
                "binary_static",
                "progressive_static",
                "progressive_openloop",
                "progressive_rolling",
            },
        )
        self.assertLess(
            results["progressive_static"]["cumulative_unmet_area"],
            results["binary_static"]["cumulative_unmet_area"],
        )
        self.assertLess(
            results["progressive_rolling"]["cumulative_unmet_area"],
            results["progressive_openloop"]["cumulative_unmet_area"],
        )
        self.assertGreater(
            results["progressive_rolling"]["average_reachable_ratio"],
            results["progressive_openloop"]["average_reachable_ratio"],
        )

if __name__ == "__main__":
    unittest.main()
