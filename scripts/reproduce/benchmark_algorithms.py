from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable

import networkx as nx

from scripts.reproduce.capacity_recovery import (
    CapacityExperimentInstance,
    CapacityIndividual,
    _assign_crowding,
    _assign_rank_and_crowding,
    _crossover,
    _create_individual,
    _dominates,
    _insert_repair,
    _move_high_demand_priority,
    _mutate,
    _rebalance_team,
    _select_next_generation,
    _swap_two_dispatches,
    _swap_two_repairs,
    _tournament,
    _update_pareto_archive,
    _weighted_score,
    evaluate_capacity_solution,
)


ALGORITHMS = ("spt", "vnd", "nsga2", "nsga2_ls", "nsga2_alns")
STOCHASTIC_ALGORITHMS = frozenset({"vnd", "nsga2", "nsga2_ls", "nsga2_alns"})

# Search groups that wrap NSGA-II with local improvement.
LOCAL_SEARCH_ALGORITHMS = frozenset({"nsga2_ls", "nsga2_alns"})

# A generation that evaluates nothing new cannot make progress. Give up after a
# few of them instead of spinning on cached clones, and record why.
MAX_STALLED_GENERATIONS = 3

STOP_BUDGET_EXHAUSTED = "budget_exhausted"
STOP_NO_PROGRESS = "no_progress"
STOP_SINGLE_PASS = "single_pass"


@dataclass(frozen=True)
class BenchmarkBudget:
    max_evaluations: int
    pop_size: int
    crossover_probability: float = 0.90
    mutation_probability: float = 0.20
    alns_probability: float = 0.35
    alns_iterations: int = 4


@dataclass
class AlgorithmRun:
    algorithm: str
    front: list[CapacityIndividual]
    representative: CapacityIndividual
    runtime_seconds: float
    evaluations: int
    convergence: list[dict[str, float]] = field(default_factory=list)
    # Why the search stopped: "budget_exhausted", "no_progress", "single_pass".
    # Never claim a budget was used that was not.
    termination_reason: str = "budget_exhausted"
    # Search diagnostics counted separately from real evaluator calls.
    diagnostics: dict[str, float] = field(default_factory=dict)


class _Evaluator:
    """Single accounting point for every real objective evaluation.

    Every candidate that is actually evaluated is snapshotted here, including
    local-search trials and rejected candidates, so the returned front can be
    built from all evaluated candidates rather than only the one individual a
    local search happened to return.
    """

    def __init__(self, instance: CapacityExperimentInstance, limit: int):
        self.instance = instance
        self.limit = limit
        self.count = 0
        self.proposals = 0
        self.cache_hits = 0
        self.local_search_evaluations = 0
        self.operator_proposals: dict[str, int] = {}
        self.evaluated: list[CapacityIndividual] = []

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.count)

    def evaluate(
        self,
        individual: CapacityIndividual,
        *,
        operator: str | None = None,
        local_search: bool = False,
    ) -> bool:
        self.proposals += 1
        if operator is not None:
            self.operator_proposals[operator] = self.operator_proposals.get(operator, 0) + 1
        if individual.objectives is not None:
            # A cached objective is reused, not re-evaluated, and is never
            # reported as a fresh budgeted evaluation.
            self.cache_hits += 1
            return True
        if self.count >= self.limit:
            return False
        individual.objectives, individual.metrics = evaluate_capacity_solution(
            self.instance,
            individual,
        )
        self.count += 1
        if local_search:
            self.local_search_evaluations += 1
        # Snapshot the decision: later mutation of the caller's object must not
        # rewrite what was evaluated.
        self.evaluated.append(individual.clone())
        return True

    def population(self, population: list[CapacityIndividual]) -> list[CapacityIndividual]:
        evaluated: list[CapacityIndividual] = []
        for individual in population:
            if not self.evaluate(individual):
                break
            evaluated.append(individual)
        return evaluated

    def archive_candidates(self) -> list[CapacityIndividual]:
        """All distinct decisions actually evaluated, in evaluation order."""
        return list(self.evaluated)

    def diagnostics(self) -> dict[str, float]:
        return {
            "proposals": float(self.proposals),
            "evaluations": float(self.count),
            "cache_hits": float(self.cache_hits),
            "local_search_evaluations": float(self.local_search_evaluations),
            "distinct_evaluated": float(len(self.evaluated)),
        }


