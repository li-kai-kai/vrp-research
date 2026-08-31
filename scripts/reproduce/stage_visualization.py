from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

from scripts.reproduce.capacity_recovery import (
    _capacity_ratio,
    build_simulation_instance,
    build_wenchuan_instance,
)
from scripts.reproduce.dynamic_interaction_experiments import (
    MECHANISMS,
    _apply_stress,
    _variant,
    run_mechanism,
)


WENCHUAN_POS = {
    1: (103.62, 30.99), 2: (103.99, 30.95), 3: (104.16, 31.10),
    4: (103.54, 30.98), 5: (103.52, 30.94), 6: (103.54, 30.89),
    7: (103.55, 30.82), 8: (103.58, 30.78), 9: (103.62, 30.82),
    10: (103.63, 30.90), 11: (103.58, 31.04), 12: (103.52, 31.07),
    13: (103.65, 31.00), 14: (103.69, 30.96), 15: (103.70, 30.90),
    16: (103.70, 31.01), 17: (103.66, 31.08), 18: (103.60, 31.11),
    19: (103.70, 31.10), 20: (103.76, 30.96), 21: (103.86, 30.97),
    22: (103.82, 31.02), 23: (103.96, 31.04), 24: (103.94, 31.12),
    25: (103.80, 31.18), 26: (103.90, 31.22), 27: (103.95, 31.19),
    28: (103.84, 31.27), 29: (103.86, 31.33), 30: (104.00, 31.14),
    31: (104.06, 31.15), 32: (104.12, 31.16), 33: (104.08, 31.24),
    34: (103.98, 31.28), 35: (104.10, 31.33), 36: (104.15, 31.26),
    37: (104.13, 31.39), 38: (104.15, 31.46),
}

ROAD_STYLE = {
    "blocked": ("#991b1b", "dashed"),
    "temporary": ("#f97316", "solid"),
    "one_lane": ("#eab308", "solid"),
    "basic": ("#2563eb", "solid"),
    "full": ("#16a34a", "solid"),
}
CREW_COLORS = ("#7c3aed", "#db2777", "#0891b2", "#4d7c0f", "#c2410c")
CREW_MARKERS = ("*", "P", "X", "D", "s")
SUPPLY_COLORS = ("#00a6d6", "#6a00f4", "#ff006e", "#00a878")


def collect_mechanism_snapshots(
    instance,
    mechanism_name,
    *,
    efficiency_seed,
    repair_efficiency_deviation,
):
    mechanism = next(
        (item for item in MECHANISMS if item.name == mechanism_name),
        None,
    )
    if mechanism is None:
        raise ValueError(f"unknown mechanism: {mechanism_name}")
    snapshots = []
    summary, rows = run_mechanism(
        instance,
        mechanism,
        efficiency_seed,
        repair_efficiency_deviation,
        state_callback=snapshots.append,
    )
    return summary, rows, snapshots


def write_stage_visualizations(instance, snapshots, output_dir):
    if not snapshots:
        raise ValueError("at least one stage snapshot is required")
    mechanism = next(
        item for item in MECHANISMS
        if item.name == snapshots[0]["mechanism"]
    )
    visual_instance = _variant(instance, mechanism.progressive)
    output_dir = Path(output_dir)
    frames_dir = output_dir / "stages"
    frames_dir.mkdir(parents=True, exist_ok=True)
    positions = _network_layout(visual_instance)
    written = []

    for snapshot in snapshots:
        path = frames_dir / f"stage_{snapshot['period']:02d}.png"
        fig, ax = plt.subplots(figsize=(12, 9), facecolor="white")
        _draw_snapshot(ax, visual_instance, snapshot, positions, compact=False)
        fig.legend(
            handles=_legend_handles(visual_instance),
            loc="lower center",
            bbox_to_anchor=(0.5, 0.015),
            ncol=5,
            fontsize=8,
            frameon=False,
        )
        fig.subplots_adjust(left=0.03, right=0.98, top=0.93, bottom=0.13)
        fig.savefig(path, dpi=180, facecolor="white")
        plt.close(fig)
        written.append(path)

    overview = output_dir / "stage_overview.png"
    _plot_overview(visual_instance, snapshots, positions, overview)
    written.append(overview)
    timeline = output_dir / "delivery_timeline.png"
    _plot_delivery_timeline(visual_instance, snapshots, timeline)
    written.append(timeline)
    sequence = output_dir / "operation_sequence.png"
    _plot_operation_sequence(visual_instance, snapshots, sequence)
    written.append(sequence)
    dispatch_dir = output_dir / "dispatch_routes"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    for snapshot in snapshots:
        dispatch_path = (
            dispatch_dir / f"stage_{snapshot['period']:02d}_dispatch.png"
        )
        _plot_stage_dispatch_routes(
            visual_instance, snapshot, positions, dispatch_path,
        )
        written.append(dispatch_path)
    manifest = output_dir / "dispatch_manifest.csv"
    _write_dispatch_manifest(snapshots, manifest)
    written.append(manifest)
    states = output_dir / "stage_states.json"
    _write_state_json(visual_instance, snapshots, states)
    written.append(states)
    return written


