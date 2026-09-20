"""Does WEN38 naturally contain a threshold-sensitive HT corridor?

The synthetic benchmarks this project has used so far have no bridges at all,
so "HT becomes binding when a damaged road is the only way through" was only
ever testable on a corridor topology invented for the purpose. WEN38 is the
real network: 38 nodes, 51 edges, 8 of them bridges, 5 of those damaged. This
module asks, without touching that network, whether it contains a
*threshold-sensitive corridor* on its own.

Four levels, kept strictly apart because they are not interchangeable:

    structural existence      a damaged edge that some supplier-demand pair
                              depends on (removing it strictly lengthens or
                              severs the route)
    dynamic exposure          at some period start, the recovery progress of a
                              damaged edge admits a strict, non-empty subset of
                              the vehicle types
    dispatch participation    with HT on and off, the same decision produces a
                              different canonical allocation set
    objective effect          those two allocations differ under
                              V2_PRECISION.key()

A bridge is one way to be structural. It is not the definition, and the code
never tests for it: `is_bridge` is recorded as a descriptor and the
classification below is computed from OD dependency, exposure and effect.

Nothing here modifies WEN38: topology, travel times, capacities, the vehicle
thresholds and the v2 evaluation semantics are read through the existing
builders and evaluated with the existing shared evaluator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import networkx as nx

if __package__ == "" or __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.benchmark_algorithms import (
    BenchmarkBudget,
    solve_benchmark_algorithm,
)
from scripts.reproduce.benchmark_suite import BenchmarkSpec, benchmark_specs, build_benchmark_instance
from scripts.reproduce.capacity_recovery import (
    CapacityIndividual,
    FullExecutionProfile,
    DamagedEdge,
    _shortest_paths_for_vehicle,
    evaluate_capacity_solution_detailed,
    model_factor_variant,
)
from scripts.reproduce.mechanism_applicability import (
    DIAGNOSTIC_SOURCES,
    _passable,
    fixed_decisions,
    mechanism_report,
    objective_changed,
    period_trace,
)
from scripts.reproduce.solution_io import (
    code_environment,
    decision_hash,
    decision_to_json,
    source_hashes,
    write_csv_atomic,
    write_json_atomic,
)


CASE_ID = "WEN38"
# WEN38 is one fixed network. The suite builder accepts an instance seed but
# only records it in the instance name; the topology, times, capacities, roles
# and damage are identical for every seed, and `assert_single_physical_network`
# holds the code to that.
WEN38_INSTANCE_SEED = 1

AUDIT_ROOT = Path("outputs/ht_natural_corridor_audit")

# The shared diagnostic sources plus this module: a manifest that pins the
# code it depends on but not the code that produced it would not let a reader
# reproduce the audit from the record alone.
AUDIT_SOURCES = DIAGNOSTIC_SOURCES + ("scripts/reproduce/ht_natural_corridor.py",)
HT_VARIANT = dict(
    progressive_recovery=True,
    heterogeneous_vehicle_thresholds=False,
    edge_capacity_constraint=True,
)

# Fixed decisions per scenario. The original network gets the larger sample
# because it is the object of study; overlays get the smaller one because there
# are many of them and each only needs to answer "did HT trigger here".
ORIGINAL_RANDOM_DECISIONS = 19   # plus SPT = 20
OVERLAY_RANDOM_DECISIONS = 4     # plus SPT = 5

# Scenario strata, fixed before any overlay is run so the grouping cannot be
# chosen to suit the result. Counts are out of the five fixed decisions.
SCENARIO_STRATA = (
    ("inactive", 0, 0),
    ("natural-active", 1, 2),
    ("strong-natural-active", 3, 5),
)


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------


def topology_fingerprint(instance) -> str:
    """Hash of the physical road network only.

    ``physical_instance_hash`` cannot serve here: it includes the instance
    *name*, and WEN38's name carries its instance seed, so the same network
    hashes differently from one seed to the next. This fingerprint covers the
    part an overlay is required to leave untouched -- nodes, edges, free-flow
    times, capacities -- and deliberately excludes roles, damage and demands,
    which overlays are allowed to re-sample.
    """
    graph = instance.base.graph
    payload = {
        "nodes": sorted(int(node) for node in graph.nodes()),
        "edges": sorted(
            [
                int(min(u, v)),
                int(max(u, v)),
                round(float(data["free_time"]), 6),
                round(float(data["capacity"]), 6),
            ]
            for u, v, data in graph.edges(data=True)
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def damaged_bridge_count(instance) -> int:
    """How many of the damaged edges are graph bridges.

    Written once, as a membership test. The obvious-looking set intersection
    (``frozenset(edge) & {frozenset(...), ...}``) is always empty -- it
    intersects a set of node ids with a set of edge keys -- and reported zero
    bridges for every overlay until it was caught.
    """
    damaged = {
        frozenset((int(edge.u), int(edge.v)))
        for edge in instance.base.damaged_edges.values()
    }
    return sum(1 for edge in nx.bridges(instance.base.graph) if frozenset(edge) in damaged)


def total_od_pairs(instance) -> int:
    """Number of ordered supplier-demand pairs; the denominator of dependency."""
    return sum(
        1
        for supplier in instance.base.suppliers
        for demand in instance.base.demands
        if supplier != demand
    )


def assert_single_physical_network(spec: BenchmarkSpec) -> None:
    """WEN38 must not be presented as several independent road networks."""
    fingerprints = {
        topology_fingerprint(build_benchmark_instance(spec, instance_seed=seed, model_version="v2"))
        for seed in (1, 2, 3, 101)
    }
    if len(fingerprints) != 1:
        raise AssertionError(
            "WEN38 is not a single fixed network: instance seeds produced "
            f"{len(fingerprints)} distinct topologies"
        )


def wen38_instance(spec: BenchmarkSpec):
    instance = build_benchmark_instance(
        spec, instance_seed=WEN38_INSTANCE_SEED, model_version="v2"
    )
    return instance


# --------------------------------------------------------------------------
# 1. structural scan
# --------------------------------------------------------------------------


def _distance(graph: nx.Graph, source: int, weight: str) -> dict[int, float]:
    return nx.single_source_dijkstra_path_length(graph, source, weight=weight)


def edge_structure(instance) -> list[dict[str, Any]]:
    """Structural descriptors for every damaged edge.

    Definitions, so the columns can be recomputed by hand:

    - ``od_shortest_path_usage_count``: OD pairs for which this edge lies on
      *some* shortest path. Tested by the exact split condition
      ``d(s,u) + t(e) + d(v,d) == d(s,d)``, so ties need no tie-break.
    - ``od_shortest_path_dependency_count``: OD pairs the edge is *strictly*
      needed by -- removing it lengthens the route or severs it. This is the
      unambiguous "does this road matter for that flow" measure and it is what
      the corridor classification uses.
    Weights here are the restored network's free-flow times: this scan asks
    what losing a road costs the *network*, independent of any period's
    recovery state. The dynamic exposure below answers a different question
    and therefore uses the evaluator's own progress-weighted vehicle graph.

    - ``detour_ratio``: ``d_without_edge(s,d) / d(s,d)``, aggregated only over
      the OD pairs this edge actually affects. Infinite when the pair becomes
      unreachable, and those are counted separately in
      ``detour_ratio_infinite_count`` rather than folded into the mean -- a
      bridge severs its flows instead of lengthening them, so a mean over all
      pairs would read 1.000 and hide exactly the case that matters.
    """
    graph = instance.base.graph
    base = instance.base
    eta_minutes = base.eta_hours * 60
    bridges = {frozenset(edge) for edge in nx.bridges(graph)}
    betweenness = nx.edge_betweenness_centrality(graph)
    betweenness_time = nx.edge_betweenness_centrality(graph, weight="free_time")

    sources = list(base.suppliers)
    sinks = list(base.demands)
    # The denominator of the dependency fraction is the number of OD pairs
    # considered, not the number of demand nodes: dividing by the demand count
    # lets the fraction exceed 1 whenever an edge is needed by more than one
    # supplier for the same demand.
    pair_total = total_od_pairs(instance)
    # All-pairs distances are computed once. Recomputing a Dijkstra inside the
    # OD loop would be a few thousand runs for no benefit.
    all_pairs = {node: _distance(graph, node, "free_time") for node in graph.nodes()}

    rows: list[dict[str, Any]] = []
    for damage_id in sorted(base.damaged_edges):
        damaged = base.damaged_edges[damage_id]
        u, v = int(damaged.u), int(damaged.v)
        traversal = float(graph[u][v]["free_time"])
        pruned = graph.copy()
        pruned.remove_edge(u, v)
        pruned_distances = {
            source: _distance(pruned, source, "free_time") for source in sources
        }

        usage = 0
        dependency = 0
        disconnected = 0
        ratios: list[float] = []
        infinite = 0
        for source in sources:
            for sink in sinks:
                if source == sink:
                    continue
                direct = all_pairs[source].get(sink, float("inf"))
                if direct in (0.0, float("inf")):
                    continue
                # Is the edge on some shortest source->sink path? Tested by the
                # exact split condition rather than by walking one path, so a
                # tie between equal-length routes needs no tie-break.
                via = min(
                    all_pairs[source].get(u, float("inf"))
                    + traversal
                    + all_pairs[v].get(sink, float("inf")),
                    all_pairs[source].get(v, float("inf"))
                    + traversal
                    + all_pairs[u].get(sink, float("inf")),
                )
                if via <= direct + 1e-9:
                    usage += 1
                after = pruned_distances[source].get(sink, float("inf"))
                if after <= direct + 1e-9:
                    # Unaffected pair: not dependent, and its ratio of 1.0
                    # would only dilute the mean severity below.
                    continue
                dependency += 1
                if after == float("inf"):
                    disconnected += 1
                    infinite += 1
                    continue
                ratios.append(after / direct)

        rows.append(
            {
                "damage_id": damage_id,
                "u": u,
                "v": v,
                "is_bridge": frozenset((u, v)) in bridges,
                "edge_betweenness": betweenness.get((u, v), betweenness.get((v, u), 0.0)),
                "edge_betweenness_time": betweenness_time.get(
                    (u, v), betweenness_time.get((v, u), 0.0)
                ),
                "od_pairs_total": pair_total,
                "od_shortest_path_usage_count": usage,
                "od_shortest_path_dependency_count": dependency,
                "od_dependency_fraction": (
                    dependency / pair_total if pair_total else 0.0
                ),
                "alternative_path_exists": disconnected == 0,
                "od_disconnected_count": disconnected,
                "detour_ratio_mean": (
                    sum(ratios) / len(ratios) if ratios else 1.0
                ),
                "detour_ratio_max": max(ratios) if ratios else 1.0,
                "detour_ratio_infinite_count": infinite,
                "repair_time": float(damaged.repair_time),
                "repair_time_over_eta": float(damaged.repair_time) / eta_minutes,
            }
        )
    return rows


# --------------------------------------------------------------------------
# 2. dynamic threshold exposure
# --------------------------------------------------------------------------


def _edge_progress(instance, progress: dict[int, float], u: int, v: int) -> float:
    """Progress of an edge: its repair fraction, or 1.0 if it was never damaged."""
    graph = instance.base.graph
    damage_id = graph[u][v].get("damage_id")
    if damage_id is None:
        return 1.0
    return progress.get(int(damage_id), 0.0)


def allowed_vehicle_types(instance, progress_for_edge: float) -> tuple[int, ...]:
    """Vehicle types the model lets through an edge at this progress.

    Delegates to the shared ``_passable`` so this diagnostic can never drift
    from the evaluator's own passability rule. In particular it is not a table
    of progress bands: passability also requires a positive capacity and speed
    ratio, which is why the bands are read off the model rather than written
    down here.
    """
    return tuple(
        vehicle.vehicle_type
        for vehicle in instance.vehicles
        if _passable(instance, progress_for_edge, vehicle)
    )


def threshold_exposure(instance, decision, decision_id: str) -> dict[str, Any]:
    """Period-by-period threshold exposure for one fixed decision.

    Returns the edge-period rows, the OD-period rows that are actually
    sensitive, and the summary counts. Non-sensitive OD-periods are counted but
    not emitted: the file would otherwise be dominated by rows that say
    nothing (105 pairs x 9 periods x every decision).
    """
    base = instance.base
    graph = base.graph
    trace = period_trace(instance, decision)
    total_types = len(instance.vehicles)

    edge_rows: list[dict[str, Any]] = []
    od_rows: list[dict[str, Any]] = []
    sensitive_edge_periods = 0
    sensitive_od_periods = 0
    od_periods_considered = 0
    access_set_changes = 0

    damaged_ids = sorted(base.damaged_edges)
    for snapshot in trace.snapshots:
        period = snapshot.period
        # Per vehicle type: which edges exist, and the resulting distances.
        allowed_by_edge: dict[int, tuple[int, ...]] = {}
        for damage_id in damaged_ids:
            allowed = allowed_vehicle_types(instance, snapshot.progress.get(damage_id, 0.0))
            allowed_by_edge[damage_id] = allowed
            damaged = base.damaged_edges[damage_id]
            sensitive = 0 < len(allowed) < total_types
            if sensitive:
                sensitive_edge_periods += 1
            edge_rows.append(
                {
                    "decision_id": decision_id,
                    "period": period,
                    "damage_id": damage_id,
                    "u": int(damaged.u),
                    "v": int(damaged.v),
                    "progress": snapshot.progress.get(damage_id, 0.0),
                    "allowed_vehicle_count": len(allowed),
                    "allowed_vehicle_types": "|".join(str(t) for t in allowed),
                    "threshold_sensitive_edge": sensitive,
                }
            )

        # The evaluator's own vehicle graph and OD paths. Using raw free_time
        # here would ignore the recovery speed ratio and the vehicle speed
        # factor, and would let the diagnostic disagree with the model it is
        # measuring -- the travel times below are the ones the evaluator
        # actually routes on.
        vehicle_types = [vehicle.vehicle_type for vehicle in instance.vehicles]
        paths: dict[int, dict[tuple[int, int], tuple[float, list[int]]]] = {
            vehicle.vehicle_type: _shortest_paths_for_vehicle(
                instance, snapshot.progress, vehicle
            )
            for vehicle in instance.vehicles
        }

        sensitive_pairs = {
            frozenset((int(base.damaged_edges[i].u), int(base.damaged_edges[i].v)))
            for i in damaged_ids
            if 0 < len(allowed_by_edge[i]) < total_types
        }

        for source in base.suppliers:
            for sink in base.demands:
                if source == sink:
                    continue
                od_periods_considered += 1
                best: dict[int, float] = {}
                routes: dict[int, list[int]] = {}
                for vehicle_type in vehicle_types:
                    entry = paths[vehicle_type].get((source, sink))
                    if entry is None:
                        best[vehicle_type] = float("inf")
                    else:
                        best[vehicle_type], routes[vehicle_type] = entry
                reachable = [t for t in vehicle_types if best[t] < float("inf")]
                unreachable = [t for t in vehicle_types if best[t] == float("inf")]
                feasibility_split = bool(reachable) and bool(unreachable)

                # Two separate questions, reported separately: do the types
                # take different routes, and do they take different amounts of
                # time? Equal-length routes that differ are a path split but
                # not a travel-time split, and only the latter changes F2.
                edge_sets = {
                    frozenset(
                        frozenset((int(a), int(b)))
                        for a, b in zip(routes[t], routes[t][1:])
                    )
                    for t in reachable
                }
                time_sets = {round(best[t], 9) for t in reachable}
                path_split = len(edge_sets) > 1
                travel_time_split = len(time_sets) > 1

                on_path: set[frozenset] = set()
                for vehicle_type in reachable:
                    route = routes[vehicle_type]
                    for a, b in zip(route, route[1:]):
                        on_path.add(frozenset((int(a), int(b))))
                sensitive_edges = len(on_path & sensitive_pairs)

                if not (feasibility_split or path_split or travel_time_split):
                    continue
                sensitive_od_periods += 1
                access_set_changes += int(feasibility_split)
                od_rows.append(
                    {
                        "decision_id": decision_id,
                        "period": period,
                        "supplier": int(source),
                        "demand": int(sink),
                        "vehicle_feasibility_split": feasibility_split,
                        "vehicle_path_split": path_split,
                        "vehicle_travel_time_split": travel_time_split,
                        "reachable_vehicle_types": "|".join(str(t) for t in reachable),
                        "threshold_sensitive_edges_on_candidate_paths": sensitive_edges,
                        "best_travel_time_min": min(best.values()),
                        "best_travel_time_by_vehicle": "|".join(
                            f"{t}:{'inf' if best[t] == float('inf') else round(best[t], 3)}"
                            for t in vehicle_types
                        ),
                    }
                )

    return {
        "edge_rows": edge_rows,
        "od_rows": od_rows,
        "summary": {
            "threshold_sensitive_edge_periods": sensitive_edge_periods,
            "threshold_sensitive_od_periods": sensitive_od_periods,
            "od_periods_considered": od_periods_considered,
            "vehicle_access_set_changes": access_set_changes,
        },
    }


# --------------------------------------------------------------------------
# 3. fixed-decision effect (dispatch participation + objective effect)
# --------------------------------------------------------------------------


def fixed_decision_effect(instance, decision, decision_id: str) -> dict[str, Any]:
    """HT on vs off with the decision held fixed.

    ``mechanism_report`` already performs exactly this comparison with the
    canonical allocation multiset and the quantized objective key, so it is
    reused rather than reimplemented -- the spec's requirement that the
    comparison be the shared one is met by construction.
    """
    report = mechanism_report(instance, decision, decision_id)
    return {
        "decision_id": decision_id,
        "decision_hash": decision_hash(decision),
        "threshold_sensitive_edge_periods": report["threshold_sensitive_edge_periods"],
        "threshold_sensitive_od_periods": report["threshold_sensitive_od_periods"],
        "vehicle_access_set_changes": report["vehicle_access_set_changes"],
        "allocation_route_changed": report["HT_allocation_route_changed"],
        "allocation_vehicle_changed": report["HT_allocation_vehicle_changed"],
        "allocation_amount_changed": report["HT_allocation_amount_changed"],
        "allocation_trips_changed": report["HT_allocation_trips_changed"],
        "allocation_pairing_changed": report["HT_allocation_pairing_changed"],
        "allocation_any_changed": report["HT_allocations_changed"],
        "delta_F1": report["HT_same_decision_delta_F1"],
        "delta_F2": report["HT_same_decision_delta_F2"],
        "delta_F3": report["HT_same_decision_delta_F3"],
        "F1": report["F1"],
        "F2": report["F2"],
        "F3": report["F3"],
        "no_ht_F1": report["F1"] + report["HT_same_decision_delta_F1"],
        "no_ht_F2": report["F2"] + report["HT_same_decision_delta_F2"],
        "no_ht_F3": report["F3"] + report["HT_same_decision_delta_F3"],
        "objective_changed": report["HT_same_decision_changed"],
    }


def evaluate_decisions(instance, decisions: dict[str, CapacityIndividual]) -> dict[str, Any]:
    """Run one fixed-decision batch and collect every level of evidence."""
    edge_rows: list[dict[str, Any]] = []
    od_rows: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    for decision_id, decision in decisions.items():
        exposure = threshold_exposure(instance, decision, decision_id)
        edge_rows.extend(exposure["edge_rows"])
        od_rows.extend(exposure["od_rows"])
        effect = fixed_decision_effect(instance, decision, decision_id)
        effect.update(exposure["summary"])
        effects.append(effect)
    return {"edge_rows": edge_rows, "od_rows": od_rows, "effects": effects}


# --------------------------------------------------------------------------
# 4. corridor ranking
# --------------------------------------------------------------------------


def corridor_ranking(
    structure: Sequence[dict[str, Any]],
    edge_rows: Sequence[dict[str, Any]],
    effects: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Per damaged edge: structural descriptors plus the four levels.

    The per-edge dispatch and objective columns are restricted to the decisions
    in which *that* edge was threshold-sensitive. That is a well-defined
    conditional count, not a causal attribution: the objective is a global
    quantity for the whole decision, and no per-edge effect can be read off it
    without an ablation that this diagnostic does not run.
    """
    by_edge: dict[int, list[dict[str, Any]]] = {}
    for row in edge_rows:
        by_edge.setdefault(int(row["damage_id"]), []).append(row)

    changed_decisions = [e for e in effects if e["objective_changed"]]
    rows: list[dict[str, Any]] = []
    for entry in structure:
        damage_id = int(entry["damage_id"])
        periods = by_edge.get(damage_id, [])
        sensitive_periods = sum(1 for p in periods if p["threshold_sensitive_edge"])
        sensitive_decisions = {p["decision_id"] for p in periods if p["threshold_sensitive_edge"]}
        relevant = [e for e in effects if e["decision_id"] in sensitive_decisions]

        dispatch_decisions = [e for e in relevant if e["allocation_any_changed"] > 0]
        objective_decisions = [e for e in relevant if e["objective_changed"]]

        row = dict(entry)
        row.update(
            {
                "threshold_sensitive_periods": sensitive_periods,
                "decisions_where_sensitive": len(sensitive_decisions),
                "decisions_tested": len(effects),
                "sensitive_od_periods": sum(
                    e["threshold_sensitive_od_periods"] for e in relevant
                ),
                "dispatch_changed_decisions": len(dispatch_decisions),
                "objective_changed_decisions": len(objective_decisions),
                "max_abs_delta_F1": max(
                    (abs(e["delta_F1"]) for e in relevant), default=0.0
                ),
                "max_abs_delta_F2": max(
                    (abs(e["delta_F2"]) for e in relevant), default=0.0
                ),
                "max_abs_delta_F3": max(
                    (abs(e["delta_F3"]) for e in relevant), default=0.0
                ),
                # The four levels, deliberately as four columns. Collapsing
                # them into one "is a corridor" label is exactly the
                # over-claim this diagnostic exists to avoid.
                "structural_corridor": entry["od_shortest_path_dependency_count"] > 0,
                "dynamic_threshold_corridor": sensitive_periods > 0,
                "operational_corridor": len(dispatch_decisions) > 0,
                "objective_binding_corridor": len(objective_decisions) > 0,
                "any_objective_effect_on_network": len(changed_decisions) > 0,
            }
        )
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# 5. semi-real overlays
# --------------------------------------------------------------------------


