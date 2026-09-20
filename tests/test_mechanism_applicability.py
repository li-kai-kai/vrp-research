"""Mechanism-applicability diagnostic: correctness of the diagnostic itself."""

from __future__ import annotations

import csv
import json
import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import networkx as nx

from scripts.reproduce.benchmark_algorithms import BenchmarkBudget, solve_benchmark_algorithm
from scripts.reproduce.benchmark_suite import benchmark_specs, build_benchmark_instance
from scripts.reproduce.capacity_recovery import (
    CapacityIndividual,
    evaluate_capacity_solution_detailed,
    model_factor_variant,
)
from scripts.reproduce.mechanism_applicability import (
    ALLOCATION_AMOUNT_RESOLUTION,
    PeriodSnapshot,
    allocation_change_flags,
    allocation_multiset,
    bottleneck_classification,
    bridge_diagnostics,
    corridor_stress_instance,
    fixed_decisions,
    mechanism_report,
    objective_changed,
    period_trace,
    require_corridor_scenario,
    scale_capacity,
    scale_road_capacity,
    scale_supply,
    stress_topology_instance,
)
from scripts.reproduce.mechanism_zone_search import (
    ZONE_SCALE_BOUNDS,
    ZONE_TARGETS,
    _probe_utilization,
    calibrate_zones,
)
from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.solution_io import decision_from_json, decision_hash, decision_to_json


def _spec():
    return {spec.case_id: spec for spec in benchmark_specs("benchmark")}["S025"]


def _allocation(**overrides):
    base = {
        "supplier": 0,
        "demand": 1,
        "vehicle_type": 1,
        "path": [0, 1],
        "amount": 10.0,
        "trips": 1,
        "travel_time": 5.0,
    }
    base.update(overrides)
    return base


def _snapshot(allocations):
    return PeriodSnapshot(
        period=1,
        progress={},
        capacity_ratio={},
        speed_ratio={},
        edge_utilization={},
        residual_capacity={},
        delivered_total=0.0,
        delivered_by_demand={},
        vehicle_trips={},
        allocations=allocations,
    )


class PeriodTraceTest(unittest.TestCase):
    def test_trace_matches_the_shared_evaluator_on_all_three_objectives(self):
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        decisions = fixed_decisions(instance, random_decisions=2, seed=7)
        for label, decision in decisions.items():
            with self.subTest(decision=label):
                trace = period_trace(instance, decision)
                outcome = evaluate_capacity_solution_detailed(
                    instance,
                    CapacityIndividual(
                        list(decision.repair_order),
                        list(decision.team_assignment),
                        list(decision.dispatch_priority),
                    ),
                )
                for ours, theirs in zip(trace.objectives, outcome.objectives):
                    self.assertAlmostEqual(ours, theirs, places=9)

    def test_exposure_summary_is_a_pure_function_of_the_decision(self):
        """Whichever order decisions are fed in, each summary must not move.

        The diagnostic must carry no state across decisions and no dependence
        on the iteration order of the inputs.
        """
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        decisions = fixed_decisions(instance, random_decisions=3, seed=11)

        forward = {
            label: mechanism_report(instance, decision, label)
            for label, decision in decisions.items()
        }
        backward = {
            label: mechanism_report(instance, decision, label)
            for label, decision in reversed(list(decisions.items()))
        }
        self.assertEqual(set(forward), set(backward))
        for label in forward:
            self.assertEqual(forward[label], backward[label], label)

        # And re-running the same decision twice is bit-for-bit identical.
        repeat = mechanism_report(instance, decisions["spt"], "spt")
        self.assertEqual(forward["spt"], repeat)