def _network_layout(instance):
    base = instance.base
    if base.name.startswith("wenchuan") and set(base.graph) == set(WENCHUAN_POS):
        return _spread_short_damaged_edges(base, WENCHUAN_POS)
    layout = nx.spring_layout(
        base.graph,
        seed=base.seed,
        weight="weight",
        iterations=180,
    )
    return {
        node: (float(point[0]), float(point[1]))
        for node, point in layout.items()
    }


def _spread_short_damaged_edges(base, positions, min_distance=0.06):
    """Slightly separate short damaged edges for display only."""
    adjusted = {
        node: [float(point[0]), float(point[1])]
        for node, point in positions.items()
    }
    suppliers = set(base.suppliers)
    for damage_id in sorted(base.damaged_edges):
        edge = base.damaged_edges[damage_id]
        start = adjusted[edge.u]
        end = adjusted[edge.v]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.hypot(dx, dy)
        if distance >= min_distance or distance <= 1e-12:
            continue
        ux, uy = dx / distance, dy / distance
        shortfall = min_distance - distance
        if edge.u in suppliers:
            end[0] += ux * shortfall
            end[1] += uy * shortfall
        elif edge.v in suppliers:
            start[0] -= ux * shortfall
            start[1] -= uy * shortfall
        else:
            shift = shortfall / 2.0
            start[0] -= ux * shift
            start[1] -= uy * shift
            end[0] += ux * shift
            end[1] += uy * shift
    return {node: tuple(point) for node, point in adjusted.items()}


def _plot_overview(instance, snapshots, positions, path):
    columns = 4
    rows = math.ceil(len(snapshots) / columns)
    fig, axes = plt.subplots(
        rows, columns, figsize=(19, 4.6 * rows),
        facecolor="white", squeeze=False,
    )
    for ax, snapshot in zip(axes.flat, snapshots):
        _draw_snapshot(ax, instance, snapshot, positions, compact=True)
    for ax in list(axes.flat)[len(snapshots):]:
        ax.axis("off")
    fig.legend(
        handles=_legend_handles(instance),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.012),
        ncol=5,
        fontsize=8,
        frameon=False,
    )
    fig.suptitle(
        f"Road-demand-repair crew evolution: {snapshots[0]['mechanism']}",
        fontsize=16,
        fontweight="bold",
    )
    fig.subplots_adjust(
        left=0.025, right=0.985, top=0.94, bottom=0.075,
        wspace=0.06, hspace=0.18,
    )
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)


def _plot_delivery_timeline(instance, snapshots, path):
    periods = [snapshot["period"] for snapshot in snapshots]
    cumulative = [snapshot["total_satisfaction"] for snapshot in snapshots]
    period_tons = [snapshot["period_delivered_tons"] for snapshot in snapshots]
    no_repair_tons = [
        snapshot["repair_impact"]["no_current_repair_delivery_tons"]
        for snapshot in snapshots
    ]
    unreachable = [
        len(instance.base.demands) - len(snapshot["reachable_demands"])
        for snapshot in snapshots
    ]
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(10, 7), sharex=True, facecolor="white",
    )
    top.plot(
        periods, cumulative, color="#0f766e", marker="o",
        linewidth=2.4, label="Cumulative satisfaction",
    )
    top.fill_between(periods, cumulative, color="#5eead4", alpha=0.25)
    for period, value in zip(periods, cumulative):
        top.text(period, value + 0.018, f"{value:.3f}", ha="center", fontsize=8)
    top.set_ylim(0.0, 1.0)
    top.set_ylabel("Cumulative satisfaction")
    top.grid(True, alpha=0.25)
    top.legend(loc="lower right")

    bottom.bar(
        [period - 0.18 for period in periods], period_tons,
        width=0.36, color="#38bdf8", alpha=0.85,
        label="Actual delivery after repair (ton)",
    )
    bottom.bar(
        [period + 0.18 for period in periods], no_repair_tons,
        width=0.36, color="#94a3b8", alpha=0.8,
        label="Counterfactual: no current-period repair",
    )
    bottom.set_ylabel("Period delivery (ton)")
    bottom.set_xlabel("Stage / decision period")
    bottom.grid(True, axis="y", alpha=0.25)
    second = bottom.twinx()
    second.plot(
        periods, unreachable, color="#991b1b", marker="x",
        linewidth=2.0, label="Unreachable demand",
    )
    second.set_ylabel("Unreachable demand count", color="#991b1b")
    second.tick_params(axis="y", colors="#991b1b")
    lines = bottom.get_legend_handles_labels()
    second_lines = second.get_legend_handles_labels()
    bottom.legend(
        lines[0] + second_lines[0], lines[1] + second_lines[1],
        loc="upper right",
    )
    fig.suptitle(
        "Cumulative demand satisfaction and period material delivery",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)


