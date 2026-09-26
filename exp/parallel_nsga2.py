#!/usr/bin/env python3
"""Formal full-budget parallel NSGA-II experiments for the ISPA 2026 paper (RQ3/RQ4).

Design (matches the paper's master-worker protocol):
  * The generational NSGA-II loop mirrors scripts/reproduce/benchmark_algorithms.py
    `_solve_nsga` (plain NSGA-II, no local search) with an identical RNG
    consumption order. The ONLY difference is that offspring evaluation is
    batched: a whole generation's offspring are created first, then evaluated
    either serially (workers=0) or by a ProcessPoolExecutor (workers>=1).
    Because evaluation consumes no RNG (local search is off), the serial path
    is bit-identical to the repository's own `solve_benchmark_algorithm`,
    including its objective-cache shortcut: an unmutated clone reuses its
    parent's objectives without consuming budget.
  * Workers are forked (Linux default) and share the parent-built instance via
    copy-on-write; no per-candidate instance rebuild. Task payloads are
    (index, repair_order, team_assignment, dispatch_priority) and results are
    reassembled by index, so the candidate order is invariant to scheduling.
  * Selection, crossover, mutation, RNG, archive and budget accounting stay
    centralized in the master process.

Outputs: results.json + results.csv under OUT_DIR.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(os.environ.get("VRP_RESEARCH_REPO", "/tmp/vrp-research"))
sys.path.insert(0, str(REPO))

from scripts.reproduce.benchmark_algorithms import (
    BenchmarkBudget,
    _crossover,
    _mutate,
    _select_next_generation,
    _tournament,
    _assign_rank_and_crowding,
    precision_for,
    solve_benchmark_algorithm,
)
from scripts.reproduce.benchmark_suite import build_benchmark_instance, benchmark_specs
from scripts.reproduce.capacity_recovery import (
    CapacityIndividual,
    _create_individual,
    evaluate_capacity_solution,
    update_pareto_archive,
)
from scripts.reproduce.objective_precision import V2_PRECISION
from scripts.reproduce.run_benchmark import pooled_quality_indicators

OUT_DIR = Path(__file__).resolve().parent / "full_budget"

# ---------------------------------------------------------------- worker side
# Forked workers inherit this from the parent (copy-on-write); the instance is
# built once per experiment, not once per candidate.
_WORKER_INSTANCE = None


def _encode(individual: CapacityIndividual, idx: int):
    return (
        idx,
        list(individual.repair_order),
        list(individual.team_assignment),
        [tuple(p) for p in individual.dispatch_priority],
    )


def _eval_chunk(chunk):
    """Evaluate one slice of a generation's offspring. Runs in a worker."""
    global _WORKER_INSTANCE
    out = []
    for idx, repair_order, team_assignment, dispatch_priority in chunk:
        ind = CapacityIndividual(repair_order, team_assignment, dispatch_priority)
        objectives, metrics = evaluate_capacity_solution(_WORKER_INSTANCE, ind)
        out.append((idx, tuple(objectives), dict(metrics)))
    return out


