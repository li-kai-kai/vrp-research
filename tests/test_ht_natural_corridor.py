"""WEN38 natural threshold-sensitive corridor diagnostic: correctness of the test.

These check the instrument, not the finding. Whether HT binds on WEN38 is an
empirical result recorded in the audit tables; what is asserted here is that
the measurement means what it says -- that overlays hold the road network
fixed, that damage overlays do not hunt for bridges, that passability and the
OD splits follow the model's own rules, and that the comparison machinery is
the shared one rather than a private copy.
"""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

import networkx as nx

from scripts.reproduce.benchmark_suite import benchmark_specs
from scripts.reproduce.capacity_recovery import (
    CapacityIndividual,
    model_factor_variant,
)
from scripts.reproduce.ht_natural_corridor import (
    OVERLAYS,
    combined_overlay,
    corridor_ranking,
    damage_overlay,
    edge_structure,
    total_od_pairs,
    fixed_decision_effect,
    role_overlay,
    scenario_stratum,
    threshold_exposure,
    topology_fingerprint,
    verify_uniform_damage_sampling,
    wen38_instance,
)
from scripts.reproduce.mechanism_applicability import (
    _passable,
    allocation_change_flags,
    fixed_decisions,
    objective_changed,
    period_trace,
)
from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.solution_io import decision_hash


def _spec():
    return {s.case_id: s for s in benchmark_specs("benchmark")}["WEN38"]


def _instance():
    return wen38_instance(_spec())


class TopologyInvarianceTest(unittest.TestCase):
    def test_every_overlay_keeps_the_wen38_network_exactly(self):
        """The overlays re-sample roles and damage, never the road network."""
        instance = _instance()
        reference = topology_fingerprint(instance)
        original = {
            frozenset((int(u), int(v))): (float(d["free_time"]), float(d["capacity"]))
            for u, v, d in instance.base.graph.edges(data=True)
        }
        for name, _description, builder in OVERLAYS:
            for seed in (1, 2, 3):
                with self.subTest(overlay=name, seed=seed):
                    overlay = builder(instance, seed)
                    self.assertEqual(topology_fingerprint(overlay), reference)
                    produced = {
                        frozenset((int(u), int(v))): (
                            float(d["free_time"]),
                            float(d["capacity"]),
                        )
                        for u, v, d in overlay.base.graph.edges(data=True)
                    }
                    self.assertEqual(produced, original)

    def test_topology_fingerprint_ignores_the_instance_seed(self):
        """The seed only renames the instance; it must not change the hash.

        ``physical_instance_hash`` includes the name, so it cannot be used to
        state "one physical network"; this is the property that replaces it.
        """
        from scripts.reproduce.benchmark_suite import build_benchmark_instance

        spec = _spec()
        fingerprints = {
            topology_fingerprint(
                build_benchmark_instance(spec, instance_seed=seed, model_version="v2")
            )
            for seed in (1, 2, 101)
        }
        self.assertEqual(len(fingerprints), 1)


class DamageOverlayIsNaturalTest(unittest.TestCase):
    def test_damage_overlay_does_not_prefer_bridges(self):
        """Uniform draws, measured against the network's own bridge rate."""
        instance = _instance()
        check = verify_uniform_damage_sampling(instance, seed=1, draws=80)
        self.assertTrue(check["within_base_rate_band"])
        # A bridge-hunting overlay would sit far above the base rate.
        self.assertLess(
            check["mean_sampled_bridge_share"], check["network_bridge_share"] + 0.10
        )

    def test_damage_overlay_keeps_the_damage_count_and_repair_times(self):
        instance = _instance()
        overlay = damage_overlay(instance, 7)
        self.assertEqual(
            len(overlay.base.damaged_edges), len(instance.base.damaged_edges)
        )
        self.assertEqual(
            sorted(float(d.repair_time) for d in overlay.base.damaged_edges.values()),
            sorted(float(d.repair_time) for d in instance.base.damaged_edges.values()),
        )

    def test_role_overlay_keeps_counts_totals_and_damage(self):
        instance = _instance()
        overlay = role_overlay(instance, 5)
        self.assertEqual(len(overlay.base.suppliers), len(instance.base.suppliers))
        self.assertEqual(len(overlay.base.demands), len(instance.base.demands))
        self.assertAlmostEqual(
            overlay.base.total_demand, instance.base.total_demand, places=6
        )
        self.assertAlmostEqual(
            overlay.base.total_supply, instance.base.total_supply, places=6
        )
        self.assertEqual(
            sorted((int(d.u), int(d.v)) for d in overlay.base.damaged_edges.values()),
            sorted((int(d.u), int(d.v)) for d in instance.base.damaged_edges.values()),
        )


