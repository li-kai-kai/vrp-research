"""Assemble the slim, auditable mechanism-applicability evidence set.

The diagnostic scripts write wide per-cell CSVs into ``outputs/mechanism_probe``.
Those are regenerable and large, so they stay out of version control; this
builder distils them into the small set of tables a reader needs in order to
check the report's claims, plus a manifest that ties every number to the code,
the scenario and the solver settings that produced it.

Nothing here re-runs the diagnostic or re-derives a mechanism result: every row
is a projection, a count or an aggregate of an existing CSV. That keeps the
audit reproducible and keeps the possibility of the audit disagreeing with the
diagnostic down to arithmetic that the reader can re-check.
"""

from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

if __package__ == "" or __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.mechanism_applicability import DIAGNOSTIC_SOURCES, objective_changed
from scripts.reproduce.solution_io import (
    code_environment,
    source_hashes,
    write_csv_atomic,
    write_json_atomic,
)


PROBE_ROOT = Path("outputs/mechanism_probe")
AUDIT_ROOT = Path("outputs/mechanism_probe_audit")

# The four topology cells: damage strategy crossed with node-role placement.
# Each cell is one run of the fixed-decision probe; together they separate
# "damage fell on bridges" from "demands were pushed to the rim", which an
# earlier version of this diagnostic conflated.
TOPOLOGY_CELLS = (
    ("fourcell_benchmark", "random damage, random roles"),
    ("fourcell_critical_random", "critical damage requested, random roles"),
    ("fourcell_critical_separated", "critical damage requested, separated roles"),
    ("fourcell_corridor", "explicit corridor topology"),
)

# Scenario directories that carry the resource grid and the repair sweep.
GRID_SCENARIOS = ("S025_random_random", "S025_corridor")

REPLAY_PLANNING_MODELS = ("PR0_HT1_EC1", "PR1_HT0_EC1", "PR1_HT1_EC0")
FULL_MODEL = "PR1_HT1_EC1"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def as_int(row: dict[str, str], key: str) -> int:
    return int(float(row[key]))


def as_bool(row: dict[str, str], key: str) -> bool:
    return row[key].strip().lower() in ("true", "1")


# --------------------------------------------------------------------------
# projections
# --------------------------------------------------------------------------


def mechanism_summary() -> list[dict[str, Any]]:
    """One slim row per fixed decision: exposure, participation, objective.

    The three levels are kept in separate column groups on purpose -- a
    mechanism can be exposed without participating in the dispatch, and can
    participate without moving the objective. Collapsing them into a single
    "effective" flag would hide exactly the distinction the report rests on.
    """
    rows: list[dict[str, Any]] = []
    for directory, description in TOPOLOGY_CELLS:
        for row in read_rows(PROBE_ROOT / directory / "mechanism_exposure.csv"):
            entry: dict[str, Any] = {
                "topology_cell": directory,
                "topology_description": description,
                "scenario": row["scenario"],
                "case_id": row["case_id"],
                "instance_seed": as_int(row, "instance_seed"),
                "decision": row["decision"],
                "graph_bridge_count": as_int(row, "graph_bridge_count"),
                "damaged_bridge_count": as_int(row, "damaged_bridge_count"),
                "bridge_gated_demand_count": as_int(row, "bridge_gated_demand_count"),
                "F1": as_float(row, "F1"),
                "F2": as_float(row, "F2"),
                "F3": as_float(row, "F3"),
            }
            for label in ("PR", "HT", "EC"):
                entry[f"{label}_allocations_changed"] = as_int(
                    row, f"{label}_allocations_changed"
                )
                entry[f"{label}_same_decision_changed"] = as_bool(
                    row, f"{label}_same_decision_changed"
                )
                entry[f"{label}_delta_F1"] = as_float(row, f"{label}_same_decision_delta_F1")
                entry[f"{label}_delta_F2"] = as_float(row, f"{label}_same_decision_delta_F2")
            entry["max_edge_utilization"] = as_float(row, "max_edge_utilization")
            entry["partial_edge_periods"] = as_int(row, "partial_edge_periods")
            entry["partial_edge_used_periods"] = as_int(row, "partial_edge_used_periods")
            entry["threshold_sensitive_od_periods"] = as_int(
                row, "threshold_sensitive_od_periods"
            )
            rows.append(entry)
    return rows


