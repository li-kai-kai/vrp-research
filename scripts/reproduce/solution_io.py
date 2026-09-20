"""Shared, rebuildable persistence for capacity-recovery runs.

Every experiment entry point writes through this module so a saved run is
enough to rebuild the physical instance, the effective model configuration and
the complete three-part decision, and to re-evaluate it later.

Design rules fixed here (see docs/model_v2_contract.md):

* Standard JSON only. Objectives and model parameters must be finite; display
  fields that are allowed to be infinite (crowding distance) are written as
  ``null`` and marked as such.
* Node identifiers are integers, and undirected edges are ordered by their
  sorted endpoints, so a snapshot hash can be rebuilt from the file alone.
* Writes are atomic: a temporary file is written and then replaces the target,
  so an interrupted run never leaves a half-written record that looks complete.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import networkx as nx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.capacity_recovery import (
    CapacityExperimentInstance,
    CapacityIndividual,
    EvaluationConfig,
    RecoveryStage,
    VehicleProfile,
)
from scripts.reproduce.objective_precision import precision_for
from scripts.reproduce.model import DamagedEdge, RandomInstance


INSTANCE_FORMAT = "capacity_recovery_instance"
INSTANCE_FORMAT_VERSION = 1
RUN_FORMAT = "capacity_recovery_run"
RUN_FORMAT_VERSION = 1

# Display-only fields that may legitimately be infinite. They are written as
# null so the file stays valid standard JSON.
INFINITE_DISPLAY_FIELDS = ("crowding_distance",)


class SolutionIOError(RuntimeError):
    """Raised when a stored artifact is missing, corrupt, or incompatible."""


# --------------------------------------------------------------------------
# canonical encoding helpers
# --------------------------------------------------------------------------


def canonical_json(payload: Any) -> str:
    """Deterministic JSON text used for every fingerprint in this module."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    """Convert a graph attribute to a JSON-safe value, or reject it."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise SolutionIOError(f"non-finite graph attribute cannot be stored: {value!r}")
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    raise SolutionIOError(f"unsupported graph attribute type: {type(value).__name__}")


def _require_int_node(node_id: Any) -> int:
    if isinstance(node_id, bool) or not isinstance(node_id, int):
        raise SolutionIOError(
            f"node identifiers must be integers, got {node_id!r} "
            f"({type(node_id).__name__})"
        )
    return node_id


def _sorted_edge(graph: nx.Graph) -> list[tuple[int, int, dict[str, Any]]]:
    """Undirected edges in a fixed order with endpoints sorted ascending."""
    rows: list[tuple[int, int, dict[str, Any]]] = []
    for u, v, data in graph.edges(data=True):
        left = _require_int_node(u)
        right = _require_int_node(v)
        if left > right:
            left, right = right, left
        rows.append((left, right, dict(data)))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def _amount_rows(amounts: dict[int, float]) -> list[list[float]]:
    return [
        [_require_int_node(node_id), float(amount)]
        for node_id, amount in sorted(amounts.items())
    ]


# --------------------------------------------------------------------------
# instance snapshot
# --------------------------------------------------------------------------


def serialize_instance(instance: CapacityExperimentInstance) -> dict[str, Any]:
    """Full snapshot: enough to rebuild every input the evaluator reads.

    The instance seed is recorded but never relied upon for rebuilding, because
    generators and defaults can change between code revisions.
    """
    base = instance.base
    return {
        "format": INSTANCE_FORMAT,
        "format_version": INSTANCE_FORMAT_VERSION,
        "name": base.name,
        "instance_seed": int(base.seed),
        "num_nodes": int(base.num_nodes),
        "gamma": int(base.gamma),
        "damage_ratio": float(base.damage_ratio),
        "eta_hours": int(base.eta_hours),
        "horizon_hours": int(base.horizon_hours),
        "repair_crews": int(base.repair_crews),
        "vehicle_capacity": float(base.vehicle_capacity),
        "vehicle_count": int(base.vehicle_count),
        "suppliers": [_require_int_node(node) for node in base.suppliers],
        "demands": [_require_int_node(node) for node in base.demands],
        "demand_amounts": _amount_rows(base.demand_amounts),
        "supply_amounts": _amount_rows(base.supply_amounts),
        "nodes": [
            {"id": _require_int_node(node_id), "attrs": _plain_attrs(attrs)}
            for node_id, attrs in sorted(base.graph.nodes(data=True))
        ],
        "edges": [
            {
                "u": u,
                "v": v,
                "free_time": float(data.get("free_time", data.get("weight", 1.0))),
                "weight": float(data.get("weight", data.get("free_time", 1.0))),
                "capacity": float(data.get("capacity", 1000.0)),
                "damaged": bool(data.get("damaged", False)),
                "damage_id": (
                    int(data["damage_id"]) if data.get("damage_id") is not None else None
                ),
                "repair_time": (
                    float(data["repair_time"]) if data.get("repair_time") is not None else None
                ),
            }
            for u, v, data in _sorted_edge(base.graph)
        ],
        "damaged_edges": [
            {
                "damage_id": int(damage_id),
                "u": _require_int_node(edge.u),
                "v": _require_int_node(edge.v),
                "repair_time": float(edge.repair_time),
            }
            for damage_id, edge in sorted(base.damaged_edges.items())
        ],
        "model": {
            "capacity_scale": float(instance.capacity_scale),
            "repair_time_weight": float(instance.repair_time_weight),
            "crew_transfer_time_scale": float(instance.crew_transfer_time_scale),
            "crew_min_access_progress": float(instance.crew_min_access_progress),
            "progressive_recovery": bool(instance.progressive_recovery),
            "heterogeneous_vehicle_thresholds": bool(
                instance.heterogeneous_vehicle_thresholds
            ),
            "edge_capacity_constraint": bool(instance.edge_capacity_constraint),
            "evaluation": instance.evaluation.as_dict(),
            "vehicles": [
                {
                    "vehicle_type": int(vehicle.vehicle_type),
                    "capacity_ton": float(vehicle.capacity_ton),
                    "count": int(vehicle.count),
                    "occupied_od_pcu_h": float(vehicle.occupied_od_pcu_h),
                    "min_recovery_progress": float(vehicle.min_recovery_progress),
                    "pcu_per_vehicle": float(vehicle.pcu_per_vehicle),
                    "speed_factor": float(vehicle.speed_factor),
                }
                for vehicle in instance.vehicles
            ],
            "recovery_stages": [
                {
                    "lower": float(stage.lower),
                    "upper": float(stage.upper),
                    "capacity_ratio": float(stage.capacity_ratio),
                    "label": str(stage.label),
                    "speed_ratio": float(stage.speed_ratio),
                }
                for stage in instance.recovery_stages
            ],
        },
    }