class PassabilityTest(unittest.TestCase):
    def test_threshold_sensitive_edge_uses_the_model_predicate(self):
        """Sensitivity is a strict non-empty proper subset, per the model."""
        from scripts.reproduce.ht_natural_corridor import allowed_vehicle_types

        instance = _instance()
        total = len(instance.vehicles)
        thresholds = sorted(v.min_recovery_progress for v in instance.vehicles)

        # At full progress every type passes: not sensitive.
        self.assertEqual(len(allowed_vehicle_types(instance, 1.0)), total)
        # Below the lowest threshold and above zero, nothing passes.
        self.assertEqual(len(allowed_vehicle_types(instance, 0.0)), 0)

        # The sensitive band ends at the LARGEST threshold, not at 1.0: once
        # every declared threshold has been reached, all types pass and the
        # edge stops being threshold-sensitive.
        for progress in (0.95, 1.0):
            with self.subTest(progress=progress, sensitive=False):
                self.assertEqual(len(allowed_vehicle_types(instance, progress)), total)

        for progress in (0.35, 0.55, 0.75):
            with self.subTest(progress=progress):
                allowed = allowed_vehicle_types(instance, progress)
                self.assertGreater(len(allowed), 0)
                self.assertLess(len(allowed), total)
                # Exactly the types whose declared threshold has been reached.
                expected = tuple(
                    v.vehicle_type
                    for v in sorted(instance.vehicles, key=lambda v: v.vehicle_type)
                    if progress >= v.min_recovery_progress - 1e-9
                )
                self.assertEqual(set(allowed), set(expected))

    def test_progress_bands_are_read_off_the_model_not_assumed(self):
        """The allowed set changes at thresholds and at stage boundaries.

        The stage table also gates passability -- an edge in the blocked stage
        admits nobody however far past a threshold the progress is -- so the
        bands cannot be written down from the thresholds alone.
        """
        from scripts.reproduce.ht_natural_corridor import allowed_vehicle_types

        instance = _instance()
        counts = {
            progress: len(allowed_vehicle_types(instance, progress))
            for progress in (0.0, 0.29, 0.31, 0.51, 0.61, 0.71, 0.81, 0.99, 1.0)
        }
        self.assertEqual(counts[0.0], 0)
        self.assertEqual(counts[0.29], 0)   # stage-blocked: no passability yet
        self.assertEqual(counts[1.0], len(instance.vehicles))
        # Non-decreasing in progress, which the stage table guarantees.
        ordered = [counts[p] for p in sorted(counts)]
        self.assertEqual(ordered, sorted(ordered))


