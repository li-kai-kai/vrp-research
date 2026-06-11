from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import TypeVar

from scripts.reproduce.metrics import evaluate_solution
from scripts.reproduce.model import RandomInstance, SolutionResult

T = TypeVar("T")


@dataclass(frozen=True)
class GAConfig:
    pop_size: int = 100
    generations: int = 100
    crossover_probability: float = 0.9
    mutation_probability: float = 0.1
    tournament_size: int = 3


@dataclass
class Individual:
    repair_order: list[int]
    team_assignment: list[int]
    dispatch_priority: list[tuple[int, int]]
    fitness: float | None = None


def solve_instance(
    instance: RandomInstance,
    config: GAConfig,
    *,
    seed: int,
) -> SolutionResult:
    rng = random.Random(seed)
    population = [_create_individual(instance, rng) for _ in range(config.pop_size)]
    convergence: list[float] = []
    start = time.perf_counter()

    for _ in range(config.generations):
        _evaluate_population(instance, population)
        population.sort(key=lambda item: item.fitness if item.fitness is not None else -1e99, reverse=True)
        convergence.append(population[0].fitness or 0.0)

        offspring: list[Individual] = []
        elite_count = max(1, config.pop_size // 10)
        offspring.extend(_clone(individual) for individual in population[:elite_count])
        while len(offspring) < config.pop_size:
            parent_a = _tournament(population, config.tournament_size, rng)
            parent_b = _tournament(population, config.tournament_size, rng)
            if rng.random() < config.crossover_probability:
                child_a, child_b = _crossover(instance, parent_a, parent_b, rng)
            else:
                child_a, child_b = _clone(parent_a), _clone(parent_b)
            _mutate(instance, child_a, config.mutation_probability, rng)
            _mutate(instance, child_b, config.mutation_probability, rng)
            offspring.append(child_a)
            if len(offspring) < config.pop_size:
                offspring.append(child_b)
        population = offspring

    _evaluate_population(instance, population)
    best = max(population, key=lambda item: item.fitness if item.fitness is not None else -1e99)
    result = evaluate_solution(
        instance,
        best.repair_order,
        best.team_assignment,
        best.dispatch_priority,
    )
    result.runtime_seconds = time.perf_counter() - start
    result.convergence = convergence
    return result


def _create_individual(instance: RandomInstance, rng: random.Random) -> Individual:
    repair_order = list(instance.damaged_edges)
    rng.shuffle(repair_order)
    team_assignment = [
        rng.randrange(instance.repair_crews)
        for _ in repair_order
    ]
    dispatch_priority = [
        (supplier, demand)
        for supplier in instance.suppliers
        for demand in instance.demands
    ]
    rng.shuffle(dispatch_priority)
    return Individual(
        repair_order=repair_order,
        team_assignment=team_assignment,
        dispatch_priority=dispatch_priority,
    )


def _evaluate_population(instance: RandomInstance, population: list[Individual]) -> None:
    for individual in population:
        if individual.fitness is None:
            individual.fitness = evaluate_solution(
                instance,
                individual.repair_order,
                individual.team_assignment,
                individual.dispatch_priority,
            ).fitness


def _tournament(
    population: list[Individual],
    tournament_size: int,
    rng: random.Random,
) -> Individual:
    competitors = rng.sample(population, min(tournament_size, len(population)))
    return max(competitors, key=lambda item: item.fitness if item.fitness is not None else -1e99)


def _crossover(
    instance: RandomInstance,
    parent_a: Individual,
    parent_b: Individual,
    rng: random.Random,
) -> tuple[Individual, Individual]:
    child_a_order = _ordered_crossover(parent_a.repair_order, parent_b.repair_order, rng)
    child_b_order = _ordered_crossover(parent_b.repair_order, parent_a.repair_order, rng)
    child_a_dispatch = _ordered_crossover(parent_a.dispatch_priority, parent_b.dispatch_priority, rng)
    child_b_dispatch = _ordered_crossover(parent_b.dispatch_priority, parent_a.dispatch_priority, rng)
    child_a_team = _uniform_team_crossover(parent_a.team_assignment, parent_b.team_assignment, rng)
    child_b_team = _uniform_team_crossover(parent_b.team_assignment, parent_a.team_assignment, rng)
    return (
        Individual(child_a_order, [team % instance.repair_crews for team in child_a_team], child_a_dispatch),
        Individual(child_b_order, [team % instance.repair_crews for team in child_b_team], child_b_dispatch),
    )


def _ordered_crossover(parent_a: list[T], parent_b: list[T], rng: random.Random) -> list[T]:
    size = len(parent_a)
    if size < 2:
        return list(parent_a)
    left, right = sorted(rng.sample(range(size), 2))
    child: list[T | None] = [None] * size
    child[left:right] = parent_a[left:right]
    fill_values = [value for value in parent_b if value not in child]
    fill_idx = 0
    for idx, value in enumerate(child):
        if value is None:
            child[idx] = fill_values[fill_idx]
            fill_idx += 1
    return [value for value in child if value is not None]


def _uniform_team_crossover(
    parent_a: list[int],
    parent_b: list[int],
    rng: random.Random,
) -> list[int]:
    return [
        team_a if rng.random() < 0.5 else team_b
        for team_a, team_b in zip(parent_a, parent_b)
    ]


def _mutate(
    instance: RandomInstance,
    individual: Individual,
    mutation_probability: float,
    rng: random.Random,
) -> None:
    if rng.random() < mutation_probability:
        _swap_two(individual.repair_order, rng)
        individual.fitness = None
    if rng.random() < mutation_probability:
        _swap_two(individual.dispatch_priority, rng)
        individual.fitness = None
    if rng.random() < mutation_probability and individual.team_assignment:
        idx = rng.randrange(len(individual.team_assignment))
        individual.team_assignment[idx] = rng.randrange(instance.repair_crews)
        individual.fitness = None


def _swap_two(values: list[T], rng: random.Random) -> None:
    if len(values) < 2:
        return
    left, right = rng.sample(range(len(values)), 2)
    values[left], values[right] = values[right], values[left]


def _clone(individual: Individual) -> Individual:
    return Individual(
        repair_order=list(individual.repair_order),
        team_assignment=list(individual.team_assignment),
        dispatch_priority=list(individual.dispatch_priority),
        fitness=individual.fitness,
    )