def scenario_stratum(objective_changed_decisions: int) -> str:
    for label, low, high in SCENARIO_STRATA:
        if low <= objective_changed_decisions <= high:
            return label
    raise ValueError(f"no stratum for {objective_changed_decisions} changed decisions")


def _rebuild(instance, base, label: str):
    """A new instance on the same physical network, with a declared profile.

    The Full profile is rebuilt from the modified instance so a later
    ``model_factor_variant`` restores this overlay's own declared data rather
    than the original network's.
    """
    new_base = replace(base, name=label)
    overlay = replace(instance, base=new_base)
    overlay.full_profile = FullExecutionProfile.from_instance(overlay, f"{label}_full")
    return overlay


def role_overlay(instance, seed: int):
    """SR-A: re-sample which nodes are suppliers and demands.

    Topology, road times, road capacities and the damage realization are
    untouched. Supplier and demand *counts* and the total demand are held at
    the original values, so only the spatial arrangement of the flows changes.
    """
    rng = random.Random(seed)
    base = instance.base
    nodes = sorted(int(node) for node in base.graph.nodes())
    supplier_count = len(base.suppliers)
    suppliers = sorted(rng.sample(nodes, supplier_count))

    remaining = [node for node in nodes if node not in suppliers]
    demand_count = min(len(base.demands), len(remaining))
    demands = sorted(rng.sample(remaining, demand_count))

    # Keep the amount multisets and re-assign them: the total is preserved
    # exactly, and no demand or supply value is invented.
    demand_pool = sorted(base.demand_amounts.values())
    rng.shuffle(demand_pool)
    demand_amounts = dict(zip(demands, demand_pool))

    supply_pool = sorted(base.supply_amounts.values())
    rng.shuffle(supply_pool)
    supply_amounts = dict(zip(suppliers, supply_pool))

    new_base = replace(
        base,
        suppliers=suppliers,
        demands=demands,
        demand_amounts=demand_amounts,
        supply_amounts=supply_amounts,
    )
    return _rebuild(instance, new_base, f"SR-A_seed{seed}")