class ExposureTest(unittest.TestCase):
    def test_od_feasibility_split_follows_the_feasible_subgraphs(self):
        """A pair is split exactly when some type can reach it and another not."""
        instance = _instance()
        decision = fixed_decisions(instance, random_decisions=0, seed=1)["spt"]
        exposure = threshold_exposure(instance, decision, "spt")
        graph = instance.base.graph
        trace = period_trace(instance, decision)
        progress_by_period = {s.period: s.progress for s in trace.snapshots}

        for row in exposure["od_rows"]:
            with self.subTest(period=row["period"], source=row["supplier"], sink=row["demand"]):
                progress = progress_by_period[int(row["period"])]
                reachable = []
                for vehicle in instance.vehicles:
                    sub = nx.Graph()
                    sub.add_nodes_from(graph.nodes())
                    for u, v, data in graph.edges(data=True):
                        damage_id = data.get("damage_id")
                        value = (
                            1.0
                            if damage_id is None
                            else progress.get(int(damage_id), 0.0)
                        )
                        if _passable(instance, value, vehicle):
                            sub.add_edge(u, v, free_time=data["free_time"])
                    reachable.append(
                        nx.has_path(sub, int(row["supplier"]), int(row["demand"]))
                    )
                self.assertEqual(
                    bool(row["vehicle_feasibility_split"]),
                    any(reachable) and not all(reachable),
                )

    def test_every_emitted_od_row_is_actually_sensitive(self):
        instance = _instance()
        decision = fixed_decisions(instance, random_decisions=0, seed=1)["spt"]
        exposure = threshold_exposure(instance, decision, "spt")
        for row in exposure["od_rows"]:
            with self.subTest(period=row["period"]):
                self.assertTrue(
                    row["vehicle_feasibility_split"]
                    or row["vehicle_path_split"]
                    or row["vehicle_travel_time_split"]
                )

    def test_od_travel_times_come_from_the_evaluator_graph(self):
        """Times must be the evaluator's, not a raw free_time Dijkstra.

        Using free_time alone prices a partially recovered road as if it were
        fully restored, which manufactures travel-time splits that the model
        does not have.
        """
        from scripts.reproduce.capacity_recovery import _shortest_paths_for_vehicle

        instance = _instance()
        decision = fixed_decisions(instance, random_decisions=1, seed=1)["random_0"]
        trace = period_trace(instance, decision)
        progress_by_period = {s.period: s.progress for s in trace.snapshots}
        exposure = threshold_exposure(instance, decision, "random_0")

        rows = [r for r in exposure["od_rows"]][:5]
        self.assertTrue(rows, "the fixture expects at least one sensitive OD")
        for row in rows:
            with self.subTest(period=row["period"], demand=row["demand"]):
                progress = progress_by_period[int(row["period"])]
                reported = {
                    int(part.split(":")[0]): part.split(":")[1]
                    for part in row["best_travel_time_by_vehicle"].split("|")
                }
                for vehicle in instance.vehicles:
                    entry = _shortest_paths_for_vehicle(
                        instance, progress, vehicle
                    ).get((int(row["supplier"]), int(row["demand"])))
                    value = "inf" if entry is None else str(round(entry[0], 3))
                    self.assertEqual(reported[vehicle.vehicle_type], value)

    def test_partial_recovery_is_not_priced_at_free_flow_speed(self):
        """A damaged edge in a partial stage costs more than its free_time.

        This is the property that made the corrected exposure counts differ;
        if it ever stops holding, the weighting has silently reverted.
        """
        from scripts.reproduce.capacity_recovery import (
            _build_vehicle_graph,
            _speed_ratio,
        )

        instance = _instance()
        decision = fixed_decisions(instance, random_decisions=19, seed=1)["spt"]
        trace = period_trace(instance, decision)
        vehicle = instance.vehicles[0]

        checked = 0
        for snapshot in trace.snapshots:
            graph = _build_vehicle_graph(instance, snapshot.progress, vehicle)
            for damage_id, damaged in instance.base.damaged_edges.items():
                progress = snapshot.progress.get(damage_id, 0.0)
                if not 0.0 < progress < 1.0:
                    continue
                if not graph.has_edge(int(damaged.u), int(damaged.v)):
                    continue
                free_time = float(
                    instance.base.graph[int(damaged.u)][int(damaged.v)]["free_time"]
                )
                weighted = graph[int(damaged.u)][int(damaged.v)]["weight"]
                speed = _speed_ratio(instance.recovery_stages, progress)
                self.assertLess(speed, 1.0)
                self.assertAlmostEqual(
                    weighted, free_time / max(speed, 0.1) / vehicle.speed_factor, places=9
                )
                self.assertGreater(weighted, free_time)
                checked += 1
        self.assertGreater(checked, 0, "the fixture expects a partially recovered edge")

    def test_summary_counts_match_the_emitted_rows(self):
        instance = _instance()
        decision = fixed_decisions(instance, random_decisions=1, seed=3)["random_0"]
        exposure = threshold_exposure(instance, decision, "random_0")
        summary = exposure["summary"]
        self.assertEqual(
            summary["threshold_sensitive_edge_periods"],
            sum(1 for r in exposure["edge_rows"] if r["threshold_sensitive_edge"]),
        )
        self.assertEqual(
            summary["threshold_sensitive_od_periods"], len(exposure["od_rows"])
        )
        self.assertEqual(
            summary["vehicle_access_set_changes"],
            sum(1 for r in exposure["od_rows"] if r["vehicle_feasibility_split"]),
        )