class AllocationComparisonTest(unittest.TestCase):
    """The comparison must not drop allocations or ignore amount and trips."""

    def test_amount_change_is_detected(self):
        on = _snapshot([_allocation(amount=10.0)])
        off = _snapshot([_allocation(amount=12.0)])
        flags = allocation_change_flags([on], [off])
        self.assertEqual(flags["allocation_amount_changed"], 1)
        self.assertEqual(flags["allocation_any_changed"], 1)
        self.assertEqual(flags["allocation_route_changed"], 0)

    def test_trips_change_is_detected(self):
        flags = allocation_change_flags(
            [_snapshot([_allocation(trips=1)])], [_snapshot([_allocation(trips=2)])]
        )
        self.assertEqual(flags["allocation_trips_changed"], 1)
        self.assertEqual(flags["allocation_any_changed"], 1)

    def test_path_change_is_detected(self):
        flags = allocation_change_flags(
            [_snapshot([_allocation(path=[0, 1])])],
            [_snapshot([_allocation(path=[0, 2, 1])])],
        )
        self.assertEqual(flags["allocation_route_changed"], 1)
        self.assertEqual(flags["allocation_any_changed"], 1)

    def test_vehicle_change_is_detected(self):
        flags = allocation_change_flags(
            [_snapshot([_allocation(vehicle_type=1)])],
            [_snapshot([_allocation(vehicle_type=2)])],
        )
        self.assertEqual(flags["allocation_vehicle_changed"], 1)
        self.assertEqual(flags["allocation_any_changed"], 1)

    def test_second_allocation_to_one_demand_is_not_dropped(self):
        """A dict keyed by (supplier, demand) would lose the second entry."""
        first = _allocation(demand=1, amount=10.0)
        second = _allocation(demand=1, amount=4.0, vehicle_type=2)
        on = _snapshot([first, second])
        off = _snapshot([first, _allocation(demand=1, amount=9.0, vehicle_type=2)])

        self.assertEqual(len(allocation_multiset(on)), 2)
        flags = allocation_change_flags([on], [off])
        self.assertEqual(flags["allocation_any_changed"], 1)
        self.assertEqual(flags["allocation_amount_changed"], 1)

        # Dropping the second entry entirely is also a change.
        reduced = allocation_change_flags([on], [_snapshot([first])])
        self.assertEqual(reduced["allocation_count_changed"], 1)
        self.assertEqual(reduced["allocation_any_changed"], 1)

    def test_input_order_alone_is_not_a_change(self):
        left = [_allocation(demand=1, amount=10.0), _allocation(demand=2, amount=4.0)]
        right = list(reversed(left))
        flags = allocation_change_flags([_snapshot(left)], [_snapshot(right)])
        self.assertEqual(flags["allocation_any_changed"], 0)

    def test_sub_resolution_amount_jitter_is_not_a_change(self):
        flags = allocation_change_flags(
            [_snapshot([_allocation(amount=10.0)])],
            [_snapshot([_allocation(amount=10.0 + ALLOCATION_AMOUNT_RESOLUTION / 4)])],
        )
        self.assertEqual(flags["allocation_any_changed"], 0)


class ObjectiveChangedTest(unittest.TestCase):
    def test_uses_the_pinned_key_not_a_tolerance(self):
        """A scale test that disagrees with the key near a bin boundary."""
        resolution = V2_PRECISION.resolutions[0]
        low = (3.0 + 0.49 * resolution, 100.0, -0.5)
        high = (3.0 + 0.51 * resolution, 100.0, -0.5)
        delta = high[0] - low[0]
        self.assertLess(delta, resolution)
        # An `abs(delta) > resolution` test would call these equal.
        self.assertFalse(abs(delta) > resolution)
        # The pinned comparison key separates them because they straddle a bin.
        self.assertNotEqual(V2_PRECISION.key(low)[0], V2_PRECISION.key(high)[0])
        self.assertTrue(objective_changed(low, high)["changed"])
        self.assertTrue(objective_changed(low, high)["changed_F1"])

    def test_identical_keys_are_unchanged(self):
        base = (3.0, 100.0, -0.5)
        same_bin = (3.0 + V2_PRECISION.resolutions[0] / 8, 100.0, -0.5)
        self.assertFalse(objective_changed(base, same_bin)["changed"])
        self.assertTrue(objective_changed(base, (4.0, 100.0, -0.5))["changed"])

    def test_per_objective_flags(self):
        flags = objective_changed((3.0, 100.0, -0.5), (3.0, 100.0, -0.4))
        self.assertFalse(flags["changed_F1"])
        self.assertFalse(flags["changed_F2"])
        self.assertTrue(flags["changed_F3"])