def damage_overlay(instance, seed: int):
    """SR-B: re-sample which edges are damaged, uniformly at random.

    Edges are drawn uniformly, with no preference for bridges or for high
    betweenness -- ``verify_uniform_damage_sampling`` checks that the realized
    bridge share matches the network's base rate. The original repair-time
    multiset is re-assigned to the sampled edges, so the repair durations stay
    the network's own; no time is shortened to keep an edge in a partial state.
    """
    rng = random.Random(seed)
    base = instance.base
    graph = base.graph.copy()
    for u, v, data in graph.edges(data=True):
        data["damaged"] = False
        data.pop("damage_id", None)
        data.pop("repair_time", None)

    edges = sorted((int(u), int(v)) for u, v in base.graph.edges())
    count = len(base.damaged_edges)
    sampled = sorted(rng.sample(edges, count))
    repair_pool = sorted(float(d.repair_time) for d in base.damaged_edges.values())
    rng.shuffle(repair_pool)

    damaged_edges: dict[int, DamagedEdge] = {}
    for damage_id, ((u, v), repair_time) in enumerate(zip(sampled, repair_pool)):
        graph[u][v]["damaged"] = True
        graph[u][v]["damage_id"] = damage_id
        graph[u][v]["repair_time"] = repair_time
        damaged_edges[damage_id] = DamagedEdge(damage_id, u, v, repair_time)

    new_base = replace(
        base,
        graph=graph,
        damaged_edges=damaged_edges,
        damage_ratio=len(damaged_edges) / graph.number_of_edges(),
    )
    return _rebuild(instance, new_base, f"SR-B_seed{seed}")