# ---------------------------------------------------------------- master side
def _solve_parallel_nsga2(
    case_id: str,
    instance_seed: int,
    solver_seed: int,
    max_evaluations: int,
    pop_size: int,
    workers: int,
) -> dict:
    """Faithful parallel re-implementation of the repo's plain NSGA-II.

    Returns wall-clock runtime, evaluation count, and the final front as a
    sorted list of raw objective triples.
    """
    global _WORKER_INSTANCE
    specs = {s.case_id: s for s in benchmark_specs("publication")}
    instance = build_benchmark_instance(
        specs[case_id], instance_seed=instance_seed, model_version="v2"
    )
    precision = precision_for(instance)
    budget = BenchmarkBudget(max_evaluations=max_evaluations, pop_size=pop_size)
    _WORKER_INSTANCE = instance

    rng = random.Random(solver_seed)
    remaining = max_evaluations
    evaluated: list[CapacityIndividual] = []
    cache_hits = 0

    def evaluate_batch(individuals: list[CapacityIndividual], executor) -> None:
        """Evaluate one batch; mirrors _Evaluator.evaluate minus bookkeeping.

        Only candidates with objectives is None reach this function (the
        repo's cache-hit shortcut is handled by the caller), so every item
        here consumes exactly one unit of budget -- but the budget was already
        reserved at creation time to keep the serial RNG order identical.
        """
        if not individuals:
            return
        if executor is None:
            for ind in individuals:
                ind.objectives, ind.metrics = evaluate_capacity_solution(instance, ind)
        else:
            n = len(individuals)
            chunks = [[] for _ in range(min(workers, n))]
            for i, ind in enumerate(individuals):
                chunks[i % len(chunks)].append(_encode(ind, i))
            results: dict[int, tuple] = {}
            for chunk_result in executor.map(_eval_chunk, chunks):
                for idx, objectives, metrics in chunk_result:
                    results[idx] = (objectives, metrics)
            assert len(results) == n, f"lost candidates: {len(results)} != {n}"
            for i, ind in enumerate(individuals):
                ind.objectives, ind.metrics = results[i]
        evaluated.extend(individuals)

    executor = (
        ProcessPoolExecutor(max_workers=workers) if workers and workers > 0 else None
    )
    start = time.perf_counter()
    try:
        initial_size = min(pop_size, remaining)
        population = [_create_individual(instance, rng) for _ in range(initial_size)]
        # Fresh individuals never hit the objective cache; mirror
        # _Evaluator.population's stop-on-exhaustion exactly.
        real_init: list[CapacityIndividual] = []
        for individual in population:
            if remaining <= 0:
                break
            real_init.append(individual)
            remaining -= 1
        population = real_init
        evaluate_batch(population, executor)

        stalled = 0
        previous_count = max_evaluations - remaining
        while remaining > 0 and len(population) >= 2:
            _assign_rank_and_crowding(population, precision)
            offspring: list[CapacityIndividual] = []
            to_evaluate: list[CapacityIndividual] = []
            while len(offspring) < pop_size and remaining > 0:
                parent_a = _tournament(population, rng)
                parent_b = _tournament(population, rng)
                if rng.random() < budget.crossover_probability:
                    children = _crossover(instance, parent_a, parent_b, rng)
                else:
                    children = (parent_a.clone(), parent_b.clone())
                for child in children:
                    _mutate(instance, child, budget.mutation_probability, rng)
                    if child.objectives is not None:
                        # Cache hit: an unmutated clone reuses its parent's
                        # objectives without consuming budget, exactly as
                        # _Evaluator.evaluate does.
                        cache_hits += 1
                        offspring.append(child)
                    elif remaining <= 0:
                        # _Evaluator.evaluate would return False: discard.
                        break
                    else:
                        # Reserve one budget unit now so the serial RNG order
                        # matches; the actual call is batched below.
                        remaining -= 1
                        offspring.append(child)
                        to_evaluate.append(child)
                    if len(offspring) >= pop_size or remaining <= 0:
                        break
            if not offspring:
                break
            evaluate_batch(to_evaluate, executor)
            population = _select_next_generation(
                population + offspring,
                min(pop_size, len(population) + len(offspring)),
                precision,
            )
            count = max_evaluations - remaining
            if count == previous_count:
                stalled += 1
                if stalled >= 3:  # MAX_STALLED_GENERATIONS in the repo
                    break
            else:
                stalled = 0
                previous_count = count
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
    runtime = time.perf_counter() - start

    front = update_pareto_archive([], evaluated, precision)
    objectives_sorted = sorted(tuple(ind.objectives) for ind in front)
    return {
        "case_id": case_id,
        "instance_seed": instance_seed,
        "solver_seed": solver_seed,
        "max_evaluations": max_evaluations,
        "pop_size": pop_size,
        "workers": workers,
        "runtime_seconds": runtime,
        "evaluations": len(evaluated),
        "cache_hits": cache_hits,
        "front_size": len(front),
        "front": [list(o) for o in objectives_sorted],
    }


def validate_fidelity() -> None:
    """The serial path must be bit-identical to the repo's own NSGA-II."""
    budget = BenchmarkBudget(max_evaluations=320, pop_size=16)
    specs = {s.case_id: s for s in benchmark_specs("publication")}
    instance = build_benchmark_instance(
        specs["WEN38"], instance_seed=1, model_version="v2"
    )
    run = solve_benchmark_algorithm("nsga2", instance, budget, seed=11)
    repo_front = sorted(
        tuple(ind.objectives) for ind in run.front
    )
    mine = _solve_parallel_nsga2("WEN38", 1, 11, 320, 16, workers=0)
    mine_front = [tuple(o) for o in mine["front"]]
    assert repo_front == mine_front, (
        f"fidelity check FAILED: repo front {len(repo_front)} vs mine {len(mine_front)}"
    )
    assert mine["evaluations"] == run.evaluations, (
        f"budget accounting differs: {mine['evaluations']} vs {run.evaluations}"
    )
    print(
        f"[validate] OK: serial path bit-identical to repo NSGA-II "
        f"(front={len(repo_front)}, evals={run.evaluations})",
        flush=True,
    )


def run_matrix() -> list[dict]:
    results: list[dict] = []
    # Union of configs; RQ3/RQ4 tables slice from this.
    # (case_id, max_evaluations, seeds, workers)
    configs = [
        ("WEN38", 1600, (11, 22, 33), (0, 1, 2, 4, 8)),  # RQ3 full matrix
        ("S025", 1600, (11, 22), (1, 2, 4, 8)),
        ("S050", 800, (11, 22), (1, 2, 4, 8)),
        ("M100", 400, (11, 22), (1, 2, 4, 8)),
    ]
    for case_id, max_evals, seeds, workers_list in configs:
        tag = "RQ3" if case_id == "WEN38" else "RQ4"
        for seed in seeds:
            for workers in workers_list:
                print(f"[{tag}] {case_id} seed={seed} workers={workers} ...", flush=True)
                results.append(
                    _solve_parallel_nsga2(case_id, 1, seed, max_evals, 32, workers)
                )
                print(
                    f"      -> {results[-1]['runtime_seconds']:.1f}s "
                    f"evals={results[-1]['evaluations']} "
                    f"front={results[-1]['front_size']}",
                    flush=True,
                )
    return results


