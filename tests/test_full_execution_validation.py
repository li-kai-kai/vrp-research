"""R3: --execution-model full must verify it really got a Full environment."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.reproduce.benchmark_algorithms import BenchmarkBudget
from dataclasses import replace

from scripts.reproduce.capacity_recovery import (
    BINARY_RECOVERY_STAGES,
    VehicleProfile,
    full_execution_problems,
    is_full_execution_environment,
    model_factor_variant,
)
from scripts.reproduce.run_model_ablation import run_model_ablation
from scripts.reproduce.solution_io import (
    RunStore,
    SolutionIOError,
    physical_instance_hash,
)
from tests.test_model_contract import _make_instance


def _source(model_version="v2", **overrides):
    return _make_instance(
        model_version=model_version,
        suppliers=[0],
        demands=[1],
        supply_amounts={0: 30.0},
        demand_amounts={1: 30.0},
        edges=[(0, 1, 10.0, 1000.0)],
        **overrides,
    )


class FullEnvironmentPredicateTest(unittest.TestCase):
    def test_a_v2_full_instance_has_no_problems(self):
        self.assertEqual(full_execution_problems(_source()), [])
        self.assertTrue(is_full_execution_environment(_source()))

    def test_each_reduced_model_is_named(self):
        cases = {
            "legacy": (_source(model_version="legacy"), "model_version"),
            "binary": (
                model_factor_variant(
                    _source(),
                    progressive_recovery=False,
                    heterogeneous_vehicle_thresholds=True,
                    edge_capacity_constraint=True,
                ),
                "progressive recovery",
            ),
            "uniform-thresholds": (
                model_factor_variant(
                    _source(),
                    progressive_recovery=True,
                    heterogeneous_vehicle_thresholds=False,
                    edge_capacity_constraint=True,
                ),
                "heterogeneous vehicle thresholds",
            ),
            "no-edge-capacity": (
                model_factor_variant(
                    _source(),
                    progressive_recovery=True,
                    heterogeneous_vehicle_thresholds=True,
                    edge_capacity_constraint=False,
                ),
                "edge-capacity",
            ),
        }
        for label, (instance, expected_fragment) in cases.items():
            problems = full_execution_problems(instance)
            self.assertTrue(problems, f"{label} should not be Full")
            self.assertTrue(
                any(expected_fragment in problem for problem in problems),
                f"{label}: {problems}",
            )

    def test_unsupported_crew_settings_are_named(self):
        problems = full_execution_problems(_source(crew_transfer_time_scale=0.5))
        self.assertTrue(any("crew_transfer_time_scale" in problem for problem in problems))


class ExecutionSnapshotTest(unittest.TestCase):
    def test_a_reduced_environment_cannot_be_loaded_as_full(self):
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            legacy = _source(model_version="legacy")
            physical = physical_instance_hash(legacy)
            store.save_execution_instance(legacy)

            # It is stored, and readable when Full is explicitly not required.
            stored = store.load_execution_instance(physical, require_full=False)
            self.assertEqual(stored.evaluation.model_version, "legacy")

            # But the Full entry point refuses it rather than mislabelling it.
            with self.assertRaises(SolutionIOError) as caught:
                store.load_execution_instance(physical)
            message = str(caught.exception)
            self.assertIn("not the agreed Full environment", message)
            self.assertIn("model_version", message)

    def test_a_full_environment_loads(self):
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            instance = _source()
            store.save_execution_instance(instance)
            loaded = store.load_execution_instance(physical_instance_hash(instance))
            self.assertTrue(is_full_execution_environment(loaded))

    def test_one_physical_scenario_keeps_one_execution_model(self):
        """A different model under the same physical hash must not overwrite."""
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            full = _source()
            reduced = model_factor_variant(
                _source(),
                progressive_recovery=False,
                heterogeneous_vehicle_thresholds=True,
                edge_capacity_constraint=True,
            )
            self.assertEqual(
                physical_instance_hash(full), physical_instance_hash(reduced)
            )
            store.save_execution_instance(full)

            with self.assertRaises(SolutionIOError) as caught:
                store.save_execution_instance(reduced)
            self.assertIn("different execution environment", str(caught.exception))

            # The stored Full snapshot is untouched.
            loaded = store.load_execution_instance(physical_instance_hash(full))
            self.assertTrue(loaded.progressive_recovery)

    def test_boolean_labels_alone_do_not_make_an_environment_full(self):
        """A snapshot claiming Full is re-verified against its own factors.

        The stored verdict is metadata, so it can be flipped without breaking
        the integrity check. The factors themselves must still fail the check.
        """
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            reduced = model_factor_variant(
                _source(),
                progressive_recovery=False,
                heterogeneous_vehicle_thresholds=True,
                edge_capacity_constraint=True,
            )
            physical = physical_instance_hash(reduced)
            store.save_execution_instance(reduced)

            path = store.execution_instance_path(physical)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(payload["is_full_execution"])
            # Flip the recorded verdict, leaving the instance untouched.
            payload["is_full_execution"] = True
            payload["full_execution_problems"] = []
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(SolutionIOError) as caught:
                store.load_execution_instance(physical)
            self.assertIn("progressive recovery", str(caught.exception))

    def test_editing_the_instance_breaks_the_snapshot_integrity_check(self):
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            instance = _source()
            physical = physical_instance_hash(instance)
            store.save_execution_instance(instance)

            path = store.execution_instance_path(physical)
            payload = json.loads(path.read_text(encoding="utf-8"))
            original = payload["model"]["capacity_scale"]
            payload["model"]["capacity_scale"] = original * 2.0 + 1.0
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(SolutionIOError) as caught:
                store.load_execution_instance(physical)
            self.assertIn("integrity check", str(caught.exception))


class FullProfileConsistencyTest(unittest.TestCase):
    """The declared Full curve and thresholds are a baseline, not a label."""

    def test_binary_curve_is_rejected_even_with_the_flag_on(self):
        full = _source()
        invalid = replace(full, recovery_stages=list(BINARY_RECOVERY_STAGES))
        self.assertTrue(invalid.progressive_recovery)
        problems = full_execution_problems(invalid)
        self.assertTrue(any("binary" in problem for problem in problems), problems)

    def test_thresholds_must_match_the_declared_profile(self):
        full = _source()
        invalid = replace(
            full,
            vehicles=[replace(v, min_recovery_progress=0.30) for v in full.vehicles],
        )
        self.assertTrue(invalid.heterogeneous_vehicle_thresholds)
        problems = full_execution_problems(invalid)
        self.assertTrue(any("threshold" in problem for problem in problems), problems)

    def test_profile_comparison_does_not_require_matching_vehicle_types(self):
        """A scenario is free to carry a different set of vehicle types."""
        full = _source()
        other = replace(
            full,
            vehicles=[
                VehicleProfile(
                    vehicle_type=99,
                    capacity_ton=1.0,
                    count=1,
                    occupied_od_pcu_h=0.0,
                    min_recovery_progress=0.42,
                    pcu_per_vehicle=1.0,
                )
            ],
        )
        # Type 99 is absent from the declared profile, so it cannot be compared
        # and must not be reported as a mismatch on its own.
        problems = [
            problem
            for problem in full_execution_problems(other)
            if "threshold" in problem
        ]
        self.assertEqual(problems, [])

    def test_reenabling_progressive_restores_the_declared_curve(self):
        """Re-labelling a reduced instance must not keep reduced data."""
        full = _source()
        reduced = model_factor_variant(
            full,
            progressive_recovery=False,
            heterogeneous_vehicle_thresholds=True,
            edge_capacity_constraint=True,
        )
        self.assertEqual(
            [s.capacity_ratio for s in reduced.recovery_stages], [0.0, 1.0]
        )

        restored = model_factor_variant(
            reduced,
            progressive_recovery=True,
            heterogeneous_vehicle_thresholds=True,
            edge_capacity_constraint=True,
        )
        self.assertEqual(
            [s.capacity_ratio for s in restored.recovery_stages],
            [s.capacity_ratio for s in full.recovery_stages],
        )
        self.assertEqual(full_execution_problems(restored), [])
        self.assertEqual(
            len(restored.recovery_stages), len(full.recovery_stages)
        )

    def test_reenabling_heterogeneous_restores_the_declared_thresholds(self):
        full = _source()
        declared = {t: v for t, v in full.full_profile.vehicle_thresholds}

        reduced = model_factor_variant(
            full,
            progressive_recovery=True,
            heterogeneous_vehicle_thresholds=False,
            edge_capacity_constraint=True,
        )
        self.assertTrue(
            all(v.min_recovery_progress == 0.30 for v in reduced.vehicles)
        )

        restored = model_factor_variant(
            reduced,
            progressive_recovery=True,
            heterogeneous_vehicle_thresholds=True,
            edge_capacity_constraint=True,
        )
        for vehicle in restored.vehicles:
            self.assertEqual(
                vehicle.min_recovery_progress, declared[vehicle.vehicle_type]
            )
        self.assertEqual(full_execution_problems(restored), [])

    def test_binary_source_without_a_profile_cannot_be_relabelled(self):
        raw = _source()
        raw.full_profile = None
        raw.recovery_stages = list(BINARY_RECOVERY_STAGES)
        with self.assertRaises(ValueError) as caught:
            model_factor_variant(
                raw,
                progressive_recovery=True,
                heterogeneous_vehicle_thresholds=True,
                edge_capacity_constraint=True,
            )
        self.assertIn("binary recovery curve", str(caught.exception))

    def test_in_memory_invalid_config_is_rejected_across_save_and_load(self):
        """Built in memory, saved, then loaded: the store must not bless it."""
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            full = _source()
            # Self-contradictory in memory: the flag says progressive, the data
            # is binary. The saved file hashes consistently either way.
            invalid = replace(
                full,
                recovery_stages=list(BINARY_RECOVERY_STAGES),
                full_profile=None,
            )
            physical = physical_instance_hash(invalid)
            store.save_execution_instance(invalid)

            payload = json.loads(
                store.execution_instance_path(physical).read_text(encoding="utf-8")
            )
            self.assertFalse(payload["is_full_execution"])
            self.assertTrue(
                any("binary" in problem for problem in payload["full_execution_problems"])
            )
            with self.assertRaises(SolutionIOError) as caught:
                store.load_execution_instance(physical)
            self.assertIn("binary", str(caught.exception))

    def test_profile_round_trips_through_the_snapshot(self):
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            instance = _source()
            fingerprint = store.save_instance(instance)
            rebuilt = store.load_instance(fingerprint)
            self.assertIsNotNone(rebuilt.full_profile)
            self.assertEqual(
                rebuilt.full_profile.fingerprint(),
                instance.full_profile.fingerprint(),
            )
            # And the restored profile still validates a variant correctly.
            restored = model_factor_variant(
                rebuilt,
                progressive_recovery=True,
                heterogeneous_vehicle_thresholds=True,
                edge_capacity_constraint=True,
            )
            self.assertEqual(full_execution_problems(restored), [])


class AblationExecutionEnvironmentTest(unittest.TestCase):
    def test_v2_ablation_stores_a_loadable_full_environment(self):
        budget = BenchmarkBudget(max_evaluations=8, pop_size=4, alns_iterations=1)
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "abl"
            rows = run_model_ablation(
                suite="smoke",
                cases=["S020"],
                instance_seeds=[1],
                solver_repeats=1,
                output_dir=output_dir,
                budget=budget,
                model_version="v2",
                algorithm="nsga2",
                model_ids=["PR1_HT1_EC1", "PR1_HT1_EC0", "PR0_HT1_EC1"],
            )
            store = RunStore(output_dir)
            records = store.load_runs_for_experiment()
            planning_instance = store.load_instance(records[0]["instance_file"])
            physical = physical_instance_hash(planning_instance)

            environment = store.load_execution_instance(physical)
            self.assertTrue(is_full_execution_environment(environment))
            # The reduced planning variants share the physical hash but are not
            # what the Full replay runs against.
            reduced = model_factor_variant(
                planning_instance,
                progressive_recovery=True,
                heterogeneous_vehicle_thresholds=False,
                edge_capacity_constraint=True,
            )
            self.assertEqual(physical, physical_instance_hash(reduced))
            self.assertFalse(is_full_execution_environment(reduced))

    def test_every_recorded_run_can_rebuild_its_planning_instance(self):
        """A run that references a snapshot must have written it.

        Both replay modes read the instance a record points at; a record whose
        snapshot was never written fails later and far from its cause.
        """
        budget = BenchmarkBudget(max_evaluations=8, pop_size=4, alns_iterations=1)
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "abl"
            run_model_ablation(
                suite="smoke",
                cases=["S020"],
                instance_seeds=[1],
                solver_repeats=1,
                output_dir=output_dir,
                budget=budget,
                model_version="v2",
                algorithm="nsga2",
                model_ids=["PR1_HT1_EC1", "PR1_HT1_EC0", "PR0_HT1_EC1"],
            )
            store = RunStore(output_dir)
            for record in store.load_runs_for_experiment():
                rebuilt = store.load_instance(record["instance_file"])
                self.assertEqual(
                    physical_instance_hash(rebuilt), record["physical_instance_hash"]
                )

    def test_legacy_ablation_stores_an_environment_full_cannot_use(self):
        budget = BenchmarkBudget(max_evaluations=8, pop_size=4, alns_iterations=1)
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "abl"
            run_model_ablation(
                suite="smoke",
                cases=["S020"],
                instance_seeds=[1],
                solver_repeats=1,
                output_dir=output_dir,
                budget=budget,
                model_version="legacy",
                algorithm="nsga2",
                model_ids=["PR1_HT1_EC1", "PR1_HT1_EC0"],
            )
            store = RunStore(output_dir)
            records = store.load_runs_for_experiment()
            physical = physical_instance_hash(
                store.load_instance(records[0]["instance_file"])
            )
            with self.assertRaises(SolutionIOError) as caught:
                store.load_execution_instance(physical)
            self.assertIn("model_version", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