class DetourTest(unittest.TestCase):
    def test_detour_ratio_matches_an_independent_removal(self):
        """Recompute removal effects from scratch and compare."""
        instance = _instance()
        structure = {row["damage_id"]: row for row in edge_structure(instance)}
        graph = instance.base.graph
        for damage_id, row in structure.items():
            with self.subTest(damage_id=damage_id):
                pruned = graph.copy()
                pruned.remove_edge(row["u"], row["v"])
                ratios = []
                severed = 0
                for source in instance.base.suppliers:
                    for sink in instance.base.demands:
                        if source == sink:
                            continue
                        direct = nx.shortest_path_length(
                            graph, source, sink, weight="free_time"
                        )
                        if not nx.has_path(pruned, source, sink):
                            severed += 1
                            continue
                        after = nx.shortest_path_length(
                            pruned, source, sink, weight="free_time"
                        )
                        if after > direct + 1e-9:
                            ratios.append(after / direct)
                self.assertEqual(row["detour_ratio_infinite_count"], severed)
                self.assertEqual(row["od_shortest_path_dependency_count"], len(ratios) + severed)
                if ratios:
                    self.assertAlmostEqual(
                        row["detour_ratio_mean"], sum(ratios) / len(ratios), places=9
                    )
                    self.assertAlmostEqual(
                        row["detour_ratio_max"], max(ratios), places=9
                    )

    def test_dependency_fraction_is_a_fraction(self):
        """Dependency over OD *pairs*, so it can never exceed 1.

        Dividing by the demand count instead lets an edge that two suppliers
        both depend on report more than one, which is not a fraction at all.
        """
        instance = _instance()
        pairs = total_od_pairs(instance)
        self.assertEqual(pairs, len(instance.base.suppliers) * len(instance.base.demands))
        for row in edge_structure(instance):
            with self.subTest(damage_id=row["damage_id"]):
                self.assertEqual(row["od_pairs_total"], pairs)
                self.assertGreaterEqual(row["od_dependency_fraction"], 0.0)
                self.assertLessEqual(row["od_dependency_fraction"], 1.0)
                self.assertLessEqual(
                    row["od_shortest_path_dependency_count"], row["od_pairs_total"]
                )
                self.assertAlmostEqual(
                    row["od_dependency_fraction"],
                    row["od_shortest_path_dependency_count"] / row["od_pairs_total"],
                    places=12,
                )

    def test_a_bridge_reports_severed_flows_not_a_diluted_mean(self):
        instance = _instance()
        structure = edge_structure(instance)
        bridges = [r for r in structure if r["is_bridge"]]
        self.assertTrue(bridges, "WEN38 has damaged bridges; the fixture assumes it")
        for row in bridges:
            with self.subTest(damage_id=row["damage_id"]):
                # A bridge severs its dependent pairs, so no finite detour
                # exists for them and the mean must not read a clean 1.000.
                self.assertGreater(row["detour_ratio_infinite_count"], 0)
                self.assertGreaterEqual(
                    row["od_shortest_path_dependency_count"],
                    row["detour_ratio_infinite_count"],
                )


