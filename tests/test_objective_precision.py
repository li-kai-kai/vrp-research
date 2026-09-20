"""R1: pinned objective resolution and the ordering properties it guarantees."""

from __future__ import annotations

import random
import unittest

from scripts.reproduce.capacity_recovery import (
    CapacityIndividual,
    _assign_crowding,
    _representative_key,
)
from scripts.reproduce.objective_precision import (
    EXACT_PRECISION,
    FRACTION_RESOLUTION,
    MINUTES_RESOLUTION,
    V2_PRECISION,
    ObjectivePrecision,
    degenerate_dimensions,
    effective_span,
    precision_for,
)
from scripts.reproduce.run_benchmark import (
    _normalize,
    hypervolume_3d,
    pooled_quality_indicators,
)
from tests.test_model_contract import _make_instance


# The two solutions from the audited replay table that motivated R1. Their F3
# values differ by 2.5e-13 while F1 differs by 11.6% and F2 by 15.1%.
AUDITED_P0001 = (4.323837164030483, 3780.431811848903, -0.8999999999999966)
AUDITED_P0012 = (3.820253964737538, 3211.345695506263, -0.8999999999997499)


def _front(*triples):
    front = []
    for index, objectives in enumerate(triples):
        front.append(
            CapacityIndividual(
                repair_order=[index],
                team_assignment=[0],
                dispatch_priority=[(0, 1)],
                objectives=tuple(objectives),
            )
        )
    return front


class AuditedCounterexampleTest(unittest.TestCase):
    def test_resolution_treats_the_audited_pair_as_fairness_equivalent(self):
        # F3 is equal at the pinned resolution; F1 and F2 are not.
        self.assertEqual(
            V2_PRECISION.key(AUDITED_P0001)[2],
            V2_PRECISION.key(AUDITED_P0012)[2],
        )
        # Therefore the far better F1/F2 now dominates instead of being "kept
        # apart" by a 2.5e-13 fairness difference.
        self.assertTrue(V2_PRECISION.dominates(AUDITED_P0012, AUDITED_P0001))

    def test_exact_rule_still_reproduces_the_old_behaviour(self):
        """The legacy rule is preserved, not silently rewritten."""
        self.assertFalse(EXACT_PRECISION.dominates(AUDITED_P0012, AUDITED_P0001))
        self.assertFalse(EXACT_PRECISION.equivalent(AUDITED_P0001, AUDITED_P0012))

    def test_representative_no_longer_follows_the_noise(self):
        p0001 = _front(AUDITED_P0001)[0]
        p0012 = _front(AUDITED_P0012)[0]

        self.assertIs(
            min([p0001, p0012], key=lambda item: _representative_key(item, EXACT_PRECISION)),
            p0001,
        )
        self.assertIs(
            min([p0001, p0012], key=lambda item: _representative_key(item, V2_PRECISION)),
            p0012,
        )

    def test_real_fairness_differences_survive(self):
        """F3 is not deleted, floored away or replaced by the supply ratio."""
        better = (4.0, 1000.0, -0.90)
        worse = (4.0, 1000.0, -0.85)
        self.assertTrue(V2_PRECISION.dominates(better, worse))
        # A difference well above the resolution still separates two points
        # that are otherwise identical.
        self.assertFalse(
            V2_PRECISION.equivalent((4.0, 1000.0, -0.9), (4.0, 1000.0, -0.9 + 1e-3))
        )

    def test_resolution_only_affects_the_fairness_scale_it_was_set_for(self):
        self.assertEqual(V2_PRECISION.resolutions[0], FRACTION_RESOLUTION)
        self.assertEqual(V2_PRECISION.resolutions[2], FRACTION_RESOLUTION)
        self.assertEqual(V2_PRECISION.resolutions[1], MINUTES_RESOLUTION)
        # A difference of one F2 resolution is distinguishable; half of one is
        # not required to be.
        base = (4.0, 1000.0, -0.5)
        self.assertFalse(V2_PRECISION.equivalent(base, (4.0, 1000.0 + 2e-6, -0.5)))
        self.assertTrue(V2_PRECISION.equivalent(base, (4.0, 1000.0 + 1e-13, -0.5)))