class CorridorTopologyTest(unittest.TestCase):
    def test_generator_critical_strategy_produces_no_bridge_at_s025(self):
        """The reason a dedicated corridor topology is needed."""
        spec = _spec()
        for seed in (1, 2, 101, 102):
            instance = stress_topology_instance(
                spec,
                instance_seed=seed,
                damage_strategy="critical",
                node_role_strategy="separated",
            )
            self.assertEqual(
                bridge_diagnostics(instance)["graph_bridge_count"],
                0,
                f"seed {seed} unexpectedly has bridges; the corridor test's "
                "premise (critical falls back to random damage) needs review",
            )

    def test_corridor_scenario_really_has_a_damaged_bridge(self):
        spec = _spec()
        for seed in (1, 101):
            instance = corridor_stress_instance(spec, instance_seed=seed)
            diagnostics = bridge_diagnostics(instance)
            self.assertGreater(diagnostics["damaged_bridge_count"], 0)
            require_corridor_scenario(instance, f"corridor seed={seed}")

    def test_removing_the_corridor_disconnects_a_supplier_from_demands(self):
        spec = _spec()
        for seed in (1, 101):
            with self.subTest(instance_seed=seed):
                instance = corridor_stress_instance(spec, instance_seed=seed)
                graph = instance.base.graph
                damaged = {
                    frozenset((edge.u, edge.v))
                    for edge in instance.base.damaged_edges.values()
                }
                damaged_bridges = {
                    frozenset(edge) for edge in nx.bridges(graph)
                } & damaged
                self.assertGreaterEqual(len(damaged_bridges), 1)
                self.assertGreaterEqual(
                    bridge_diagnostics(instance)["bridge_gated_demand_count"], 1
                )

                # Independent of bridge_diagnostics: cut the damaged bridges
                # and recount the separated supplier-demand pairs with plain
                # connectivity, so the reported number is reproducible from
                # first principles rather than from the function under test.
                pruned = graph.copy()
                for u, v in damaged_bridges:
                    pruned.remove_edge(u, v)
                separated = sum(
                    1
                    for supplier in instance.base.suppliers
                    for demand in instance.base.demands
                    if not nx.has_path(pruned, supplier, demand)
                )
                self.assertGreaterEqual(separated, 1)
                self.assertEqual(
                    separated,
                    bridge_diagnostics(instance)["bridge_gated_demand_count"],
                )

    def test_a_corridor_label_without_a_corridor_is_refused(self):
        spec = _spec()
        broken = build_benchmark_instance(spec, instance_seed=101, model_version="v2")
        with self.assertRaises(AssertionError) as caught:
            require_corridor_scenario(broken, "corridor seed=101")
        self.assertIn("damaged_bridge_count=0", str(caught.exception))