def solve_benchmark_algorithm(
    algorithm: str,
    instance: CapacityExperimentInstance,
    budget: BenchmarkBudget,
    *,
    seed: int,
) -> AlgorithmRun:
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm: {algorithm}")
    if budget.max_evaluations < 1:
        raise ValueError("max_evaluations must be positive")
    if budget.pop_size < 2:
        raise ValueError("pop_size must be at least 2")

    start = time.perf_counter()
    evaluator = _Evaluator(instance, budget.max_evaluations)
    rng = random.Random(seed)
    if algorithm == "spt":
        front, convergence = _solve_spt(instance, evaluator)
        termination_reason = STOP_SINGLE_PASS
    elif algorithm == "vnd":
        front, convergence, termination_reason = _solve_vnd(instance, evaluator, rng)
    else:
        # nsga2_ls uses the same operators, acceptance and call probability as
        # nsga2_alns but selects them uniformly instead of adapting weights, so
        # adaptive selection can be separated from local search itself.
        front, convergence, termination_reason = _solve_nsga(
            instance,
            evaluator,
            budget,
            rng,
            use_local_search=algorithm in LOCAL_SEARCH_ALGORITHMS,
            adaptive=algorithm == "nsga2_alns",
        )
    _assign_crowding(front)
    representative = min(front, key=_representative_key)
    return AlgorithmRun(
        algorithm=algorithm,
        front=front,
        representative=representative,
        runtime_seconds=time.perf_counter() - start,
        evaluations=evaluator.count,
        convergence=convergence,
        termination_reason=termination_reason,
        diagnostics=evaluator.diagnostics(),
    )


def _solve_spt(
    instance: CapacityExperimentInstance,
    evaluator: _Evaluator,
) -> tuple[list[CapacityIndividual], list[dict[str, float]]]:
    individual = _greedy_individual(instance)
    evaluator.evaluate(individual)
    return [individual], [_convergence_row(evaluator.count, individual)]


def _greedy_individual(instance: CapacityExperimentInstance) -> CapacityIndividual:
    base = instance.base
    repair_order = sorted(
        base.damaged_edges,
        key=lambda damage_id: (
            base.damaged_edges[damage_id].repair_time,
            damage_id,
        ),
    )
    team_free = [0.0] * base.repair_crews
    team_assignment: list[int] = []
    for damage_id in repair_order:
        team_id = min(range(base.repair_crews), key=lambda team: (team_free[team], team))
        team_assignment.append(team_id)
        team_free[team_id] += base.damaged_edges[damage_id].repair_time

    distance: dict[tuple[int, int], float] = {}
    for supplier in base.suppliers:
        lengths = nx.single_source_dijkstra_path_length(
            base.graph,
            supplier,
            weight="weight",
        )
        for demand in base.demands:
            distance[(supplier, demand)] = float(lengths.get(demand, math.inf))
    dispatch_priority = sorted(
        distance,
        key=lambda pair: (
            distance[pair],
            -base.demand_amounts[pair[1]],
            pair,
        ),
    )
    return CapacityIndividual(repair_order, team_assignment, dispatch_priority)


def _solve_vnd(
    instance: CapacityExperimentInstance,
    evaluator: _Evaluator,
    rng: random.Random,
) -> tuple[list[CapacityIndividual], list[dict[str, float]], str]:
    current = _greedy_individual(instance)
    evaluator.evaluate(current)
    convergence = [_convergence_row(evaluator.count, current)]
    operators = _local_operators()
    operator_idx = 0
    failures = 0
    termination_reason = STOP_BUDGET_EXHAUSTED
    while evaluator.remaining > 0:
        candidate = current.clone()
        operators[operator_idx](instance, candidate, rng)
        candidate.objectives = None
        candidate.metrics = None
        if not evaluator.evaluate(candidate, operator=operators[operator_idx].__name__):
            termination_reason = STOP_BUDGET_EXHAUSTED
            break
        if _accept_improvement(instance, candidate, current):
            current = candidate
            operator_idx = 0
            failures = 0
        else:
            operator_idx = (operator_idx + 1) % len(operators)
            failures += 1
            if failures >= len(operators) * 3 and evaluator.remaining > 0:
                # A small restart prevents VND from being trapped by the SPT seed.
                current = _create_individual(instance, rng)
                evaluator.evaluate(current)
                failures = 0
        convergence.append(
            _convergence_row(
                evaluator.count,
                min(evaluator.archive_candidates(), key=_representative_key),
            )
        )
    front = _archived_front(instance, evaluator)
    return front, convergence, termination_reason


