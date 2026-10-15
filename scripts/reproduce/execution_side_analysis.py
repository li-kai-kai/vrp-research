"""Paired execution-side tests for the formal model-value experiment.

Family declaration (fixed before the tests are read): within each case tier the
family is the three one-factor-off simplifications (No-PR, No-HT, No-EC) on the
two pre-declared endpoints of the shared Full execution -- the execution front
hypervolume (Full - simplified) and the planning-preselected representative's
F1 (simplified - Full). Six tests per tier, Holm-adjusted within the tier;
positive values favour Full. The analysis unit is the instance: solver repeats
are averaged first. A tier with a single instance (WEN38) is reported
descriptively only.

Execution hypervolume is normalised against the pooled reference front and
lives on a 0-1 scale; the magnitude table reports per-model means so the paired
deltas can be read against the scale.

The permutation test is the sign-flip primitive used by the planning-side
analysis (``model_ablation_analysis._sign_flip_p_value``); the declared sample
count and seed are recorded in the manifest.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import statistics
import sys

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.model_ablation_analysis import _sign_flip_p_value

SIMPLIFIED_MODELS = ("No-PR", "No-HT", "No-EC")
METRICS = ("delta_hv", "representative_delta_F1")
PERMUTATION_SAMPLES = 20_000
ANALYSIS_SEED = 202_608_31
TOLERANCE = 1e-9


def _holm(p_values: list[float]) -> list[float]:
    """Holm step-down adjustment; order is preserved on return."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [1.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, p_values[index] * (len(p_values) - rank)))
        adjusted[index] = running
    return adjusted


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _unit_means(rows, model, metric):
    by_instance = defaultdict(list)
    for row in rows:
        if row["model"] == model:
            by_instance[int(row["instance_seed"])].append(float(row[metric]))
    return {
        instance: statistics.fmean(values)
        for instance, values in sorted(by_instance.items())
    }


def analyze_tier(exec_dir: Path) -> tuple[list[dict], list[dict]]:
    pairs = _read_rows(exec_dir / "execution_pairs.csv")
    test_rows: list[dict] = []
    raw = []
    for model in SIMPLIFIED_MODELS:
        for metric in METRICS:
            means = _unit_means(pairs, model, metric)
            values = list(means.values())
            favor = sum(1 for v in values if v > TOLERANCE)
            against = sum(1 for v in values if v < -TOLERANCE)
            if len(values) >= 2:
                p_value = _sign_flip_p_value(
                    values, samples=PERMUTATION_SAMPLES, seed=ANALYSIS_SEED
                )
            else:
                p_value = None
            test_rows.append(
                {
                    "tier": exec_dir.name.replace("exec_", ""),
                    "model": model,
                    "metric": metric,
                    "n_units": len(values),
                    "mean_delta": statistics.fmean(values),
                    "favor_full_units": favor,
                    "against_full_units": against,
                    "raw_p": p_value,
                    "holm_p": None,
                    "note": "" if len(values) >= 2 else "single instance: descriptive only",
                }
            )
            raw.append(p_value)
    adjusted = _holm([p for p in raw if p is not None])
    for row, value in zip((r for r in test_rows if r["raw_p"] is not None), adjusted):
        row["holm_p"] = value
    magnitude = []
    for row in _read_rows(exec_dir / "execution_runs.csv"):
        magnitude.append(row)
    return test_rows, magnitude


def magnitude_rows(rows, tier) -> list[dict]:
    by_model = defaultdict(list)
    for row in rows:
        by_model[row["model"]].append(row)
    result = []
    for model, members in sorted(by_model.items()):
        result.append(
            {
                "tier": tier,
                "model": model,
                "runs": len(members),
                "mean_execution_hypervolume": statistics.fmean(
                    float(m["hypervolume"]) for m in members
                ),
                "mean_representative_execution_F1": statistics.fmean(
                    float(m["representative_F1"]) for m in members
                ),
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execution-side paired tests with a declared family and Holm adjustment."
    )
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    # Accept only the four-model screen replays; a directory whose pairs also
    # cover the two- and three-way-off combinations belongs to the factorial
    # analysis (execution_2x3_analysis.py) instead.
    screen_models = {"Full", "No-PR", "No-HT", "No-EC"}
    exec_dirs = []
    for path in sorted(args.input_root.glob("exec_*")):
        pairs_path = path / "execution_pairs.csv"
        if not pairs_path.is_file():
            continue
        with pairs_path.open(newline="", encoding="utf-8") as handle:
            models = {row["model"] for row in csv.DictReader(handle)}
        if models and models <= screen_models:
            exec_dirs.append(path)
    if not exec_dirs:
        parser.error(f"no four-model exec_* directories below {args.input_root}")

    test_rows: list[dict] = []
    magnitude: list[dict] = []
    for exec_dir in exec_dirs:
        tier_tests, tier_runs = analyze_tier(exec_dir)
        test_rows.extend(tier_tests)
        magnitude.extend(magnitude_rows(tier_runs, exec_dir.name.replace("exec_", "")))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "execution_tests.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(test_rows[0].keys()))
        writer.writeheader()
        writer.writerows(test_rows)
    with (args.output_dir / "magnitude_context.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(magnitude[0].keys()))
        writer.writeheader()
        writer.writerows(magnitude)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_dirs": [str(path) for path in exec_dirs],
        "family_declaration": (
            "per tier: {No-PR, No-HT, No-EC} x {delta_hv, representative_delta_F1} = 6 tests; "
            "Holm within the tier; positive favours Full; unit = instance (repeats averaged)"
        ),
        "permutation_samples": PERMUTATION_SAMPLES,
        "analysis_seed": ANALYSIS_SEED,
        "hypervolume_scale": "normalised against the pooled reference front (0-1)",
    }
    (args.output_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        "wrote %d test rows and %d magnitude rows to %s"
        % (len(test_rows), len(magnitude), args.output_dir)
    )


if __name__ == "__main__":
    main()
