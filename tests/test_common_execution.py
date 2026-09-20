"""P4 tests: planning-model subsets and the shared Full execution environment."""

from __future__ import annotations

import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.reproduce.benchmark_algorithms import BenchmarkBudget
from scripts.reproduce.capacity_recovery import (
    BINARY_RECOVERY_STAGES,
    CapacityIndividual,
    VehicleProfile,
    evaluate_capacity_solution,
    model_factor_variant,
)
from scripts.reproduce.run_model_ablation import (
    FULL_EXECUTION_FACTORS,
    MODEL_FACTORS_BY_ID,
    run_model_ablation,
)
from scripts.reproduce.solution_io import physical_instance_hash
from tests.test_model_contract import _make_instance


PLANNING_GROUP_IDS = ("PR1_HT1_EC1", "PR0_HT1_EC1", "PR1_HT0_EC1", "PR1_HT1_EC0")


def _variant(source, model_id):
    factors = MODEL_FACTORS_BY_ID[model_id]
    return model_factor_variant(
        source,
        progressive_recovery=factors.progressive_recovery,
        heterogeneous_vehicle_thresholds=factors.heterogeneous_vehicle_thresholds,
        edge_capacity_constraint=factors.edge_capacity_constraint,
    )


def _priority(instance):
    return [(s, d) for s in instance.base.suppliers for d in instance.base.demands]


class PhysicalScenarioSharingTest(unittest.TestCase):
    def test_planning_groups_and_execution_environment_share_one_scenario(self):
        source = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1, 2],
            supply_amounts={0: 90.0},
            demand_amounts={1: 70.0, 2: 70.0},
            edges=[(0, 1, 10.0, 1000.0), (0, 2, 12.0, 1000.0)],
            damaged=[(0, 1, 300.0)],
        )
        planning = [_variant(source, model_id) for model_id in PLANNING_GROUP_IDS]
        execution = _variant(source, "PR1_HT1_EC1")

        self.assertEqual(
            {physical_instance_hash(v) for v in planning},
            {physical_instance_hash(source)},
        )
        self.assertEqual(physical_instance_hash(execution), physical_instance_hash(source))
        # The planning assumptions differ even though the scenario does not.
        self.assertEqual(len({model_fingerprint_id(v) for v in planning}), 4)

    def test_no_ec_only_removes_throughput_accounting(self):
        """Throughput throttling disappears; passability and timing do not."""
        source = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 30.0},
            demand_amounts={1: 30.0},
            edges=[(0, 1, 10.0, 1000.0)],
            # 1000 * 8h * 0.0002 = 1.6 PCU per period: one trip at a time.
            capacity_scale=0.0002,
            vehicles=[
                VehicleProfile(
                    vehicle_type=1,
                    capacity_ton=10.0,
                    count=10,
                    occupied_od_pcu_h=0.0,
                    min_recovery_progress=0.0,
                    pcu_per_vehicle=1.0,
                )
            ],
        )
        with_ec = _variant(source, "PR1_HT1_EC1")
        without_ec = _variant(source, "PR1_HT1_EC0")
        decision = CapacityIndividual([], [], _priority(source))

        constrained_objectives, constrained = evaluate_capacity_solution(
            with_ec, decision.clone()
        )
        unconstrained_objectives, unconstrained = evaluate_capacity_solution(
            without_ec, decision.clone()
        )

        self.assertEqual(unconstrained["max_edge_utilization"], 0.0)
        self.assertGreater(constrained["max_edge_utilization"], 0.0)
        # Without throughput accounting the whole order moves in one period.
        self.assertGreater(unconstrained["max_period_delivered"], 10.0 + 1e-9)
        self.assertLessEqual(constrained["max_period_delivered"], 10.0 + 1e-9)
        # Throttling delays service, which shows up as a worse cumulative gap.
        self.assertGreater(constrained_objectives[0], unconstrained_objectives[0])
        # Disabling throughput accounting must not disable passability or the
        # within-period time condition.
        self.assertEqual(without_ec.vehicles, with_ec.vehicles)
        self.assertEqual(without_ec.recovery_stages, with_ec.recovery_stages)

    def test_binary_recovery_makes_vehicle_thresholds_inert(self):
        """Under PR0 the passability threshold cannot discriminate."""
        source = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 60.0},
            demand_amounts={1: 60.0},
            edges=[(0, 1, 10.0, 1000.0)],
            damaged=[(0, 1, 240.0)],
            recovery_stages=BINARY_RECOVERY_STAGES,
        )
        heterogeneous = _variant(source, "PR0_HT1_EC1")
        uniform = _variant(source, "PR0_HT0_EC1")
        self.assertNotEqual(
            [v.min_recovery_progress for v in heterogeneous.vehicles],
            [v.min_recovery_progress for v in uniform.vehicles],
        )
        decision = CapacityIndividual([0], [0], _priority(source))

        heterogeneous_objectives, heterogeneous_metrics = evaluate_capacity_solution(
            heterogeneous,
            decision.clone(),
        )
        uniform_objectives, uniform_metrics = evaluate_capacity_solution(
            uniform,
            decision.clone(),
        )

        self.assertEqual(heterogeneous_objectives, uniform_objectives)
        # Only the recorded factor flags may differ; every behavioural metric
        # must be identical when binary recovery makes the threshold inert.
        configuration_flags = {
            "progressive_recovery",
            "heterogeneous_vehicle_thresholds",
            "edge_capacity_constraint",
        }
        behavioural = {
            key: value
            for key, value in heterogeneous_metrics.items()
            if key not in configuration_flags
        }
        for key, value in behavioural.items():
            self.assertAlmostEqual(value, uniform_metrics[key], places=12, msg=key)

    def test_no_ht_keeps_load_pcu_and_counts(self):
        source = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 60.0},
            demand_amounts={1: 60.0},
            edges=[(0, 1, 10.0, 1000.0)],
        )
        heterogeneous = _variant(source, "PR1_HT1_EC1")
        uniform = _variant(source, "PR1_HT0_EC1")

        self.assertNotEqual(
            [v.min_recovery_progress for v in heterogeneous.vehicles],
            [v.min_recovery_progress for v in uniform.vehicles],
        )
        for left, right in zip(heterogeneous.vehicles, uniform.vehicles):
            self.assertEqual(left.capacity_ton, right.capacity_ton)
            self.assertEqual(left.count, right.count)
            self.assertEqual(left.pcu_per_vehicle, right.pcu_per_vehicle)
            self.assertEqual(left.speed_factor, right.speed_factor)