def _plain_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _plain(value) for key, value in sorted(attrs.items())}


def deserialize_instance(payload: dict[str, Any]) -> CapacityExperimentInstance:
    """Rebuild an instance from a snapshot, validating its structure."""
    if not isinstance(payload, dict):
        raise SolutionIOError("instance snapshot must be a JSON object")
    if payload.get("format") != INSTANCE_FORMAT:
        raise SolutionIOError(
            f"unexpected instance format {payload.get('format')!r}"
        )
    if payload.get("format_version") != INSTANCE_FORMAT_VERSION:
        raise SolutionIOError(
            "unsupported instance format version "
            f"{payload.get('format_version')!r}; expected {INSTANCE_FORMAT_VERSION}"
        )

    graph = nx.Graph()
    for node in _require_field(payload, "nodes", list):
        node_id = _require_int_node(_require_field(node, "id", int))
        graph.add_node(node_id, **_require_field(node, "attrs", dict))

    for edge in _require_field(payload, "edges", list):
        u = _require_int_node(_require_field(edge, "u", int))
        v = _require_int_node(_require_field(edge, "v", int))
        if u == v:
            raise SolutionIOError(f"self-loop edge at node {u} in instance snapshot")
        attributes: dict[str, Any] = {
            "free_time": float(_require_field(edge, "free_time", (int, float))),
            "weight": float(_require_field(edge, "weight", (int, float))),
            "capacity": float(_require_field(edge, "capacity", (int, float))),
            "damaged": bool(_require_field(edge, "damaged", bool)),
        }
        if edge.get("damage_id") is not None:
            attributes["damage_id"] = int(edge["damage_id"])
        if edge.get("repair_time") is not None:
            attributes["repair_time"] = float(edge["repair_time"])
        graph.add_edge(u, v, **attributes)

    damaged_edges: dict[int, DamagedEdge] = {}
    for row in _require_field(payload, "damaged_edges", list):
        damage_id = int(_require_field(row, "damage_id", int))
        u = _require_int_node(_require_field(row, "u", int))
        v = _require_int_node(_require_field(row, "v", int))
        repair_time = float(_require_field(row, "repair_time", (int, float)))
        if not graph.has_edge(u, v):
            raise SolutionIOError(
                f"damaged edge {damage_id} references missing edge {(u, v)}"
            )
        damaged_edges[damage_id] = DamagedEdge(damage_id, u, v, repair_time)

    base = RandomInstance(
        name=str(_require_field(payload, "name", str)),
        seed=int(_require_field(payload, "instance_seed", int)),
        num_nodes=int(_require_field(payload, "num_nodes", int)),
        gamma=int(_require_field(payload, "gamma", int)),
        damage_ratio=float(_require_field(payload, "damage_ratio", (int, float))),
        eta_hours=int(_require_field(payload, "eta_hours", int)),
        horizon_hours=int(_require_field(payload, "horizon_hours", int)),
        graph=graph,
        suppliers=[_require_int_node(node) for node in _require_field(payload, "suppliers", list)],
        demands=[_require_int_node(node) for node in _require_field(payload, "demands", list)],
        demand_amounts=_parse_amount_rows(_require_field(payload, "demand_amounts", list)),
        supply_amounts=_parse_amount_rows(_require_field(payload, "supply_amounts", list)),
        damaged_edges=damaged_edges,
        repair_crews=int(_require_field(payload, "repair_crews", int)),
        vehicle_capacity=float(_require_field(payload, "vehicle_capacity", (int, float))),
        vehicle_count=int(_require_field(payload, "vehicle_count", int)),
    )

    model = _require_field(payload, "model", dict)
    evaluation_payload = _require_field(model, "evaluation", dict)
    try:
        evaluation = EvaluationConfig(**evaluation_payload)
    except (ValueError, TypeError) as error:
        raise SolutionIOError(f"invalid stored evaluation config: {error}") from error

    vehicles = [
        VehicleProfile(
            vehicle_type=int(_require_field(row, "vehicle_type", int)),
            capacity_ton=float(_require_field(row, "capacity_ton", (int, float))),
            count=int(_require_field(row, "count", int)),
            occupied_od_pcu_h=float(_require_field(row, "occupied_od_pcu_h", (int, float))),
            min_recovery_progress=float(
                _require_field(row, "min_recovery_progress", (int, float))
            ),
            pcu_per_vehicle=float(_require_field(row, "pcu_per_vehicle", (int, float))),
            speed_factor=float(_require_field(row, "speed_factor", (int, float))),
        )
        for row in _require_field(model, "vehicles", list)
    ]
    if not vehicles:
        raise SolutionIOError("instance snapshot contains no vehicle profiles")

    recovery_stages = [
        RecoveryStage(
            lower=float(_require_field(row, "lower", (int, float))),
            upper=float(_require_field(row, "upper", (int, float))),
            capacity_ratio=float(_require_field(row, "capacity_ratio", (int, float))),
            label=str(_require_field(row, "label", str)),
            speed_ratio=float(_require_field(row, "speed_ratio", (int, float))),
        )
        for row in _require_field(model, "recovery_stages", list)
    ]
    if not recovery_stages:
        raise SolutionIOError("instance snapshot contains no recovery stages")

    return CapacityExperimentInstance(
        base=base,
        vehicles=vehicles,
        recovery_stages=recovery_stages,
        capacity_scale=float(model["capacity_scale"]),
        repair_time_weight=float(model["repair_time_weight"]),
        crew_transfer_time_scale=float(model["crew_transfer_time_scale"]),
        crew_min_access_progress=float(model["crew_min_access_progress"]),
        progressive_recovery=bool(model["progressive_recovery"]),
        heterogeneous_vehicle_thresholds=bool(model["heterogeneous_vehicle_thresholds"]),
        edge_capacity_constraint=bool(model["edge_capacity_constraint"]),
        evaluation=evaluation,
    )