class BaseInstanceStateTest(unittest.TestCase):
    def test_switching_a_mechanism_off_does_not_mutate_the_base(self):
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        before = {
            "stages": [s.capacity_ratio for s in instance.recovery_stages],
            "thresholds": [v.min_recovery_progress for v in instance.vehicles],
            "flags": (
                instance.progressive_recovery,
                instance.heterogeneous_vehicle_thresholds,
                instance.edge_capacity_constraint,
            ),
            "profile": instance.full_profile.fingerprint(),
        }
        for variant in (
            dict(progressive_recovery=False,
                 heterogeneous_vehicle_thresholds=True,
                 edge_capacity_constraint=True),
            dict(progressive_recovery=True,
                 heterogeneous_vehicle_thresholds=False,
                 edge_capacity_constraint=True),
            dict(progressive_recovery=True,
                 heterogeneous_vehicle_thresholds=True,
                 edge_capacity_constraint=False),
        ):
            model_factor_variant(instance, **variant)

        self.assertEqual(
            [s.capacity_ratio for s in instance.recovery_stages], before["stages"]
        )
        self.assertEqual(
            [v.min_recovery_progress for v in instance.vehicles], before["thresholds"]
        )
        self.assertEqual(
            (
                instance.progressive_recovery,
                instance.heterogeneous_vehicle_thresholds,
                instance.edge_capacity_constraint,
            ),
            before["flags"],
        )
        self.assertEqual(instance.full_profile.fingerprint(), before["profile"])

    def test_each_switch_changes_only_its_own_mechanism(self):
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        binary = model_factor_variant(
            instance,
            progressive_recovery=False,
            heterogeneous_vehicle_thresholds=True,
            edge_capacity_constraint=True,
        )
        self.assertEqual(len(binary.recovery_stages), 2)
        self.assertEqual(
            [v.min_recovery_progress for v in binary.vehicles],
            [v.min_recovery_progress for v in instance.vehicles],
        )

        uniform = model_factor_variant(
            instance,
            progressive_recovery=True,
            heterogeneous_vehicle_thresholds=False,
            edge_capacity_constraint=True,
        )
        self.assertEqual(
            [s.capacity_ratio for s in uniform.recovery_stages],
            [s.capacity_ratio for s in instance.recovery_stages],
        )
        self.assertEqual(
            {v.min_recovery_progress for v in uniform.vehicles}, {0.30}
        )


class SupplyAndBottleneckTest(unittest.TestCase):
    def test_supply_relaxation_changes_only_supply(self):
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        relaxed = scale_supply(instance, 1.5)
        self.assertAlmostEqual(
            relaxed.base.total_supply, instance.base.total_supply * 1.5, places=6
        )
        self.assertEqual(relaxed.base.demand_amounts, instance.base.demand_amounts)
        self.assertEqual(
            relaxed.base.supply_amounts.keys(), instance.base.supply_amounts.keys()
        )
        # The base instance is untouched.
        original = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        self.assertAlmostEqual(
            instance.base.total_supply, original.base.total_supply, places=9
        )

    def test_road_capacity_probe_loosens_rather_than_tightens(self):
        """A probe that tightened its resource would answer the wrong question.

        ``capacity_scale`` is an absolute calibration, so passing a small
        absolute number to it *adds* a constraint to an already-calibrated
        scenario while the result is labelled a relaxation.
        """
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        baseline = instance.capacity_scale
        relaxed = scale_road_capacity(instance, 2.0)
        self.assertAlmostEqual(relaxed.capacity_scale, baseline * 2.0, places=12)
        self.assertGreater(relaxed.capacity_scale, baseline)
        # The instance itself is untouched.
        self.assertAlmostEqual(instance.capacity_scale, baseline, places=12)

    def test_bottleneck_refuses_an_axis_that_would_tighten(self):
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        decision = fixed_decisions(instance, random_decisions=0, seed=101)["spt"]
        for axis in ("fleet_multiplier", "supply_multiplier", "capacity_multiplier"):
            with self.subTest(axis=axis):
                with self.assertRaises(ValueError):
                    bottleneck_classification(instance, decision, **{axis: 0.5})

    def test_road_probe_is_sensitive_where_capacity_binds(self):
        """A zero from the road probe must mean "not binding", not "broken".

        The same probe has to fire when road throughput genuinely binds, or a
        zero elsewhere carries no information.
        """
        spec = _spec()
        scenario = corridor_stress_instance(spec, instance_seed=101)
        placements = {zone: (scale, achieved) for zone, scale, achieved in calibrate_zones(scenario, 101)}

        readings = {}
        for zone in ("inactive", "binding"):
            scale, _ = placements[zone]
            instance = scale_capacity(scenario, scale)
            decision = fixed_decisions(instance, random_decisions=0, seed=101)["spt"]
            row = bottleneck_classification(instance, decision)
            readings[zone] = row["relax_road_capacity_changed_objective"]

        self.assertFalse(readings["inactive"])
        self.assertTrue(readings["binding"])

    def test_bottleneck_is_classified_by_relaxation(self):
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        decision = fixed_decisions(instance, random_decisions=0, seed=101)["spt"]
        row = bottleneck_classification(instance, decision)
        for key in (
            "relax_fleet_changed_objective",
            "relax_supply_changed_objective",
            "relax_road_capacity_changed_objective",
        ):
            self.assertIn(key, row)
        # F1 is minimised, and a relaxation only ever loosens a constraint, so
        # it can never make cumulative unmet demand worse. This is the sanity
        # check that keeps the classification a measurement, not a label.
        for label in ("fleet", "supply", "road_capacity"):
            self.assertIsInstance(row[f"relax_{label}_changed_objective"], bool)
            self.assertLessEqual(
                row[f"relax_{label}_delta_F1"],
                1e-9,
                f"relaxing {label} increased cumulative unmet demand",
            )