def _solve_nsga(
    instance: CapacityExperimentInstance,
    evaluator: _Evaluator,
    budget: BenchmarkBudget,
    rng: random.Random,
    *,
    use_local_search: bool,
    adaptive: bool,
) -> tuple[list[CapacityIndividual], list[dict[str, float]], str]:
    initial_size = min(budget.pop_size, evaluator.remaining)
    population = [_create_individual(instance, rng) for _ in range(initial_size)]
    population = evaluator.population(population)
    convergence = [
        _convergence_row(
            evaluator.count,
            min(evaluator.archive_candidates(), key=_representative_key),
        )
    ]
    selector = _AdaptiveOperators(_local_operators(), adaptive=adaptive)
    # Local search is skipped entirely when it is switched off, so no operator
    # randomness is consumed and the evaluation sequence matches plain NSGA-II.
    local_search_enabled = (
        use_local_search
        and budget.alns_iterations > 0
        and budget.alns_probability > 0.0
    )
    termination_reason = STOP_BUDGET_EXHAUSTED
    stalled = 0
    previous_count = evaluator.count

    while evaluator.remaining > 0 and len(population) >= 2:
        _assign_rank_and_crowding(population)
        offspring: list[CapacityIndividual] = []
        while len(offspring) < budget.pop_size and evaluator.remaining > 0:
            parent_a = _tournament(population, rng)
            parent_b = _tournament(population, rng)
            if rng.random() < budget.crossover_probability:
                children = _crossover(instance, parent_a, parent_b, rng)
            else:
                children = (parent_a.clone(), parent_b.clone())
            for child in children:
                _mutate(instance, child, budget.mutation_probability, rng)
                if not evaluator.evaluate(child):
                    break
                if local_search_enabled and rng.random() < budget.alns_probability:
                    child = _adaptive_improve(
                        instance,
                        child,
                        evaluator,
                        selector,
                        budget.alns_iterations,
                        rng,
                    )
                offspring.append(child)
                if len(offspring) >= budget.pop_size or evaluator.remaining <= 0:
                    break
        if not offspring:
            break
        population = _select_next_generation(
            population + offspring,
            min(budget.pop_size, len(population) + len(offspring)),
        )
        convergence.append(
            _convergence_row(
                evaluator.count,
                min(evaluator.archive_candidates(), key=_representative_key),
            )
        )
        # A combination such as crossover=0 with mutation=0 rebuilds only
        # already-evaluated clones. Stop after a bounded number of such
        # generations instead of looping until the budget is faked.
        if evaluator.count == previous_count:
            stalled += 1
            if stalled >= MAX_STALLED_GENERATIONS:
                termination_reason = STOP_NO_PROGRESS
                break
        else:
            stalled = 0
            previous_count = evaluator.count
    if evaluator.remaining <= 0:
        termination_reason = STOP_BUDGET_EXHAUSTED
    front = _archived_front(instance, evaluator)
    return front, convergence, termination_reason


def _archived_front(
    instance: CapacityExperimentInstance,
    evaluator: _Evaluator,
) -> list[CapacityIndividual]:
    """Non-dominated front over every decision the run actually evaluated."""
    front = _update_pareto_archive([], evaluator.archive_candidates())
    if not front:
        raise RuntimeError("evaluator produced no candidates to archive")
    return front


Operator = Callable[[CapacityExperimentInstance, CapacityIndividual, random.Random], None]


def _local_operators() -> list[Operator]:
    return [
        _swap_two_repairs,
        _insert_repair,
        _rebalance_team,
        _swap_two_dispatches,
        _move_high_demand_priority,
    ]