def _parse_amount_rows(rows: list[Any]) -> dict[int, float]:
    amounts: dict[int, float] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            raise SolutionIOError(f"amount rows must be [node_id, amount], got {row!r}")
        amounts[_require_int_node(row[0])] = float(row[1])
    return amounts


def _require_field(payload: dict[str, Any], key: str, expected: Any) -> Any:
    if not isinstance(payload, dict) or key not in payload:
        raise SolutionIOError(f"missing required field {key!r}")
    value = payload[key]
    if not isinstance(value, expected):
        raise SolutionIOError(
            f"field {key!r} must be {expected}, got {type(value).__name__}"
        )
    return value


# --------------------------------------------------------------------------
# fingerprints
# --------------------------------------------------------------------------


def physical_instance_hash(instance: CapacityExperimentInstance) -> str:
    """Fingerprint of the shared physical scenario.

    Deliberately excludes every planning-model factor (progressive recovery,
    heterogeneous thresholds, edge-capacity accounting) and the evaluation
    profile, so all planning variants of one scenario share this hash.
    """
    base = instance.base
    payload = {
        "format": INSTANCE_FORMAT,
        "format_version": INSTANCE_FORMAT_VERSION,
        "name": base.name,
        "num_nodes": int(base.num_nodes),
        "gamma": int(base.gamma),
        "damage_ratio": float(base.damage_ratio),
        "eta_hours": int(base.eta_hours),
        "horizon_hours": int(base.horizon_hours),
        "repair_crews": int(base.repair_crews),
        "suppliers": [_require_int_node(node) for node in base.suppliers],
        "demands": [_require_int_node(node) for node in base.demands],
        "demand_amounts": _amount_rows(base.demand_amounts),
        "supply_amounts": _amount_rows(base.supply_amounts),
        "nodes": [
            {"id": _require_int_node(node_id), "attrs": _plain_attrs(attrs)}
            for node_id, attrs in sorted(base.graph.nodes(data=True))
        ],
        "edges": [
            {
                "u": u,
                "v": v,
                "free_time": float(data.get("free_time", data.get("weight", 1.0))),
                "weight": float(data.get("weight", data.get("free_time", 1.0))),
                "capacity": float(data.get("capacity", 1000.0)),
                "damaged": bool(data.get("damaged", False)),
                "damage_id": (
                    int(data["damage_id"]) if data.get("damage_id") is not None else None
                ),
                "repair_time": (
                    float(data["repair_time"]) if data.get("repair_time") is not None else None
                ),
            }
            for u, v, data in _sorted_edge(base.graph)
        ],
        "damaged_edges": [
            {
                "damage_id": int(damage_id),
                "u": _require_int_node(edge.u),
                "v": _require_int_node(edge.v),
                "repair_time": float(edge.repair_time),
            }
            for damage_id, edge in sorted(base.damaged_edges.items())
        ],
        # Fleet identity and payload only; the passability threshold is a
        # planning assumption (HT), not part of the physical scene.
        "fleet": [
            {
                "vehicle_type": int(vehicle.vehicle_type),
                "capacity_ton": float(vehicle.capacity_ton),
                "count": int(vehicle.count),
                "occupied_od_pcu_h": float(vehicle.occupied_od_pcu_h),
                "pcu_per_vehicle": float(vehicle.pcu_per_vehicle),
                "speed_factor": float(vehicle.speed_factor),
            }
            for vehicle in instance.vehicles
        ],
        "capacity_scale": float(instance.capacity_scale),
        "repair_time_weight": float(instance.repair_time_weight),
        "crew_transfer_time_scale": float(instance.crew_transfer_time_scale),
        "crew_min_access_progress": float(instance.crew_min_access_progress),
    }
    return _digest(payload)


