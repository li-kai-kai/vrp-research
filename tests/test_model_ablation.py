import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.reproduce.benchmark_algorithms import BenchmarkBudget
from scripts.reproduce.run_model_ablation import MODEL_FACTOR_COMBINATIONS, run_model_ablation
from scripts.reproduce.model_ablation_analysis import METRICS, analyze_model_ablation, merge_model_ablation_shards


class ModelAblationTest(unittest.TestCase):
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