class FullExecutionReplayTest(unittest.TestCase):
    """A No-EC decision must collide with reality in the Full environment."""

    def _constrained_source(self):
        return _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 30.0},
            demand_amounts={1: 30.0},
            edges=[(0, 1, 10.0, 1000.0)],
            # 1000 * 8h * 0.0002 = 1.6 PCU per period: one trip at a time.
            capacity_scale=0.0002,
            vehicles=[
                VehicleProfile(
                    vehicle_type=1,
                    capacity_ton=10.0,
                    count=10,
                    occupied_od_pcu_h=0.0,
                    min_recovery_progress=0.0,
                    pcu_per_vehicle=1.0,
                )
            ],
        )

    def test_no_ec_decision_is_penalized_in_the_full_environment(self):
        source = self._constrained_source()
        planned_under = _variant(source, "PR1_HT1_EC0")
        full_execution = _variant(source, "PR1_HT1_EC1")
        decision = CapacityIndividual([], [], _priority(source))

        planning_objectives, _planning_metrics = evaluate_capacity_solution(
            planned_under,
            decision.clone(),
        )
        replay_objectives, replay_metrics = evaluate_capacity_solution(
            full_execution,
            decision.clone(),
        )

        # The road throughput that the planning model ignored now binds.
        self.assertGreater(replay_objectives[0], planning_objectives[0])
        self.assertGreater(replay_metrics["capacity_blocked_tons"], 0.0)
        self.assertLessEqual(replay_metrics["max_edge_utilization"], 1.0 + 1e-9)

    def test_full_planning_replays_identically_in_the_full_environment(self):
        source = self._constrained_source()
        full = _variant(source, "PR1_HT1_EC1")
        decision = CapacityIndividual([], [], _priority(source))

        planning_objectives, _metrics = evaluate_capacity_solution(full, decision.clone())
        replay_objectives, _metrics = evaluate_capacity_solution(full, decision.clone())

        self.assertEqual(tuple(planning_objectives), tuple(replay_objectives))


class AblationSubsetTest(unittest.TestCase):
    def test_subset_reports_no_significance_tables(self):
        budget = BenchmarkBudget(max_evaluations=8, pop_size=4, alns_iterations=1)
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "subset"
            rows = run_model_ablation(
                suite="smoke",
                cases=["S020"],
                instance_seeds=[1],
                solver_repeats=2,
                output_dir=output_dir,
                budget=budget,
                model_version="v2",
                algorithm="nsga2",
                model_ids=list(PLANNING_GROUP_IDS),
            )

            self.assertEqual(len(rows), 8)
            self.assertEqual(
                {row["model_id"] for row in rows},
                set(PLANNING_GROUP_IDS),
            )
            # One shared physical scenario across every planning group.
            self.assertEqual({row["physical_instance_hash"] for row in rows}, {
                rows[0]["physical_instance_hash"]
            })

            with (output_dir / "factor_effects.csv").open(newline="", encoding="utf-8") as handle:
                effects = list(csv.DictReader(handle))
            self.assertEqual(len(effects), 1)
            self.assertEqual(effects[0]["formal_analysis"], "not_applicable")
            self.assertIn("subset", effects[0]["reason"])

            # The real per-run descriptive table is still produced.
            with (output_dir / "model_ablation.csv").open(newline="", encoding="utf-8") as handle:
                ablation = list(csv.DictReader(handle))
            self.assertEqual(len(ablation), 8)
            for column in ("F1", "F2", "F3", "hypervolume", "igd", "model_id"):
                self.assertIn(column, ablation[0])
            # Every run reused the shared execution environment snapshot.
            self.assertTrue((output_dir / "executions").is_dir())
            self.assertEqual(len(list((output_dir / "executions").glob("*.json"))), 1)

    def test_full_design_still_computes_the_formal_analysis(self):
        budget = BenchmarkBudget(max_evaluations=8, pop_size=4, alns_iterations=1)
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "full"
            run_model_ablation(
                suite="smoke",
                cases=["S020"],
                instance_seeds=[1],
                solver_repeats=1,
                output_dir=output_dir,
                budget=budget,
                model_version="v2",
                algorithm="nsga2_alns",
            )
            with (output_dir / "factor_effects.csv").open(newline="", encoding="utf-8") as handle:
                effects = list(csv.DictReader(handle))
            self.assertNotEqual(effects[0].get("formal_analysis"), "not_applicable")


def model_fingerprint_id(instance) -> str:
    from scripts.reproduce.solution_io import model_fingerprint

    return model_fingerprint(instance)


if __name__ == "__main__":
    unittest.main()
