from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx

from scripts.reproduce.metrics import build_available_graph
from scripts.reproduce.model import SolutionResult


def write_all_figures(results: list[SolutionResult], output_dir: Path) -> None:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    if not results:
        return

    best = max(results, key=lambda item: item.fitness)
    readable_network = _readable_network_result(results)
    plot_convergence(best, figures_dir / "convergence.png")
    plot_period_metric(results, "total_satisfaction", figures_dir / "satisfaction_over_time.png")
    plot_period_metric(results, "accessibility", figures_dir / "accessibility_over_time.png")
    plot_repair_gantt(best, figures_dir / "repair_gantt.png")
    plot_network_snapshot(readable_network, figures_dir / "network_snapshot.png")
    plot_sensitivity(results, figures_dir / "sensitivity_damage_eta.png")


def plot_convergence(result: SolutionResult, path: Path) -> None:
    plt.figure(figsize=(8, 4.5))
    plt.plot(
        range(1, len(result.convergence) + 1),
        result.convergence,
        color="#1f77b4",
        marker="o",
        markersize=3,
        linewidth=1.8,
    )
    plt.xlabel("Generation")
    plt.ylabel("Best fitness")
    plt.title(f"GA convergence: {result.instance.name}")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def plot_period_metric(results: list[SolutionResult], metric_name: str, path: Path) -> None:
    plt.figure(figsize=(8, 4.8))
    for result in _representative_results(results):
        xs = [metric.time_hours for metric in result.period_metrics]
        ys = [getattr(metric, metric_name) for metric in result.period_metrics]
        label = (
            f"N={result.instance.num_nodes}, "
            f"g={result.instance.gamma}, "
            f"d={result.instance.damage_ratio:.1f}, "
            f"eta={result.instance.eta_hours}"
        )
        plt.plot(xs, ys, marker="o", linewidth=1.8, label=label)
    plt.xlabel("Time (hours)")
    plt.ylabel(metric_name.replace("_", " ").title())
    plt.title(metric_name.replace("_", " ").title())
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def plot_repair_gantt(result: SolutionResult, path: Path) -> None:
    instance = result.instance
    plt.figure(figsize=(10, max(3.5, instance.repair_crews * 0.7)))
    ax = plt.gca()
    for task in result.repair_schedule.tasks:
        if not task.repaired:
            continue
        ax.broken_barh(
            [(task.start_time / 60, (task.finish_time - task.start_time) / 60)],
            (task.team_id - 0.38, 0.76),
            facecolors="#2ca02c",
            edgecolors="black",
            linewidth=0.6,
            alpha=0.85,
        )
        ax.text(
            (task.start_time + task.finish_time) / 120,
            task.team_id,
            str(task.damage_id),
            ha="center",
            va="center",
            color="white",
            fontsize=8,
        )
    ax.set_yticks(range(instance.repair_crews))
    ax.set_ylabel("Repair crew")
    ax.set_xlabel("Time (hours)")
    ax.set_xlim(0, instance.horizon_hours)
    ax.set_title(f"Repair schedule: {instance.name}")
    ax.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def plot_network_snapshot(result: SolutionResult, path: Path) -> None:
    instance = result.instance
    final_graph = build_available_graph(
        instance,
        result.repair_schedule,
        instance.horizon_minutes,
    )
    pos = nx.spring_layout(
        instance.graph,
        seed=instance.seed,
        weight="weight",
        k=1.4 / max(instance.graph.number_of_nodes() ** 0.5, 1),
        iterations=120,
    )
    plt.figure(figsize=(10, 8))

    nx.draw_networkx_nodes(
        instance.graph,
        pos,
        nodelist=[
            node
            for node in instance.graph.nodes
            if node not in instance.demands and node not in instance.suppliers
        ],
        node_color="#d9d9d9",
        node_size=22,
        alpha=0.55,
        label="Other node",
    )
    nx.draw_networkx_nodes(
        instance.graph,
        pos,
        nodelist=instance.demands,
        node_color="#9ecae1",
        node_size=55,
        edgecolors="#4f9fcf",
        linewidths=0.5,
        label="Demand",
    )
    nx.draw_networkx_edges(
        instance.graph,
        pos,
        edgelist=[
            (u, v)
            for u, v, data in instance.graph.edges(data=True)
            if not data.get("damaged")
        ],
        edge_color="#c7c7c7",
        alpha=0.12,
        width=0.6,
        label="Intact road",
    )
    nx.draw_networkx_nodes(
        instance.graph,
        pos,
        nodelist=instance.suppliers,
        node_color="#d62728",
        node_shape="^",
        node_size=160,
        edgecolors="#7f0000",
        linewidths=0.8,
        label="Supply",
    )

    repaired_edges = []
    unrepaired_edges = []
    repaired_labels: dict[tuple[float, float], str] = {}
    unrepaired_labels: dict[tuple[float, float], str] = {}
    for damage_id, edge in instance.damaged_edges.items():
        edge_pair = (edge.u, edge.v)
        midpoint = (
            (pos[edge.u][0] + pos[edge.v][0]) / 2,
            (pos[edge.u][1] + pos[edge.v][1]) / 2,
        )
        if final_graph.has_edge(edge.u, edge.v):
            repaired_edges.append(edge_pair)
            repaired_labels[midpoint] = str(damage_id)
        else:
            unrepaired_edges.append(edge_pair)
            unrepaired_labels[midpoint] = str(damage_id)

    nx.draw_networkx_edges(
        instance.graph,
        pos,
        edgelist=unrepaired_edges,
        edge_color="#111111",
        style="dashed",
        width=1.7,
        alpha=0.85,
        label="Unrepaired",
    )
    nx.draw_networkx_edges(
        instance.graph,
        pos,
        edgelist=repaired_edges,
        edge_color="#2ca02c",
        width=2.8,
        alpha=0.95,
        label="Repaired",
    )
    nx.draw_networkx_labels(
        instance.graph,
        pos,
        labels={node: str(node) for node in instance.suppliers},
        font_size=8,
        font_color="white",
        font_weight="bold",
    )
    _draw_edge_id_labels(repaired_labels, color="#1f7a1f")
    _draw_edge_id_labels(unrepaired_labels, color="#111111")
    repaired_count = len(repaired_edges)
    total_damaged = len(instance.damaged_edges)
    plt.title(
        f"Final damaged-road status: {instance.name} "
        f"({repaired_count}/{total_damaged} repaired)"
    )
    plt.legend(fontsize=8)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _draw_edge_id_labels(labels: dict[tuple[float, float], str], color: str) -> None:
    for (x, y), text in labels.items():
        plt.text(
            x,
            y,
            text,
            ha="center",
            va="center",
            fontsize=6,
            color=color,
            bbox={
                "boxstyle": "round,pad=0.16",
                "facecolor": "white",
                "edgecolor": color,
                "linewidth": 0.5,
                "alpha": 0.85,
            },
        )


