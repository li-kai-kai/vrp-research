# Repository Guidelines

## Project Structure & Module Organization

This Python research repository studies post-disaster road repair and relief logistics using the Wenchuan case, capacity recovery, and NSGA-II/ALNS optimization.

- `scripts/reproduce/`: shared models, scheduling, dispatch, solvers, benchmarks, and experiment entry points. Extend these modules instead of duplicating data or solver logic.
- `scripts/legacy/`: maintained ordinary-GA reference chain; shared instance/model modules remain in `scripts/reproduce/`.
- `scripts/plot_*.py`: network and experiment visualizations based on shared instances and measured outputs.
- `tests/`: regression tests for reproduction, benchmarks, and ablations.
- `docs/`: current `research.md`, `experiments.md`, and maintenance records; `background/` holds source notes and `archive/` historical documents.
- `references/`: retained source literature.
- `outputs/`: generated experiment artifacts, ignored by Git.

## Build, Test, and Development Commands

Run commands from the repository root with Python 3.12+ and `uv`:

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python scripts/legacy/run_random_experiments.py --config quick
uv run python scripts/reproduce/run_model_ablation.py --suite smoke --output-dir outputs/model_ablation_smoke
```

These install locked dependencies, run the test suite, execute a quick GA baseline, and exercise model-factor ablations, respectively. See `scripts/README.md` for capacity-recovery, dynamic-interaction, visualization, and publication experiment commands. There is no central application build step.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for modules/functions/variables, `PascalCase` for classes, and `UPPER_CASE` for constants. Follow existing type annotations and dataclass-based model definitions. Keep shared evaluation logic in `scripts/reproduce/`. No formatter or linter is currently configured; match nearby code and avoid unrelated formatting changes.

## Testing Guidelines

Use standard-library `unittest`, with files named `test_*.py`, `unittest.TestCase` subclasses, and methods named `test_*`. Add regression coverage for changed model constraints, objective calculations, or experiment aggregation. Use fixed seeds, small evaluation budgets, and temporary directories for generated files. Run the full suite before submitting code changes; no numerical coverage threshold is configured.

## Commit & Pull Request Guidelines

History mixes imperative subjects with `feat:` and `docs:` prefixes. Write concise, action-oriented subjects describing one coherent change. PRs should explain the research or implementation change, relevant assumptions, commands run, and results. Link related issues when applicable; include representative figures for visualization changes.

## Experiment Reproducibility

Preserve seeds, parameter manifests, and paired comparison budgets. Distinguish measured inputs from hypothetical stress parameters. Keep generated artifacts under `outputs/`, and update relevant documentation when model assumptions or reported conclusions change.