def model_fingerprint(instance: CapacityExperimentInstance) -> str:
    """Fingerprint of the planning/evaluation/numerical assumptions in force.

    The objective-comparison precision is part of the model: it decides which
    decisions count as tied, which enter the archive, and which one is reported
    as the representative, so two runs that differ only in resolution are not
    the same model and must not share a fingerprint.
    """
    precision = precision_for(instance)
    payload = {
        "physical_instance_hash": physical_instance_hash(instance),
        "objective_precision": precision.as_dict(),
        "objective_precision_fingerprint": precision.fingerprint(),
        "progressive_recovery": bool(instance.progressive_recovery),
        "heterogeneous_vehicle_thresholds": bool(
            instance.heterogeneous_vehicle_thresholds
        ),
        "edge_capacity_constraint": bool(instance.edge_capacity_constraint),
        "vehicle_thresholds": [
            [int(vehicle.vehicle_type), float(vehicle.min_recovery_progress)]
            for vehicle in instance.vehicles
        ],
        "recovery_stages": [
            [float(stage.lower), float(stage.upper), float(stage.capacity_ratio),
             float(stage.speed_ratio)]
            for stage in instance.recovery_stages
        ],
        "evaluation": instance.evaluation.as_dict(),
    }
    return _digest(payload)


# --------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------


def decision_to_json(individual: CapacityIndividual) -> dict[str, Any]:
    return {
        "repair_order": [int(value) for value in individual.repair_order],
        "team_assignment": [int(value) for value in individual.team_assignment],
        "dispatch_priority": [
            [int(supplier), int(demand)] for supplier, demand in individual.dispatch_priority
        ],
    }


def decision_hash(individual: CapacityIndividual) -> str:
    return _digest(
        {
            "repair_order": [int(value) for value in individual.repair_order],
            "team_assignment": [int(value) for value in individual.team_assignment],
            "dispatch_priority": [
                [int(supplier), int(demand)] for supplier, demand in individual.dispatch_priority
            ],
        }
    )[:16]


def decision_from_json(
    payload: Any,
    instance: CapacityExperimentInstance,
) -> CapacityIndividual:
    """Rebuild a clean individual, validating it against its instance.

    A corrupt or mismatched decision raises instead of silently being repaired,
    because a repaired decision would no longer be the decision that was run.
    """
    if not isinstance(payload, dict):
        raise SolutionIOError("decision must be a JSON object")
    repair_order = _require_field(payload, "repair_order", list)
    team_assignment = _require_field(payload, "team_assignment", list)
    dispatch_priority = _require_field(payload, "dispatch_priority", list)

    base = instance.base
    if len(repair_order) != len(team_assignment):
        raise SolutionIOError(
            "repair_order and team_assignment must have the same length "
            f"({len(repair_order)} != {len(team_assignment)})"
        )

    known_damage_ids = set(base.damaged_edges)
    seen: set[int] = set()
    for value in repair_order:
        damage_id = int(value)
        if damage_id not in known_damage_ids:
            raise SolutionIOError(
                f"repair_order references unknown damage id {damage_id}"
            )
        if damage_id in seen:
            raise SolutionIOError(f"repair_order repeats damage id {damage_id}")
        seen.add(damage_id)
    if seen != known_damage_ids:
        missing = sorted(known_damage_ids - seen)
        raise SolutionIOError(f"repair_order omits damage ids {missing}")

    crews = base.repair_crews
    for team_id in team_assignment:
        if not 0 <= int(team_id) < crews:
            raise SolutionIOError(
                f"team_assignment id {team_id} is outside [0, {crews})"
            )

    known_suppliers = set(base.suppliers)
    known_demands = set(base.demands)
    for pair in dispatch_priority:
        if not isinstance(pair, list) or len(pair) != 2:
            raise SolutionIOError(
                f"dispatch_priority entries must be [supplier, demand], got {pair!r}"
            )
        supplier, demand = int(pair[0]), int(pair[1])
        if supplier not in known_suppliers:
            raise SolutionIOError(
                f"dispatch_priority references unknown supplier {supplier}"
            )
        if demand not in known_demands:
            raise SolutionIOError(
                f"dispatch_priority references unknown demand {demand}"
            )

    return CapacityIndividual(
        repair_order=[int(value) for value in repair_order],
        team_assignment=[int(value) for value in team_assignment],
        dispatch_priority=[
            (int(pair[0]), int(pair[1])) for pair in dispatch_priority
        ],
    )


# --------------------------------------------------------------------------
# run keys
# --------------------------------------------------------------------------


