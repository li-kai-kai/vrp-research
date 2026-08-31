import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import networkx as nx

from scripts.reproduce.dispatch import dispatch_relief
from scripts.reproduce.instance_generator import generate_random_instance
from scripts.reproduce.metrics import evaluate_solution
from scripts.reproduce.capacity_recovery import (
    CapacityNSGAConfig,
    _dominates,
    _dispatch_with_vehicle_types,
    _plot_pareto_front,
    _write_outputs,
    build_wenchuan_instance,
    solve_capacity_instance,
)
from scripts.reproduce.dynamic_interaction_experiments import (
    MECHANISMS,
    RepairEfficiencyUncertainty,
    _apply_stress,
    _sample_repair_efficiencies,
    _variant,
    run_mechanism,
)


class ReproductionFrameworkTest(unittest.TestCase):
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

    def test_deterministic_openloop_matches_rolling_without_new_information(self):
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
        self.assertAlmostEqual(
            results["progressive_rolling"]["cumulative_unmet_area"],
            results["progressive_openloop"]["cumulative_unmet_area"],
        )
        self.assertAlmostEqual(
            results["progressive_rolling"]["average_reachable_ratio"],
            results["progressive_openloop"]["average_reachable_ratio"],
        )

    def test_dynamic_state_snapshots_cover_every_period(self):
        instance = _apply_stress(
            build_wenchuan_instance(seed=1),
            2.0,
            2,
            capacity_scale=0.05,
        )
        snapshots = []
        mechanism = next(
            item for item in MECHANISMS
            if item.name == "progressive_rolling"
        )
        summary, rows = run_mechanism(
            instance,
            mechanism,
            40001,
            0.30,
            state_callback=snapshots.append,
        )

        self.assertEqual(len(rows), instance.base.periods)
        self.assertEqual(len(snapshots), instance.base.periods + 1)
        self.assertEqual([item["period"] for item in snapshots], list(range(10)))
        self.assertEqual(len(snapshots[-1]["road_progress"]), 16)
        self.assertEqual(len(snapshots[-1]["delivered_by_demand"]), 35)
        self.assertEqual(len(snapshots[-1]["crew_locations"]), 2)
        self.assertIn("period_delivery_by_demand", snapshots[-1])
        self.assertIn("shipments", snapshots[-1])
        self.assertIn("crew_transfers", snapshots[-1])
        self.assertAlmostEqual(
            snapshots[-1]["total_satisfaction"],
            summary["final_total_satisfaction"],
        )

    def test_crew_transfer_time_consumes_period_repair_budget(self):
        mechanism = next(
            item for item in MECHANISMS
            if item.name == "progressive_rolling"
        )
        snapshots = {}
        for scale in (0.0, 1.0):
            instance = _apply_stress(
                build_wenchuan_instance(seed=1),
                2.0,
                2,
                capacity_scale=0.05,
                crew_transfer_time_scale=scale,
                crew_min_access_progress=0.30,
            )
            captured = []
            run_mechanism(
                instance,
                mechanism,
                40001,
                0.30,
                state_callback=captured.append,
            )
            snapshots[scale] = captured

        transfer_minutes = sum(
            item["minutes"]
            for transfers in snapshots[1.0][1]["crew_transfers"].values()
            for item in transfers
        )
        self.assertGreater(transfer_minutes, 0.0)
        self.assertLess(
            sum(snapshots[1.0][1]["road_progress"].values()),
            sum(snapshots[0.0][1]["road_progress"].values()),
        )
        for snapshot in snapshots[1.0][1:]:
            before = snapshot["road_progress_before"]
            for transfers in snapshot["crew_transfers"].values():
                for transfer in transfers:
                    for u, v in zip(transfer["path"], transfer["path"][1:]):
                        damage_id = instance.base.graph[u][v].get("damage_id")
                        if damage_id is not None:
                            self.assertGreaterEqual(
                                before[damage_id],
                                instance.crew_min_access_progress - 1e-9,
                            )

    def test_revealed_repair_efficiency_can_change_rolling_decisions(self):
        instance = _apply_stress(
            build_wenchuan_instance(seed=1),
            2.0,
            2,
            capacity_scale=0.05,
        )
        uncertainty = RepairEfficiencyUncertainty(0.30)
        first = _sample_repair_efficiencies(instance.base, 40001, uncertainty)
        repeated = _sample_repair_efficiencies(instance.base, 40001, uncertainty)
        different = _sample_repair_efficiencies(instance.base, 40002, uncertainty)
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different)

        results = {
            mechanism.name: run_mechanism(
                instance,
                mechanism,
                40001,
                repair_efficiency_deviation=0.30,
            )[0]
            for mechanism in MECHANISMS
        }
        self.assertLess(
            results["progressive_rolling"]["cumulative_unmet_area"],
            results["progressive_openloop"]["cumulative_unmet_area"],
        )
        self.assertEqual(
            results["progressive_rolling"]["repair_efficiency_scenario_seed"],
            results["progressive_openloop"]["repair_efficiency_scenario_seed"],
        )

if __name__ == "__main__":
    unittest.main()
