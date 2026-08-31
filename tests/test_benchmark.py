import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.reproduce.benchmark_algorithms import (
    ALGORITHMS,
    BenchmarkBudget,
    solve_benchmark_algorithm,
)
from scripts.reproduce.benchmark_suite import (
    benchmark_specs,
    build_benchmark_instance,
)
from scripts.reproduce.run_benchmark import (
    hypervolume_3d,
    inverted_generational_distance,
)
from scripts.reproduce.run_model_ablation import (
    MODEL_FACTOR_COMBINATIONS,
    run_model_ablation,
)
from scripts.reproduce.model_ablation_analysis import (
    METRICS,
    analyze_model_ablation,
    merge_model_ablation_shards,
)


class BenchmarkFrameworkTest(unittest.TestCase):
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

    def test_model_ablation_runs_all_eight_paired_combinations(self):
        budget = BenchmarkBudget(
            max_evaluations=2,
            pop_size=2,
            alns_iterations=0,
        )
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            rows = run_model_ablation(
                suite="smoke",
                cases=["S020"],
                instance_seeds=[1],
                solver_repeats=1,
                output_dir=output_dir,
                budget=budget,
            )

            self.assertEqual(len(MODEL_FACTOR_COMBINATIONS), 8)
            self.assertEqual(len(rows), 8)
            self.assertEqual(len({row["model_id"] for row in rows}), 8)
            self.assertEqual({row["algorithm"] for row in rows}, {"nsga2_alns"})
            self.assertEqual({row["instance_seed"] for row in rows}, {1})
            self.assertEqual({row["solver_seed"] for row in rows}, {60_000})
            self.assertEqual({row["max_evaluations"] for row in rows}, {2})
            for row in rows:
                for column in (
                    "hypervolume",
                    "igd",
                    "F1",
                    "F2",
                    "F3",
                    "average_reachable_ratio",
                    "capacity_blocked_tons",
                ):
                    self.assertIn(column, row)
            for filename in (
                "model_ablation.csv",
                "pareto_points.csv",
                "pooled_reference_front.csv",
                "model_summary.csv",
                "factor_effects_raw.csv",
                "factor_effects.csv",
                "factorial_completeness.csv",
                "experiment_manifest.json",
            ):
                self.assertTrue((output_dir / filename).is_file(), filename)

    def test_formal_factorial_analysis_uses_instance_means_and_known_effects(self):
        rows = []
        for instance_seed in (1, 2):
            for repeat in (0, 1):
                solver_seed = 60_000 + instance_seed * 10 + repeat
                for progressive in (0, 1):
                    for heterogeneous in (0, 1):
                        for capacity in (0, 1):
                            x_progressive = 1 if progressive else -1
                            x_heterogeneous = 1 if heterogeneous else -1
                            x_capacity = 1 if capacity else -1
                            response = (
                                10.0
                                + x_progressive
                                + 2.0 * x_heterogeneous
                                + 3.0 * x_capacity
                                + 4.0 * x_progressive * x_heterogeneous
                            )
                            row = {
                                "run_key": (
                                    f"S025:i{instance_seed}:s{solver_seed}:"
                                    f"PR{progressive}_HT{heterogeneous}_EC{capacity}"
                                ),
                                "case_id": "S025",
                                "source": "synthetic",
                                "instance_seed": instance_seed,
                                "solver_seed": solver_seed,
                                "algorithm": "nsga2_alns",
                                "model_id": (
                                    f"PR{progressive}_HT{heterogeneous}_EC{capacity}"
                                ),
                                "progressive_recovery": progressive,
                                "heterogeneous_vehicle_thresholds": heterogeneous,
                                "edge_capacity_constraint": capacity,
                                "max_evaluations": 100,
                                "evaluations": 100,
                            }
                            row.update({metric: response for metric in METRICS})
                            rows.append(row)

        model_summary, _raw, effects, completeness = analyze_model_ablation(
            rows,
            bootstrap_samples=100,
            permutation_samples=100,
            analysis_seed=7,
        )

        hv_model = next(
            row for row in model_summary
            if row["model_id"] == "PR0_HT0_EC0" and row["metric"] == "hypervolume"
        )
        self.assertEqual(hv_model["analysis_unit"], "instance_mean")
        self.assertEqual(hv_model["n_units"], 2)
        expected = {
            "progressive_recovery": 2.0,
            "heterogeneous_vehicle_thresholds": 4.0,
            "edge_capacity_constraint": 6.0,
            "progressive_recovery:heterogeneous_vehicle_thresholds": 8.0,
            "progressive_recovery:edge_capacity_constraint": 0.0,
            "heterogeneous_vehicle_thresholds:edge_capacity_constraint": 0.0,
        }
        hv_effects = {
            row["term"]: row["mean"]
            for row in effects
            if row["metric"] == "hypervolume"
        }
        self.assertEqual(hv_effects, expected)
        self.assertEqual(len(completeness), 4)
        self.assertTrue(all(row["complete"] == 1 for row in completeness))

    def test_formal_factorial_analysis_rejects_incomplete_blocks(self):
        row = {
            "run_key": "S025:i1:s60000:PR0_HT0_EC0",
            "case_id": "S025",
            "source": "synthetic",
            "instance_seed": 1,
            "solver_seed": 60_000,
            "algorithm": "nsga2_alns",
            "model_id": "PR0_HT0_EC0",
            "progressive_recovery": 0,
            "heterogeneous_vehicle_thresholds": 0,
            "edge_capacity_constraint": 0,
            "max_evaluations": 100,
            "evaluations": 100,
        }
        row.update({metric: 0.0 for metric in METRICS})

        with self.assertRaisesRegex(ValueError, "incomplete or unpaired"):
            analyze_model_ablation([row])

    def test_shard_merge_recomputes_one_pooled_front_across_solver_repeats(self):
        budget = BenchmarkBudget(
            max_evaluations=2,
            pop_size=2,
            alns_iterations=0,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = []
            for repeat_start in (0, 1):
                shard = root / f"repeat_{repeat_start}"
                run_model_ablation(
                    suite="smoke",
                    cases=["S020"],
                    instance_seeds=[1],
                    solver_repeats=1,
                    solver_repeat_start=repeat_start,
                    output_dir=shard,
                    budget=budget,
                    bootstrap_samples=10,
                    permutation_samples=10,
                )
                inputs.append(shard / "model_ablation.csv")

            rows, pareto_rows, reference_rows = merge_model_ablation_shards(inputs)

            self.assertEqual(len(rows), 16)
            self.assertEqual({row["solver_seed"] for row in rows}, {"60000", "60001"})
            self.assertTrue(pareto_rows)
            self.assertTrue(reference_rows)
            self.assertEqual(
                len({row["pooled_ideal_F1"] for row in rows}),
                1,
            )
            self.assertEqual(
                len({row["pooled_reference_front_size"] for row in rows}),
                1,
            )


if __name__ == "__main__":
    unittest.main()
