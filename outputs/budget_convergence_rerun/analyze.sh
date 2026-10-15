# Pre-declared analysis invocation for the re-run ladder.
uv run --frozen python scripts/reproduce/budget_convergence_analysis.py \
  --input-roots \
  outputs/budget_convergence_rerun/budget_500/seed_60000 \
  outputs/budget_convergence_rerun/budget_500/seed_60001 \
  outputs/budget_convergence_rerun/budget_500/seed_60002 \
  outputs/budget_convergence_rerun/budget_500/seed_60003 \
  outputs/budget_convergence_rerun/budget_500/seed_60004 \
  outputs/budget_convergence_rerun/budget_2000/seed_60000 \
  outputs/budget_convergence_rerun/budget_2000/seed_60001 \
  outputs/budget_convergence_rerun/budget_2000/seed_60002 \
  outputs/budget_convergence_rerun/budget_2000/seed_60003 \
  outputs/budget_convergence_rerun/budget_2000/seed_60004 \
  outputs/budget_convergence_rerun/budget_5000/seed_60000 \
  outputs/budget_convergence_rerun/budget_5000/seed_60001 \
  outputs/budget_convergence_rerun/budget_5000/seed_60002 \
  outputs/budget_convergence_rerun/budget_5000/seed_60003 \
  outputs/budget_convergence_rerun/budget_5000/seed_60004 \
  outputs/budget_convergence_rerun/budget_10000/seed_60000 \
  outputs/budget_convergence_rerun/budget_10000/seed_60001 \
  outputs/budget_convergence_rerun/budget_10000/seed_60002 \
  outputs/budget_convergence_rerun/budget_10000/seed_60003 \
  outputs/budget_convergence_rerun/budget_10000/seed_60004 \
  --protocol outputs/budget_convergence_rerun/protocol.json \
  --output-dir outputs/budget_convergence_rerun/analysis \
  --representative-traces

# Phase 2 analysis (all five budgets, 100 runs; phase-1 result preserved in analysis_phase1/).
uv run --frozen python scripts/reproduce/budget_convergence_analysis.py \
  --input-roots \
  outputs/budget_convergence_rerun/budget_500/seed_60000 \
  outputs/budget_convergence_rerun/budget_500/seed_60001 \
  outputs/budget_convergence_rerun/budget_500/seed_60002 \
  outputs/budget_convergence_rerun/budget_500/seed_60003 \
  outputs/budget_convergence_rerun/budget_500/seed_60004 \
  outputs/budget_convergence_rerun/budget_2000/seed_60000 \
  outputs/budget_convergence_rerun/budget_2000/seed_60001 \
  outputs/budget_convergence_rerun/budget_2000/seed_60002 \
  outputs/budget_convergence_rerun/budget_2000/seed_60003 \
  outputs/budget_convergence_rerun/budget_2000/seed_60004 \
  outputs/budget_convergence_rerun/budget_5000/seed_60000 \
  outputs/budget_convergence_rerun/budget_5000/seed_60001 \
  outputs/budget_convergence_rerun/budget_5000/seed_60002 \
  outputs/budget_convergence_rerun/budget_5000/seed_60003 \
  outputs/budget_convergence_rerun/budget_5000/seed_60004 \
  outputs/budget_convergence_rerun/budget_10000/seed_60000 \
  outputs/budget_convergence_rerun/budget_10000/seed_60001 \
  outputs/budget_convergence_rerun/budget_10000/seed_60002 \
  outputs/budget_convergence_rerun/budget_10000/seed_60003 \
  outputs/budget_convergence_rerun/budget_10000/seed_60004 \
  outputs/budget_convergence_rerun/budget_20000/seed_60000_PR1_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60000_PR0_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60000_PR1_HT0_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60000_PR1_HT1_EC0 \
  outputs/budget_convergence_rerun/budget_20000/seed_60001_PR1_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60001_PR0_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60001_PR1_HT0_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60001_PR1_HT1_EC0 \
  outputs/budget_convergence_rerun/budget_20000/seed_60002_PR1_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60002_PR0_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60002_PR1_HT0_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60002_PR1_HT1_EC0 \
  outputs/budget_convergence_rerun/budget_20000/seed_60003_PR1_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60003_PR0_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60003_PR1_HT0_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60003_PR1_HT1_EC0 \
  outputs/budget_convergence_rerun/budget_20000/seed_60004_PR1_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60004_PR0_HT1_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60004_PR1_HT0_EC1 \
  outputs/budget_convergence_rerun/budget_20000/seed_60004_PR1_HT1_EC0 \
  --protocol outputs/budget_convergence_rerun/protocol.json \
  --output-dir outputs/budget_convergence_rerun/analysis \
  --representative-traces
