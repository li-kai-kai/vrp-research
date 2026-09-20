"""Search-side contract tests: archive completeness, budget, scoring, controls."""

from __future__ import annotations


import random
import unittest

from scripts.reproduce.benchmark_algorithms import (
    ALGORITHMS,
    BenchmarkBudget,
    STOP_BUDGET_EXHAUSTED,
    STOP_NO_PROGRESS,
    STOP_SINGLE_PASS,
    _AdaptiveOperators,
    _Evaluator,
    _local_operators,
    _normalized_score,
    _update_pareto_archive,
    solve_benchmark_algorithm,
)
from scripts.reproduce.benchmark_suite import benchmark_specs, build_benchmark_instance
from scripts.reproduce.capacity_recovery import (
    BINARY_RECOVERY_STAGES,
    CapacityIndividual,
    VehicleProfile,
    _dominates,
    evaluate_capacity_solution,
)
from scripts.reproduce.run_benchmark import hypervolume_3d
from tests.test_model_contract import _make_instance


def _tiny_instance(model_version: str = "v2"):
    """Three damaged edges with slow undamaged bypasses.

    Every demand stays reachable before any repair, and the repair times
    straddle period boundaries, so repair order and crew assignment change when
    capacity becomes available rather than gating all service. Without that,
    all 3! x 2^3 encodings collapse onto a single objective vector.
    """
    return _make_instance(
        model_version=model_version,
        suppliers=[0],
        demands=[1, 2],
        # Supply exceeds what the always-reachable node can absorb, so the
        # remaining tonnage is stranded until node 1's road is repaired.
        supply_amounts={0: 80.0},
        demand_amounts={1: 100.0, 2: 20.0},
        edges=[
            (0, 2, 25.0, 10_000.0),  # node 2 is always reachable
            (0, 3, 20.0, 10_000.0),  # transit spur
            (0, 1, 10.0, 10_000.0),  # damaged: only short link to node 1
            (3, 1, 12.0, 10_000.0),  # damaged: alternate link to node 1
            (3, 2, 15.0, 10_000.0),  # damaged: shortcut to node 2
        ],
        # Repair times straddle the 480-minute period boundary, so the order
        # decides in which period node 1 becomes serviceable.
        damaged=[(0, 1, 300.0), (3, 1, 450.0), (3, 2, 500.0)],
        repair_crews=2,
        # Binary recovery with a full-recovery threshold: a damaged road is
        # genuinely impassable until its repair finishes.
        recovery_stages=BINARY_RECOVERY_STAGES,
        vehicles=[
            VehicleProfile(
                vehicle_type=1,
                capacity_ton=500.0,
                count=10,
                occupied_od_pcu_h=0.0,
                min_recovery_progress=1.0,
                pcu_per_vehicle=1.0,
            )
        ],
    )


def _decision(instance, order, teams, priority):
    return CapacityIndividual(list(order), list(teams), list(priority))


class ArchiveTest(unittest.TestCase):
    def test_all_evaluated_candidates_enter_the_archive(self):
        """A candidate the scalar score rejects still enters the archive."""
        better_scalar = CapacityIndividual(
            repair_order=[0], team_assignment=[0], dispatch_priority=[(0, 1)],
            objectives=(0.0, 10.0, 0.5),
        )
        non_dominated_but_worse_scalar = CapacityIndividual(
            repair_order=[1], team_assignment=[0], dispatch_priority=[(0, 1)],
            objectives=(10.0, 0.0, 0.5),
        )
        dominated = CapacityIndividual(
            repair_order=[2], team_assignment=[0], dispatch_priority=[(0, 1)],
            objectives=(20.0, 20.0, 0.5),
        )
        archive = _update_pareto_archive(
            [],
            [better_scalar, non_dominated_but_worse_scalar, dominated],
        )
        signatures = {tuple(item.repair_order) for item in archive}

        self.assertIn((0,), signatures)
        self.assertIn((1,), signatures)
        self.assertNotIn((2,), signatures)

    def test_archive_holds_clones_not_live_references(self):
        candidate = CapacityIndividual(
            repair_order=[0, 1],
            team_assignment=[0, 0],
            dispatch_priority=[(0, 1)],
            objectives=(1.0, 1.0, -0.5),
        )
        archive = _update_pareto_archive([], [candidate])
        # Mutating the caller's object afterwards must not rewrite history.
        candidate.repair_order.reverse()
        candidate.objectives = (99.0, 99.0, 99.0)
        self.assertEqual(archive[0].repair_order, [0, 1])
        self.assertEqual(archive[0].objectives, (1.0, 1.0, -0.5))

    def test_archive_hypervolume_never_regresses_with_more_evaluations(self):
        instance = _tiny_instance()
        rng = random.Random(11)
        priority = [(0, 1), (0, 2)]
        candidates = []
        for index in range(12):
            order = [0, 1, 2]
            rng.shuffle(order)
            teams = [rng.randrange(2) for _ in order]
            individual = _decision(instance, order, teams, priority)
            individual.objectives, individual.metrics = evaluate_capacity_solution(
                instance,
                individual,
            )
            candidates.append(individual)

        # One fixed reference point for every step, never recomputed from the
        # archive itself, so a shrinking front cannot be hidden by a moving
        # reference frame.
        reference = (
            max(c.objectives[0] for c in candidates) + 1.0,
            max(c.objectives[1] for c in candidates) + 1.0,
            1.0,
        )

        archive = []
        previous = -1.0
        for candidate in candidates:
            archive = _update_pareto_archive(archive, [candidate])
            points = [tuple(item.objectives) for item in archive]
            current = hypervolume_3d(points, reference)
            # Accumulating evaluated candidates must never lose ground.
            self.assertGreaterEqual(current, previous - 1e-12)
            previous = current


