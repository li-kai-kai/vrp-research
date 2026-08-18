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


ALGORITHMS = ("spt", "vnd", "nsga2", "nsga2_alns")
STOCHASTIC_ALGORITHMS = frozenset({"vnd", "nsga2", "nsga2_alns"})


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


class _Evaluator:
    def __init__(self, instance: CapacityExperimentInstance, limit: int):
        self.instance = instance
        self.limit = limit
        self.count = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.count)

    def evaluate(self, individual: CapacityIndividual) -> bool:
        if individual.objectives is not None:
            return True
        if self.count >= self.limit:
            return False
        individual.objectives, individual.metrics = evaluate_capacity_solution(
            self.instance,
            individual,
        )
        self.count += 1
        return True

    def population(self, population: list[CapacityIndividual]) -> list[CapacityIndividual]:
        evaluated: list[CapacityIndividual] = []
        for individual in population:
            if not self.evaluate(individual):
                break
            evaluated.append(individual)
        return evaluated


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
    elif algorithm == "vnd":
        front, convergence = _solve_vnd(instance, evaluator, rng)
    else:
        front, convergence = _solve_nsga(
            instance,
            evaluator,
            budget,
            rng,
            use_alns=algorithm == "nsga2_alns",
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
) -> tuple[list[CapacityIndividual], list[dict[str, float]]]:
    current = _greedy_individual(instance)
    evaluator.evaluate(current)
    archive = [current.clone()]
    convergence = [_convergence_row(evaluator.count, current)]
    operators = _local_operators()
    operator_idx = 0
    failures = 0
    while evaluator.remaining > 0:
        candidate = current.clone()
        operators[operator_idx](instance, candidate, rng)
        candidate.objectives = None
        candidate.metrics = None
        evaluator.evaluate(candidate)
        archive = _update_pareto_archive(archive, [candidate])
        if _accept_improvement(candidate, current):
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
                archive = _update_pareto_archive(archive, [current])
                failures = 0
        convergence.append(_convergence_row(evaluator.count, min(archive, key=_representative_key)))
    return archive, convergence


def _solve_nsga(
    instance: CapacityExperimentInstance,
    evaluator: _Evaluator,
    budget: BenchmarkBudget,
    rng: random.Random,
    *,
    use_alns: bool,
) -> tuple[list[CapacityIndividual], list[dict[str, float]]]:
    initial_size = min(budget.pop_size, evaluator.remaining)
    population = [_create_individual(instance, rng) for _ in range(initial_size)]
    population = evaluator.population(population)
    archive = _update_pareto_archive([], population)
    convergence = [_convergence_row(evaluator.count, min(archive, key=_representative_key))]
    alns = _AdaptiveOperators(_local_operators())

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
                if use_alns and rng.random() < budget.alns_probability:
                    child = _adaptive_improve(
                        instance,
                        child,
                        evaluator,
                        alns,
                        budget.alns_iterations,
                        rng,
                    )
                offspring.append(child)
                if len(offspring) >= budget.pop_size or evaluator.remaining <= 0:
                    break
        if not offspring:
            break
        archive = _update_pareto_archive(archive, population + offspring)
        population = _select_next_generation(
            population + offspring,
            min(budget.pop_size, len(population) + len(offspring)),
        )
        convergence.append(
            _convergence_row(evaluator.count, min(archive, key=_representative_key))
        )
    return archive, convergence


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
    def __init__(self, operators: list[Operator]):
        self.operators = operators
        self.weights = [1.0] * len(operators)

    def choose(self, rng: random.Random) -> tuple[int, Operator]:
        idx = rng.choices(range(len(self.operators)), weights=self.weights, k=1)[0]
        return idx, self.operators[idx]

    def reward(self, idx: int, value: float, reaction: float = 0.20) -> None:
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
    temperature = max(abs(_weighted_score(current)) * 0.02, 1e-6)
    for _ in range(iterations):
        if evaluator.remaining <= 0:
            break
        idx, operator = adaptive.choose(rng)
        candidate = current.clone()
        operator(instance, candidate, rng)
        candidate.objectives = None
        candidate.metrics = None
        evaluator.evaluate(candidate)
        delta = _weighted_score(candidate) - _weighted_score(current)
        accepted = _accept_improvement(candidate, current)
        if not accepted and delta > 0:
            accepted = rng.random() < math.exp(-delta / max(temperature, 1e-9))
        if accepted:
            current = candidate
            if _accept_improvement(candidate, best):
                best = candidate.clone()
                adaptive.reward(idx, 5.0)
            else:
                adaptive.reward(idx, 2.0)
        else:
            adaptive.reward(idx, 0.5)
        temperature *= 0.95
    return best


def _accept_improvement(candidate: CapacityIndividual, incumbent: CapacityIndividual) -> bool:
    if candidate.objectives is None or incumbent.objectives is None:
        return False
    return _dominates(candidate.objectives, incumbent.objectives) or (
        _weighted_score(candidate) < _weighted_score(incumbent)
    )


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