class SharedMachineryTest(unittest.TestCase):
    def test_effect_reuses_the_canonical_allocation_comparison(self):
        """The dispatch comparison must be the shared one, not a copy."""
        instance = _instance()
        decision = fixed_decisions(instance, random_decisions=0, seed=1)["spt"]
        effect = fixed_decision_effect(instance, decision, "spt")

        from scripts.reproduce.ht_natural_corridor import HT_VARIANT

        off = model_factor_variant(instance, **HT_VARIANT)
        flags = allocation_change_flags(
            period_trace(instance, decision).snapshots,
            period_trace(off, decision).snapshots,
        )
        for field in ("route", "vehicle", "amount", "trips", "pairing"):
            self.assertEqual(
                effect[f"allocation_{field}_changed"], flags[f"allocation_{field}_changed"]
            )
        self.assertEqual(effect["allocation_any_changed"], flags["allocation_any_changed"])
        self.assertEqual(effect["decision_hash"], decision_hash(decision))

    def test_objective_change_uses_the_quantized_key(self):
        instance = _instance()
        decision = fixed_decisions(instance, random_decisions=1, seed=1)["random_0"]
        effect = fixed_decision_effect(instance, decision, "random_0")
        on = (effect["F1"], effect["F2"], effect["F3"])
        off = (effect["no_ht_F1"], effect["no_ht_F2"], effect["no_ht_F3"])
        self.assertEqual(
            effect["objective_changed"], V2_PRECISION.key(on) != V2_PRECISION.key(off)
        )

    def test_ht_switch_leaves_pr_ec_and_the_base_instance_alone(self):
        instance = _instance()
        before = {
            "stages": [s.capacity_ratio for s in instance.recovery_stages],
            "thresholds": [v.min_recovery_progress for v in instance.vehicles],
            "damage": sorted(
                (int(d.u), int(d.v), float(d.repair_time))
                for d in instance.base.damaged_edges.values()
            ),
            "flags": (
                instance.progressive_recovery,
                instance.heterogeneous_vehicle_thresholds,
                instance.edge_capacity_constraint,
            ),
        }
        decision = fixed_decisions(instance, random_decisions=0, seed=1)["spt"]
        fixed_decision_effect(instance, decision, "spt")

        from scripts.reproduce.ht_natural_corridor import HT_VARIANT

        variant = model_factor_variant(instance, **HT_VARIANT)
        self.assertTrue(variant.progressive_recovery)
        self.assertFalse(variant.heterogeneous_vehicle_thresholds)
        self.assertTrue(variant.edge_capacity_constraint)
        self.assertEqual(
            [s.capacity_ratio for s in variant.recovery_stages], before["stages"]
        )
        # Turning HT off collapses every type onto the one uniform threshold;
        # that is the definition of the switch, and it must not also edit the
        # source instance's declared thresholds (checked below).
        self.assertEqual(
            {v.min_recovery_progress for v in variant.vehicles},
            {variant.vehicles[0].min_recovery_progress},
        )
        # The source instance is untouched.
        self.assertEqual(
            [s.capacity_ratio for s in instance.recovery_stages], before["stages"]
        )
        self.assertEqual(
            [v.min_recovery_progress for v in instance.vehicles], before["thresholds"]
        )
        self.assertEqual(
            sorted(
                (int(d.u), int(d.v), float(d.repair_time))
                for d in instance.base.damaged_edges.values()
            ),
            before["damage"],
        )
        self.assertEqual(
            (
                instance.progressive_recovery,
                instance.heterogeneous_vehicle_thresholds,
                instance.edge_capacity_constraint,
            ),
            before["flags"],
        )

    def test_ht_off_admits_a_superset_of_vehicles(self):
        """Uniform 0.30 admits every vehicle the declared thresholds do.

        This is a statement about the FEASIBLE SET only. It does NOT make the
        objective monotone: dispatch is generated by a greedy decoder, so a
        larger feasible set does not guarantee a better plan. The sign and the
        size of any F2 difference are empirical findings, not corollaries --
        pinned here so the result is not read the other way round.
        """
        from scripts.reproduce.ht_natural_corridor import HT_VARIANT

        instance = _instance()
        variant = model_factor_variant(instance, **HT_VARIANT)
        self.assertLessEqual(
            variant.vehicles[0].min_recovery_progress,
            min(v.min_recovery_progress for v in instance.vehicles),
        )
        for progress in (0.35, 0.55, 0.75, 0.95, 1.0):
            with self.subTest(progress=progress):
                on = {v.vehicle_type for v in instance.vehicles if _passable(instance, progress, v)}
                off = {v.vehicle_type for v in variant.vehicles if _passable(variant, progress, v)}
                self.assertTrue(on.issubset(off))
        # Feasible-set containment says nothing about objective monotonicity:
        # no assertion about F1/F2/F3 ordering belongs in this test.


