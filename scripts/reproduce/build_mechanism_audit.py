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
from typing import Any, Sequence

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
GRID_SCENARIOS = ("S025_random_random", "S025_corridor", "S050_benchmark", "S050_corridor",
                  "M100_benchmark", "M100_corridor")

# The per-field dispatch-change flags, mirrored into the slim table so an
# objective-neutral change can be told apart from an unexplained one.
ALLOCATION_CHANGE_FIELDS = (
    "supplier",
    "demand",
    "route",
    "vehicle",
    "amount",
    "trips",
    "count",
    "pairing",
    "any",
)

# The cross-scale replication: the same two scenario families run on ever
# larger networks. Listed explicitly rather than discovered so that a missing
# run shows up as a missing row instead of silently shrinking the evidence.
SCALE_CELLS = (
    # (case_id, probe directory, scenario family, size group)
    ("S025", "S025_random_random", "benchmark", "25 nodes"),
    ("S025", "S025_corridor", "corridor", "25 nodes"),
    ("S050", "S050_benchmark", "benchmark", "50 nodes"),
    ("S050", "S050_corridor", "corridor", "50 nodes"),
    ("M100", "M100_benchmark", "benchmark", "100 nodes"),
    ("M100", "M100_corridor", "corridor", "100 nodes"),
)

# Utilization bands for the EC anchor. The upper edge is exclusive except for
# the last band, which absorbs a utilization of exactly 1.0.
EC_BANDS = ((0.0, 0.5), (0.5, 0.85), (0.85, 0.97), (0.97, 1.01))

# Cells carried row by row in mechanism_summary.csv: the S025 damage x role
# comparison plus the larger scales of the cross-scale replication. The S025
# benchmark and corridor probes appear once, under their topology-cell names,
# even though the cross-scale list builds the same scenario -- listing both
# would publish the same 20 decisions twice.
SUMMARY_CELLS = TOPOLOGY_CELLS + (
    ("S050_benchmark", "50 nodes, random damage, random roles"),
    ("S050_corridor", "50 nodes, explicit corridor topology"),
    ("M100_benchmark", "100 nodes, random damage, random roles"),
    ("M100_corridor", "100 nodes, explicit corridor topology"),
)

