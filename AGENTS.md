# Repository Guidelines

This branch contains only the current v2 post-disaster road-recovery research and parallel NSGA-II paper.

- `scripts/reproduce/`: shared model, instances, solvers, replay, mechanism and budget analysis. Extend shared modules; do not duplicate evaluators.
- `exp/`: parallel evaluation and frozen 136-run evidence.
- `outputs/`: final evidence sets listed in `docs/experiments.md`. Preserve measured values and original provenance.
- `paper/ispa2026/`: editable paper and data-generated tables.
- `docs/`: current scope, contracts, reports and consolidation record.
- `tests/`: current model and reproducibility regressions.

Use Python 3.12+ and `uv sync --frozen`. Run `uv run python -m unittest discover -s tests -v` after code changes, plus relevant smoke or replay checks. Use fixed seeds and small budgets for regression tests. Parallel experiments require Linux/WSL fork.

Only v2 semantics are supported. Do not reintroduce retired GA, dynamic or evaluation paths. Raw numerical comparison may be used as a precision-test control only. Keep v2 serialization and fingerprints stable unless changing the research protocol explicitly.

Use four-space indentation, snake_case functions and PascalCase classes. Keep paired budgets, instance seeds and solver seeds explicit. Do not alter historical manifests or replace saved results with new measurements. New experiments use new directories.

Commit messages should describe the concrete change. Report validation and distinguish implementation, diagnostic evidence, measured timing, convergence and statistical claims.