def topology_summary() -> list[dict[str, Any]]:
    """Per topology cell: how often each mechanism changed the dispatch.

    This is the table that retracts the earlier bridge-damage claim -- the
    `critical` cells are reported with their *measured* bridge counts, so a
    cell with ``damaged_bridge_count = 0`` cannot be read as bridge damage.
    """
    rows: list[dict[str, Any]] = []
    for directory, description in TOPOLOGY_CELLS:
        source = read_rows(PROBE_ROOT / directory / "mechanism_exposure.csv")
        if not source:
            continue
        seeds = sorted({as_int(row, "instance_seed") for row in source})
        entry: dict[str, Any] = {
            "topology_cell": directory,
            "topology_description": description,
            "scenario": source[0]["scenario"],
            "decisions": len(source),
            "instance_seeds": " ".join(str(seed) for seed in seeds),
            "graph_bridge_count": as_int(source[0], "graph_bridge_count"),
            "damaged_bridge_count": as_int(source[0], "damaged_bridge_count"),
            "bridge_gated_demand_count": as_int(source[0], "bridge_gated_demand_count"),
        }
        for label in ("PR", "HT", "EC"):
            entry[f"{label}_dispatch_changed_decisions"] = sum(
                1 for row in source if as_int(row, f"{label}_allocations_changed") > 0
            )
            entry[f"{label}_objective_changed_decisions"] = sum(
                1 for row in source if as_bool(row, f"{label}_same_decision_changed")
            )
        rows.append(entry)
    return rows


def resource_grid_summary() -> list[dict[str, Any]]:
    """The resource grid, reduced to one row per (scenario, seed, axis point)."""
    rows: list[dict[str, Any]] = []
    for scenario in GRID_SCENARIOS:
        path = PROBE_ROOT / scenario / "resource_grid.csv"
        if not path.is_file():
            continue
        for row in read_rows(path):
            rows.append(
                {
                    "scenario": scenario,
                    "case_id": row["case_id"],
                    "instance_seed": as_int(row, "instance_seed"),
                    "fleet_multiplier": as_float(row, "fleet_multiplier"),
                    "capacity_scale": as_float(row, "capacity_scale"),
                    "supply_multiplier": as_float(row, "supply_multiplier"),
                    "max_edge_utilization": as_float(row, "max_edge_utilization"),
                    "capacity_reroutes": as_int(row, "capacity_reroutes"),
                    "EC_changed_objective": as_bool(row, "EC_same_decision_changed"),
                    "EC_delta_F1": as_float(row, "EC_same_decision_delta_F1"),
                    "EC_delta_F2": as_float(row, "EC_same_decision_delta_F2"),
                    "F1": as_float(row, "F1"),
                    "F2": as_float(row, "F2"),
                    "total_delivered": as_float(row, "total_delivered"),
                    "remaining_supply": as_float(row, "remaining_supply"),
                    "unused_vehicle_trips": as_int(row, "unused_vehicle_trips"),
                }
            )
    return rows


def bottleneck_summary() -> list[dict[str, Any]]:
    """Per scenario and seed: which resource relaxation moved the objective."""
    rows: list[dict[str, Any]] = []
    for scenario in GRID_SCENARIOS:
        path = PROBE_ROOT / scenario / "bottleneck_relaxation.csv"
        if not path.is_file():
            continue
        for row in read_rows(path):
            entry: dict[str, Any] = {
                "scenario": scenario,
                "case_id": row["case_id"],
                "instance_seed": as_int(row, "instance_seed"),
                "baseline_F1": as_float(row, "baseline_F1"),
                "baseline_F2": as_float(row, "baseline_F2"),
                "damaged_bridge_count": as_int(row, "damaged_bridge_count"),
            }
            for axis in ("fleet", "supply", "road_capacity"):
                key = f"relax_{axis}_changed_objective"
                entry[key] = as_bool(row, key) if key in row else None
                entry[f"relax_{axis}_delta_F1"] = (
                    as_float(row, f"relax_{axis}_delta_F1")
                    if f"relax_{axis}_delta_F1" in row
                    else None
                )
            rows.append(entry)
    return rows


