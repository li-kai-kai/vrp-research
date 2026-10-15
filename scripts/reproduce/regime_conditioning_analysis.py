"""Regime conditioning for the formal model-value experiment.

For each tier this joins the per-instance execution-side cost of ignoring a
mechanism (shared-execution replay delta of the planning-preselected
representative's F1; positive = Full's plan executes better) with the
instance's measured exposure to that mechanism under the Full model:

- PR exposure: mean ``partial_recovery_edge_periods`` over the Full planning
  runs of the instance (edge-periods actually sitting in a partial-recovery
  state);
- EC exposure: mean ``max_edge_utilization`` over the Full planning runs.

HT conditioning is structural rather than exposure-based: heterogeneous
thresholds act only through partial-recovery states, which the 2^3
execution-side analysis shows directly (the PR x HT interaction equals the HT
main effect); the PR exposure column is reported alongside for reference.

Spearman rank correlation is reported descriptively -- conditioning is a
description of where effects appear, not a hypothesis test.
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

from scripts.reproduce.model_ablation_analysis import merge_model_ablation_shards


FULL_MODEL = "PR1_HT1_EC1"
COSTS = {
    "ignoring_PR": "PR0_HT1_EC1",
    "ignoring_HT": "PR1_HT0_EC1",
    "ignoring_EC": "PR1_HT1_EC0",
}
EXPOSURES = {
    "PR": "partial_recovery_edge_periods",
    "EC": "max_edge_utilization",
}


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        rank = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            mean_rank = (i + j) / 2.0
            for k in range(i, j + 1):
                rank[order[k]] = mean_rank
            i = j + 1
        return rank

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (
        sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)
    ) ** 0.5
    return num / den if den > 1e-12 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", type=Path, required=True)
    parser.add_argument("--exec-dir", type=Path, required=True, help="exec_all directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    shards = sorted(args.track.glob("*/model_ablation.csv"))
    rows, _, _ = merge_model_ablation_shards(shards)

    exposure = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["model_id"] == FULL_MODEL:
            for name, column in EXPOSURES.items():
                exposure[(row["case_id"], row["instance_seed"])][name].append(
                    float(row[column])
                )

    with (args.exec_dir / "execution_pairs.csv").open(newline="", encoding="utf-8") as handle:
        pairs = list(csv.DictReader(handle))
    costs = defaultdict(lambda: defaultdict(list))
    for row in pairs:
        for name, model_id in COSTS.items():
            if row["model_id"] == model_id:
                costs[(row["case_id"], row["instance_seed"])][name].append(
                    float(row["representative_delta_F1"])
                )

    table = []
    for key in sorted(exposure):
        case, instance = key
        entry = {"case_id": case, "instance_seed": instance}
        for name in EXPOSURES:
            entry[f"{name}_exposure"] = statistics.fmean(exposure[key][name])
        for name in COSTS:
            values = costs[key].get(name)
            entry[f"{name}_dF1"] = statistics.fmean(values) if values else None
        table.append(entry)

    summary = []
    for case in sorted({row["case_id"] for row in table}):
        members = [row for row in table if row["case_id"] == case]
        for exposure_name in EXPOSURES:
            for cost_name in COSTS:
                usable = [
                    row for row in members if row[f"{cost_name}_dF1"] is not None
                ]
                xs = [row[f"{exposure_name}_exposure"] for row in usable]
                ys = [row[f"{cost_name}_dF1"] for row in usable]
                note = ""
                if len(set(ys)) == 1:
                    note = "outcome constant across instances"
                elif len(set(xs)) == 1:
                    note = "exposure constant within tier"
                summary.append(
                    {
                        "case_id": case,
                        "exposure": exposure_name,
                        "cost": cost_name,
                        "instances": len(xs),
                        "spearman_rho": _spearman(xs, ys),
                        "note": note,
                    }
                )
        for cost_name in COSTS:
            values = [
                row[f"{cost_name}_dF1"] for row in members
                if row[f"{cost_name}_dF1"] is not None
            ]
            summary.append(
                {
                    "case_id": case,
                    "exposure": "-",
                    "cost": cost_name,
                    "instances": len(values),
                    "spearman_rho": None,
                    "note": "instances with cost>0: %d/%d; range %.4f..%.4f"
                    % (
                        sum(1 for v in values if v > 1e-9),
                        len(values),
                        min(values),
                        max(values),
                    ),
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "regime_conditioning.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0].keys()))
        writer.writeheader()
        writer.writerows(table)
    with (args.output_dir / "regime_correlations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)
    (args.output_dir / "analysis_manifest.json").write_text(
        json.dumps(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "exposure_columns": EXPOSURES,
                "cost_definitions": COSTS,
                "note": (
                    "descriptive conditioning; exposure from Full planning runs, "
                    "cost from the shared-execution replay (positive = Full better)"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    for row in summary:
        rho = row["spearman_rho"]
        print("%-6s %-4s 暴露 → %-11s ρ = %s (n=%d)" % (
            row["case_id"], row["exposure"], row["cost"],
            f"{rho:+.3f}" if rho is not None else "NA", row["instances"]))


if __name__ == "__main__":
    main()