class ZoneDecisionStoreTest(unittest.TestCase):
    def test_calibration_lands_in_the_requested_band_or_says_it_did_not(self):
        """A zone is a measured placement, never a scale we assumed."""
        spec = _spec()
        scenario = corridor_stress_instance(spec, instance_seed=101)
        placements = calibrate_zones(scenario, 101)
        self.assertEqual([zone for zone, _, _ in placements], [z for z, _ in ZONE_TARGETS])
        for (zone, scale, achieved), (_, target) in zip(placements, ZONE_TARGETS):
            with self.subTest(zone=zone):
                low, high = ZONE_SCALE_BOUNDS
                self.assertTrue(low <= scale <= high)
                # The reported utilization is re-measured, not echoed back.
                self.assertAlmostEqual(
                    _probe_utilization(scenario, 101, scale), achieved, places=9
                )
                self.assertLessEqual(abs(achieved - target), 1.0)

    def test_zone_search_stores_rebuildable_decisions(self):
        """Every replayed decision must be reconstructible from the store."""
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        decision = fixed_decisions(instance, random_decisions=0, seed=101)["spt"]
        payload = decision_to_json(decision)
        rebuilt = decision_from_json(payload, instance)
        self.assertEqual(list(rebuilt.repair_order), list(decision.repair_order))
        self.assertEqual(list(rebuilt.team_assignment), list(decision.team_assignment))
        self.assertEqual(
            [tuple(pair) for pair in rebuilt.dispatch_priority],
            [tuple(pair) for pair in decision.dispatch_priority],
        )
        self.assertEqual(decision_hash(rebuilt), decision_hash(decision))


class ZoneReplayTest(unittest.TestCase):
    def test_full_self_replay_is_exactly_zero(self):
        """A decision planned by the Full model must replay identically."""
        instance = build_benchmark_instance(_spec(), instance_seed=101, model_version="v2")
        full = model_factor_variant(
            instance,
            progressive_recovery=True,
            heterogeneous_vehicle_thresholds=True,
            edge_capacity_constraint=True,
        )
        run = solve_benchmark_algorithm(
            "nsga2", full, BenchmarkBudget(max_evaluations=60, pop_size=8), seed=101
        )
        self.assertGreater(len(run.front), 0)
        for individual in run.front:
            replayed = evaluate_capacity_solution_detailed(
                full,
                CapacityIndividual(
                    list(individual.repair_order),
                    list(individual.team_assignment),
                    list(individual.dispatch_priority),
                ),
            ).objectives
            for planned, again in zip(individual.objectives, replayed):
                self.assertAlmostEqual(planned, again, places=12)