def zone_exposure_summary() -> list[dict[str, Any]]:
    """Where each zone actually landed after calibration.

    The capacity scale is an output of the calibration, not an input to it, so
    the measured utilization is carried next to the target it was aiming for.
    """
    path = PROBE_ROOT / "zone_search" / "zone_exposure.csv"
    if not path.is_file():
        return []
    return [
        {
            "zone": row["zone"],
            "instance_seed": as_int(row, "instance_seed"),
            "capacity_scale": as_float(row, "capacity_scale"),
            "target_utilization": as_float(row, "target_utilization"),
            "measured_utilization": as_float(row, "max_edge_utilization"),
            "in_target_band": as_bool(row, "in_target_band"),
            "graph_bridge_count": as_int(row, "graph_bridge_count"),
            "damaged_bridge_count": as_int(row, "damaged_bridge_count"),
            "EC_changed_dispatch": as_bool(row, "EC_same_decision_changed"),
            "HT_changed_dispatch": as_bool(row, "HT_same_decision_changed"),
            "PR_changed_dispatch": as_bool(row, "PR_same_decision_changed"),
        }
        for row in read_rows(path)
    ]


def zone_bottleneck_summary() -> list[dict[str, Any]]:
    """Per zone: whether relaxing each resource moves the objective.

    This is an independent route to the same claim as the EC on/off column in
    ``zone_exposure.csv``: capacity relaxation can only change the objective
    where road throughput actually binds.
    """
    path = PROBE_ROOT / "zone_search" / "zone_bottleneck.csv"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for row in read_rows(path):
        entry: dict[str, Any] = {
            "zone": row["zone"],
            "instance_seed": as_int(row, "instance_seed"),
            "measured_utilization": as_float(row, "measured_utilization"),
            "baseline_F1": as_float(row, "baseline_F1"),
        }
        for axis in ("fleet", "supply", "road_capacity"):
            entry[f"relax_{axis}_changed_objective"] = as_bool(
                row, f"relax_{axis}_changed_objective"
            )
            entry[f"relax_{axis}_delta_F1"] = as_float(row, f"relax_{axis}_delta_F1")
        rows.append(entry)
    return rows


def zone_replay_summary() -> list[dict[str, Any]]:
    """Stage 3, one row per (zone, planning model).

    Every saved decision is executed in the *same* Full environment, so the
    deltas measure what the planning model failed to foresee. The Full model's
    own rows are the identity control and are reported separately.
    """
    path = PROBE_ROOT / "zone_search" / "zone_replay.csv"
    if not path.is_file():
        return []
    source = read_rows(path)
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in source:
        grouped.setdefault((row["zone"], row["model_id"]), []).append(row)

    rows: list[dict[str, Any]] = []
    for (zone, model_id), group in sorted(grouped.items()):
        deltas_f1 = [as_float(row, "execution_minus_planning_F1") for row in group]
        deltas_f2 = [as_float(row, "execution_minus_planning_F2") for row in group]
        deltas_f3 = [as_float(row, "execution_minus_planning_F3") for row in group]
        # "Did execution differ from the plan?" is the same question the rest
        # of the pipeline answers, so it is asked on the same quantized key --
        # over all three objectives, F3 included. A raw float comparison would
        # call two sub-resolution differences a change and count a pure F3
        # difference as none.
        changed = [
            objective_changed(
                (
                    as_float(row, "planning_F1"),
                    as_float(row, "planning_F2"),
                    as_float(row, "planning_F3"),
                ),
                (
                    as_float(row, "execution_F1"),
                    as_float(row, "execution_F2"),
                    as_float(row, "execution_F3"),
                ),
            )
            for row in group
        ]
        rows.append(
            {
                "zone": zone,
                "model_id": model_id,
                "is_full_self_replay": model_id == FULL_MODEL,
                "decisions": len(group),
                "objective_changed": sum(1 for flags in changed if flags["changed"]),
                "objective_changed_F1": sum(1 for flags in changed if flags["changed_F1"]),
                "objective_changed_F2": sum(1 for flags in changed if flags["changed_F2"]),
                "objective_changed_F3": sum(1 for flags in changed if flags["changed_F3"]),
                "mean_delta_F1": statistics.fmean(deltas_f1),
                "mean_delta_F2": statistics.fmean(deltas_f2),
                "mean_delta_F3": statistics.fmean(deltas_f3),
                "max_abs_delta_F1": max(abs(value) for value in deltas_f1),
                "max_abs_delta_F2": max(abs(value) for value in deltas_f2),
                "max_abs_delta_F3": max(abs(value) for value in deltas_f3),
            }
        )
    return rows