class EvaluatorAccountingTest(unittest.TestCase):
    def test_evaluator_counts_real_calls_hits_and_local_search(self):
        instance = _tiny_instance()
        evaluator = _Evaluator(instance, limit=3)
        priority = [(0, 1), (0, 2)]

        first = _decision(instance, [0, 1, 2], [0, 0, 0], priority)
        evaluator.evaluate(first)
        second = _decision(instance, [0, 2, 1], [0, 0, 0], priority)
        evaluator.evaluate(second, operator="swap", local_search=True)
        third = _decision(instance, [1, 0, 2], [0, 0, 0], priority)
        evaluator.evaluate(third)

        self.assertEqual(evaluator.count, 3)
        self.assertEqual(evaluator.remaining, 0)
        self.assertEqual(evaluator.local_search_evaluations, 1)
        self.assertEqual(evaluator.operator_proposals, {"swap": 1})

        # A cached objective is a hit, never a fresh evaluation.
        evaluator.evaluate(first)
        self.assertEqual(evaluator.count, 3)
        self.assertEqual(evaluator.diagnostics()["cache_hits"], 1.0)

        # The budget blocks further real evaluations but still counts proposals:
        # three real calls, one cached hit, one blocked proposal.
        fourth = _decision(instance, [2, 1, 0], [0, 0, 0], priority)
        self.assertFalse(evaluator.evaluate(fourth))
        self.assertEqual(evaluator.count, 3)
        self.assertIsNone(fourth.objectives)
        self.assertEqual(evaluator.diagnostics()["proposals"], 5.0)

        # Every decision that was really evaluated is archived.
        self.assertEqual(len(evaluator.archive_candidates()), 3)


