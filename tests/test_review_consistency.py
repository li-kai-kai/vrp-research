"""Copy into tests/ of vrp-research and run from the repository root.

    uv run python -m unittest discover -s tests -p test_review_consistency.py -v

Target inspected: 65c10142e624db07369002176c9d72932153b21f.
These are proposed regression tests, not a claim that the full repository was
executed by the reviewer. Isolated function-body probes are supplied separately.
"""
from dataclasses import replace
import math
import unittest

from scripts.reproduce.capacity_recovery import (
    BINARY_RECOVERY_STAGES,
    CapacityIndividual,
    _assign_crowding,
    build_wenchuan_instance,
    full_execution_problems,
)
from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.run_benchmark import pooled_quality_indicators


class PrecisionConsistencyReviewTest(unittest.TestCase):
    def test_original_representative_counterexample_is_fixed(self):
        old = (4.323837164030483, 3780.4318118489027, -0.8999999999999966)
        better = (3.820253964737538, 3211.345695506263, -0.8999999999997499)
        self.assertEqual(V2_PRECISION.key(old)[2], V2_PRECISION.key(better)[2])
        self.assertTrue(V2_PRECISION.dominates(better, old))

    def test_equivalent_singletons_have_equal_hv(self):
        a = (4.0, 3000.0, -0.9)
        b = (4.0, 3000.0, -0.9 + 4e-9)
        self.assertTrue(V2_PRECISION.equivalent(a, b))
        rows, _ = pooled_quality_indicators([[a], [b]], V2_PRECISION)
        self.assertAlmostEqual(rows[0]['hypervolume'], rows[1]['hypervolume'], places=12)

    def test_reference_front_deduplicates_equivalent_keys(self):
        a = (4.0, 3000.0, -0.9)
        b = (4.0, 3000.0, -0.9 + 4e-9)
        _, metadata = pooled_quality_indicators([[a], [b]], V2_PRECISION)
        self.assertEqual(metadata['reference_front_size'], 1)

    def test_equal_fronts_with_two_active_dimensions_have_zero_igd(self):
        a = (4.0, 3000.0, -0.9)
        b = (4.0, 3000.0, -0.9 + 4e-9)
        c = (3.0, 4000.0, -0.9)
        rows, metadata = pooled_quality_indicators([[a, c], [b, c]], V2_PRECISION)
        self.assertEqual(metadata['reference_front_size'], 2)
        for row in rows:
            self.assertAlmostEqual(row['igd'], 0.0, places=12)
        self.assertAlmostEqual(rows[0]['hypervolume'], rows[1]['hypervolume'], places=12)

    def test_crowding_is_invariant_when_comparison_keys_are_unchanged(self):
        original = [(3., 1000., -.7), (3., 2000., -.9),
                    (2., 3000., -.95), (1., 4000., -.98)]
        jittered = list(original)
        jittered[1] = (3. - 4e-9, 2000., -.9)
        self.assertEqual([V2_PRECISION.key(p) for p in original],
                         [V2_PRECISION.key(p) for p in jittered])

        def distances(points):
            front = [CapacityIndividual([i], [0], [(0, 1)], objectives=p)
                     for i, p in enumerate(points)]
            _assign_crowding(front, V2_PRECISION)
            return {p.repair_order[0]: p.crowding for p in front}

        first, second = distances(original), distances(jittered)
        for label in first:
            self.assertEqual(math.isinf(first[label]), math.isinf(second[label]))
            if math.isfinite(first[label]):
                self.assertAlmostEqual(first[label], second[label], places=12)


class FullProfileConsistencyReviewTest(unittest.TestCase):
    def test_binary_curve_cannot_pass_just_because_pr_label_is_true(self):
        full = build_wenchuan_instance(model_version='v2')
        invalid = replace(full, recovery_stages=list(BINARY_RECOVERY_STAGES))
        self.assertTrue(invalid.progressive_recovery)
        self.assertTrue(full_execution_problems(invalid),
                        'Binary recovery data must not be validated as progressive Full.')

    def test_uniform_thresholds_do_not_match_the_declared_wenchuan_full_profile(self):
        # This fixture has four vehicle types and a known heterogeneous profile.
        # Do not generalize this test into requiring four types for every scenario.
        full = build_wenchuan_instance(model_version='v2')
        invalid = replace(full, vehicles=[replace(v, min_recovery_progress=0.30)
                                          for v in full.vehicles])
        self.assertTrue(invalid.heterogeneous_vehicle_thresholds)
        self.assertTrue(full_execution_problems(invalid),
                        'Compare actual thresholds with the declared scenario Full profile.')


if __name__ == '__main__':
    unittest.main()
