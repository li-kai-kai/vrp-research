#!/bin/sh
# Commands actually executed, from the repository root; output root belongs to this run.
set -eu
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -v > outputs/handoff_20260925/baseline_tests.log 2>&1
uv run --frozen python scripts/reproduce/run_benchmark.py --suite benchmark --cases WEN38 --instance-seeds 1 --model-version v2 --solver-repeats 2 --solver-seed-start 50000 --algorithms nsga2 --max-evaluations 500 --pop-size 32 --output-dir outputs/handoff_20260925/readiness/wen38_search
uv run --frozen python scripts/reproduce/run_model_ablation.py --suite benchmark --cases WEN38 --model-version v2 --algorithm nsga2 --model-ids PR1_HT1_EC1 PR0_HT1_EC1 PR1_HT0_EC1 PR1_HT1_EC0 --instance-seeds 1 --solver-repeats 2 --solver-seed-start 50000 --max-evaluations 500 --pop-size 32 --output-dir outputs/handoff_20260925/pilot/wen38
uv run --frozen python scripts/reproduce/mechanism_zone_search.py --suite benchmark --case S025 --instance-seeds 101 102 --scenario corridor --algorithm nsga2 --solver-repeats 2 --solver-seed-start 50000 --max-evaluations 500 --pop-size 32 --output-dir outputs/handoff_20260925/pilot/corridor
uv run --frozen python scripts/reproduce/research_readiness.py --historical-root outputs/claude_v2_reviewfix2/pilot_algorithm --search-root outputs/handoff_20260925/readiness/wen38_search --output-dir outputs/handoff_20260925/readiness/analysis
uv run --frozen python scripts/reproduce/common_execution_analysis.py --input-roots outputs/handoff_20260925/pilot/wen38 outputs/handoff_20260925/pilot/corridor --output-dir outputs/handoff_20260925/pilot/analysis --representative-traces
uv run --frozen python scripts/plot_common_execution.py --input-dir outputs/handoff_20260925/pilot/analysis --output-dir outputs/handoff_20260925/pilot/figures
uv run --frozen python -m unittest discover -s tests -v > outputs/handoff_20260925/tests.log 2>&1