class CorridorClassifierTest(unittest.TestCase):
    def test_bridge_and_non_bridge_are_both_admissible(self):
        """The classifier must not encode corridor = bridge."""
        instance = _instance()
        structure = edge_structure(instance)
        ranking = corridor_ranking(
            structure,
            [
                {
                    "decision_id": "d",
                    "damage_id": row["damage_id"],
                    "threshold_sensitive_edge": True,
                }
                for row in structure
            ],
            [
                {
                    "decision_id": "d",
                    "objective_changed": True,
                    "allocation_any_changed": 1,
                    "threshold_sensitive_od_periods": 1,
                    "delta_F1": 1.0,
                    "delta_F2": 1.0,
                    "delta_F3": 1.0,
                }
            ],
        )
        accepted = [r for r in ranking if r["objective_binding_corridor"]]
        self.assertTrue(accepted)
        self.assertTrue(any(r["is_bridge"] for r in accepted))
        self.assertTrue(any(not r["is_bridge"] for r in accepted))

    def test_a_zero_dependency_edge_is_not_structural(self):
        instance = _instance()
        structure = edge_structure(instance)
        ranking = corridor_ranking(structure, [], [])
        for row in ranking:
            with self.subTest(damage_id=row["damage_id"]):
                self.assertEqual(
                    row["structural_corridor"],
                    row["od_shortest_path_dependency_count"] > 0,
                )

    def test_scenario_strata_partition_every_count(self):
        for count in range(0, 6):
            with self.subTest(decisions=count):
                label = scenario_stratum(count)
                self.assertIn(
                    label, ("inactive", "natural-active", "strong-natural-active")
                )
        self.assertEqual(scenario_stratum(0), "inactive")
        self.assertEqual(scenario_stratum(5), "strong-natural-active")


class ReproducibilityTest(unittest.TestCase):
    def test_overlays_are_reproducible_from_their_seed(self):
        instance = _instance()
        for name, _description, builder in OVERLAYS:
            with self.subTest(overlay=name):
                first = builder(instance, 11)
                second = builder(instance, 11)
                third = builder(instance, 12)
                self.assertEqual(
                    topology_fingerprint(first), topology_fingerprint(second)
                )
                self.assertEqual(
                    sorted((int(d.u), int(d.v)) for d in first.base.damaged_edges.values()),
                    sorted((int(d.u), int(d.v)) for d in second.base.damaged_edges.values()),
                )
                self.assertEqual(first.base.suppliers, second.base.suppliers)
                self.assertEqual(first.base.demands, second.base.demands)
                # A different seed is allowed to differ, and in the dimension
                # that overlay actually re-samples: roles for SR-A, damaged
                # edges for SR-B, both for SR-C. A damage overlay legitimately
                # leaves supplier nodes alone, so the two are checked apart.
                if name in ("SR-A", "SR-C"):
                    self.assertNotEqual(first.base.suppliers, third.base.suppliers)
                if name in ("SR-B", "SR-C"):
                    self.assertNotEqual(
                        sorted(
                            (int(d.u), int(d.v))
                            for d in first.base.damaged_edges.values()
                        ),
                        sorted(
                            (int(d.u), int(d.v))
                            for d in third.base.damaged_edges.values()
                        ),
                    )

    def test_combined_overlay_is_damage_on_top_of_roles(self):
        instance = _instance()
        combined = combined_overlay(instance, 9)
        expected = damage_overlay(role_overlay(instance, 9), 9)
        self.assertEqual(combined.base.suppliers, expected.base.suppliers)
        self.assertEqual(combined.base.demands, expected.base.demands)
        self.assertEqual(
            sorted((int(d.u), int(d.v)) for d in combined.base.damaged_edges.values()),
            sorted((int(d.u), int(d.v)) for d in expected.base.damaged_edges.values()),
        )


