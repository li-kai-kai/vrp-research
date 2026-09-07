import unittest
from scripts.reproduce.benchmark_algorithms import ALGORITHMS, BenchmarkBudget, solve_benchmark_algorithm
from scripts.reproduce.benchmark_suite import benchmark_specs, build_benchmark_instance
from scripts.reproduce.run_benchmark import hypervolume_3d, inverted_generational_distance


class BenchmarkTest(unittest.TestCase):
    def test_publication_suite_covers_real_and_all_size_groups(self):
        specs = benchmark_specs("publication")

        self.assertEqual(
            {spec.size_group for spec in specs},
            {"case_study", "small", "medium", "large"},
        )
        self.assertEqual([spec.num_nodes for spec in specs if spec.size_group == "large"], [400, 800])
        self.assertTrue(any(spec.source == "wenchuan" for spec in specs))

    def test_instance_builder_is_reproducible_and_scales_fleet(self):
        small_spec, _, large_spec = benchmark_specs("smoke")
        first = build_benchmark_instance(small_spec, instance_seed=7)
        repeated = build_benchmark_instance(small_spec, instance_seed=7)
        large = build_benchmark_instance(large_spec, instance_seed=7)

        self.assertEqual(first.base.name, repeated.base.name)
        self.assertEqual(first.base.demand_amounts, repeated.base.demand_amounts)
        self.assertEqual(
            [(edge.u, edge.v, edge.repair_time) for edge in first.base.damaged_edges.values()],
            [(edge.u, edge.v, edge.repair_time) for edge in repeated.base.damaged_edges.values()],
        )
        self.assertGreater(
            sum(vehicle.count for vehicle in large.vehicles),
            sum(vehicle.count for vehicle in first.vehicles),
        )
        for instance in (first, large):
            nominal_capacity = sum(
                vehicle.capacity_ton * vehicle.count for vehicle in instance.vehicles
            )
            self.assertLess(nominal_capacity, instance.base.total_supply)
            self.assertAlmostEqual(
                nominal_capacity / instance.base.total_demand,
                0.14,
                delta=0.02,
            )

    def test_all_baselines_share_evaluation_budget_and_objectives(self):
        spec = benchmark_specs("smoke")[0]
        instance = build_benchmark_instance(spec, instance_seed=1)
        budget = BenchmarkBudget(max_evaluations=4, pop_size=2, alns_iterations=1)

        results = {
            algorithm: solve_benchmark_algorithm(algorithm, instance, budget, seed=51_001)
            for algorithm in ALGORITHMS
        }

        self.assertEqual(results["spt"].evaluations, 1)
        for algorithm in ("vnd", "nsga2", "nsga2_alns"):
            self.assertEqual(results[algorithm].evaluations, budget.max_evaluations)
        for result in results.values():
            self.assertGreaterEqual(len(result.front), 1)
            self.assertEqual(len(result.representative.objectives), 3)

    def test_quality_indicators_have_known_values(self):
        points = [(0.0, 1.0, 1.0), (1.0, 0.0, 0.0)]
        reference = (1.1, 1.1, 1.1)

        self.assertAlmostEqual(hypervolume_3d(points, reference), 0.131)
        self.assertEqual(inverted_generational_distance(points, points), 0.0)



if __name__ == "__main__":
    unittest.main()
