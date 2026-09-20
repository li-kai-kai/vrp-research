"""R2: one directory holds exactly one experiment."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.reproduce.benchmark_algorithms import BenchmarkBudget
from scripts.reproduce.run_benchmark import main as run_benchmark_main
from scripts.reproduce.run_model_ablation import run_model_ablation
from scripts.reproduce.solution_io import RunStore, SolutionIOError


def _benchmark_argv(output_dir: Path, *, model_version="v2", budget=12, pop_size=4,
                    algorithms=("nsga2",), extra=()):
    return [
        "run_benchmark.py",
        "--suite", "smoke",
        "--cases", "S020",
        "--instance-seeds", "101",
        "--model-version", model_version,
        "--solver-repeats", "1",
        "--algorithms", *algorithms,
        "--max-evaluations", str(budget),
        "--pop-size", str(pop_size),
        "--output-dir", str(output_dir),
        *extra,
    ]


def _run_benchmark(argv, *, resume=False):
    import sys

    saved = sys.argv
    sys.argv = list(argv) + (["--resume"] if resume else [])
    try:
        run_benchmark_main()
    finally:
        sys.argv = saved


class ExperimentContractTest(unittest.TestCase):
    def test_contract_is_written_and_lists_its_variation(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "exp"
            _run_benchmark(_benchmark_argv(output_dir))

            contract = json.loads((output_dir / "experiment_contract.json").read_text())
            self.assertEqual(contract["fixed"]["model_version"], "v2")
            self.assertEqual(contract["fixed"]["budget"]["max_evaluations"], 12)
            self.assertEqual(contract["fixed"]["entry_point"], "run_benchmark")
            self.assertIn("source_fingerprint", contract["fixed"])
            self.assertIn("algorithms", contract["varying"])

    def test_switching_model_version_in_one_directory_is_refused(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "exp"
            _run_benchmark(_benchmark_argv(output_dir, model_version="legacy"))

            runs_before = sorted(path.name for path in (output_dir / "runs").glob("*.json"))
            contract_before = (output_dir / "experiment_contract.json").read_text()

            with self.assertRaises(SolutionIOError) as caught:
                _run_benchmark(_benchmark_argv(output_dir, model_version="v2"))
            self.assertIn("model_version", str(caught.exception))

            # The rejected run must not have touched anything.
            self.assertEqual(
                sorted(path.name for path in (output_dir / "runs").glob("*.json")),
                runs_before,
            )
            self.assertEqual(
                (output_dir / "experiment_contract.json").read_text(),
                contract_before,
            )

    def test_changing_the_budget_in_one_directory_is_refused(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "exp"
            _run_benchmark(_benchmark_argv(output_dir, budget=12))

            runs_before = sorted(path.name for path in (output_dir / "runs").glob("*.json"))
            with self.assertRaises(SolutionIOError) as caught:
                _run_benchmark(_benchmark_argv(output_dir, budget=20))
            self.assertIn("budget", str(caught.exception))

            # Refused before writing, so no run was appended and no snapshot
            # was overwritten.
            self.assertEqual(
                sorted(path.name for path in (output_dir / "runs").glob("*.json")),
                runs_before,
            )

    def test_identical_configuration_resumes_without_duplicates(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "exp"
            argv = _benchmark_argv(output_dir)
            _run_benchmark(argv)
            first = sorted(path.name for path in (output_dir / "runs").glob("*.json"))

            _run_benchmark(argv, resume=True)
            second = sorted(path.name for path in (output_dir / "runs").glob("*.json"))

            self.assertEqual(first, second)

            manifest = json.loads((output_dir / "experiment_manifest.json").read_text())
            self.assertEqual(manifest["resumed_runs"], 1)
            self.assertEqual(manifest["runs_in_directory"], 1)
            self.assertEqual(manifest["runs_this_invocation"], 1)

    def test_declared_variation_may_grow_the_same_experiment(self):
        """Adding an algorithm is a declared dimension, not a new experiment."""
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "exp"
            _run_benchmark(_benchmark_argv(output_dir, algorithms=("nsga2",)))
            _run_benchmark(_benchmark_argv(output_dir, algorithms=("nsga2", "nsga2_ls")))

            contract = json.loads((output_dir / "experiment_contract.json").read_text())
            self.assertEqual(contract["varying"]["algorithms"], ["nsga2", "nsga2_ls"])

            # Summaries cover the whole directory, so the newly added run is
            # present and replay reads exactly the same set.
            summaries = (output_dir / "runs.csv").read_text().splitlines()
            self.assertEqual(len(summaries) - 1, 2)
            self.assertEqual(len(RunStore(output_dir).load_runs_for_experiment()), 2)

    def test_summaries_and_replay_see_the_same_run_set(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "exp"
            _run_benchmark(_benchmark_argv(output_dir, algorithms=("nsga2",)))
            _run_benchmark(
                _benchmark_argv(output_dir, algorithms=("nsga2", "nsga2_ls")), resume=True
            )

            import csv

            with (output_dir / "runs.csv").open(newline="", encoding="utf-8") as handle:
                summary_keys = {row["run_key"] for row in csv.DictReader(handle)}
            replay_keys = {
                record["run_key"]
                for record in RunStore(output_dir).load_runs_for_experiment()
            }
            manifest = json.loads((output_dir / "experiment_manifest.json").read_text())
            self.assertEqual(summary_keys, replay_keys)
            self.assertEqual(manifest["runs_in_directory"], len(replay_keys))

    def test_ablation_treats_the_solver_as_fixed(self):
        budget = BenchmarkBudget(max_evaluations=8, pop_size=4, alns_iterations=1)
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "abl"
            run_model_ablation(
                suite="smoke",
                cases=["S020"],
                instance_seeds=[1],
                solver_repeats=1,
                output_dir=output_dir,
                budget=budget,
                model_version="v2",
                algorithm="nsga2",
                model_ids=["PR1_HT1_EC1", "PR1_HT1_EC0"],
            )
            with self.assertRaises(SolutionIOError) as caught:
                run_model_ablation(
                    suite="smoke",
                    cases=["S020"],
                    instance_seeds=[1],
                    solver_repeats=1,
                    output_dir=output_dir,
                    budget=budget,
                    model_version="v2",
                    algorithm="nsga2_alns",
                    model_ids=["PR1_HT1_EC1", "PR1_HT1_EC0"],
                )
            self.assertIn("algorithm", str(caught.exception))

    def test_ablation_may_extend_its_declared_model_group(self):
        """The four-model subset is a declared variation, not a new experiment."""
        budget = BenchmarkBudget(max_evaluations=8, pop_size=4, alns_iterations=1)
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "abl"
            common = dict(
                suite="smoke",
                cases=["S020"],
                instance_seeds=[1],
                solver_repeats=1,
                output_dir=output_dir,
                budget=budget,
                model_version="v2",
                algorithm="nsga2",
            )
            # Two groups first, then the full four-group diagnostic.
            run_model_ablation(
                model_ids=["PR1_HT1_EC1", "PR0_HT1_EC1"],
                **common,
            )
            run_model_ablation(
                model_ids=["PR1_HT1_EC1", "PR0_HT1_EC1", "PR1_HT0_EC1", "PR1_HT1_EC0"],
                **common,
            )

            contract = json.loads((output_dir / "experiment_contract.json").read_text())
            self.assertEqual(
                contract["varying"]["model_ids"],
                ["PR0_HT1_EC1", "PR1_HT0_EC1", "PR1_HT1_EC0", "PR1_HT1_EC1"],
            )
            records = RunStore(output_dir).load_runs_for_experiment()
            self.assertEqual(len(records), 4)
            # One shared physical scenario across every planning group.
            self.assertEqual(
                len({record["physical_instance_hash"] for record in records}), 1
            )

    def test_source_fingerprint_covers_dependencies(self):
        from scripts.reproduce.run_benchmark import SOURCE_FILES

        self.assertIn("uv.lock", SOURCE_FILES)
        self.assertIn("pyproject.toml", SOURCE_FILES)
        self.assertIn("scripts/reproduce/objective_precision.py", SOURCE_FILES)


if __name__ == "__main__":
    unittest.main()