class PublishedAuditTest(unittest.TestCase):
    """The committed evidence set must stay consistent with itself."""

    AUDIT = Path("outputs/ht_natural_corridor_audit")

    def setUp(self):
        if not (self.AUDIT / "manifest.json").is_file():
            self.skipTest("HT natural-corridor audit is not present")

    def _rows(self, name):
        with (self.AUDIT / name).open() as handle:
            return list(csv.DictReader(handle))

    def test_manifest_bridge_count_matches_the_edge_structure_table(self):
        """The manifest's damaged-bridge count must agree with the scan.

        The count was previously computed with a set intersection that is
        always empty, so it read zero for every overlay while the edge table
        said otherwise. This pins the two together.
        """
        manifest = json.loads((self.AUDIT / "manifest.json").read_text())
        structure = self._rows("wen38_edge_structure.csv")
        expected = sum(1 for row in structure if row["is_bridge"] == "True")
        self.assertEqual(manifest["network"]["damaged_bridge_count"], expected)
        self.assertGreater(expected, 0, "WEN38 has damaged bridges; a zero is the bug")
        self.assertEqual(
            manifest["network"]["damaged_edge_count"], len(structure)
        )

    def test_overlay_bridge_counts_are_recomputable_and_not_all_zero(self):
        """Overlay counts come from the same helper, and sampling is uniform."""
        import statistics

        overlay_rows = self._rows("semi_real_overlay_manifest.csv")
        counts = [int(row["damaged_bridge_count"]) for row in overlay_rows]
        self.assertEqual(
            sum(1 for row in overlay_rows if "damaged_bridge_count" not in row), 0
        )
        # A uniform draw of 16 of 51 edges with 8 bridges expects ~2.5; all
        # zero would mean the membership test is broken again.
        self.assertGreater(statistics.fmean(counts), 1.0)
        self.assertLessEqual(max(counts), len(self._rows("wen38_edge_structure.csv")))

    def test_manifest_records_one_physical_network(self):
        manifest = json.loads((self.AUDIT / "manifest.json").read_text())
        self.assertTrue(manifest["single_physical_network"])
        self.assertIn("wen38_topology_fingerprint", manifest)
        self.assertTrue(manifest["overlay_design"]["topology_invariant_across_overlays"])
        self.assertTrue(manifest["damage_sampling_check"]["within_base_rate_band"])

    def test_overlay_manifest_agrees_with_the_summary(self):
        overlays = {
            (r["overlay_type"], r["overlay_seed"]): r
            for r in self._rows("semi_real_overlay_manifest.csv")
        }
        for row in self._rows("semi_real_ht_summary.csv"):
            key = (row["overlay_type"], row["overlay_seed"])
            with self.subTest(overlay=key):
                self.assertIn(key, overlays)
                self.assertEqual(overlays[key]["topology_unchanged"], "True")

    def test_summary_counts_match_the_per_decision_table(self):
        from collections import Counter

        counts = Counter(
            (r["overlay_type"], r["overlay_seed"])
            for r in self._rows("semi_real_ht_decisions.csv")
            if r["objective_changed"] == "True"
        )
        for row in self._rows("semi_real_ht_summary.csv"):
            key = (row["overlay_type"], row["overlay_seed"])
            with self.subTest(overlay=key):
                self.assertEqual(
                    int(row["decisions_with_objective_change"]), counts.get(key, 0)
                )

    def test_full_self_replay_is_exact_in_the_published_replay(self):
        rows = [r for r in self._rows("wen38_ht_search_replay.csv") if r.get("is_full_self_replay") == "True"]
        if not rows:
            self.skipTest("search stage was not run")
        for row in rows:
            with self.subTest(solver_seed=row["solver_seed"]):
                self.assertEqual(float(row["delta_F1"]), 0.0)
                self.assertEqual(float(row["delta_F2"]), 0.0)
                self.assertEqual(float(row["delta_F3"]), 0.0)

    def test_the_chain_holds_in_both_directions_where_it_was_measured(self):
        """Necessity and sufficiency both hold on WEN38 and its overlays.

        This is the opposite of M100, where dispatch changed without an
        objective effect; the contrast is part of the result, so it is pinned.
        """
        for name in ("wen38_ht_fixed_decision_effect.csv", "semi_real_ht_decisions.csv"):
            rows = self._rows(name)
            if not rows:
                continue
            with self.subTest(table=name):
                for row in rows:
                    dispatch = int(row["allocation_any_changed"]) > 0
                    objective = row["objective_changed"] == "True"
                    self.assertEqual(objective and not dispatch, False)
                    self.assertEqual(dispatch and not objective, False)


if __name__ == "__main__":
    unittest.main()