def combined_overlay(instance, seed: int):
    """SR-C: re-sample business roles and damage together."""
    return damage_overlay(role_overlay(instance, seed), seed)


OVERLAYS = (
    ("SR-A", "role", role_overlay),
    ("SR-B", "damage", damage_overlay),
    ("SR-C", "role+damage", combined_overlay),
)


def verify_uniform_damage_sampling(instance, seed: int, draws: int = 200) -> dict[str, Any]:
    """Check the damage overlay really samples edges uniformly.

    A natural overlay must not be a stress scenario in disguise. The test is
    distributional: over many seeds, the share of damaged edges that are
    bridges has to match the network's own bridge share, not exceed it.
    """
    graph = instance.base.graph
    bridges = {frozenset(edge) for edge in nx.bridges(graph)}
    edges = sorted((int(u), int(v)) for u, v in graph.edges())
    bridge_share = len(bridges) / len(edges)
    observed = []
    for offset in range(draws):
        overlay = damage_overlay(instance, seed * 100_000 + offset)
        damaged = overlay.base.damaged_edges.values()
        selected = {frozenset((int(d.u), int(d.v))) for d in damaged}
        observed.append(len(selected & bridges) / max(len(selected), 1))
    mean = sum(observed) / len(observed)
    return {
        "draws": draws,
        "network_bridge_share": bridge_share,
        "mean_sampled_bridge_share": mean,
        "min_sampled_bridge_share": min(observed),
        "max_sampled_bridge_share": max(observed),
        # Uniform sampling fluctuates around the base rate. A stress overlay
        # that hunted for bridges would sit far above it.
        "within_base_rate_band": abs(mean - bridge_share) <= 0.10,
    }


