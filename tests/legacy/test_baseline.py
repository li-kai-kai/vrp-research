import unittest

import networkx as nx

from scripts.legacy.dispatch import dispatch_relief
from scripts.legacy.metrics import evaluate_solution
from scripts.reproduce.instance_generator import generate_random_instance


class LegacyBaselineTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