class OrderingPropertyTest(unittest.TestCase):
    """The comparison key must be an actual order, not a chain of isclose."""

    def _sample(self, rng: random.Random, count: int):
        return [
            (
                round(rng.uniform(0.0, 9.0), 9),
                round(rng.uniform(0.0, 5000.0), 6),
                round(rng.uniform(-1.0, 0.0), 9),
            )
            for _ in range(count)
        ]

    def test_dominance_is_irreflexive_and_antisymmetric(self):
        rng = random.Random(11)
        for precision in (EXACT_PRECISION, V2_PRECISION):
            for point in self._sample(rng, 200):
                self.assertFalse(precision.dominates(point, point))
            for left in self._sample(rng, 120):
                for right in self._sample(rng, 40):
                    if precision.dominates(left, right):
                        self.assertFalse(precision.dominates(right, left))

    def test_dominance_is_transitive(self):
        rng = random.Random(12)
        for precision in (EXACT_PRECISION, V2_PRECISION):
            sample = self._sample(rng, 90)
            for a in sample:
                for b in sample:
                    if not precision.dominates(a, b):
                        continue
                    for c in sample:
                        if precision.dominates(b, c):
                            self.assertTrue(
                                precision.dominates(a, c),
                                f"dominance not transitive: {a} > {b} > {c}",
                            )

    def test_equivalence_is_reflexive_symmetric_and_transitive(self):
        rng = random.Random(13)
        for precision in (EXACT_PRECISION, V2_PRECISION):
            sample = self._sample(rng, 120)
            for point in sample:
                self.assertTrue(precision.equivalent(point, point))
            for left in sample:
                for right in sample:
                    self.assertEqual(
                        precision.equivalent(left, right),
                        precision.equivalent(right, left),
                    )
            # Transitivity is what a chain of isclose tests cannot provide.
            by_key: dict = {}
            for point in sample:
                by_key.setdefault(precision.key(point), []).append(point)
            for members in by_key.values():
                for left in members:
                    for right in members:
                        self.assertTrue(precision.equivalent(left, right))

    def test_key_is_deterministic(self):
        rng = random.Random(14)
        for precision in (EXACT_PRECISION, V2_PRECISION):
            for point in self._sample(rng, 200):
                self.assertEqual(precision.key(point), precision.key(point))