def make_run_key(
    *,
    case_id: str,
    instance_seed: int,
    algorithm: str,
    solver_seed: int,
    budget: dict[str, Any],
    model_fingerprint_value: str,
    source_fingerprint: str,
    solver_repeat: int = 0,
    model_id: str = "",
) -> str:
    """Content-addressed run identifier.

    Carries the case, instance, algorithm, model slot and solver seed for
    readability plus a digest over the full configuration, so two different
    configurations cannot collide on the same key.
    """
    for label, value in (
        ("case_id", case_id),
        ("algorithm", algorithm),
        ("model_id", model_id),
    ):
        if value and (":" in value or "/" in value):
            raise SolutionIOError(
                f"{label} must be free of ':' or '/', got {value!r}"
            )
    if not case_id or not algorithm:
        raise SolutionIOError(
            f"case_id and algorithm must be non-empty, got {case_id!r}, {algorithm!r}"
        )
    payload = {
        "case_id": case_id,
        "instance_seed": int(instance_seed),
        "algorithm": algorithm,
        "model_id": model_id,
        "solver_seed": int(solver_seed),
        "solver_repeat": int(solver_repeat),
        "budget": budget,
        "model_fingerprint": model_fingerprint_value,
        "source_fingerprint": source_fingerprint,
    }
    model_slot = f":{model_id}" if model_id else ""
    return (
        f"{case_id}:i{int(instance_seed)}:{algorithm}:s{int(solver_seed)}"
        f":r{int(solver_repeat)}{model_slot}:{_digest(payload)[:12]}"
    )


def run_file_name(run_key: str) -> str:
    return f"{run_key.replace(':', '_')}.json"


# --------------------------------------------------------------------------
# code and environment fingerprints
# --------------------------------------------------------------------------


