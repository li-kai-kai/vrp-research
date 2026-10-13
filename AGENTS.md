# Repository Guidelines

This branch contains the v2 post-disaster road-recovery research and parallel NSGA-II experiments.

- `scripts/reproduce/`: shared model, instances, solvers, replay, mechanism and budget analysis. Extend shared modules; do not duplicate evaluators.
- `scripts/plot_*.py`: figures generated from retained analysis outputs.
- `exp/`: parallel evaluation and frozen 136-run evidence.
- `outputs/`: final evidence sets listed in `docs/experiments.md`. Preserve measured values and original provenance.
- `docs/`: current scope, contracts, reports and evidence index.
- `references/`: retained source literature.
- `tests/`: current model and reproducibility regressions.

Run commands from the repository root; `scripts/README.md` lists the current entry points.

Use Python 3.12+ and `uv sync --frozen`. Run `uv run python -m unittest discover -s tests -v` after code changes, plus relevant smoke or replay checks. Use fixed seeds and small budgets for regression tests. Parallel experiments require Linux/WSL fork.

Only v2 semantics are supported. Raw numerical comparison may be used as a precision-test control only. Keep v2 serialization and fingerprints stable unless changing the research protocol explicitly.

Use four-space indentation, snake_case functions and PascalCase classes. Keep paired budgets, instance seeds and solver seeds explicit. Do not alter historical manifests or replace saved results with new measurements. New experiments use new directories.

Commit messages should describe the concrete change. Report validation and distinguish implementation, diagnostic evidence, measured timing, convergence and statistical claims.