class BudgetAndTerminationTest(unittest.TestCase):
    def test_budget_is_never_exceeded(self):
        instance = build_benchmark_instance(
            benchmark_specs("smoke")[0],
            instance_seed=1,
            model_version="v2",
        )
        budget = BenchmarkBudget(max_evaluations=24, pop_size=6, alns_iterations=2)
        for algorithm in ALGORITHMS:
            run = solve_benchmark_algorithm(algorithm, instance, budget, seed=99)
            self.assertLessEqual(run.evaluations, budget.max_evaluations, algorithm)
            self.assertGreaterEqual(len(run.front), 1, algorithm)
            if algorithm in {"nsga2", "nsga2_ls", "nsga2_alns"}:
                self.assertEqual(run.evaluations, budget.max_evaluations, algorithm)
                self.assertEqual(run.termination_reason, STOP_BUDGET_EXHAUSTED, algorithm)
            if algorithm == "spt":
                self.assertEqual(run.evaluations, 1)
                self.assertEqual(run.termination_reason, STOP_SINGLE_PASS)

    def test_no_progress_terminates_without_faking_the_budget(self):
        """crossover=0 with mutation=0 rebuilds only evaluated clones."""
        instance = build_benchmark_instance(
            benchmark_specs("smoke")[0],
            instance_seed=1,
            model_version="v2",
        )
        budget = BenchmarkBudget(
            max_evaluations=200,
            pop_size=4,
            crossover_probability=0.0,
            mutation_probability=0.0,
            alns_probability=0.0,
            alns_iterations=4,
        )
        run = solve_benchmark_algorithm("nsga2_alns", instance, budget, seed=5)

        self.assertEqual(run.termination_reason, STOP_NO_PROGRESS)
        # It stopped early honestly instead of inventing evaluations.
        self.assertLess(run.evaluations, budget.max_evaluations)
        self.assertEqual(run.evaluations, budget.pop_size)

    def test_closed_local_search_matches_plain_nsga(self):
        """Local search off must not consume randomness or change the archive."""
        for model_version in ("legacy", "v2"):
            instance = build_benchmark_instance(
                benchmark_specs("smoke")[0],
                instance_seed=1,
                model_version=model_version,
            )
            budget = BenchmarkBudget(
                max_evaluations=60,
                pop_size=8,
                alns_probability=0.0,
                alns_iterations=2,
            )
            plain = solve_benchmark_algorithm("nsga2", instance, budget, seed=7)
            hybrid = solve_benchmark_algorithm("nsga2_alns", instance, budget, seed=7)

            self.assertEqual(plain.evaluations, hybrid.evaluations, model_version)
            self.assertEqual(
                hybrid.diagnostics["local_search_evaluations"],
                0.0,
                model_version,
            )
            self.assertEqual(
                [tuple(i.objectives) for i in plain.front],
                [tuple(i.objectives) for i in hybrid.front],
                model_version,
            )

            # The same holds when iterations are zero but the probability is
            # positive: the local search must still not be entered.
            zero_iteration_budget = BenchmarkBudget(
                max_evaluations=60,
                pop_size=8,
                alns_probability=0.9,
                alns_iterations=0,
            )
            plain = solve_benchmark_algorithm("nsga2", instance, zero_iteration_budget, seed=7)
            hybrid = solve_benchmark_algorithm(
                "nsga2_alns", instance, zero_iteration_budget, seed=7
            )
            self.assertEqual(hybrid.diagnostics["local_search_evaluations"], 0.0)
            self.assertEqual(
                [tuple(i.objectives) for i in plain.front],
                [tuple(i.objectives) for i in hybrid.front],
            )


class ScoringTest(unittest.TestCase):
    def test_normalized_score_is_fixed_and_instance_level(self):
        instance = _tiny_instance(model_version="v2")
        individual = _decision(instance, [0, 1, 2], [0, 0, 0], [(0, 1), (0, 2)])
        individual.objectives, individual.metrics = evaluate_capacity_solution(
            instance,
            individual,
        )
        f1, f2, f3 = individual.objectives
        base = instance.base
        expected = (
            f1 / base.periods
            + f2
            / max(
                base.horizon_minutes * sum(v.count for v in instance.vehicles)
                + instance.repair_time_weight * base.repair_crews * base.horizon_minutes,
                1.0,
            )
            + (f3 + 1.0)
        ) / 3.0

        self.assertAlmostEqual(_normalized_score(instance, individual), expected, places=12)
        # Deterministic and independent of whatever else has been evaluated.
        self.assertEqual(
            _normalized_score(instance, individual),
            _normalized_score(instance, individual),
        )

    def test_normalized_score_depends_only_on_the_candidate_itself(self):
        """The scale is fixed by physical magnitude, not by the run's own front."""
        instance = _tiny_instance(model_version="v2")
        individual = _decision(instance, [0, 1, 2], [0, 0, 0], [(0, 1), (0, 2)])
        individual.objectives = (1.0, 1000.0, -0.5)
        score = _normalized_score(instance, individual)

        # A very different candidate in the same instance scores differently,
        # and neither score depends on the other having been evaluated.
        other = _decision(instance, [2, 1, 0], [1, 1, 1], [(0, 2), (0, 1)])
        other.objectives = (0.5, 100.0, -0.9)
        self.assertNotAlmostEqual(_normalized_score(instance, other), score)
        self.assertEqual(_normalized_score(instance, individual), score)

    def test_legacy_keeps_its_original_weighted_score(self):
        from scripts.reproduce.benchmark_algorithms import _score
        from scripts.reproduce.capacity_recovery import _weighted_score

        instance = _tiny_instance(model_version="legacy")
        individual = _decision(instance, [0, 1, 2], [0, 0, 0], [(0, 1), (0, 2)])
        individual.objectives = (2.0, 500.0, -0.25)

        # The scalar used for acceptance follows the instance's own profile.
        self.assertEqual(_score(instance, individual), _weighted_score(individual))
        self.assertNotEqual(
            _normalized_score(_tiny_instance(model_version="v2"), individual),
            _weighted_score(individual),
        )