# --------------------------------------------------------------------------
# 6. small-budget search: Full vs No-HT, then one common Full replay
# --------------------------------------------------------------------------


def search_and_replay(
    instance,
    *,
    budget: BenchmarkBudget,
    solver_seeds: Sequence[int],
    label: str,
) -> list[dict[str, Any]]:
    """Plan under Full and under No-HT, then replay both into the Full model.

    Only the HT factor is switched; PR and EC stay as the scenario declares
    them, so a difference cannot be attributed to another mechanism.
    """
    full = model_factor_variant(
        instance,
        progressive_recovery=instance.progressive_recovery,
        heterogeneous_vehicle_thresholds=True,
        edge_capacity_constraint=instance.edge_capacity_constraint,
    )
    no_ht = model_factor_variant(instance, **HT_VARIANT)

    rows: list[dict[str, Any]] = []
    for solver_seed in solver_seeds:
        planned = {
            "Full": solve_benchmark_algorithm("nsga2", full, budget, seed=solver_seed),
            "No-HT": solve_benchmark_algorithm("nsga2", no_ht, budget, seed=solver_seed),
        }
        for planning_model, run in planned.items():
            for index, individual in enumerate(run.front):
                planning = tuple(individual.objectives or (0.0, 0.0, 0.0))
                execution = evaluate_capacity_solution_detailed(
                    full,
                    CapacityIndividual(
                        list(individual.repair_order),
                        list(individual.team_assignment),
                        list(individual.dispatch_priority),
                    ),
                ).objectives
                flags = objective_changed(planning, execution)
                rows.append(
                    {
                        "label": label,
                        "solver_seed": solver_seed,
                        "planning_model": planning_model,
                        "solution_index": index,
                        "decision_hash": decision_hash(individual),
                        "planning_F1": planning[0],
                        "planning_F2": planning[1],
                        "planning_F3": planning[2],
                        "execution_F1": execution[0],
                        "execution_F2": execution[1],
                        "execution_F3": execution[2],
                        "delta_F1": execution[0] - planning[0],
                        "delta_F2": execution[1] - planning[1],
                        "delta_F3": execution[2] - planning[2],
                        "objective_changed": flags["changed"],
                        "changed_F1": flags["changed_F1"],
                        "changed_F2": flags["changed_F2"],
                        "changed_F3": flags["changed_F3"],
                        "is_full_self_replay": planning_model == "Full",
                        "decision": json.dumps(decision_to_json(individual)),
                    }
                )
    return rows


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def main() -> None:
    args = _parse_args()
    audit = Path(args.output_dir)
    audit.mkdir(parents=True, exist_ok=True)

    spec = {s.case_id: s for s in benchmark_specs(args.suite)}[CASE_ID]
    if args.instance_seeds != [WEN38_INSTANCE_SEED]:
        raise SystemExit(
            f"{CASE_ID} is one fixed road network; run it with "
            f"--instance-seeds {WEN38_INSTANCE_SEED}"
        )
    assert_single_physical_network(spec)
    instance = wen38_instance(spec)
    graph = instance.base.graph
    print(f"{CASE_ID}: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges, "
          f"{len(instance.base.damaged_edges)} damaged")

    # --- stage 1+2+3: the original network -------------------------------
    structure = edge_structure(instance)
    decisions = fixed_decisions(
        instance, random_decisions=ORIGINAL_RANDOM_DECISIONS, seed=WEN38_INSTANCE_SEED
    )
    original = evaluate_decisions(instance, decisions)
    ranking = corridor_ranking(structure, original["edge_rows"], original["effects"])

    write_csv_atomic(audit / "wen38_edge_structure.csv", structure, list(structure[0]))
    write_csv_atomic(
        audit / "wen38_ht_exposure.csv",
        original["edge_rows"],
        list(original["edge_rows"][0]),
    )
    if original["od_rows"]:
        write_csv_atomic(
            audit / "wen38_ht_od_exposure.csv",
            original["od_rows"],
            list(original["od_rows"][0]),
        )
    write_csv_atomic(
        audit / "wen38_ht_fixed_decision_effect.csv",
        original["effects"],
        list(original["effects"][0]),
    )
    write_csv_atomic(
        audit / "wen38_ht_corridor_ranking.csv", ranking, list(ranking[0])
    )

    # --- stage 4: semi-real overlays ------------------------------------
    overlay_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    topology_reference = topology_fingerprint(instance)
    for overlay_type, description, builder in OVERLAYS:
        for seed in range(1, args.overlay_seeds + 1):
            overlay = builder(instance, seed)
            fingerprint = topology_fingerprint(overlay)
            if fingerprint != topology_reference:
                raise AssertionError(
                    f"{overlay_type} seed {seed} changed the physical network"
                )
            sample = fixed_decisions(
                overlay, random_decisions=OVERLAY_RANDOM_DECISIONS, seed=seed
            )
            result = evaluate_decisions(overlay, sample)
            effects = result["effects"]
            changed = [e for e in effects if e["objective_changed"]]
            dispatch = [e for e in effects if e["allocation_any_changed"] > 0]
            exposed = [e for e in effects if e["threshold_sensitive_od_periods"] > 0]
            stratum = scenario_stratum(len(changed))

            overlay_rows.append(
                {
                    "overlay_type": overlay_type,
                    "overlay_description": description,
                    "overlay_seed": seed,
                    "scenario_stratum": stratum,
                    "topology_fingerprint": fingerprint,
                    "topology_unchanged": fingerprint == topology_reference,
                    "suppliers": "|".join(str(s) for s in overlay.base.suppliers),
                    "demand_count": len(overlay.base.demands),
                    "damaged_edge_count": len(overlay.base.damaged_edges),
                    "damaged_bridge_count": damaged_bridge_count(overlay),
                    "total_demand": overlay.base.total_demand,
                    "total_supply": overlay.base.total_supply,
                }
            )
            summary_rows.append(
                {
                    "overlay_type": overlay_type,
                    "overlay_seed": seed,
                    "scenario_stratum": stratum,
                    "decisions_tested": len(effects),
                    "decisions_with_exposure": len(exposed),
                    "decisions_with_dispatch_change": len(dispatch),
                    "decisions_with_objective_change": len(changed),
                    "num_threshold_sensitive_edges": len(
                        {r["damage_id"] for r in result["edge_rows"] if r["threshold_sensitive_edge"]}
                    ),
                    "num_threshold_sensitive_od_periods": sum(
                        e["threshold_sensitive_od_periods"] for e in effects
                    ),
                    "mean_abs_delta_F1": _mean_abs(effects, "delta_F1"),
                    "max_abs_delta_F1": _max_abs(effects, "delta_F1"),
                    "mean_abs_delta_F2": _mean_abs(effects, "delta_F2"),
                    "max_abs_delta_F2": _max_abs(effects, "delta_F2"),
                }
            )
            for effect in effects:
                row = {"overlay_type": overlay_type, "overlay_seed": seed}
                row.update(effect)
                decision_rows.append(row)

    write_csv_atomic(
        audit / "semi_real_overlay_manifest.csv", overlay_rows, list(overlay_rows[0])
    )
    write_csv_atomic(
        audit / "semi_real_ht_summary.csv", summary_rows, list(summary_rows[0])
    )
    write_csv_atomic(
        audit / "semi_real_ht_decisions.csv", decision_rows, list(decision_rows[0])
    )

    # The natural-overlay claim is only meaningful if the damage overlays are
    # really uniform draws, so it is measured rather than asserted.
    sampling_check = verify_uniform_damage_sampling(instance, seed=1, draws=args.sampling_draws)

    # --- stage 5: small-budget search on selected strata -----------------
    replay_rows: list[dict[str, Any]] = []
    if args.search:
        replay_rows = _run_search(instance, summary_rows, args)

    write_csv_atomic(
        audit / "wen38_ht_search_replay.csv",
        replay_rows,
        list(replay_rows[0]) if replay_rows else ["label", "objective_changed"],
    )
    write_json_atomic(
        audit / "manifest.json",
        _manifest(
            spec=spec,
            instance=instance,
            structure=structure,
            effects=original["effects"],
            ranking=ranking,
            summary_rows=summary_rows,
            overlay_rows=overlay_rows,
            sampling_check=sampling_check,
            replay_rows=replay_rows,
            args=args,
            topology_fingerprint_value=topology_reference,
        ),
    )
    print(f"Wrote HT natural-corridor audit to {audit}")