def source_fingerprint(root: Path, relative_paths: Iterable[str | Path]) -> str:
    """Hash the source files that determine a run's numerical behaviour."""
    payload: dict[str, str] = {}
    for relative_path in relative_paths:
        path = Path(root) / relative_path
        if not path.is_file():
            raise SolutionIOError(f"source file missing: {path}")
        payload[str(relative_path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _digest(payload)


def source_hashes(root: Path, relative_paths: Iterable[str | Path]) -> dict[str, str]:
    return {
        str(relative_path): hashlib.sha256((Path(root) / relative_path).read_bytes()).hexdigest()
        for relative_path in relative_paths
        if (Path(root) / relative_path).is_file()
    }


def code_environment() -> dict[str, Any]:
    return {
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "python": sys.version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_dirty() -> bool | None:
    try:
        return bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return None


# --------------------------------------------------------------------------
# atomic writes
# --------------------------------------------------------------------------


def write_json_atomic(path: Path, payload: Any) -> None:
    """Write JSON through a temporary file and atomically replace the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    _atomic_write(path, text)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, text)


def _atomic_write(path: Path, text: str) -> None:
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_csv_atomic(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if not rows and fieldnames is None:
        write_text_atomic(path, "")
        return
    names = fieldnames if fieldnames is not None else list(rows[0])
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=names, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    write_text_atomic(path, buffer.getvalue())


# --------------------------------------------------------------------------
# run store
# --------------------------------------------------------------------------


@dataclass
class RunStore:
    """Owns the on-disk layout of one experiment directory."""

    root: Path

    @property
    def instances_dir(self) -> Path:
        return self.root / "instances"

    @property
    def executions_dir(self) -> Path:
        return self.root / "executions"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def instance_path(self, model_fingerprint_value: str) -> Path:
        return self.instances_dir / f"{model_fingerprint_value}.json"

    def execution_instance_path(self, physical_hash: str) -> Path:
        return self.executions_dir / f"{physical_hash}.json"

    def run_path(self, run_key: str) -> Path:
        return self.runs_dir / run_file_name(run_key)

    # -- instances ---------------------------------------------------------

    # Metadata keys are stored next to the snapshot body and stripped again on
    # load, so the integrity check covers the snapshot itself.
    _SNAPSHOT_METADATA = ("snapshot_sha256", "physical_instance_hash", "model_fingerprint")

    def save_instance(self, instance: CapacityExperimentInstance) -> str:
        """Store one planning variant and return its model fingerprint.

        Snapshots are keyed by the model fingerprint, not the physical hash,
        because several planning variants legitimately share one physical
        scenario and must not overwrite each other.
        """
        fingerprint = model_fingerprint(instance)
        payload = serialize_instance(instance)
        payload["snapshot_sha256"] = _digest(payload)
        payload["physical_instance_hash"] = physical_instance_hash(instance)
        payload["model_fingerprint"] = fingerprint
        write_json_atomic(self.instance_path(fingerprint), payload)
        return fingerprint

    def save_execution_instance(self, instance: CapacityExperimentInstance) -> str:
        """Store the shared execution environment for one physical scenario."""
        physical_hash = physical_instance_hash(instance)
        payload = serialize_instance(instance)
        payload["snapshot_sha256"] = _digest(payload)
        payload["physical_instance_hash"] = physical_hash
        payload["model_fingerprint"] = model_fingerprint(instance)
        write_json_atomic(self.execution_instance_path(physical_hash), payload)
        return physical_hash

    def load_instance(self, model_fingerprint_value: str) -> CapacityExperimentInstance:
        return self._load_snapshot(
            self.instance_path(model_fingerprint_value),
            expected_model_fingerprint=model_fingerprint_value,
        )

    def load_execution_instance(self, physical_hash: str) -> CapacityExperimentInstance:
        path = self.execution_instance_path(physical_hash)
        payload = _read_json(path)
        if payload.get("physical_instance_hash") != physical_hash:
            raise SolutionIOError(f"execution snapshot {path} does not match its file name")
        return self._load_snapshot(path, expected_physical_hash=physical_hash)

    def _load_snapshot(
        self,
        path: Path,
        *,
        expected_model_fingerprint: str | None = None,
        expected_physical_hash: str | None = None,
    ) -> CapacityExperimentInstance:
        payload = _read_json(path)
        stored = payload.get("snapshot_sha256")
        body = {
            key: value
            for key, value in payload.items()
            if key not in self._SNAPSHOT_METADATA
        }
        if stored is None or _digest(body) != stored:
            raise SolutionIOError(f"instance snapshot {path} failed its integrity check")
        rebuilt = deserialize_instance(body)
        if expected_model_fingerprint is not None:
            actual = model_fingerprint(rebuilt)
            if actual != expected_model_fingerprint:
                raise SolutionIOError(
                    f"rebuilt instance from {path} has model fingerprint {actual}, "
                    f"expected {expected_model_fingerprint}"
                )
        if expected_physical_hash is not None:
            actual = physical_instance_hash(rebuilt)
            if actual != expected_physical_hash:
                raise SolutionIOError(
                    f"rebuilt instance from {path} has physical hash {actual}, "
                    f"expected {expected_physical_hash}"
                )
        return rebuilt

    # -- runs --------------------------------------------------------------

    def save_run(self, record: dict[str, Any]) -> Path:
        run_key = record.get("run_key")
        if not isinstance(run_key, str) or not run_key:
            raise SolutionIOError("run record is missing a run_key")
        payload = dict(record)
        payload["format"] = RUN_FORMAT
        payload["format_version"] = RUN_FORMAT_VERSION
        payload.setdefault("complete", True)
        absolute = self.run_path(run_key)
        payload["record_sha256"] = _digest(
            {key: value for key, value in payload.items() if key != "record_sha256"}
        )
        write_json_atomic(absolute, payload)
        return absolute

    def load_run(self, run_key: str) -> dict[str, Any]:
        return self._validate_run(_read_json(self.run_path(run_key)), run_key)

    def has_complete_run(self, run_key: str) -> bool:
        path = self.run_path(run_key)
        if not path.is_file():
            return False
        try:
            self._validate_run(_read_json(path), run_key)
        except SolutionIOError:
            return False
        return True

    def load_all_runs(self) -> list[dict[str, Any]]:
        if not self.runs_dir.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.runs_dir.glob("*.json")):
            records.append(self._validate_run(_read_json(path), path.stem))
        return records

    def check_source_consistency(self, source_fingerprint_value: str) -> None:
        """Refuse to mix runs produced by different code revisions.

        Every run in one directory must come from the same source fingerprint.
        Mixing revisions would silently combine numbers that were produced by
        different implementations, so the caller is told to use a new directory
        instead.
        """
        stale: list[str] = []
        for path in sorted(self.runs_dir.glob("*.json")) if self.runs_dir.is_dir() else []:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # A partial file from an interrupted write is not evidence of a
                # different revision; the run loop will never treat it as done.
                continue
            if not isinstance(payload, dict):
                continue
            stored = payload.get("source_fingerprint")
            if stored is not None and stored != source_fingerprint_value:
                stale.append(path.name)
        if stale:
            raise SolutionIOError(
                f"{len(stale)} run record(s) in {self.runs_dir} were produced by a "
                "different code revision (for example "
                f"{sorted(stale)[0]}); write this run to a new output directory "
                "instead of mixing revisions"
            )

    def _validate_run(self, payload: dict[str, Any], run_key: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise SolutionIOError(f"run {run_key} is not a JSON object")
        if payload.get("format") != RUN_FORMAT:
            raise SolutionIOError(f"run {run_key} has format {payload.get('format')!r}")
        if payload.get("format_version") != RUN_FORMAT_VERSION:
            raise SolutionIOError(
                f"run {run_key} has unsupported format version "
                f"{payload.get('format_version')!r}"
            )
        if not payload.get("complete"):
            # An interrupted write must never be mistaken for a finished run.
            raise SolutionIOError(f"run {run_key} is not marked complete")
        stored = payload.get("record_sha256")
        body = {key: value for key, value in payload.items() if key != "record_sha256"}
        if stored is None or _digest(body) != stored:
            raise SolutionIOError(f"run {run_key} failed its integrity check")
        if payload.get("run_key") != run_key and run_file_name(
            str(payload.get("run_key"))
        ) != f"{run_key}.json":
            raise SolutionIOError(
                f"run file {run_key} declares a different run_key "
                f"{payload.get('run_key')!r}"
            )
        return payload


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SolutionIOError(f"missing file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SolutionIOError(f"{path} is not valid JSON: {error}") from error


def finite_or_none(value: Any) -> Any:
    """Write an infinite display field as null and mark the substitution."""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


SUMMARY_COLUMNS = (
    "run_key",
    "case_id",
    "suite",
    "source",
    "size_group",
    "num_nodes",
    "instance_seed",
    "solver_seed",
    "solver_repeat",
    "algorithm",
    "model_version",
    "physical_instance_hash",
    "model_fingerprint",
    "decision_hash",
    "evaluations",
    "max_evaluations",
    "termination_reason",
    "proposals",
    "cache_hits",
    "local_search_evaluations",
    "distinct_evaluated",
    "operator_swap_two_repairs",
    "operator_insert_repair",
    "operator_rebalance_team",
    "operator_swap_two_dispatches",
    "operator_move_high_demand_priority",
    "runtime_seconds",
    "pareto_size",
    "reference_front_size",
    "hypervolume",
    "igd",
    "F1",
    "F2",
    "F3",
    "final_total_satisfaction",
    "final_min_satisfaction",
    "average_reachable_ratio",
    "final_repaired_ratio",
    "zero_service_ratio",
    "remaining_supply",
    "total_delivered",
    "unmet_ratio_hours",
    "time_infeasible_candidates",
    "capacity_blocked_tons",
    "total_vehicle_trips",
)

PARETO_COLUMNS = (
    "run_key",
    "case_id",
    "size_group",
    "instance_seed",
    "solver_seed",
    "algorithm",
    "point_id",
    "decision_hash",
    "F1",
    "F2",
    "F3",
    "final_total_satisfaction",
    "final_min_satisfaction",
    "crowding_distance",
    "representative",
)


def build_run_record(
    *,
    run_key: str,
    case_id: str,
    suite: str,
    source: str,
    size_group: str,
    num_nodes: int,
    instance_seed: int,
    solver_seed: int,
    solver_repeat: int,
    algorithm: str,
    instance: CapacityExperimentInstance,
    front: list[CapacityIndividual],
    representative: CapacityIndividual,
    evaluations: int,
    runtime_seconds: float,
    convergence: list[dict[str, float]],
    budget: dict[str, Any],
    termination_reason: str,
    source_fingerprint_value: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble one complete, self-describing run unit."""
    precision = precision_for(instance)
    representative_hash = decision_hash(representative)
    solutions: list[dict[str, Any]] = []
    for index, individual in enumerate(front, start=1):
        objectives = individual.objectives
        if objectives is None:
            raise SolutionIOError(
                f"run {run_key} has an unevaluated candidate in its front"
            )
        metrics = individual.metrics or {}
        solutions.append(
            {
                "solution_id": f"p{index:04d}",
                "decision_hash": decision_hash(individual),
                "objectives": [float(value) for value in objectives],
                "metrics": _finite_metrics(metrics),
                # Infinite crowding distance is a display value; it is written
                # as null because standard JSON has no Infinity literal.
                "crowding_distance": finite_or_none(float(individual.crowding)),
                "decision": decision_to_json(individual),
            }
        )

    record: dict[str, Any] = {
        "run_key": run_key,
        "case_id": case_id,
        "suite": suite,
        "source": source,
        "size_group": size_group,
        "num_nodes": int(num_nodes),
        "instance_seed": int(instance_seed),
        "solver_seed": int(solver_seed),
        "solver_repeat": int(solver_repeat),
        "algorithm": algorithm,
        "budget": dict(budget),
        "evaluations": int(evaluations),
        "runtime_seconds": float(runtime_seconds),
        "termination_reason": termination_reason,
        "physical_instance_hash": physical_instance_hash(instance),
        "model_fingerprint": model_fingerprint(instance),
        "evaluation": instance.evaluation.as_dict(),
        "evaluation_fingerprint": instance.evaluation.fingerprint(),
        # The resolution objectives are compared at. Raw objectives below are
        # the untouched measured values; only the comparison key is quantized.
        "objective_precision": precision.as_dict(),
        "objective_precision_fingerprint": precision.fingerprint(),
        "source_fingerprint": source_fingerprint_value,
        "objectives": [float(value) for value in (representative.objectives or ())],
        "metrics": _finite_metrics(representative.metrics or {}),
        "decision_hash": representative_hash,
        "representative_decision": decision_to_json(representative),
        "pareto_front": solutions,
        "convergence": [
            {key: float(value) for key, value in row.items()} for row in convergence
        ],
        "complete": True,
    }
    if extra:
        record.update(extra)
    return record


def _finite_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, bool):
            output[key] = float(value)
        elif isinstance(value, (int, float)):
            if not _is_finite(value):
                raise SolutionIOError(
                    f"metric {key!r} is not finite ({value!r}); "
                    "objectives and model parameters must be finite"
                )
            output[key] = float(value)
        else:
            raise SolutionIOError(f"metric {key!r} is not numeric ({value!r})")
    return output


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def run_summary_row(record: dict[str, Any]) -> dict[str, Any]:
    objectives = record.get("objectives") or [None, None, None]
    metrics = record.get("metrics") or {}
    diagnostics = record.get("diagnostics") or {}
    row = {
        "run_key": record["run_key"],
        "case_id": record["case_id"],
        "suite": record.get("suite"),
        "source": record.get("source"),
        "size_group": record.get("size_group"),
        "num_nodes": record.get("num_nodes"),
        "instance_seed": record["instance_seed"],
        "solver_seed": record["solver_seed"],
        "solver_repeat": record.get("solver_repeat"),
        "algorithm": record["algorithm"],
        "model_version": (record.get("evaluation") or {}).get("model_version"),
        "physical_instance_hash": record["physical_instance_hash"],
        "model_fingerprint": record["model_fingerprint"],
        "decision_hash": record.get("decision_hash"),
        "evaluations": record.get("evaluations"),
        "max_evaluations": (record.get("budget") or {}).get("max_evaluations"),
        "termination_reason": record.get("termination_reason"),
        "runtime_seconds": record.get("runtime_seconds"),
        "pareto_size": len(record.get("pareto_front") or []),
        "reference_front_size": record.get("reference_front_size"),
        "hypervolume": record.get("hypervolume"),
        "igd": record.get("igd"),
        "F1": objectives[0],
        "F2": objectives[1],
        "F3": objectives[2],
        "final_total_satisfaction": metrics.get("final_total_satisfaction"),
        "final_min_satisfaction": metrics.get("final_min_satisfaction"),
        "average_reachable_ratio": metrics.get("average_reachable_ratio"),
        "final_repaired_ratio": metrics.get("final_repaired_ratio"),
        "zero_service_ratio": metrics.get("zero_service_ratio"),
        "remaining_supply": metrics.get("remaining_supply"),
        "total_delivered": metrics.get("total_delivered"),
        "unmet_ratio_hours": metrics.get("unmet_ratio_hours"),
        "time_infeasible_candidates": metrics.get("time_infeasible_candidates"),
        "capacity_blocked_tons": metrics.get("capacity_blocked_tons"),
        "total_vehicle_trips": metrics.get("total_vehicle_trips"),
        "proposals": diagnostics.get("proposals"),
        "cache_hits": diagnostics.get("cache_hits"),
        "local_search_evaluations": diagnostics.get("local_search_evaluations"),
        "distinct_evaluated": diagnostics.get("distinct_evaluated"),
    }
    # Operator contributions are written as flat columns so the search
    # diagnostics are auditable from the summary CSV alone.
    for key, value in diagnostics.items():
        if key.startswith("operator."):
            row[f"operator_{key.split('.', 1)[1].lstrip('_')}"] = value
    return row


def pareto_point_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for solution in record.get("pareto_front") or []:
        objectives = solution["objectives"]
        metrics = solution.get("metrics") or {}
        rows.append(
            {
                "run_key": record["run_key"],
                "case_id": record["case_id"],
                "size_group": record.get("size_group"),
                "instance_seed": record["instance_seed"],
                "solver_seed": record["solver_seed"],
                "algorithm": record["algorithm"],
                "point_id": solution["solution_id"],
                "decision_hash": solution["decision_hash"],
                "F1": objectives[0],
                "F2": objectives[1],
                "F3": objectives[2],
                "final_total_satisfaction": metrics.get("final_total_satisfaction"),
                "final_min_satisfaction": metrics.get("final_min_satisfaction"),
                "crowding_distance": solution.get("crowding_distance"),
                "representative": (
                    solution["decision_hash"] == record.get("decision_hash")
                ),
            }
        )
    return rows


def solution_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    """One JSONL row per stored non-dominated decision, decisions included."""
    return [
        {
            "run_key": record["run_key"],
            "case_id": record["case_id"],
            "instance_seed": record["instance_seed"],
            "solver_seed": record["solver_seed"],
            "algorithm": record["algorithm"],
            "physical_instance_hash": record["physical_instance_hash"],
            "model_fingerprint": record["model_fingerprint"],
            "evaluation_fingerprint": record.get("evaluation_fingerprint"),
            "solution_id": solution["solution_id"],
            "decision_hash": solution["decision_hash"],
            "objectives": solution["objectives"],
            "metrics": solution.get("metrics") or {},
            "decision": solution["decision"],
        }
        for solution in (record.get("pareto_front") or [])
    ]


def convergence_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "run_key": record["run_key"],
            "case_id": record["case_id"],
            "instance_seed": record["instance_seed"],
            "solver_seed": record["solver_seed"],
            "algorithm": record["algorithm"],
            **row,
        }
        for row in (record.get("convergence") or [])
    ]


