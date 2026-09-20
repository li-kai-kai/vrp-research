"""Persistence, resume and replay tests for the shared run store."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.reproduce.benchmark_algorithms import (
    BenchmarkBudget,
    solve_benchmark_algorithm,
)
from scripts.reproduce.benchmark_suite import benchmark_specs, build_benchmark_instance
from scripts.reproduce.capacity_recovery import (
    evaluate_capacity_solution,
    model_factor_variant,
)
from scripts.reproduce.solution_io import (
    RunStore,
    SolutionIOError,
    build_run_record,
    decision_from_json,
    decision_to_json,
    make_run_key,
    model_fingerprint,
    physical_instance_hash,
)


def _spec():
    return benchmark_specs("smoke")[0]


def _instance(model_version: str = "v2", instance_seed: int = 101):
    return build_benchmark_instance(
        _spec(),
        instance_seed=instance_seed,
        model_version=model_version,
    )


def _solve(instance, *, seed: int = 60_001, algorithm: str = "nsga2"):
    budget = BenchmarkBudget(max_evaluations=12, pop_size=4, alns_iterations=1)
    return solve_benchmark_algorithm(algorithm, instance, budget, seed=seed), budget


def _record(store: RunStore, instance, *, run_key: str = "S020:i101:nsga2:s60001:r0:abc123"):
    instance_file = store.save_instance(instance)
    result, budget = _solve(instance)
    return build_run_record(
        run_key=run_key,
        case_id=_spec().case_id,
        suite="smoke",
        source=_spec().source,
        size_group=_spec().size_group,
        num_nodes=_spec().num_nodes,
        instance_seed=101,
        solver_seed=60_001,
        solver_repeat=0,
        algorithm="nsga2",
        instance=instance,
        front=result.front,
        representative=result.representative,
        evaluations=result.evaluations,
        runtime_seconds=result.runtime_seconds,
        convergence=result.convergence,
        budget={"max_evaluations": budget.max_evaluations, "pop_size": budget.pop_size},
        termination_reason=result.termination_reason,
        source_fingerprint_value="test-source-fingerprint",
        extra={"instance_file": instance_file},
    )


class SolutionIOTest(unittest.TestCase):
    def test_instance_snapshot_round_trip_reproduces_fingerprints(self):
        instance = _instance()
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            instance_file = store.save_instance(instance)
            rebuilt = store.load_instance(instance_file)

        self.assertEqual(model_fingerprint(rebuilt), model_fingerprint(instance))
        self.assertEqual(
            physical_instance_hash(rebuilt),
            physical_instance_hash(instance),
        )
        self.assertEqual(rebuilt.evaluation, instance.evaluation)
        self.assertEqual(
            [v.min_recovery_progress for v in rebuilt.vehicles],
            [v.min_recovery_progress for v in instance.vehicles],
        )
        self.assertEqual(
            sum(v.count for v in rebuilt.vehicles),
            sum(v.count for v in instance.vehicles),
        )

    def test_saved_run_replays_to_identical_objectives(self):
        instance = _instance()
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            record = _record(store, instance)
            store.save_run(record)
            loaded = store.load_run(record["run_key"])
            rebuilt_instance = store.load_instance(record["instance_file"])

            for solution in loaded["pareto_front"]:
                # Rebuild a clean individual: no cached objectives are reused.
                decision = decision_from_json(solution["decision"], rebuilt_instance)
                self.assertIsNone(decision.objectives)
                objectives, _metrics = evaluate_capacity_solution(
                    rebuilt_instance,
                    decision,
                )
                for stored, replayed in zip(solution["objectives"], objectives):
                    self.assertAlmostEqual(stored, replayed, places=12)

    def test_repeated_evaluation_is_stateless(self):
        instance = _instance()
        decision = _record_source_decision(instance)

        first = evaluate_capacity_solution(instance, decision.clone())[0]
        second = evaluate_capacity_solution(instance, decision.clone())[0]
        third = evaluate_capacity_solution(instance, decision.clone())[0]

        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def test_physical_hash_is_shared_across_model_factors(self):
        source = _instance()
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
            {physical_instance_hash(variant) for variant in variants},
            {physical_instance_hash(source)},
        )
        # The planning assumptions themselves must differ.
        self.assertGreater(len({model_fingerprint(v) for v in variants}), 1)
        self.assertNotIn(model_fingerprint(source), {model_fingerprint(v) for v in variants if not v.progressive_recovery})

    def test_evaluation_profile_changes_the_model_fingerprint(self):
        legacy_variant = model_factor_variant(
            _instance(model_version="legacy"),
            progressive_recovery=True,
            heterogeneous_vehicle_thresholds=True,
            edge_capacity_constraint=True,
        )
        self.assertNotEqual(
            model_fingerprint(legacy_variant),
            model_fingerprint(_instance(model_version="v2")),
        )

    def test_only_matching_complete_runs_are_skipped(self):
        instance = _instance()
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            record = _record(store, instance)
            store.save_run(record)
            self.assertTrue(store.has_complete_run(record["run_key"]))

            def key(**overrides):
                base = {
                    "case_id": "S020",
                    "instance_seed": 101,
                    "algorithm": "nsga2",
                    "solver_seed": 60_001,
                    "solver_repeat": 0,
                    "budget": {"max_evaluations": 12, "pop_size": 4},
                    "model_fingerprint_value": "fp",
                    "source_fingerprint": "src",
                }
                base.update(overrides)
                return make_run_key(**base)

            # The same configuration rebuilds the same key, so a resumed run
            # cannot create a duplicate record.
            self.assertEqual(key(), key())

            # A different budget is a different run and must not be skipped.
            different_budget = key(budget={"max_evaluations": 999, "pop_size": 4})
            self.assertNotEqual(different_budget, key())
            self.assertFalse(store.has_complete_run(different_budget))

            # Neither must a different planning model nor a different code
            # revision be mistaken for the stored run.
            self.assertFalse(store.has_complete_run(key(model_fingerprint_value="other")))
            self.assertFalse(store.has_complete_run(key(source_fingerprint="other")))

    def test_mixing_code_revisions_in_one_directory_is_refused(self):
        instance = _instance()
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            store.save_run(_record(store, instance))

            # The same revision is fine; a different one is refused outright
            # rather than silently combined with the stored numbers.
            store.check_source_consistency("test-source-fingerprint")
            with self.assertRaises(SolutionIOError):
                store.check_source_consistency("some-other-revision")

            # A partial file from an interrupted write is not a revision clash.
            partial = store.runs_dir / "interrupted.json"
            partial.write_text('{"run_key": "interrupted"', encoding="utf-8")
            store.check_source_consistency("test-source-fingerprint")

    def test_operator_contributions_are_reported(self):
        instance = _instance()
        result, _budget = _solve(instance, algorithm="nsga2_ls")
        operators = {
            key: value
            for key, value in result.diagnostics.items()
            if key.startswith("operator.")
        }
        self.assertGreater(result.diagnostics["local_search_evaluations"], 0.0)
        self.assertEqual(sum(operators.values()), result.diagnostics["local_search_evaluations"])

    def test_completed_runs_survive_an_interrupted_write(self):
        instance = _instance()
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            finished = _record(store, instance, run_key="S020:i101:nsga2:s60001:r0:first")
            store.save_run(finished)

            # Simulate a process that died mid-write: a partial file appears
            # under the next run key and is never atomically replaced.
            interrupted_key = "S020:i101:nsga2:s60002:r1:second"
            partial = store.run_path(interrupted_key)
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_text('{"run_key": "S020:i101:nsga2:s60002:r1:second", "compl', encoding="utf-8")

            self.assertTrue(store.has_complete_run(finished["run_key"]))
            self.assertFalse(store.has_complete_run(interrupted_key))
            self.assertEqual(store.load_run(finished["run_key"])["run_key"], finished["run_key"])
            with self.assertRaises(SolutionIOError):
                store.load_run(interrupted_key)

            # The finished run is still replayable on its own.
            rebuilt = store.load_instance(finished["instance_file"])
            decision = decision_from_json(
                finished["pareto_front"][0]["decision"],
                rebuilt,
            )
            objectives, _metrics = evaluate_capacity_solution(rebuilt, decision)
            for stored, replayed in zip(finished["pareto_front"][0]["objectives"], objectives):
                self.assertAlmostEqual(stored, replayed, places=12)

    def test_corrupt_artifacts_fail_loudly(self):
        instance = _instance()
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            instance_file = store.save_instance(instance)
            record = _record(store, instance)
            record["instance_file"] = instance_file
            path = store.save_run(record)
            rebuilt = store.load_instance(instance_file)

            # 1. Tampered payload breaks the record checksum.
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["evaluations"] = payload["evaluations"] + 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(SolutionIOError):
                store.load_run(record["run_key"])

            # 2. Truncated snapshot.
            snapshot_path = store.instance_path(instance_file)
            snapshot_path.write_text('{"format": "capacity_recovery_instance"', encoding="utf-8")
            with self.assertRaises(SolutionIOError):
                store.load_instance(instance_file)

        # 3. Invalid decisions against a valid instance.
        valid = decision_to_json(_record_source_decision(instance))
        for mutation, message in (
            (lambda payload: payload.update(repair_order=[9999] * len(payload["repair_order"])), "unknown damage"),
            (lambda payload: payload.update(team_assignment=[99] * len(payload["team_assignment"])), "team out of range"),
            (
                lambda payload: payload.update(
                    dispatch_priority=[[9999, payload["dispatch_priority"][0][1]]]
                    + payload["dispatch_priority"][1:]
                ),
                "unknown supplier",
            ),
            (lambda payload: payload.update(team_assignment=payload["team_assignment"] + [0]), "length mismatch"),
        ):
            payload = json.loads(json.dumps(valid))
            mutation(payload)
            with self.assertRaises(SolutionIOError, msg=message):
                decision_from_json(payload, instance)

        # A repeated damage id is rejected rather than silently de-duplicated.
        payload = json.loads(json.dumps(valid))
        payload["repair_order"][1] = payload["repair_order"][0]
        with self.assertRaises(SolutionIOError):
            decision_from_json(payload, instance)

    def test_infinite_display_fields_are_written_as_null(self):
        instance = _instance()
        with TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            record = _record(store, instance)
            store.save_run(record)
            text = store.run_path(record["run_key"]).read_text(encoding="utf-8")

        self.assertNotIn("Infinity", text)
        self.assertNotIn("NaN", text)
        # Standard JSON: the file parses without a permissive decoder.
        json.loads(text)


def _record_source_decision(instance):
    budget = BenchmarkBudget(max_evaluations=8, pop_size=4, alns_iterations=1)
    result = solve_benchmark_algorithm("nsga2", instance, budget, seed=4_242)
    return result.front[0]


if __name__ == "__main__":
    unittest.main()