REPLAY_PLANNING_MODELS = ("PR0_HT1_EC1", "PR1_HT0_EC1", "PR1_HT1_EC0")
FULL_MODEL = "PR1_HT1_EC1"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def fieldnames(rows: Sequence[dict[str, Any]]) -> list[str]:
    """Every column any row carries, in first-seen order.

    ``write_csv_atomic`` otherwise takes the header from the first row and
    drops the rest, so a probe table written by an older build silently loses
    the columns it did not have -- which is exactly how the dispatch sub-flags
    went missing from the published summary.
    """
    names: list[str] = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    return names


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
    for directory, description in SUMMARY_CELLS:
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
                # What changed, not just that something did. The M100
                # counter-examples are objective-neutral *vehicle pairings*,
                # and without these flags a reader could not tell that from
                # the untracked wide tables.
                for field in ALLOCATION_CHANGE_FIELDS:
                    key = f"{label}_allocation_{field}_changed"
                    if key in row:
                        entry[key] = as_int(row, key)
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
        # The directory name is the join key; case_id is what the band table
        # pools by, so both are carried for the reader to check the pooling.
        directory_to_case = {
            probe_directory: case
            for case, probe_directory, _family, _size in SCALE_CELLS
        }
        for row in read_rows(path):
            rows.append(
                {
                    "scenario": scenario,
                    "case_id": directory_to_case.get(scenario, row["case_id"]),
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


def scale_summary() -> list[dict[str, Any]]:
    """Cross-scale check of the exposure -> dispatch -> objective chain.

    The chain has two directions and they are *not* symmetric, so both are
    counted separately:

    - ``objective_without_dispatch`` is a violation of necessity: the objective
      moved while the dispatch encoding stayed identical, which would mean the
      diagnostic is not looking at what the model acts on.
    - ``dispatch_without_objective`` is a violation of sufficiency: the
      dispatch encoding changed while every objective stayed bit-identical.
      This is the one that appears at 100 nodes.
    """
    rows: list[dict[str, Any]] = []
    for case_id, directory, family, size_group in SCALE_CELLS:
        path = PROBE_ROOT / directory / "mechanism_exposure.csv"
        if not path.is_file():
            continue
        source = read_rows(path)
        entry: dict[str, Any] = {
            "case_id": case_id,
            "size_group": size_group,
            "scenario_family": family,
            "probe_directory": directory,
            "decisions": len(source),
            "instance_seeds": " ".join(
                str(seed) for seed in sorted({as_int(r, "instance_seed") for r in source})
            ),
            "graph_bridge_count": as_int(source[0], "graph_bridge_count"),
            "damaged_bridge_count": as_int(source[0], "damaged_bridge_count"),
            "bridge_gated_demand_count": as_int(source[0], "bridge_gated_demand_count"),
        }
        for mechanism in ("PR", "HT", "EC"):
            dispatch = [
                r for r in source if as_int(r, f"{mechanism}_allocations_changed") > 0
            ]
            objective = [
                r for r in source if as_bool(r, f"{mechanism}_same_decision_changed")
            ]
            entry[f"{mechanism}_dispatch_changed"] = len(dispatch)
            entry[f"{mechanism}_objective_changed"] = len(objective)
            entry[f"{mechanism}_objective_without_dispatch"] = sum(
                1 for r in objective if as_int(r, f"{mechanism}_allocations_changed") == 0
            )
            entry[f"{mechanism}_dispatch_without_objective"] = sum(
                1
                for r in dispatch
                if not as_bool(r, f"{mechanism}_same_decision_changed")
            )
        rows.append(entry)
    return rows


def ec_band_summary() -> list[dict[str, Any]]:
    """EC binding against measured edge utilization, per scale and pooled.

    Utilization is a *label*; the definition of binding stays "turning EC off
    changed the objective". The bands only summarise where that definition
    starts to bite, and are reported per scale so a moving boundary is visible
    rather than averaged away.
    """
    rows: list[dict[str, Any]] = []
    per_scale: dict[str, list[dict[str, str]]] = {}
    for case_id, directory, _family, _size in SCALE_CELLS:
        path = PROBE_ROOT / directory / "resource_grid.csv"
        if not path.is_file():
            continue
        per_scale.setdefault(case_id, []).extend(read_rows(path))

    for case_id, source in per_scale.items():
        rows.extend(_bands(case_id, source))

    pooled: list[dict[str, str]] = []
    for source in per_scale.values():
        pooled.extend(source)
    if pooled:
        rows.extend(_bands("pooled", pooled))
    return rows


def _bands(scope: str, source: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    """Utilization bands, each also split by whether a reroute occurred.

    Utilization is a label. Whether the capacity accounting actually *forced a
    different allocation* is much closer to the definition, and the two are
    reported together so a band that binds anyway can be told apart from one
    that only looks tight. ``bands`` covers the four utilization bands;
    ``reroutes>0`` and ``reroutes=0`` cover every cell pooled, because the
    reroute split is the sharper of the two indicators.
    """
    rows: list[dict[str, Any]] = []
    for low, high in EC_BANDS:
        cells = [r for r in source if low <= as_float(r, "max_edge_utilization") < high]
        rows.append(_band_row(scope, low, high, cells))
    rows.append(_band_row(scope, None, None, list(source), reroute="positive"))
    rows.append(_band_row(scope, None, None, list(source), reroute="zero"))
    return rows


def _band_row(
    scope: str,
    low: float | None,
    high: float | None,
    cells: Sequence[dict[str, str]],
    reroute: str | None = None,
) -> dict[str, Any]:
    if reroute == "positive":
        cells = [r for r in cells if as_int(r, "capacity_reroutes") > 0]
    elif reroute == "zero":
        cells = [r for r in cells if as_int(r, "capacity_reroutes") == 0]
    changed = [r for r in cells if as_bool(r, "EC_same_decision_changed")]
    return {
        "scope": scope,
        "utilization_low": low,
        "utilization_high": high,
        "selection": "all" if reroute is None else f"capacity_reroutes {'>0' if reroute == 'positive' else '=0'}",
        "cells": len(cells),
        "ec_changed": len(changed),
        "ec_changed_share": (len(changed) / len(cells)) if cells else None,
        "max_abs_delta_F1": (
            max(abs(as_float(r, "EC_same_decision_delta_F1")) for r in cells) if cells else 0.0
        ),
        "max_abs_delta_F2": (
            max(abs(as_float(r, "EC_same_decision_delta_F2")) for r in cells) if cells else 0.0
        ),
    }


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
        "scale_cells": [
            {
                "case_id": case_id,
                "probe_directory": directory,
                "scenario_family": family,
                "size_group": size_group,
            }
            for case_id, directory, family, size_group in SCALE_CELLS
        ],
        "ec_bands": [{"low": low, "high": high} for low, high in EC_BANDS],
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
        "scale_summary.csv": scale_summary(),
        "ec_band_summary.csv": ec_band_summary(),
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
        write_csv_atomic(AUDIT_ROOT / name, rows, fieldnames(rows))

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