def _plot_operation_sequence(instance, snapshots, path):
    """Plot repair and dispatch decision order across and within stages."""
    base = instance.base
    periods = [snapshot["period"] for snapshot in snapshots]
    fig, (repair_ax, delivery_ax) = plt.subplots(
        2, 1, figsize=(18, 12), facecolor="white",
        gridspec_kw={"height_ratios": [2.2, 7.8]},
    )

    for ax in (repair_ax, delivery_ax):
        for period in periods:
            if period % 2 == 0:
                ax.axvspan(
                    period - 0.5, period + 0.5,
                    color="#f8fafc", zorder=0,
                )
        ax.set_xlim(min(periods) - 0.5, max(periods) + 0.5)
        ax.set_xticks(periods, [f"S{period}" for period in periods])
        ax.grid(axis="x", color="#cbd5e1", linewidth=0.7, alpha=0.8)

    crew_points = {crew_id: [] for crew_id in range(base.repair_crews)}
    for snapshot in snapshots:
        period = snapshot["period"]
        for crew_id in range(base.repair_crews):
            tasks = snapshot["crew_activity"].get(crew_id, [])
            for order, damage_id in enumerate(tasks, start=1):
                x = _stage_event_x(period, order, len(tasks))
                y = base.repair_crews - crew_id
                crew_points[crew_id].append((x, y))
                repair_ax.scatter(
                    x, y, s=155,
                    marker=CREW_MARKERS[crew_id % len(CREW_MARKERS)],
                    color=CREW_COLORS[crew_id % len(CREW_COLORS)],
                    edgecolor="#111827", linewidth=0.8, zorder=3,
                )
                repair_ax.annotate(
                    f"R{damage_id}", (x, y), xytext=(0, 12),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=8, fontweight="semibold",
                )
    for crew_id, points in crew_points.items():
        if len(points) > 1:
            repair_ax.plot(
                [point[0] for point in points],
                [point[1] for point in points],
                color=CREW_COLORS[crew_id % len(CREW_COLORS)],
                linewidth=1.5, alpha=0.55, zorder=1,
            )
    repair_ax.set_yticks(
        [base.repair_crews - crew_id for crew_id in range(base.repair_crews)],
        [f"Crew C{crew_id + 1}" for crew_id in range(base.repair_crews)],
    )
    repair_ax.set_ylim(0.45, base.repair_crews + 0.75)
    repair_ax.set_title(
        "Repair decision order (left to right within each stage)",
        fontsize=12, fontweight="semibold",
    )

    supplier_index = {
        supplier: index for index, supplier in enumerate(base.suppliers)
    }
    max_amount = max(
        (
            shipment["amount"]
            for snapshot in snapshots
            for shipment in snapshot["shipments"]
        ),
        default=1.0,
    )
    for snapshot in snapshots:
        period = snapshot["period"]
        shipments = snapshot["shipments"]
        for order, shipment in enumerate(shipments, start=1):
            x = _stage_event_x(period, order, len(shipments))
            supplier = shipment["supplier"]
            delivery_ax.scatter(
                x, shipment["demand"],
                s=22 + 120 * shipment["amount"] / max_amount,
                color=SUPPLY_COLORS[
                    supplier_index[supplier] % len(SUPPLY_COLORS)
                ],
                edgecolor="#334155", linewidth=0.45, alpha=0.82, zorder=3,
            )
        if shipments:
            delivery_ax.text(
                period, max(base.demands) + 1.15,
                f"{len(shipments)} dispatches\n"
                f"{sum(item['amount'] for item in shipments):.0f} t",
                ha="center", va="bottom", fontsize=7.5, color="#334155",
            )
    delivery_ax.set_yticks(base.demands)
    delivery_ax.set_ylim(min(base.demands) - 0.8, max(base.demands) + 3.6)
    delivery_ax.set_ylabel("Demand node")
    delivery_ax.set_xlabel(
        "Stage and within-stage dispatch allocation order (left to right)"
    )
    delivery_ax.set_title(
        "Material dispatch decision order (bubble size = tons)",
        fontsize=12, fontweight="semibold",
    )
    delivery_ax.grid(axis="y", color="#e2e8f0", linewidth=0.55, alpha=0.75)
    delivery_ax.legend(
        handles=[
            Line2D(
                [0], [0], marker="o", linestyle="none",
                markerfacecolor=SUPPLY_COLORS[index % len(SUPPLY_COLORS)],
                markeredgecolor="#334155", markersize=8,
                label=f"Supply {supplier}",
            )
            for index, supplier in enumerate(base.suppliers)
        ],
        loc="upper right", ncol=len(base.suppliers), frameon=False,
    )
    fig.suptitle(
        "Repair and material dispatch sequence",
        fontsize=16, fontweight="bold",
    )
    fig.text(
        0.5, 0.012,
        "Sequence semantics: order of repair and dispatch decisions recorded "
        "by the stage model; not minute-level vehicle departure or arrival time.",
        ha="center", fontsize=9, color="#475569",
    )
    fig.subplots_adjust(
        left=0.065, right=0.985, top=0.93, bottom=0.075, hspace=0.22,
    )
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)