def full_self_replay_check() -> dict[str, Any]:
    """The identity control: a Full-planned decision must replay to itself."""
    path = PROBE_ROOT / "zone_search" / "zone_replay.csv"
    if not path.is_file():
        return {}
    source = [
        row for row in read_rows(path) if row["is_full_planning_model"].strip() == "True"
    ]
    if not source:
        return {}
    return {
        "decisions": len(source),
        "max_abs_delta_F1": max(
            abs(as_float(row, "execution_minus_planning_F1")) for row in source
        ),
        "max_abs_delta_F2": max(
            abs(as_float(row, "execution_minus_planning_F2")) for row in source
        ),
    }


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------


def build_manifest(
    tables: dict[str, list[dict[str, Any]]],
    zone_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    topology = tables["topology_summary.csv"]
    zones = tables["zone_exposure.csv"]
    return {
        "scope": (
            "mechanism applicability (PR / HT / EC) diagnostic evidence; the "
            "diagnostic is read-only with respect to the model, the search, "
            "replay, numerical precision and FullExecutionProfile"
        ),
        "code": code_environment(),
        "source_hashes": source_hashes(root, DIAGNOSTIC_SOURCES),
        "audit_builder": "scripts/reproduce/build_mechanism_audit.py",
        "provenance_note": (
            "git_sha and git_dirty are captured when this file is written, so "
            "git_dirty is true whenever the evidence set itself is not yet "
            "committed. source_hashes is the authoritative pin: it is the "
            "content digest of the scripts that produced the probe outputs, "
            "and it is unaffected by commit timing."
        ),
        "tables": {name: len(rows) for name, rows in tables.items()},
        "topology_cells": [
            {
                "cell": row["topology_cell"],
                "description": row["topology_description"],
                "graph_bridge_count": row["graph_bridge_count"],
                "damaged_bridge_count": row["damaged_bridge_count"],
                "bridge_gated_demand_count": row["bridge_gated_demand_count"],
            }
            for row in topology
        ],
        "zone_landing": [
            {
                "zone": row["zone"],
                "instance_seed": row["instance_seed"],
                "measured_utilization": row["measured_utilization"],
                "in_target_band": row["in_target_band"],
            }
            for row in zones
        ],
        "full_self_replay_check": full_self_replay_check(),
        "zone_search_manifest": zone_manifest,
        "evidence_limits": [
            "single case (S025), single network family",
            "fleet multipliers, capacity scales, supply multipliers and repair "
            "time multipliers are stress values, not measured Wenchuan parameters",
            "corridor and separated-role topologies are constructed, not observed",
            "fixed decisions diagnose whether a mechanism can trigger; they are "
            "not a sample for statistical inference",
            "stage 2/3 search budgets are small and diagnostic, not a benchmark",
        ],
    }


def main() -> None:
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)

    tables: dict[str, list[dict[str, Any]]] = {
        "mechanism_summary.csv": mechanism_summary(),
        "topology_summary.csv": topology_summary(),
        "resource_grid_summary.csv": resource_grid_summary(),
        "bottleneck_summary.csv": bottleneck_summary(),
        "zone_exposure.csv": zone_exposure_summary(),
        "zone_bottleneck.csv": zone_bottleneck_summary(),
        "zone_replay_summary.csv": zone_replay_summary(),
    }

    for name, rows in tables.items():
        if not rows:
            print(f"WARNING: {name} is empty; its source probe output is missing")
            continue
        write_csv_atomic(AUDIT_ROOT / name, rows, list(rows[0]))

    # The stage 2/3 search settings live in the zone-search manifest; copying
    # it keeps the audit self-contained instead of pointing at an untracked
    # probe directory.
    zone_manifest_path = PROBE_ROOT / "zone_search" / "zone_search_manifest.json"
    zone_manifest = None
    if zone_manifest_path.is_file():
        import json

        zone_manifest = json.loads(zone_manifest_path.read_text())

    write_json_atomic(AUDIT_ROOT / "manifest.json", build_manifest(tables, zone_manifest))
    print(
        "Wrote audit tables to "
        + ", ".join(f"{name} ({len(rows)})" for name, rows in tables.items())
        + f" and manifest.json to {AUDIT_ROOT}"
    )


if __name__ == "__main__":
    main()
