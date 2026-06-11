import unittest

import networkx as nx

from scripts.reproduce.dispatch import dispatch_relief
from scripts.reproduce.instance_generator import generate_random_instance
from scripts.reproduce.metrics import evaluate_solution
from scripts.reproduce.capacity_recovery import build_wenchuan_instance


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

if __name__ == "__main__":
    unittest.main()