REPRESENTATIVE_RULE = (
    "lowest overlay_seed within each stratum; ties broken by overlay_type lexical order"
)


def choose_stratum_representative(
    candidates: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """The one overlay that represents a stratum in the search stage.

    Both keys are explicit. Ordering on the seed alone would leave the choice
    between two overlay types sharing the lowest seed to depend on the order
    ``summary_rows`` happened to be built in, which is not a rule a reader can
    reproduce. Selecting on the measured effect would be worse still: it would
    turn the replayed figures into a best case rather than a representative
    one.
    """
    return min(
        candidates,
        key=lambda row: (int(row["overlay_seed"]), str(row["overlay_type"])),
    )


def _run_search(instance, summary_rows, args) -> list[dict[str, Any]]:
    """One representative per stratum, chosen by a rule fixed in advance.

    The result is a diagnostic representative, not a population average: it is
    one overlay per stratum, so the replay figures below describe what happens
    in those two overlays and must not be read as the typical natural-scenario
    effect size.
    """
    rows: list[dict[str, Any]] = []
    budget = BenchmarkBudget(max_evaluations=args.max_evaluations, pop_size=args.pop_size)
    by_stratum: dict[str, list[dict[str, Any]]] = {}
    for row in summary_rows:
        by_stratum.setdefault(row["scenario_stratum"], []).append(row)
    for stratum, _low, _high in SCENARIO_STRATA:
        candidates = by_stratum.get(stratum, [])
        if not candidates:
            continue
        chosen = choose_stratum_representative(candidates)
        builder = {name: fn for name, _desc, fn in OVERLAYS}[chosen["overlay_type"]]
        overlay = builder(instance, int(chosen["overlay_seed"]))
        rows.extend(
            search_and_replay(
                overlay,
                budget=budget,
                solver_seeds=args.solver_seeds,
                label=f"{chosen['overlay_type']}_seed{chosen['overlay_seed']}_{stratum}",
            )
        )
    return rows


def _mean_abs(rows: Sequence[dict[str, Any]], key: str) -> float:
    values = [abs(float(row[key])) for row in rows]
    return sum(values) / len(values) if values else 0.0


def _max_abs(rows: Sequence[dict[str, Any]], key: str) -> float:
    values = [abs(float(row[key])) for row in rows]
    return max(values) if values else 0.0


def _manifest(
    *,
    spec: BenchmarkSpec,
    instance,
    structure,
    effects,
    ranking,
    summary_rows,
    overlay_rows,
    sampling_check,
    replay_rows,
    args,
    topology_fingerprint_value: str,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    changed = [e for e in effects if e["objective_changed"]]
    dispatch = [e for e in effects if e["allocation_any_changed"] > 0]
    exposed = [e for e in effects if e["threshold_sensitive_od_periods"] > 0]
    return {
        "scope": (
            "natural HT threshold-sensitive corridor diagnostic on the WEN38 "
            "road network and semi-real overlays of it; WEN38 topology, travel "
            "times, capacities, thresholds and v2 semantics are unmodified"
        ),
        "case_id": CASE_ID,
        "suite": args.suite,
        "instance_seeds": list(args.instance_seeds),
        "single_physical_network": True,
        "wen38_topology_fingerprint": topology_fingerprint_value,
        "network": {
            "num_nodes": instance.base.graph.number_of_nodes(),
            "num_edges": instance.base.graph.number_of_edges(),
            "graph_bridge_count": len(list(nx.bridges(instance.base.graph))),
            "damaged_edge_count": len(instance.base.damaged_edges),
            "damaged_bridge_count": damaged_bridge_count(instance),
            "supplier_count": len(instance.base.suppliers),
            "demand_count": len(instance.base.demands),
            "total_demand": instance.base.total_demand,
            "total_supply": instance.base.total_supply,
        },
        "vehicle_thresholds": [
            {"vehicle_type": v.vehicle_type, "min_recovery_progress": v.min_recovery_progress}
            for v in instance.vehicles
        ],
        "recovery_stages": [stage.capacity_ratio for stage in instance.recovery_stages],
        "eta_hours": instance.base.eta_hours,
        "horizon_hours": instance.base.horizon_hours,
        "periods": instance.base.periods,
        "fixed_decisions": {
            "original_random_decisions": args.random_decisions,
            "overlay_random_decisions": OVERLAY_RANDOM_DECISIONS,
            "original_decisions_tested": len(effects),
        },
        "scenario_strata": [
            {"label": label, "min_changed_decisions": low, "max_changed_decisions": high}
            for label, low, high in SCENARIO_STRATA
        ],
        "original_network_result": {
            "decisions_tested": len(effects),
            "decisions_with_exposure": len(exposed),
            "decisions_with_dispatch_change": len(dispatch),
            "decisions_with_objective_change": len(changed),
            "structural_corridor_edges": sum(
                1 for r in ranking if r["structural_corridor"]
            ),
            "dynamic_threshold_corridor_edges": sum(
                1 for r in ranking if r["dynamic_threshold_corridor"]
            ),
            "operational_corridor_edges": sum(
                1 for r in ranking if r["operational_corridor"]
            ),
            "objective_binding_corridor_edges": sum(
                1 for r in ranking if r["objective_binding_corridor"]
            ),
            "structural_corridor_bridges": sum(
                1 for r in ranking if r["structural_corridor"] and r["is_bridge"]
            ),
            "operational_corridor_bridges": sum(
                1 for r in ranking if r["operational_corridor"] and r["is_bridge"]
            ),
        },
        "damage_sampling_check": sampling_check,
        "overlay_design": {
            "types": [name for name, _desc, _fn in OVERLAYS],
            "seeds_per_type": args.overlay_seeds,
            "statistical_unit": (
                "scenario overlays on one common physical topology; not "
                "independent road networks"
            ),
            "constraints": (
                "damage is sampled uniformly over edges with the original "
                "repair-time multiset re-assigned; no bridge or betweenness "
                "preference, no repair-time adjustment, no threshold change"
            ),
            "topology_invariant_across_overlays": all(
                row["topology_unchanged"] for row in overlay_rows
            ),
            "overlays_run": len(overlay_rows),
            "strata_counts": {
                label: sum(1 for row in summary_rows if row["scenario_stratum"] == label)
                for label, _low, _high in SCENARIO_STRATA
            },
        },
        "search": {
            "enabled": bool(args.search),
            "algorithm": "nsga2",
            "max_evaluations": args.max_evaluations,
            "pop_size": args.pop_size,
            "solver_seeds": list(args.solver_seeds),
            "planning_models": ["Full", "No-HT"],
            "representative_rule": REPRESENTATIVE_RULE,
            "representativeness": (
                "one diagnostic representative per stratum; the replay figures "
                "are not a population average over overlays"
            ),
            "strata_searched": sorted(
                {row["label"].rsplit("_", 1)[-1] for row in replay_rows}
            ),
            "execution_model": "Full",
            "replayed_rows": len(replay_rows),
        },
        "objective_comparison": "V2_PRECISION quantized key, all three objectives",
        "allocation_comparison": (
            "shared canonical allocation multiset (supplier, demand, vehicle, "
            "route, amount, trips, travel time) with per-field and pairing flags"
        ),
        "code": code_environment(),
        "source_hashes": source_hashes(root, AUDIT_SOURCES),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WEN38 natural HT threshold-sensitive corridor diagnostic.",
    )
    parser.add_argument("--suite", choices=["benchmark", "publication"], default="benchmark")
    parser.add_argument("--instance-seeds", type=int, nargs="+", default=[WEN38_INSTANCE_SEED])
    parser.add_argument("--random-decisions", type=int, default=ORIGINAL_RANDOM_DECISIONS)
    parser.add_argument("--overlay-seeds", type=int, default=20)
    parser.add_argument("--sampling-draws", type=int, default=200)
    parser.add_argument("--search", action="store_true", help="run the Full vs No-HT search stage")
    parser.add_argument("--max-evaluations", type=int, default=200)
    parser.add_argument("--pop-size", type=int, default=16)
    parser.add_argument("--solver-seeds", type=int, nargs="+", default=[70_001, 70_002])
    parser.add_argument("--output-dir", default=str(AUDIT_ROOT))
    return parser.parse_args()


if __name__ == "__main__":
    main()