class NearConstantDimensionTest(unittest.TestCase):
    """A dimension that barely moves must not be amplified into "diversity"."""

    def test_crowding_ignores_a_sub_resolution_dimension(self):
        """A noise-only dimension contributes exactly nothing to crowding."""
        noisy = _front(
            (4.0, 3000.0, -0.9),
            (3.0, 3500.0, -0.9 + 1e-13),
            (2.0, 4000.0, -0.9 - 1e-13),
            (1.0, 4500.0, -0.9 + 2e-13),
        )
        constant = _front(
            (4.0, 3000.0, -0.9),
            (3.0, 3500.0, -0.9),
            (2.0, 4000.0, -0.9),
            (1.0, 4500.0, -0.9),
        )
        _assign_crowding(noisy, V2_PRECISION)
        _assign_crowding(constant, V2_PRECISION)

        # _assign_crowding sorts the front in place, so key by the individual's
        # own identity (the repair_order index set up in _front).
        def crowding_by_index(front):
            return {
                individual.repair_order[0]: individual.crowding
                for individual in front
            }

        # Replacing sub-resolution jitter with an exactly constant value must
        # not change a single crowding distance.
        self.assertEqual(crowding_by_index(noisy), crowding_by_index(constant))
        # The interior points are still separated by the dimensions that move.
        interior = [individual for individual in noisy if individual.repair_order[0] in (1, 2)]
        self.assertTrue(all(individual.crowding > 0.0 for individual in interior))

    def test_crowding_does_not_invent_endpoints_from_noise(self):
        """When only a noise dimension varies, nothing earns infinite crowding."""
        front = _front(
            (4.0, 3000.0, -0.9),
            (4.0, 3000.0, -0.9 + 1e-13),
            (4.0, 3000.0, -0.9 - 1e-13),
        )
        _assign_crowding(front, V2_PRECISION)
        self.assertTrue(
            all(individual.crowding == 0.0 for individual in front),
            "a front that is constant at the resolution has no spread to reward",
        )

        # The historical exact rule still marks endpoints, unchanged.
        legacy_front = _front(
            (4.0, 3000.0, -0.9),
            (4.0, 3000.0, -0.9 + 1e-13),
            (4.0, 3000.0, -0.9 - 1e-13),
        )
        _assign_crowding(legacy_front, EXACT_PRECISION)
        self.assertEqual(legacy_front[0].crowding, float("inf"))
        self.assertEqual(legacy_front[-1].crowding, float("inf"))

    def test_crowding_still_uses_a_dimension_that_really_moves(self):
        front = _front(
            (4.0, 3000.0, -0.9),
            (3.0, 3500.0, -0.5),
            (2.0, 4000.0, -0.2),
            (1.0, 4500.0, -0.1),
        )
        _assign_crowding(front, V2_PRECISION)
        self.assertEqual(front[0].crowding, float("inf"))
        self.assertEqual(front[-1].crowding, float("inf"))
        self.assertTrue(all(individual.crowding != float("inf") for individual in front[1:-1]))

    def test_degenerate_dimension_is_reported_and_floored(self):
        ideal = (1.0, 100.0, -0.9000000001)
        nadir = (9.0, 5000.0, -0.9)
        self.assertEqual(degenerate_dimensions(ideal, nadir, V2_PRECISION), [2])

        span, floored = effective_span(ideal[2], nadir[2], FRACTION_RESOLUTION)
        self.assertTrue(floored)
        self.assertEqual(span, FRACTION_RESOLUTION)

        # Normalization therefore cannot divide by a 1e-10 range.
        normalized = _normalize(nadir, ideal, nadir, V2_PRECISION)
        self.assertTrue(all(value == value for value in normalized))
        self.assertLessEqual(max(abs(value) for value in normalized), 1e6)

    def test_quality_indicators_record_raw_ranges_and_effective_dimensions(self):
        fronts = [
            [(4.0, 3000.0, -0.9), (2.0, 4000.0, -0.9 + 1e-13)],
            [(3.0, 3500.0, -0.9), (1.0, 4500.0, -0.9 - 1e-13)],
        ]
        _rows, metadata = pooled_quality_indicators(fronts, V2_PRECISION)

        self.assertEqual(metadata["degenerate_dimensions"], [2])
        self.assertEqual(metadata["effective_dimensions"], 2)
        self.assertLess(metadata["raw_ranges"][2], FRACTION_RESOLUTION)
        self.assertEqual(metadata["precision"]["label"], "v2_service_resolution")
        # Raw objectives are not overwritten by the normalization.
        self.assertEqual(metadata["ideal"][0], 1.0)
        self.assertEqual(metadata["nadir"][1], 4500.0)

    def test_hypervolume_does_not_move_with_noise_alone(self):
        """Two fronts equal at the resolution score equal HV."""
        base = [(4.0, 3000.0, -0.9), (2.0, 4000.0, -0.9)]
        noisy = [(4.0 + 1e-13, 3000.0, -0.9 - 1e-13), (2.0, 4000.0 + 1e-13, -0.9)]
        reference = (9.0, 5000.0, 0.0)
        ideal = (0.0, 0.0, -1.0)
        nadir = (9.0, 5000.0, 0.0)

        def score(points):
            normalized = [_normalize(point, ideal, nadir, V2_PRECISION) for point in points]
            return hypervolume_3d(normalized, (1.1, 1.1, 1.1))

        self.assertAlmostEqual(score(base), score(noisy), places=9)


class PrecisionWiringTest(unittest.TestCase):
    def test_precision_follows_the_model_version(self):
        self.assertIs(precision_for(_make_instance(model_version="v2",
                                                   suppliers=[0], demands=[1],
                                                   supply_amounts={0: 10.0},
                                                   demand_amounts={1: 10.0},
                                                   edges=[(0, 1, 10.0, 1000.0)])),
                      V2_PRECISION)
        self.assertIs(precision_for(_make_instance(model_version="legacy",
                                                   suppliers=[0], demands=[1],
                                                   supply_amounts={0: 10.0},
                                                   demand_amounts={1: 10.0},
                                                   edges=[(0, 1, 10.0, 1000.0)])),
                      EXACT_PRECISION)

    def test_precision_is_part_of_the_model_fingerprint(self):
        from scripts.reproduce.solution_io import model_fingerprint

        instance = _make_instance(
            model_version="v2",
            suppliers=[0],
            demands=[1],
            supply_amounts={0: 10.0},
            demand_amounts={1: 10.0},
            edges=[(0, 1, 10.0, 1000.0)],
        )
        baseline = model_fingerprint(instance)
        # A different numerical policy is a different model.
        import scripts.reproduce.objective_precision as precision_module

        original = precision_module.V2_PRECISION
        try:
            precision_module.V2_PRECISION = ObjectivePrecision(
                "v2_alternative", (1e-4, 1e-4, 1e-4)
            )
            self.assertNotEqual(model_fingerprint(instance), baseline)
        finally:
            precision_module.V2_PRECISION = original
        self.assertEqual(model_fingerprint(instance), baseline)


if __name__ == "__main__":
    unittest.main()