def _stage_event_x(period, order, total):
    if total <= 0:
        return float(period)
    return period - 0.42 + 0.84 * order / (total + 1)


def _plot_stage_dispatch_routes(instance, snapshot, positions, path):
    base = instance.base
    progress = snapshot["road_progress"]
    fig, ax = plt.subplots(figsize=(13, 9), facecolor="white")
    intact = [
        (u, v) for u, v, data in base.graph.edges(data=True)
        if data.get("damage_id") is None
    ]
    nx.draw_networkx_edges(
        base.graph, positions, ax=ax, edgelist=intact,
        edge_color="#cbd5e1", width=1.3, alpha=0.78,
    )
    for label, (color, style) in ROAD_STYLE.items():
        edges = [
            (edge.u, edge.v)
            for damage_id, edge in base.damaged_edges.items()
            if _road_stage(
                instance, progress.get(damage_id, 0.0),
            )["label"] == label
        ]
        if edges:
            nx.draw_networkx_edges(
                base.graph, positions, ax=ax, edgelist=edges,
                edge_color=color, width=2.5, style=style, alpha=0.82,
            )

    supplier_index = {
        supplier: index for index, supplier in enumerate(base.suppliers)
    }
    edge_flow = {}
    demand_supply = {}
    for shipment in snapshot["shipments"]:
        supplier = shipment["supplier"]
        demand = shipment["demand"]
        demand_supply.setdefault(demand, {})
        demand_supply[demand][supplier] = (
            demand_supply[demand].get(supplier, 0.0) + shipment["amount"]
        )
        for u, v in zip(shipment["path"], shipment["path"][1:]):
            edge = tuple(sorted((u, v)))
            key = (supplier, edge)
            edge_flow[key] = edge_flow.get(key, 0.0) + shipment["amount"]
    max_flow = max(edge_flow.values(), default=1.0)
    for supplier in base.suppliers:
        flows = {
            edge: amount
            for (source, edge), amount in edge_flow.items()
            if source == supplier
        }
        if not flows:
            continue
        nx.draw_networkx_edges(
            base.graph, positions, ax=ax,
            edgelist=list(flows),
            edge_color=SUPPLY_COLORS[
                supplier_index[supplier] % len(SUPPLY_COLORS)
            ],
            width=[2.0 + 6.0 * amount / max_flow for amount in flows.values()],
            alpha=0.58,
        )

    nx.draw_networkx_nodes(
        base.graph, positions, ax=ax, nodelist=base.demands,
        node_color="white", node_size=100,
        edgecolors="#f59e0b", linewidths=1.7,
    )
    nx.draw_networkx_nodes(
        base.graph, positions, ax=ax, nodelist=base.suppliers,
        node_shape="^", node_color="#fb923c", node_size=230,
        edgecolors="#7c2d12", linewidths=1.0,
    )
    nx.draw_networkx_labels(
        base.graph, positions, ax=ax,
        labels={node: str(node) for node in base.graph},
        font_size=5.8, font_color="#0f172a",
    )
    for demand, by_supplier in demand_supply.items():
        parts = [
            f"S{supplier}:{amount:.0f}t"
            for supplier, amount in sorted(by_supplier.items())
        ]
        ax.annotate(
            " | ".join(parts), positions[demand],
            xytext=(5, 7), textcoords="offset points",
            ha="left", va="bottom", fontsize=6.5, color="#0f172a",
            bbox={
                "boxstyle": "round,pad=0.18", "facecolor": "white",
                "edgecolor": "#cbd5e1", "alpha": 0.88,
                "linewidth": 0.45,
            },
        )
    ax.set_title(
        f"Stage {snapshot['period']}",
        fontsize=14, fontweight="semibold",
    )
    if not snapshot["shipments"]:
        ax.text(
            0.5, 0.5, "No material dispatched in this stage",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=15, color="#64748b",
            bbox={
                "boxstyle": "round,pad=0.5", "facecolor": "white",
                "edgecolor": "#cbd5e1", "alpha": 0.92,
            },
        )
    ax.legend(
        handles=[
            Line2D(
                [0], [0], color=SUPPLY_COLORS[
                    index % len(SUPPLY_COLORS)
                ],
                linewidth=4, alpha=0.7, label=f"Supply {supplier} route",
            )
            for index, supplier in enumerate(base.suppliers)
        ],
        loc="lower center", bbox_to_anchor=(0.5, -0.02),
        ncol=len(base.suppliers), frameon=False,
    )
    ax.axis("off")
    fig.subplots_adjust(left=0.025, right=0.99, top=0.92, bottom=0.075)
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)