def plot_sensitivity(results: list[SolutionResult], path: Path) -> None:
    grouped: dict[tuple[float, int], list[float]] = {}
    for result in results:
        key = (result.instance.damage_ratio, result.instance.eta_hours)
        grouped.setdefault(key, []).append(result.period_metrics[-1].total_satisfaction)

    labels = sorted(grouped)
    values = [sum(grouped[key]) / len(grouped[key]) for key in labels]
    x_labels = [f"d={damage:.1f}\neta={eta}" for damage, eta in labels]

    plt.figure(figsize=(max(7, len(labels) * 0.8), 4.8))
    plt.bar(range(len(labels)), values, color="#4c78a8")
    plt.xticks(range(len(labels)), x_labels)
    plt.ylim(0, 1.05)
    plt.ylabel("Final total satisfaction")
    plt.title("Sensitivity by damage ratio and update interval")
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def _representative_results(results: list[SolutionResult], limit: int = 6) -> list[SolutionResult]:
    sorted_results = sorted(
        results,
        key=lambda item: (
            item.instance.num_nodes,
            item.instance.gamma,
            item.instance.damage_ratio,
            item.instance.eta_hours,
            item.instance.seed,
        ),
    )
    if len(sorted_results) <= limit:
        return sorted_results
    step = max(1, len(sorted_results) // limit)
    chosen = sorted_results[::step][:limit]
    best = max(results, key=lambda item: item.fitness)
    if best not in chosen:
        chosen[-1] = best
    return chosen


def _readable_network_result(results: list[SolutionResult]) -> SolutionResult:
    return min(
        results,
        key=lambda item: (
            item.instance.num_nodes,
            len(item.instance.damaged_edges),
            item.instance.damage_ratio,
            -item.fitness,
        ),
    )