class _AdaptiveOperators:
    """Operator chooser.

    ``adaptive=True`` keeps rewarded weights; ``adaptive=False`` picks uniformly
    and ignores rewards entirely, which is the nsga2_ls control.
    """

    def __init__(self, operators: list[Operator], *, adaptive: bool = True):
        self.operators = operators
        self.adaptive = adaptive
        self.weights = [1.0] * len(operators)

    def choose(self, rng: random.Random) -> tuple[int, Operator]:
        if self.adaptive:
            idx = rng.choices(range(len(self.operators)), weights=self.weights, k=1)[0]
        else:
            idx = rng.randrange(len(self.operators))
        return idx, self.operators[idx]

    def reward(self, idx: int, value: float, reaction: float = 0.20) -> None:
        if not self.adaptive:
            return
        self.weights[idx] = (1.0 - reaction) * self.weights[idx] + reaction * value


def _adaptive_improve(
    instance: CapacityExperimentInstance,
    initial: CapacityIndividual,
    evaluator: _Evaluator,
    adaptive: _AdaptiveOperators,
    iterations: int,
    rng: random.Random,
) -> CapacityIndividual:
    current = initial.clone()
    best = current.clone()
    temperature = max(abs(_score(instance, current)) * 0.02, 1e-6)
    for _ in range(iterations):
        if evaluator.remaining <= 0:
            break
        idx, operator = adaptive.choose(rng)
        candidate = current.clone()
        operator(instance, candidate, rng)
        candidate.objectives = None
        candidate.metrics = None
        # Local-search trials count against the same budget and are archived
        # like any other evaluated candidate.
        if not evaluator.evaluate(
            candidate,
            operator=operator.__name__,
            local_search=True,
        ):
            break
        delta = _score(instance, candidate) - _score(instance, current)
        accepted = _accept_improvement(instance, candidate, current)
        if not accepted and delta > 0:
            accepted = rng.random() < math.exp(-delta / max(temperature, 1e-9))
        if accepted:
            current = candidate
            if _accept_improvement(instance, candidate, best):
                best = candidate.clone()
                adaptive.reward(idx, 5.0)
            else:
                adaptive.reward(idx, 2.0)
        else:
            adaptive.reward(idx, 0.5)
        temperature *= 0.95
    return best


def _accept_improvement(
    instance: CapacityExperimentInstance,
    candidate: CapacityIndividual,
    incumbent: CapacityIndividual,
) -> bool:
    if candidate.objectives is None or incumbent.objectives is None:
        return False
    return _dominates(candidate.objectives, incumbent.objectives) or (
        _score(instance, candidate) < _score(instance, incumbent)
    )


def _score(instance: CapacityExperimentInstance, individual: CapacityIndividual) -> float:
    """Scalar used only by scalar-dependent acceptance logic.

    Outer NSGA-II still ranks by non-dominance and crowding distance.
    """
    if instance.evaluation.model_version == "v2":
        return _normalized_score(instance, individual)
    return _weighted_score(individual)


def _normalized_score(
    instance: CapacityExperimentInstance,
    individual: CapacityIndividual,
) -> float:
    """Deterministic, instance-level normalized score.

    The scale is fixed by physical magnitudes and known before the run starts.
    It never uses the run's own ideal or nadir points, so a run cannot make its
    own candidates look better by having explored badly. Record the raw
    objectives alongside it: this scale may be loose.
    """
    objectives = individual.objectives
    if objectives is None:
        return math.inf
    base = instance.base
    periods = max(base.periods, 1)
    fleet_size = sum(vehicle.count for vehicle in instance.vehicles)
    horizon_minutes = float(base.horizon_minutes)
    f1 = objectives[0] / periods
    denominator = max(
        horizon_minutes * fleet_size
        + instance.repair_time_weight * base.repair_crews * horizon_minutes,
        1.0,
    )
    f2 = objectives[1] / denominator
    f3 = objectives[2] + 1.0
    return (f1 + f2 + f3) / 3.0


def _representative_key(individual: CapacityIndividual) -> tuple[float, float, float]:
    objectives = individual.objectives or (math.inf, math.inf, math.inf)
    return objectives[2], objectives[0], objectives[1]


def _convergence_row(evaluations: int, individual: CapacityIndividual) -> dict[str, float]:
    objectives = individual.objectives or (math.inf, math.inf, math.inf)
    metrics = individual.metrics or {}
    return {
        "evaluations": float(evaluations),
        "unmet_area": objectives[0],
        "time_cost": objectives[1],
        "neg_min_satisfaction": objectives[2],
        "final_total_satisfaction": metrics.get("final_total_satisfaction", 0.0),
        "final_min_satisfaction": metrics.get("final_min_satisfaction", 0.0),
    }