def _write_dispatch_manifest(snapshots, path):
    fields = [
        "stage", "dispatch_order", "supplier", "demand", "amount_tons",
        "vehicle_type", "trips", "travel_time_minutes", "path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for snapshot in snapshots:
            for order, shipment in enumerate(snapshot["shipments"], start=1):
                writer.writerow({
                    "stage": snapshot["period"],
                    "dispatch_order": order,
                    "supplier": shipment["supplier"],
                    "demand": shipment["demand"],
                    "amount_tons": f"{shipment['amount']:.6f}",
                    "vehicle_type": shipment["vehicle_type"],
                    "trips": shipment["trips"],
                    "travel_time_minutes": f"{shipment['travel_time']:.6f}",
                    "path": "->".join(map(str, shipment["path"])),
                })


def _draw_snapshot(ax, instance, snapshot, positions, *, compact):
    base = instance.base
    reachable = set(snapshot["reachable_demands"])
    progress = snapshot["road_progress"]
    before_progress = snapshot["road_progress_before"]
    selected = set(snapshot["selected_repairs"])
    upgraded = {
        damage_id
        for damage_id in base.damaged_edges
        if _capacity_ratio(
            instance.recovery_stages,
            progress.get(damage_id, 0.0),
        )
        > _capacity_ratio(
            instance.recovery_stages,
            before_progress.get(damage_id, 0.0),
        ) + 1e-9
    }
    intact = [
        (u, v) for u, v, data in base.graph.edges(data=True)
        if data.get("damage_id") is None
    ]
    nx.draw_networkx_edges(
        base.graph, positions, ax=ax, edgelist=intact,
        edge_color="#cbd5e1", width=1.0 if compact else 1.3, alpha=0.72,
    )

    for label, (color, style) in ROAD_STYLE.items():
        edges = [
            (edge.u, edge.v)
            for damage_id, edge in base.damaged_edges.items()
            if _road_stage(instance, progress.get(damage_id, 0.0))["label"] == label
        ]
        if edges:
            nx.draw_networkx_edges(
                base.graph, positions, ax=ax, edgelist=edges,
                edge_color=color, width=2.2 if compact else 3.0,
                style=style, alpha=0.95,
            )

    _draw_delivery_flows(ax, snapshot, positions, compact=compact)
    selected_edges = [
        (base.damaged_edges[item].u, base.damaged_edges[item].v)
        for item in selected if item in base.damaged_edges
    ]
    if selected_edges:
        nx.draw_networkx_edges(
            base.graph, positions, ax=ax, edgelist=selected_edges,
            edge_color="#111827", width=4.6 if compact else 6.0, alpha=0.22,
        )
    upgraded_edges = [
        (base.damaged_edges[item].u, base.damaged_edges[item].v)
        for item in upgraded
    ]
    if upgraded_edges:
        nx.draw_networkx_edges(
            base.graph, positions, ax=ax, edgelist=upgraded_edges,
            edge_color="#d946ef", width=5.6 if compact else 8.0,
            alpha=0.32,
        )
    delivered = snapshot["delivered_by_demand"]
    period_delivery = snapshot["period_delivery_by_demand"]
    cmap = plt.get_cmap("viridis")
    reachable_unserved = [
        node for node in base.demands
        if node in reachable and delivered.get(node, 0.0) <= 1e-9
    ]
    colors = [
        (
            "#ffffff" if delivered.get(node, 0.0) <= 1e-9
            else cmap(min(1.0, delivered.get(node, 0.0) / base.demand_amounts[node]))
        )
        for node in base.demands
    ]
    max_period_delivery = max(period_delivery.values(), default=0.0)
    sizes = [
        (55 if compact else 105)
        + (45 if compact else 95)
        * period_delivery.get(node, 0.0) / max(max_period_delivery, 1e-9)
        for node in base.demands
    ]
    edge_colors = [
        "#f59e0b" if delivered.get(node, 0.0) <= 1e-9
        else "#06b6d4" if period_delivery.get(node, 0.0) > 1e-9
        else "#334155"
        for node in base.demands
    ]
    line_widths = [
        2.0 if delivered.get(node, 0.0) <= 1e-9
        else 1.8 if period_delivery.get(node, 0.0) > 1e-9
        else 0.6
        for node in base.demands
    ]
    nx.draw_networkx_nodes(
        base.graph, positions, ax=ax, nodelist=base.demands,
        node_color=colors, node_size=sizes,
        edgecolors=edge_colors, linewidths=line_widths,
    )
    nx.draw_networkx_nodes(
        base.graph, positions, ax=ax, nodelist=base.suppliers,
        node_shape="^", node_color="#fb923c",
        node_size=120 if compact else 220,
        edgecolors="#7c2d12", linewidths=1.0,
    )

    if not compact:
        demand_labels = {
            node: (
                str(node)
                if delivered.get(node, 0.0) <= 1e-9
                else f"{node}\n{100 * delivered.get(node, 0.0) / base.demand_amounts[node]:.0f}%"
            )
            for node in base.demands
        }
        nx.draw_networkx_labels(
            base.graph, positions, ax=ax,
            labels={
                **{node: str(node) for node in base.suppliers},
                **demand_labels,
            },
            font_size=5.5, font_color="#0f172a",
        )
        nx.draw_networkx_edge_labels(
            base.graph, positions, ax=ax,
            edge_labels={
                (edge.u, edge.v): str(damage_id)
                for damage_id, edge in base.damaged_edges.items()
            },
            font_size=6, font_color="#111827",
            bbox={
                "boxstyle": "round,pad=0.12", "facecolor": "white",
                "edgecolor": "#94a3b8", "alpha": 0.85, "linewidth": 0.4,
            },
        )

    _draw_crew_transfers(
        ax, snapshot["crew_transfers"], positions, compact=compact,
    )
    _draw_crews(
        ax, base, snapshot["crew_locations"], positions, compact=compact,
    )
    repaired = sum(value >= 1.0 - 1e-9 for value in progress.values())
    partial = sum(1e-9 < value < 1.0 - 1e-9 for value in progress.values())
    active = ",".join(map(str, snapshot["selected_repairs"])) or "-"
    crew_text = "; ".join(
        f"C{int(crew_id) + 1}:" + (
            ",".join(map(str, damage_ids)) if damage_ids else "idle"
        )
        for crew_id, damage_ids in snapshot["crew_activity"].items()
    ) or "all idle"
    total_trips = sum(snapshot["vehicle_trips"].values())
    trip_text = ", ".join(
        f"V{vehicle_type}:{trips}"
        for vehicle_type, trips in sorted(snapshot["vehicle_trips"].items())
        if trips
    ) or "none"
    ax.set_title(
        f"Stage {snapshot['period']} | satisfaction={snapshot['total_satisfaction']:.3f}",
        fontsize=9 if compact else 13,
        fontweight="semibold",
    )
    if not compact:
        impact = snapshot["repair_impact"]
        newly_reachable = impact["newly_reachable_demands"]
        upgraded_text = ",".join(map(str, sorted(upgraded))) or "-"
        newly_reachable_text = ",".join(map(str, newly_reachable)) or "-"
        ax.text(
            0.012, 0.012,
            f"reachable demand: {len(reachable)}/{len(base.demands)}\n"
            f"reachable but not served: {len(reachable_unserved)}\n"
            f"period delivery: {snapshot['period_delivered_tons']:.1f} t, "
            f"{total_trips} trips\n"
            f"vehicle trips: {trip_text}\n"
            f"roads: {repaired} full, {partial} partial\n"
            f"capacity-upgraded roads: {upgraded_text}\n"
            f"repair impact: {impact['enabled_delivery_tons']:+.1f} t; "
            f"new reachable: {newly_reachable_text}\n"
            f"repairs this stage: {active}\n"
            f"crew tasks: {crew_text}",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=9,
            color="#0f172a",
            bbox={
                "boxstyle": "round,pad=0.4", "facecolor": "white",
                "edgecolor": "#cbd5e1", "alpha": 0.92,
            },
        )
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")


def _draw_crews(ax, base, crew_locations, positions, *, compact):
    xs = [point[0] for point in positions.values()]
    ys = [point[1] for point in positions.values()]
    x_span, y_span = max(xs) - min(xs), max(ys) - min(ys)
    count = max(len(crew_locations), 1)
    for raw_id, location in crew_locations.items():
        crew_id = int(raw_id)
        if location["kind"] == "edge":
            edge = base.damaged_edges[int(location["damage_id"])]
            x = (positions[edge.u][0] + positions[edge.v][0]) / 2
            y = (positions[edge.u][1] + positions[edge.v][1]) / 2
        else:
            x, y = positions[int(location["node_id"])]
        angle = 2 * math.pi * crew_id / count
        x += 0.016 * x_span * math.cos(angle)
        y += 0.016 * y_span * math.sin(angle)
        color = CREW_COLORS[crew_id % len(CREW_COLORS)]
        marker = CREW_MARKERS[crew_id % len(CREW_MARKERS)]
        ax.scatter(
            [x], [y], marker=marker, s=145 if compact else 310,
            color=color, edgecolor="#111827", linewidth=0.7, zorder=12,
        )
        ax.text(
            x, y, f"C{crew_id + 1}", ha="center", va="center",
            fontsize=5 if compact else 7, fontweight="bold",
            color="white", zorder=13,
        )


def _draw_crew_transfers(ax, crew_transfers, positions, *, compact):
    for raw_id, transfers in crew_transfers.items():
        crew_id = int(raw_id)
        color = CREW_COLORS[crew_id % len(CREW_COLORS)]
        for transfer in transfers:
            path = transfer.get("path", [])
            edges = list(zip(path, path[1:]))
            if edges:
                nx.draw_networkx_edges(
                    nx.Graph(edges),
                    positions,
                    ax=ax,
                    edgelist=edges,
                    edge_color=color,
                    width=1.8 if compact else 2.8,
                    style="dotted",
                    alpha=0.9,
                )


def _draw_delivery_flows(ax, snapshot, positions, *, compact):
    by_supplier = {}
    for shipment in snapshot["shipments"]:
        supplier = int(shipment["supplier"])
        edge_tons = by_supplier.setdefault(supplier, {})
        for u, v in zip(shipment["path"], shipment["path"][1:]):
            key = tuple(sorted((u, v)))
            edge_tons[key] = edge_tons.get(key, 0.0) + shipment["amount"]
    maximum = max(
        (tons for edges in by_supplier.values() for tons in edges.values()),
        default=0.0,
    )
    for index, (supplier, edge_tons) in enumerate(sorted(by_supplier.items())):
        if not edge_tons:
            continue
        edges = list(edge_tons)
        widths = [
            (0.8 if compact else 1.2)
            + (2.6 if compact else 4.2) * edge_tons[edge] / max(maximum, 1e-9)
            for edge in edges
        ]
        nx.draw_networkx_edges(
            nx.Graph(edges),
            positions,
            ax=ax,
            edgelist=edges,
            edge_color=SUPPLY_COLORS[index % len(SUPPLY_COLORS)],
            width=widths,
            alpha=0.42,
        )


def _road_stage(instance, progress):
    if progress >= 1.0 - 1e-9:
        return {"label": "full", "capacity_ratio": 1.0}
    for stage in instance.recovery_stages:
        if stage.lower <= progress < stage.upper:
            return {"label": stage.label, "capacity_ratio": stage.capacity_ratio}
    return {
        "label": "blocked",
        "capacity_ratio": _capacity_ratio(instance.recovery_stages, progress),
    }


def _legend_handles(instance):
    labels = {stage.label for stage in instance.recovery_stages}
    roads = [
        Line2D(
            [0], [0], color=color, linestyle=style, linewidth=3,
            label=_stage_legend_label(instance, label),
        )
        for label, (color, style) in ROAD_STYLE.items()
        if label in labels
    ]
    cmap = plt.get_cmap("viridis")
    demands = [
        Line2D(
            [0], [0], marker="o", linestyle="none",
            markerfacecolor=cmap(level), markeredgecolor="#334155",
            markersize=7, label=f"Demand {int(level * 100)}%",
        )
        for level in (0.25, 0.5, 0.75, 1.0)
    ]
    crew_handles = [
        Line2D(
            [0], [0], marker=CREW_MARKERS[crew_id % len(CREW_MARKERS)],
            linestyle="none",
            markerfacecolor=CREW_COLORS[crew_id % len(CREW_COLORS)],
            markeredgecolor="#111827", markersize=10,
            label=f"Repair crew C{crew_id + 1}",
        )
        for crew_id in range(instance.base.repair_crews)
    ]
    supply_handles = [
        Line2D(
            [0], [0], color=SUPPLY_COLORS[index % len(SUPPLY_COLORS)],
            linewidth=3, alpha=0.65, label=f"Supply {supplier} flow",
        )
        for index, supplier in enumerate(instance.base.suppliers)
    ]
    return [
        *roads, *demands,
        Line2D(
            [0], [0], marker="o", linestyle="none",
            markerfacecolor="white", markeredgecolor="#f59e0b",
            markeredgewidth=2, markersize=7,
            label="Not yet served",
        ),
        Line2D(
            [0], [0], color="#d946ef", linewidth=6, alpha=0.45,
            label="Road capacity upgraded this stage",
        ),
        *crew_handles,
        *supply_handles,
    ]


def _stage_legend_label(instance, label):
    stage = next(stage for stage in instance.recovery_stages if stage.label == label)
    if label == "full":
        return "Full (100% capacity)"
    lower = int(round(stage.lower * 100))
    upper = int(round(min(stage.upper, 1.0) * 100))
    capacity = int(round(stage.capacity_ratio * 100))
    return f"{label.replace('_', ' ').title()} ({lower}-{upper}% repair, {capacity}% cap.)"


def _write_state_json(instance, snapshots, path):
    base = instance.base
    result = {
        "instance": base.name,
        "mechanism": snapshots[0]["mechanism"],
        "eta_hours": base.eta_hours,
        "crew_transfer_time_scale": instance.crew_transfer_time_scale,
        "crew_min_access_progress": instance.crew_min_access_progress,
        "sequence_semantics": (
            "repair_sequence and dispatch_order record decision order within "
            "each stage; they are not minute-level departure or arrival times."
        ),
        "position_semantics": (
            "Crew markers show the final work site in each period. "
            "Dotted crew-colored lines show midpoint-to-midpoint transfer "
            "approximated on the physical network; the scaled transfer time "
            "is deducted from period repair work. Period-0 markers use supply "
            "nodes as visual and dispatch anchors."
            if instance.crew_transfer_time_scale > 0
            else (
                "Crew markers show the final work site in each period. "
                "Transfer time is disabled; period-0 markers use supply nodes "
                "as visual anchors."
            )
        ),
        "recovery_stage_definitions": [
            {
                "label": stage.label,
                "repair_progress_lower": stage.lower,
                "repair_progress_upper": min(stage.upper, 1.0),
                "capacity_ratio": stage.capacity_ratio,
                "speed_ratio": stage.speed_ratio,
            }
            for stage in instance.recovery_stages
        ],
        "stages": [],
    }
    for snapshot in snapshots:
        roads = []
        for damage_id, edge in base.damaged_edges.items():
            value = snapshot["road_progress"].get(damage_id, 0.0)
            before_value = snapshot["road_progress_before"].get(damage_id, 0.0)
            before_state = _road_stage(instance, before_value)
            after_state = _road_stage(instance, value)
            roads.append({
                "damage_id": damage_id, "u": edge.u, "v": edge.v,
                "progress_before": before_value,
                "progress": value,
                "stage_before": before_state["label"],
                "capacity_ratio_before": before_state["capacity_ratio"],
                **after_state,
                "capacity_upgraded": (
                    after_state["capacity_ratio"]
                    > before_state["capacity_ratio"] + 1e-9
                ),
            })
        reachable = set(snapshot["reachable_demands"])
        demands = []
        for demand in base.demands:
            delivered = snapshot["delivered_by_demand"].get(demand, 0.0)
            status = (
                "unreachable" if demand not in reachable
                else "reachable_unserved" if delivered <= 1e-9
                else "served"
            )
            demands.append({
                "node_id": demand,
                "demand": base.demand_amounts[demand],
                "delivered": delivered,
                "satisfaction": min(
                    1.0, delivered / max(base.demand_amounts[demand], 1e-9),
                ),
                "reachable": demand in reachable,
                "status": status,
            })
        result["stages"].append({
            "period": snapshot["period"],
            "time_hours": snapshot["time_hours"],
            "total_satisfaction": snapshot["total_satisfaction"],
            "selected_repairs": snapshot["selected_repairs"],
            "period_delivery_by_demand": snapshot["period_delivery_by_demand"],
            "period_delivered_tons": snapshot["period_delivered_tons"],
            "shipments": [
                {**shipment, "dispatch_order": order}
                for order, shipment in enumerate(
                    snapshot["shipments"], start=1,
                )
            ],
            "vehicle_trips": snapshot["vehicle_trips"],
            "road_states": roads,
            "demand_states": demands,
            "crew_locations": snapshot["crew_locations"],
            "crew_transfers": snapshot["crew_transfers"],
            "crew_activity": snapshot["crew_activity"],
            "repair_sequence": [
                {
                    "crew_id": int(crew_id),
                    "repair_order": order,
                    "damage_id": damage_id,
                }
                for crew_id, damage_ids in sorted(
                    snapshot["crew_activity"].items(),
                )
                for order, damage_id in enumerate(damage_ids, start=1)
            ],
            "repair_impact": snapshot["repair_impact"],
        })
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Render road, demand, and repair-crew states for every period "
            "of one dynamic interaction experiment."
        )
    )
    parser.add_argument(
        "--scenario", choices=["wenchuan", "simulation"], default="wenchuan",
    )
    parser.add_argument(
        "--mechanism", choices=[item.name for item in MECHANISMS],
        default="progressive_rolling",
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--sim-nodes", type=int, default=25)
    parser.add_argument("--repair-scale", type=float, default=2.0)
    parser.add_argument("--crews", type=int, default=2)
    parser.add_argument("--capacity-scale", type=float, default=0.05)
    parser.add_argument("--crew-transfer-time-scale", type=float, default=1.0)
    parser.add_argument("--crew-min-access-progress", type=float, default=0.30)
    parser.add_argument("--repair-efficiency-deviation", type=float, default=0.30)
    parser.add_argument("--output-dir", default="outputs/stage_visualization")
    args = parser.parse_args()
    if args.crews <= 0:
        parser.error("--crews must be greater than zero")
    if args.repair_scale <= 0 or args.capacity_scale <= 0:
        parser.error("--repair-scale and --capacity-scale must be greater than zero")
    if args.crew_transfer_time_scale < 0:
        parser.error("--crew-transfer-time-scale must be non-negative")
    if not 0.0 <= args.crew_min_access_progress <= 1.0:
        parser.error("--crew-min-access-progress must be in [0, 1]")
    if not 0.0 <= args.repair_efficiency_deviation < 1.0:
        parser.error("--repair-efficiency-deviation must be in [0, 1)")
    return args


def run_cli():
    args = _parse_args()
    instance = (
        build_wenchuan_instance(args.seed)
        if args.scenario == "wenchuan"
        else build_simulation_instance(args.seed, num_nodes=args.sim_nodes)
    )
    instance = _apply_stress(
        instance,
        args.repair_scale,
        args.crews,
        args.capacity_scale,
        args.crew_transfer_time_scale,
        args.crew_min_access_progress,
    )
    summary, _rows, snapshots = collect_mechanism_snapshots(
        instance,
        args.mechanism,
        efficiency_seed=args.seed + 40_000,
        repair_efficiency_deviation=args.repair_efficiency_deviation,
    )
    output_dir = Path(args.output_dir)
    paths = write_stage_visualizations(instance, snapshots, output_dir)
    with (output_dir / "mechanism_summary.json").open(
        "w", encoding="utf-8",
    ) as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    print(
        f"wrote {len(snapshots)} stages for {args.mechanism} to {output_dir}; "
        f"overview={output_dir / 'stage_overview.png'}"
    )
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    run_cli()