def analyze(results: list[dict]) -> list[dict]:
    """Attach pooled HV/IGD per case and invariance deltas vs the serial run."""
    # Pool fronts per case across all seeds/workers for HV/IGD normalization.
    by_case: dict[str, list[dict]] = {}
    for row in results:
        by_case.setdefault(row["case_id"], []).append(row)
    for case_id, rows in by_case.items():
        fronts = [[tuple(o) for o in r["front"]] for r in rows]
        quality_rows, meta = pooled_quality_indicators(fronts, V2_PRECISION)
        for r, q in zip(rows, quality_rows):
            r["hypervolume"] = q["hypervolume"]
            r["igd"] = q["igd"]
        print(
            f"[pooled] {case_id}: reference_front={meta['reference_front_size']} "
            f"ideal={[round(v,3) for v in meta['ideal']]} "
            f"nadir={[round(v,3) for v in meta['nadir']]}",
            flush=True,
        )
    # Invariance: max |Delta objectives| of each run vs the serial (workers=0)
    # run with the same (case, seed). RQ4 has no workers=0; compare vs workers=1.
    ref: dict[tuple[str, int], list] = {}
    for r in results:
        key = (r["case_id"], r["solver_seed"])
        if r["workers"] == 0:
            ref[key] = r["front"]
    for r in results:
        key = (r["case_id"], r["solver_seed"])
        baseline = ref.get(key)
        if baseline is None:
            w1 = next(
                x for x in results
                if (x["case_id"], x["solver_seed"], x["workers"]) == (r["case_id"], r["solver_seed"], 1)
            )
            baseline = w1["front"]
        other = r["front"]
        if len(baseline) != len(other):
            r["max_abs_delta_vs_serial"] = math.inf
            r["front_identical_to_serial"] = False
        else:
            d = max(
                abs(a - b)
                for pa, pb in zip(baseline, other)
                for a, b in zip(pa, pb)
            )
            r["max_abs_delta_vs_serial"] = d
            r["front_identical_to_serial"] = d == 0.0
    return results


def save(results: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "results.json", "w") as f:
        json.dump(results, f, indent=1)
    fields = [
        "case_id", "solver_seed", "max_evaluations", "pop_size", "workers",
        "runtime_seconds", "evaluations", "cache_hits", "front_size",
        "hypervolume", "igd", "max_abs_delta_vs_serial",
        "front_identical_to_serial",
    ]
    with open(OUT_DIR / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in fields})
    print(f"[save] {OUT_DIR / 'results.json'}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    validate_fidelity()
    if args.validate_only:
        return
    results = run_matrix()
    results = analyze(results)
    save(results)
    # Console summary tables for the paper.
    print("\n=== RQ3 (WEN38, budget=1600, pop=32) ===")
    rq3 = [r for r in results if r["case_id"] == "WEN38" and r["solver_seed"] in (11, 22, 33) and r["max_evaluations"] == 1600]
    for r in sorted(rq3, key=lambda x: (x["solver_seed"], x["workers"])):
        print(
            f"seed={r['solver_seed']} W={r['workers']:>2} "
            f"t={r['runtime_seconds']:7.1f}s evals={r['evaluations']} "
            f"front={r['front_size']:>2} HV={r['hypervolume']:.4f} IGD={r['igd']:.4f} "
            f"identical={r['front_identical_to_serial']}",
            flush=True,
        )
    print("\n=== RQ4 (speedup vs W=1, mean over seeds 11,22) ===")
    from collections import defaultdict
    import statistics
    groups: dict[tuple[str, int], list[float]] = defaultdict(list)
    for r in results:
        if r["workers"] < 1 or r["solver_seed"] not in (11, 22):
            continue
        groups[(r["case_id"], r["workers"])].append(r["runtime_seconds"])
    base = {c: statistics.fmean(groups[(c, 1)]) for c in ("WEN38", "S025", "S050", "M100")}
    for c in ("WEN38", "S025", "S050", "M100"):
        row = f"{c:>6}: "
        for w in (1, 2, 4, 8):
            t = statistics.fmean(groups[(c, w)])
            row += f"W={w}: {t:7.1f}s ({base[c]/t:4.2f}x)  "
        print(row, flush=True)
    print("\n=== invariance ===")
    bad = [r for r in results if not r["front_identical_to_serial"]]
    print(f"non-identical fronts: {len(bad)} / {len(results)}", flush=True)


if __name__ == "__main__":
    main()
