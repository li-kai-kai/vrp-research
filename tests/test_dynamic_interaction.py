import unittest
from scripts.reproduce.capacity_recovery import build_wenchuan_instance
from scripts.reproduce.dynamic_interaction_experiments import MECHANISMS, RepairEfficiencyUncertainty, _apply_stress, _sample_repair_efficiencies, run_mechanism


class DynamicInteractionTest(unittest.TestCase):
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
