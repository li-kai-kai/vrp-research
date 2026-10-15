"""Sensitivity-track comparisons for the formal experiment.

Each sensitivity cell changes one instance parameter set (capacity calibration,
vehicle thresholds, node-role layout, repair crews, repair duration, fleet or
supply scale) and plans with a matched pair of models on the *same* modified
instance. This script compares the planning-preselected representatives after
the shared Full-environment replay (``replay_solutions.py --execution-model
full`` per store):

- two-model cells (EC / HT / PR): per unit, simplified - Full on replay F1/F2/F3
  (positive = Full's plan executes better), decision-hash equality;
- single-model cells (resources): per unit, modified - baseline Full using the
  baseline executions from the model track's shared replay
  (``exec_all/execution_runs.csv``).

Per cell: mean deltas over the 12 units, sign counts and sign-flip p-values
(exact for n <= 12). Descriptive mechanism-activation cells, not calibration
claims.
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

TWO_MODEL_CELLS = {
    "ec_cap0p0005": ("PR1_HT1_EC1", "PR1_HT1_EC0"),
    "ec_cap0p0002": ("PR1_HT1_EC1", "PR1_HT1_EC0"),
    "ht_scale0p75": ("PR1_HT1_EC1", "PR1_HT0_EC1"),
    "ht_scale1p25": ("PR1_HT1_EC1", "PR1_HT0_EC1"),
    "ht_role_sep": ("PR1_HT1_EC1", "PR1_HT0_EC1"),
    "pr_crews4": ("PR1_HT1_EC1", "PR0_HT1_EC1"),
    "pr_dur0p5": ("PR1_HT1_EC1", "PR0_HT1_EC1"),
    "pr_dur2": ("PR1_HT1_EC1", "PR0_HT1_EC1"),
}
RESOURCE_CELLS = ("res_fleet0p5", "res_fleet2", "res_supply0p5", "res_supply2")
BASELINE_MODEL = "PR1_HT1_EC1"
TOLERANCE = 1e-9


def _representative_rows(store: Path) -> dict:
    path = store / "replay_full" / "replay_results.csv"
    if not path.is_file():
        raise SystemExit(f"missing replay: {store}")
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["representative_selected_before_replay"] == "True":
                return row
    raise SystemExit(f"no representative row in {path}")


def _metric_delta(simplified: dict, full: dict, metric: str) -> float:
    return float(simplified[metric]) - float(full[metric])


def _summarize(values: list[float]) -> dict:
    favor_full = sum(1 for v in values if v > TOLERANCE)
    against_full = sum(1 for v in values if v < -TOLERANCE)
    return {
        "units": len(values),
        "mean_delta": statistics.fmean(values),
        "favor_full_units": favor_full,
        "against_full_units": against_full,
        "sign_flip_p": _sign_flip_p_value(values, samples=20_000, seed=202_608_31),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensitivity-root", type=Path, required=True)
    parser.add_argument("--exec-all", type=Path, required=True, help="exec_all directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    baseline = {}
    with (args.exec_all / "execution_runs.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["model_id"] == BASELINE_MODEL:
                baseline[(row["case_id"], int(row["instance_seed"]), int(row["solver_seed"]))] = row

    units = defaultdict(dict)
    for store in sorted(args.sensitivity_root.glob("*/")):
        tag = store.name.rsplit("_i", 1)[0]
        suffix = store.name.rsplit("_i", 1)[1]
        instance = int(suffix.split("_s")[0])
        seed = int(suffix.split("_s")[1].split("_")[0])
        model = store.name.rsplit("_", 3)[-3] + "_" + store.name.rsplit("_", 2)[-2] + "_" + store.name.rsplit("_", 1)[-1]
        units[tag][(instance, seed, model)] = _representative_rows(store)

    table = []
    for tag in sorted(set(TWO_MODEL_CELLS) | set(RESOURCE_CELLS)):
        members = units[tag]
        keys = sorted({(i, s) for (i, s, _m) in members})
        rows_out = {"cell": tag}
        if tag in TWO_MODEL_CELLS:
            model_full, model_simplified = TWO_MODEL_CELLS[tag]
            deltas = {"replay_F1": [], "replay_F2": [], "replay_F3": []}
            same = 0
            for instance, seed in keys:
                full = members.get((instance, seed, model_full))
                simplified = members.get((instance, seed, model_simplified))
                if full is None or simplified is None:
                    raise SystemExit(f"incomplete unit {tag} i{instance} s{seed}")
                for metric in deltas:
                    deltas[metric].append(_metric_delta(simplified, full, metric))
                same += full["decision_hash"] == simplified["decision_hash"]
            rows_out["comparison"] = "simplified_minus_full"
            rows_out["decision_same_units"] = same
        else:
            model_full = BASELINE_MODEL
            deltas = {"replay_F1": [], "replay_F2": [], "replay_F3": []}
            same = 0
            for instance, seed in keys:
                cell = members.get((instance, seed, model_full))
                base = baseline.get(("S025", instance, seed))
                if cell is None or base is None:
                    raise SystemExit(f"incomplete baseline unit {tag} i{instance} s{seed}")
                deltas["replay_F1"].append(float(cell["replay_F1"]) - float(base["representative_F1"]))
                deltas["replay_F2"].append(float(cell["replay_F2"]) - float(base["representative_F2"]))
                deltas["replay_F3"].append(float(cell["replay_F3"]) - float(base["representative_F3"]))
            rows_out["comparison"] = "modified_minus_baseline"
            rows_out["decision_same_units"] = None
        for metric, values in deltas.items():
            rows_out.update({f"{metric}_{k}": v for k, v in _summarize(values).items()})
        table.append(rows_out)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "sensitivity_cells.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0].keys()))
        writer.writeheader()
        writer.writerows(table)
    (args.output_dir / "analysis_manifest.json").write_text(
        json.dumps(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "two_model_cells": TWO_MODEL_CELLS,
                "resource_cells": list(RESOURCE_CELLS),
                "baseline": "model track Full runs, same instances and seeds (exec_all executions)",
                "permutation_samples": 20_000,
                "note": "descriptive; positive delta = decision executes better than Full's / than baseline",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    for row in table:
        print(
            "%-14s %-22s dF1 %+8.4f (p=%s, %d/%d)  dF2 %+9.1f  决策相同 %s"
            % (
                row["cell"],
                row["comparison"],
                row["replay_F1_mean_delta"],
                ("%.4f" % row["replay_F1_sign_flip_p"]) if row["replay_F1_sign_flip_p"] is not None else "NA",
                row["replay_F1_favor_full_units"],
                row["replay_F1_units"],
                row["replay_F2_mean_delta"],
                row["decision_same_units"],
            )
        )


if __name__ == "__main__":
    main()
