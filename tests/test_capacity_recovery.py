import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.reproduce.capacity_recovery import CapacityNSGAConfig, _dominates, _dispatch_with_vehicle_types, _plot_pareto_front, _write_outputs, build_wenchuan_instance, model_factor_variant, solve_capacity_instance
from scripts.reproduce.dynamic_interaction_experiments import _variant


class CapacityRecoveryTest(unittest.TestCase):
    def test_capacity_solver_exports_complete_non_dominated_archive(self):
        config = CapacityNSGAConfig(
            pop_size=6,
            generations=2,
            crossover_probability=0.9,
            mutation_probability=0.2,
            alns_probability=0.0,
            alns_iterations=0,
        )
        result = solve_capacity_instance(
            build_wenchuan_instance(seed=1),
            config,
            seed=30001,
            scenario="wenchuan",
        )

        self.assertGreater(len(result.pareto_front), 0)
        self.assertEqual(
            len({solution.decision_hash for solution in result.pareto_front}),
            len(result.pareto_front),
        )
        for left_idx, left in enumerate(result.pareto_front):
            for right_idx, right in enumerate(result.pareto_front):
                if left_idx != right_idx:
                    self.assertFalse(_dominates(left.objectives, right.objectives))

        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            _write_outputs([result], output_dir, config)
            _plot_pareto_front([result], output_dir / "pareto_front.png")
            for filename in (
                "runs.csv",
                "solutions.json",
                "convergence.csv",
                "pareto_front_runs.csv",
                "pareto_front.csv",
                "pareto_solutions.json",
                "experiment_manifest.json",
                "pareto_front.png",
            ):
                self.assertTrue((output_dir / filename).is_file(), filename)

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

    def test_model_factors_are_orthogonal_and_do_not_mutate_source(self):
        source = build_wenchuan_instance(seed=1)
        original_thresholds = [
            vehicle.min_recovery_progress
            for vehicle in source.vehicles
        ]
        variants = [
            model_factor_variant(
                source,
                progressive_recovery=progressive,
                heterogeneous_vehicle_thresholds=heterogeneous,
                edge_capacity_constraint=capacity,
            )
            for progressive in (False, True)
            for heterogeneous in (False, True)
            for capacity in (False, True)
        ]

        self.assertEqual(
            {
                (
                    item.progressive_recovery,
                    item.heterogeneous_vehicle_thresholds,
                    item.edge_capacity_constraint,
                )
                for item in variants
            },
            {
                (progressive, heterogeneous, capacity)
                for progressive in (False, True)
                for heterogeneous in (False, True)
                for capacity in (False, True)
            },
        )
        for item in variants:
            ratios = [stage.capacity_ratio for stage in item.recovery_stages]
            if item.progressive_recovery:
                self.assertEqual(ratios, [0.0, 0.3, 0.6, 0.8, 1.0])
            else:
                self.assertEqual(ratios, [0.0, 1.0])
            thresholds = {
                vehicle.min_recovery_progress
                for vehicle in item.vehicles
            }
            if item.heterogeneous_vehicle_thresholds:
                self.assertEqual(thresholds, set(original_thresholds))
            else:
                self.assertEqual(thresholds, {0.30})
        self.assertEqual(
            [vehicle.min_recovery_progress for vehicle in source.vehicles],
            original_thresholds,
        )
        self.assertEqual(len(source.recovery_stages), 5)

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
        self.assertAlmostEqual(
            sum(item["amount"] for item in result["allocations"]),
            sum(result["delivered"].values()),
        )
        for allocation in result["allocations"]:
            self.assertEqual(allocation["path"][0], allocation["supplier"])
            self.assertEqual(allocation["path"][-1], allocation["demand"])
        for vehicle in instance.vehicles:
            self.assertLessEqual(
                result["vehicle_trips"][vehicle.vehicle_type],
                vehicle.count,
            )

    def test_edge_capacity_factor_can_disable_only_throughput_accounting(self):
        source = build_wenchuan_instance(seed=1)
        source.capacity_scale = 0.001
        constrained = model_factor_variant(
            source,
            progressive_recovery=True,
            heterogeneous_vehicle_thresholds=True,
            edge_capacity_constraint=True,
        )
        unlimited = model_factor_variant(
            source,
            progressive_recovery=True,
            heterogeneous_vehicle_thresholds=True,
            edge_capacity_constraint=False,
        )
        progress = {edge_id: 1.0 for edge_id in source.base.damaged_edges}
        priority = [
            (supplier, demand)
            for supplier in source.base.suppliers
            for demand in source.base.demands
        ]

        constrained_result = _dispatch_with_vehicle_types(
            constrained,
            priority,
            progress,
            dict(source.base.supply_amounts),
            dict(source.base.demand_amounts),
        )
        unlimited_result = _dispatch_with_vehicle_types(
            unlimited,
            priority,
            progress,
            dict(source.base.supply_amounts),
            dict(source.base.demand_amounts),
        )

        self.assertGreater(constrained_result["capacity_blocked_tons"], 0.0)
        self.assertEqual(unlimited_result["capacity_blocked_tons"], 0.0)
        self.assertEqual(unlimited_result["max_edge_utilization"], 0.0)
        self.assertGreaterEqual(
            sum(unlimited_result["delivered"].values()),
            sum(constrained_result["delivered"].values()),
        )



if __name__ == "__main__":
    unittest.main()