class PublishedAuditTest(unittest.TestCase):
    """The committed evidence set must stay consistent with itself.

    ``outputs/mechanism_probe_audit/`` is version-controlled, so a reader can
    check the report's numbers without re-running the diagnostic. That only
    holds while the tables agree with one another and with the manifest, which
    is what this checks. It does not re-derive any mechanism result.
    """

    AUDIT = Path("outputs/mechanism_probe_audit")
    PROBE_ROOT = Path("outputs/mechanism_probe")

    def setUp(self):
        if not (self.AUDIT / "manifest.json").is_file():
            self.skipTest("mechanism audit evidence set is not present")

    def _rows(self, name):
        with (self.AUDIT / name).open() as handle:
            return list(csv.DictReader(handle))

    def test_manifest_table_counts_match_the_files(self):
        manifest = json.loads((self.AUDIT / "manifest.json").read_text())
        for name, count in manifest["tables"].items():
            with self.subTest(table=name):
                self.assertEqual(len(self._rows(name)), count)

    def test_topology_summary_is_a_recount_of_the_summary_table(self):
        summary = self._rows("mechanism_summary.csv")
        for row in self._rows("topology_summary.csv"):
            cell = row["topology_cell"]
            subset = [r for r in summary if r["topology_cell"] == cell]
            with self.subTest(cell=cell):
                self.assertEqual(len(subset), int(row["decisions"]))
                for mechanism in ("PR", "HT", "EC"):
                    expected = sum(
                        1 for r in subset if int(r[f"{mechanism}_allocations_changed"]) > 0
                    )
                    self.assertEqual(
                        int(row[f"{mechanism}_dispatch_changed_decisions"]), expected
                    )

    def test_no_audit_row_claims_bridge_damage_without_a_damaged_bridge(self):
        for row in self._rows("mechanism_summary.csv"):
            with self.subTest(cell=row["topology_cell"], seed=row["instance_seed"]):
                self.assertGreaterEqual(int(row["graph_bridge_count"]), 0)
                self.assertLessEqual(
                    int(row["damaged_bridge_count"]), int(row["graph_bridge_count"])
                )

    def test_replay_summary_agrees_with_a_recount_on_the_quantized_key(self):
        """The summary must count changes the same way the pipeline does."""
        source = self.PROBE_ROOT / "zone_search" / "zone_replay.csv"
        if not source.is_file():
            self.skipTest("wide zone-replay table is not present")
        with source.open() as handle:
            rows = list(csv.DictReader(handle))
        grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
        for row in rows:
            grouped.setdefault((row["zone"], row["model_id"]), []).append(row)

        summary = {
            (row["zone"], row["model_id"]): row
            for row in self._rows("zone_replay_summary.csv")
        }
        for key, group in grouped.items():
            with self.subTest(zone=key[0], model=key[1]):
                expected = sum(
                    1
                    for row in group
                    if objective_changed(
                        (float(row["planning_F1"]), float(row["planning_F2"]),
                         float(row["planning_F3"])),
                        (float(row["execution_F1"]), float(row["execution_F2"]),
                         float(row["execution_F3"])),
                    )["changed"]
                )
                self.assertEqual(summary[key]["objective_changed"], str(expected))
                # The overall count includes every objective, so it dominates
                # each per-objective count.
                for objective in ("F1", "F2", "F3"):
                    self.assertLessEqual(
                        int(summary[key][f"objective_changed_{objective}"]), expected
                    )

    def test_manifest_records_the_identity_control_as_exact(self):
        manifest = json.loads((self.AUDIT / "manifest.json").read_text())
        check = manifest.get("full_self_replay_check") or {}
        if not check:
            self.skipTest("no Full self-replay recorded")
        self.assertEqual(check["max_abs_delta_F1"], 0.0)
        self.assertEqual(check["max_abs_delta_F2"], 0.0)


if __name__ == "__main__":
    unittest.main()