def write_store_indexes(
    store: RunStore,
    records: list[dict[str, Any]],
    *,
    reference_front_by_case: dict[tuple[str, int], dict[str, Any]] | None = None,
) -> None:
    """Regenerate the flat summaries from the complete per-run records."""
    summaries = [run_summary_row(record) for record in records]
    if reference_front_by_case:
        for row, record in zip(summaries, records):
            reference = reference_front_by_case.get(
                (record["case_id"], record["instance_seed"])
            )
            if reference:
                row["reference_front_size"] = reference.get("size")
    write_csv_atomic(store.root / "runs.csv", summaries, list(SUMMARY_COLUMNS))

    pareto_rows = [row for record in records for row in pareto_point_rows(record)]
    write_csv_atomic(store.root / "pareto_points.csv", pareto_rows, list(PARETO_COLUMNS))

    convergence_rows_all = [row for record in records for row in convergence_rows(record)]
    write_csv_atomic(store.root / "convergence.csv", convergence_rows_all)

    lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False)
        for record in records
        for row in solution_rows(record)
    ]
    write_text_atomic(
        store.root / "solutions.jsonl",
        "\n".join(lines) + ("\n" if lines else ""),
    )


def write_manifest(store: RunStore, payload: dict[str, Any]) -> None:
    write_json_atomic(store.root / "experiment_manifest.json", payload)