class SelectorTest(unittest.TestCase):
    def test_uniform_and_adaptive_selection_modes(self):
        operators = _local_operators()
        rng = random.Random(3)

        uniform = _AdaptiveOperators(operators, adaptive=False)
        chosen = {uniform.choose(rng)[0] for _ in range(200)}
        self.assertGreater(len(chosen), 1, "uniform selection must not be stuck")
        uniform.reward(0, 5.0)
        self.assertEqual(uniform.weights, [1.0] * len(operators))

        adaptive = _AdaptiveOperators(operators, adaptive=True)
        adaptive.reward(0, 5.0)
        self.assertGreater(adaptive.weights[0], 1.0)
        self.assertEqual(adaptive.weights[1:], [1.0] * (len(operators) - 1))


class EnumeratedSubproblemTest(unittest.TestCase):
    """Reference over a finite repair-encoding subspace.

    With three damaged edges, two crews and a fixed dispatch priority the whole
    repair search space is 3! x 2^3 = 48 encodings. This is a reference for a
    fixed dispatch decoder, not a proof of global VRP optimality.
    """

    def test_enumeration_covers_subspace_and_matches_evaluation(self):
        instance = _tiny_instance(model_version="v2")
        damage_ids = sorted(instance.base.damaged_edges)
        self.assertEqual(len(damage_ids), 3)
        priority = [(0, 1), (0, 2)]

        decisions = []
        for permutation in _permutations(damage_ids):
            for crews in _team_assignments(len(damage_ids), instance.base.repair_crews):
                decisions.append(_decision(instance, permutation, crews, priority))
        self.assertEqual(len(decisions), 48)

        points = []
        for decision in decisions:
            objectives, _metrics = evaluate_capacity_solution(instance, decision)
            decision.objectives = objectives
            points.append((objectives, decision))

        non_dominated = [
            decision
            for objectives, decision in points
            if not any(
                _dominates(other_objectives, objectives)
                for other_objectives, other in points
                if other is not decision
            )
        ]
        self.assertGreater(len(non_dominated), 0)

        # Re-evaluating any enumerated decision reproduces its objectives: the
        # reference front is derived from the shared evaluator, not from a
        # parallel implementation.
        for decision in non_dominated:
            repeated, _metrics = evaluate_capacity_solution(instance, decision.clone())
            self.assertEqual(tuple(decision.objectives), tuple(repeated))

        # The archive of the enumerated subspace is exactly the pairwise
        # non-dominated set.
        archive = _update_pareto_archive([], [decision for _objectives, decision in points])
        self.assertEqual(
            sorted(tuple(item.objectives) for item in archive),
            sorted(tuple(item.objectives) for item in non_dominated),
        )

    def test_search_front_is_never_dominated_by_an_enumerated_decision(self):
        """NSGA-II may not return a point an enumerated encoding dominates."""
        instance = _tiny_instance(model_version="v2")
        damage_ids = sorted(instance.base.damaged_edges)
        priority = [(0, 1), (0, 2)]
        enumerated = []
        for permutation in _permutations(damage_ids):
            for crews in _team_assignments(len(damage_ids), instance.base.repair_crews):
                decision = _decision(instance, permutation, crews, priority)
                decision.objectives, _metrics = evaluate_capacity_solution(
                    instance,
                    decision,
                )
                enumerated.append(decision)

        budget = BenchmarkBudget(max_evaluations=200, pop_size=10, alns_iterations=3)
        run = solve_benchmark_algorithm("nsga2_alns", instance, budget, seed=13)
        for point in run.front:
            for reference in enumerated:
                self.assertFalse(
                    _dominates(reference.objectives, point.objectives),
                    "an exhaustive repair encoding dominates a returned front point",
                )


def _permutations(values):
    if len(values) <= 1:
        yield list(values)
        return
    for index, value in enumerate(values):
        rest = values[:index] + values[index + 1 :]
        for tail in _permutations(rest):
            yield [value, *tail]


def _team_assignments(size: int, crews: int):
    for mask in range(crews**size):
        digits = []
        remainder = mask
        for _ in range(size):
            digits.append(remainder % crews)
            remainder //= crews
        yield digits


if __name__ == "__main__":
    unittest.main()
