from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.ga_solver import GAConfig, solve_instance
from scripts.reproduce.instance_generator import generate_random_instance
from scripts.reproduce.model import SolutionResult
from scripts.reproduce.visualize import write_all_figures


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    nodes, gammas, damages, etas, seeds = resolve_experiment_grid(args)
    ga_config = GAConfig(
        pop_size=args.pop_size,
        generations=args.generations,
        crossover_probability=args.pc,
        mutation_probability=args.pm,
    )

    results: list[SolutionResult] = []
    total = len(nodes) * len(gammas) * len(damages) * len(etas) * len(seeds)
    run_idx = 0
    for num_nodes in nodes:
        for gamma in gammas:
            for damage_ratio in damages:
                for eta_hours in etas:
                    for seed in seeds:
                        run_idx += 1
                        instance = generate_random_instance(
                            num_nodes=num_nodes,
                            gamma=gamma,
                            damage_ratio=damage_ratio,
                            eta_hours=eta_hours,
                            seed=seed,
                            supply_ratio=args.supply_ratio,
                        )
                        print(f"[{run_idx}/{total}] Solving {instance.name}")
                        result = solve_instance(
                            instance,
                            ga_config,
                            seed=seed + args.ga_seed_offset,
                        )
                        results.append(result)
                        final = result.period_metrics[-1]
                        print(
                            "  "
                            f"fitness={result.fitness:.4f}, "
                            f"sat={final.total_satisfaction:.3f}, "
                            f"min_sat={final.minimum_satisfaction:.3f}, "
                            f"repair={final.repaired_ratio:.3f}, "
                            f"time={result.runtime_seconds:.2f}s"
                        )

    write_outputs(results, output_dir)
    write_all_figures(results, output_dir)
    print(f"Done. Results written to {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run random-instance reproduction experiments for MP-NRWSRLP.",
    )
    parser.add_argument("--config", choices=["quick", "full"], default="quick")
    parser.add_argument("--nodes", type=int, nargs="*", help="Override node counts.")
    parser.add_argument("--gamma", type=int, nargs="*", help="Override gamma values.")
    parser.add_argument("--damage", type=float, nargs="*", help="Override damage ratios.")
    parser.add_argument("--eta", type=int, nargs="*", help="Override eta values in hours.")
    parser.add_argument("--seeds", type=int, default=None, help="Number of sequential seeds.")
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--ga-seed-offset", type=int, default=10_000)
    parser.add_argument("--pop-size", type=int, default=100)
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--pc", type=float, default=0.9)
    parser.add_argument("--pm", type=float, default=0.1)
    parser.add_argument("--supply-ratio", type=float, default=0.8)
    parser.add_argument(
        "--output-dir",
        default="outputs/random_experiments",
        help="Directory for CSV, JSON, and figures.",
    )
    return parser.parse_args()


def resolve_experiment_grid(
    args: argparse.Namespace,
) -> tuple[list[int], list[int], list[float], list[int], list[int]]:
    if args.config == "quick":
        nodes = [25, 50, 100]
        gammas = [3, 4, 5]
        damages = [0.1, 0.3, 0.5]
        etas = [8, 12]
        seed_count = 1
    else:
        nodes = [25, 32, 50, 64, 100, 150, 200, 300, 400, 600, 800, 1000]
        gammas = [3, 4, 5]
        damages = [0.05, 0.1, 0.25, 0.3, 0.5]
        etas = [4, 8, 12, 24]
        seed_count = 30

    if args.nodes:
        nodes = args.nodes
    if args.gamma:
        gammas = args.gamma
    if args.damage:
        damages = args.damage
    if args.eta:
        etas = args.eta
    if args.seeds is not None:
        seed_count = args.seeds

    seeds = list(range(args.seed_start, args.seed_start + seed_count))
    return nodes, gammas, damages, etas, seeds


def write_outputs(results: list[SolutionResult], output_dir: Path) -> None:
    _write_csv(
        output_dir / "runs.csv",
        [result.summary_row() for result in results],
    )
    period_rows = [
        metric.__dict__
        for result in results
        for metric in result.period_metrics
    ]
    _write_csv(output_dir / "period_metrics.csv", period_rows)
    with (output_dir / "solutions.json").open("w", encoding="utf-8") as fh:
        json.dump(
            [result.to_jsonable() for result in results],
            fh,
            indent=2,
            ensure_ascii=False,
        )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()

