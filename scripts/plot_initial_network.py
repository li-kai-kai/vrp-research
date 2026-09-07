import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")

import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects

from scripts.reproduce.capacity_recovery import build_wenchuan_instance
from scripts.reproduce.benchmark_suite import (
    BenchmarkSpec,
    benchmark_specs,
    build_benchmark_instance,
)

# ================= 0. 字体设置 =================
plt.rcParams['font.sans-serif'] = [
    'Noto Sans CJK SC', 'WenQuanYi Zen Hei', 'Arial Unicode MS',
    'PingFang SC', 'Microsoft YaHei', 'SimHei', 'DejaVu Sans',
]
plt.rcParams['axes.unicode_minus'] = False

# ================= 1. 节点数据 (ID, Name, Type, Quantity) =================
node_names = {1: '都江堰', 2: '彭州', 3: '什邡', 4: '玉堂', 5: '中兴', 6: '青城山', 7: '大观', 8: '安龙', 9: '石羊', 10: '翠月湖', 11: '紫坪铺', 12: '龙池', 13: '幸福', 14: '聚源', 15: '崇义', 16: '胥家', 17: '蒲阳', 18: '虹口', 19: '向娥', 20: '天马', 21: '丽春', 22: '桂花', 23: '隆丰', 24: '丹景山', 25: '磁峰', 26: '通济', 27: '新兴', 28: '小鱼洞', 29: '龙门山', 30: '葛仙山', 31: '红岩', 32: '师古', 33: '湔底', 34: '白鹿', 35: '八角', 36: '洛水', 37: '莹华', 38: '红白'}
instance = build_wenchuan_instance().base
node_info = {
    node: {"name": node_names[node], "type": "supply" if node in instance.suppliers else "demand", "val": data["value"]}
    for node, data in instance.graph.nodes(data=True)
}

# Display coordinates are approximate and do not set travel times.
pos = {
    # --- 左下区域 (都江堰) ---
    1:  (103.62, 30.99), # 都江堰
    13: (103.65, 31.00), # 幸福
    16: (103.70, 31.01), # 胥家
    17: (103.66, 31.08), # 蒲阳
    
    # 周边节点
    4:  (103.54, 30.98), # 玉堂
    5:  (103.52, 30.94), # 中兴
    6:  (103.54, 30.89), # 青城山
    7:  (103.55, 30.82), # 大观
    8:  (103.58, 30.78), # 安龙
    9:  (103.62, 30.82), # 石羊
    10: (103.63, 30.90), # 翠月湖
    11: (103.58, 31.04), # 紫坪铺
    12: (103.52, 31.07), # 龙池 (深山)
    14: (103.69, 30.96), # 聚源
    15: (103.70, 30.90), # 崇义
    18: (103.60, 31.11), # 虹口
    19: (103.70, 31.10), # 向娥

    # --- 中部过渡区域 (彭州西) ---
    20: (103.76, 30.96), # 天马
    2:  (103.99, 30.95), # 彭州市区
    21: (103.86, 30.97), # 丽春
    22: (103.82, 31.02), # 桂花
    23: (103.96, 31.04), # 隆丰

    # --- 中部及深山 (龙门山脉) ---
    24: (103.94, 31.12), # 丹景山 
    25: (103.80, 31.18), # 磁峰
    26: (103.90, 31.22), # 通济
    27: (103.95, 31.19), # 新兴
    28: (103.84, 31.27), # 小鱼洞
    29: (103.86, 31.33), # 龙门山
    34: (103.98, 31.28), # 白鹿

    # --- 右侧区域 (什邡及沿线) ---
    30: (104.00, 31.14), # 葛仙山
    31: (104.06, 31.15), # 红岩
    32: (104.12, 31.16), # 师古
    33: (104.08, 31.24), # 湔底
    
    3:  (104.16, 31.10), # 什邡市区
    35: (104.10, 31.33), # 八角
    36: (104.15, 31.26), # 洛水
    37: (104.13, 31.39), # 莹华
    38: (104.15, 31.46), # 红白
}

# ================= 3. 边数据整合 =================

# A. 基础路网数据 (u, v, travel_time, repair_time)
# 注意：这里包含了所有物理连接的基础属性
G = instance.graph.copy()
for u, v, data in G.edges(data=True):
    data["travel_time"] = data["free_time"]
    data["status"] = "damaged" if data["damaged"] else "normal"
    if data["damaged"]:
        data["task_id"] = data["damage_id"] + 1

# ================= 4. 绘图 =================
fig = plt.figure(figsize=(18, 16), facecolor='white') # 加大画布，防止密集
ax = plt.gca()

# --- 4.1 绘制边 ---
normal_list = [(u, v) for u, v, d in G.edges(data=True) if d['status'] == 'normal']
damaged_list = [(u, v) for u, v, d in G.edges(data=True) if d['status'] == 'damaged']

nx.draw_networkx_edges(G, pos, edgelist=normal_list, edge_color='#888888', width=1.5, alpha=0.5)
nx.draw_networkx_edges(G, pos, edgelist=damaged_list, edge_color='#d32f2f', style='dashed', width=2.5)

# --- 4.2 绘制节点 (大小=需求量) ---
supply_list = [n for n in G.nodes if node_info[n]['type'] == 'supply']
demand_list = [n for n in G.nodes if node_info[n]['type'] == 'demand']
# 需求量映射节点大小：基数 + 系数 * 需求量
demand_sizes = [150 + (node_info[n]['val'] * 1.5) for n in demand_list]

nx.draw_networkx_nodes(G, pos, nodelist=supply_list, node_size=1100, 
                       node_shape='^', node_color='#ff9800', edgecolors='#333333', label='供应点')
nx.draw_networkx_nodes(G, pos, nodelist=demand_list, node_size=demand_sizes, 
                       node_color='#81d4fa', edgecolors='#333333', label='需求点')

# --- 4.3 绘制边上的信息 (核心整合) ---
halo_white = [path_effects.withStroke(linewidth=3, foreground='white')]

for u, v, d in G.edges(data=True):
    x_mid = (pos[u][0] + pos[v][0]) / 2
    y_mid = (pos[u][1] + pos[v][1]) / 2
    
    t_val = d['travel_time']
    
    if d['status'] == 'normal':
        # 正常路段：只显示 T:xx
        # 使用深灰色，避免抢夺视线
        label = f"T:{t_val}"
        txt = plt.text(x_mid, y_mid, label, color='#555555', fontsize=7, 
                       ha='center', va='center', zorder=15)
        txt.set_path_effects(halo_white)
        
    else:
        # 受损路段：显示任务ID(圆圈) + 修复时间(R) + 通行时间(T)
        r_val = d['repair_time']
        t_id = d['task_id']
        
        # 1. 绘制任务ID圆圈
        plt.plot(x_mid, y_mid, 'o', markersize=16, markerfacecolor='white', markeredgecolor='#d32f2f', markeredgewidth=1.5, zorder=25)
        plt.text(x_mid, y_mid, str(t_id), color='#d32f2f', fontsize=8, fontweight='bold', ha='center', va='center', zorder=30)
        
        # 2. 绘制时间信息 (R和T)
        # 稍微偏移一点，别挡住圆圈
        info_label = f"R:{r_val}\nT:{t_val}"
        txt = plt.text(x_mid, y_mid - 0.015, info_label, color='#d32f2f', fontsize=7, fontweight='bold',
                       ha='center', va='top', zorder=20)
        txt.set_path_effects(halo_white)

# --- 4.4 绘制节点名称与数值 ---
# 内部ID
nx.draw_networkx_labels(G, pos, font_size=8, font_color='black', font_weight='bold')

# 外部名称+需求量
text_labels = {}
for n in G.nodes:
    if node_info[n]['type'] == 'supply':
        text_labels[n] = f"{node_info[n]['name']}"
    else:
        text_labels[n] = f"{node_info[n]['name']}\n({node_info[n]['val']})"

label_pos = {k: (v[0], v[1]-0.018) for k, v in pos.items()}
txt_items = nx.draw_networkx_labels(G, label_pos, labels=text_labels, font_color='#333333', font_size=8)
for _, t in txt_items.items():
    t.set_path_effects(halo_white)

# --- 4.5 图例 ---
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='^', color='w', label='供应中心', markerfacecolor='#ff9800', markeredgecolor='black', markersize=12),
    Line2D([0], [0], marker='o', color='w', label='需求点', markerfacecolor='#81d4fa', markeredgecolor='black', markersize=10),
    Line2D([0], [0], color='#888888', lw=1.5, label='正常道路 (T:通行时间)'),
    Line2D([0], [0], color='#d32f2f', lw=2.5, linestyle='--', label='受损道路 (R:修复时间)'),
    Line2D([0], [0], marker='o', color='w', label='受损任务编号', markerfacecolor='white', markeredgecolor='#d32f2f', markersize=10),
]
plt.legend(handles=legend_elements, loc='lower right', frameon=True, facecolor='white', edgecolor='#cccccc', fontsize=10)
plt.subplots_adjust(left=0.02, right=0.98, top=0.93, bottom=0.05)
ax = plt.gca()
ax.set_xlim(103.45, 104.25)
ax.set_ylim(30.75, 31.50)
plt.title("汶川案例初始路网拓扑", fontsize=16, y=0.9)
plt.axis('off')
plt.tight_layout()
ax.set_aspect(1 / math.cos(math.radians(31.1)))


def save_figure(output_dir: Path) -> tuple[Path, Path]:
    """将汶川案例初始拓扑同时导出为 PNG 和可缩放 SVG。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / "wenchuan_case_topology.png"
    svg_path = output_dir / "wenchuan_case_topology.svg"
    fig.savefig(png_path, dpi=220, bbox_inches="tight", facecolor="white")
    fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
    return png_path, svg_path


SYNTHETIC_SIZE_GROUPS = ("small", "medium", "large")
SYNTHETIC_GROUP_LABELS = {
    "small": "小规模",
    "medium": "中等规模",
    "large": "大规模",
}


def select_synthetic_cases(
    *,
    selection_seed: int,
    instance_seed_min: int,
    instance_seed_max: int,
) -> list[tuple[str, BenchmarkSpec, int]]:
    """按固定抽样种子各选取一个小、中、大规模合成实例。"""
    rng = random.Random(selection_seed)
    specs = benchmark_specs("publication")
    selections = []
    for size_group in SYNTHETIC_SIZE_GROUPS:
        candidates = [spec for spec in specs if spec.size_group == size_group]
        selections.append(
            (
                size_group,
                rng.choice(candidates),
                rng.randint(instance_seed_min, instance_seed_max),
            )
        )
    return selections


def draw_synthetic_topology(
    axis: plt.Axes,
    instance,
    *,
    size_group: str,
    spec: BenchmarkSpec,
) -> None:
    """使用与汶川初始路网相同的节点、道路和受损配色绘制合成实例。"""
    graph = instance.graph
    damaged_keys = {
        frozenset((edge.u, edge.v))
        for edge in instance.damaged_edges.values()
    }
    normal_edges = [
        edge for edge in graph.edges() if frozenset(edge) not in damaged_keys
    ]
    damaged_edges = [
        edge for edge in graph.edges() if frozenset(edge) in damaged_keys
    ]
    positions = nx.spring_layout(
        graph,
        seed=instance.seed,
        weight=None,
        iterations=160,
        k=1.45 / max(graph.number_of_nodes() ** 0.5, 1.0),
    )

    node_count = graph.number_of_nodes()
    normal_width = max(0.35, min(1.6, 32.0 / node_count))
    damaged_width = max(0.65, min(2.5, normal_width * 2.2))
    normal_alpha = max(0.28, min(0.65, 80.0 / node_count))
    other_size = max(5.0, min(42.0, 850.0 / node_count))
    demand_base = max(10.0, min(88.0, 1_600.0 / node_count))
    supply_size = max(42.0, min(210.0, 3_500.0 / node_count))

    nx.draw_networkx_edges(
        graph,
        positions,
        ax=axis,
        edgelist=normal_edges,
        edge_color="#5f6368",
        width=normal_width,
        alpha=normal_alpha,
    )
    nx.draw_networkx_edges(
        graph,
        positions,
        ax=axis,
        edgelist=damaged_edges,
        edge_color="#d32f2f",
        style="dashed",
        width=damaged_width,
        alpha=0.72,
    )

    ordinary_nodes = [
        node
        for node in graph.nodes()
        if node not in instance.suppliers and node not in instance.demands
    ]
    nx.draw_networkx_nodes(
        graph,
        positions,
        ax=axis,
        nodelist=ordinary_nodes,
        node_size=other_size,
        node_color="#d9d9d9",
        edgecolors="#333333",
        linewidths=0.25,
        alpha=0.82,
    )
    maximum_demand = max(instance.demand_amounts.values(), default=1.0)
    demand_sizes = [
        demand_base * (0.72 + 0.70 * instance.demand_amounts[node] / maximum_demand)
        for node in instance.demands
    ]
    nx.draw_networkx_nodes(
        graph,
        positions,
        ax=axis,
        nodelist=instance.demands,
        node_size=demand_sizes,
        node_color="#81d4fa",
        edgecolors="#333333",
        linewidths=0.45,
        alpha=0.94,
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        ax=axis,
        nodelist=instance.suppliers,
        node_size=supply_size,
        node_shape="^",
        node_color="#ff9800",
        edgecolors="#333333",
        linewidths=0.8,
    )

    if node_count <= 50:
        nx.draw_networkx_labels(
            graph,
            positions,
            ax=axis,
            labels={node: str(node) for node in graph.nodes()},
            font_size=6.5,
            font_color="#333333",
            font_weight="bold",
        )

    axis.set_title(
        f"{SYNTHETIC_GROUP_LABELS[size_group]}合成案例 · {spec.case_id}\n"
        f"N={node_count}, E={graph.number_of_edges()}, "
        f"受损道路={len(instance.damaged_edges)}, "
        f"供给点={len(instance.suppliers)}, 需求点={len(instance.demands)}",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    axis.margins(0.08)
    axis.set_axis_off()


def _synthetic_legend(figure: plt.Figure, *, y: float) -> None:
    legend_elements = [
        Line2D(
            [0],
            [0],
            marker="^",
            color="w",
            label="供应中心",
            markerfacecolor="#ff9800",
            markeredgecolor="#333333",
            markersize=10,
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label="需求点",
            markerfacecolor="#81d4fa",
            markeredgecolor="#333333",
            markersize=8,
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            label="普通节点",
            markerfacecolor="#d9d9d9",
            markeredgecolor="#333333",
            markersize=7,
        ),
        Line2D([0], [0], color="#5f6368", lw=1.8, label="正常道路"),
        Line2D(
            [0],
            [0],
            color="#d32f2f",
            lw=2.5,
            linestyle="--",
            label="受损道路",
        ),
    ]
    figure.legend(
        handles=legend_elements,
        loc="lower center",
        bbox_to_anchor=(0.5, y),
        ncol=5,
        frameon=True,
        facecolor="white",
        edgecolor="#cccccc",
        fontsize=9,
    )


def save_synthetic_figures(
    output_dir: Path,
    *,
    selection_seed: int,
    instance_seed_min: int,
    instance_seed_max: int,
    dpi: int,
) -> list[dict[str, object]]:
    synthetic_dir = output_dir / "synthetic_topology_random"
    synthetic_dir.mkdir(parents=True, exist_ok=True)
    selections = select_synthetic_cases(
        selection_seed=selection_seed,
        instance_seed_min=instance_seed_min,
        instance_seed_max=instance_seed_max,
    )
    samples = []
    for size_group, spec, instance_seed in selections:
        instance = build_benchmark_instance(spec, instance_seed=instance_seed)
        samples.append((size_group, spec, instance_seed, instance))
        stem = f"{size_group}_{spec.case_id}_seed{instance_seed}_topology"
        figure, axis = plt.subplots(figsize=(10.5, 7.2), facecolor="white")
        draw_synthetic_topology(
            axis,
            instance.base,
            size_group=size_group,
            spec=spec,
        )
        _synthetic_legend(figure, y=0.025)
        figure.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.14)
        figure.savefig(
            synthetic_dir / f"{stem}.png",
            dpi=dpi,
            bbox_inches="tight",
            facecolor="white",
        )
        figure.savefig(
            synthetic_dir / f"{stem}.svg",
            bbox_inches="tight",
            facecolor="white",
        )
        plt.close(figure)

    rows = [
        {
            "size_group": size_group,
            "case_id": spec.case_id,
            "instance_seed": instance_seed,
            "nodes": instance.base.graph.number_of_nodes(),
            "edges": instance.base.graph.number_of_edges(),
            "damaged_edges": len(instance.base.damaged_edges),
            "suppliers": len(instance.base.suppliers),
            "demands": len(instance.base.demands),
            "gamma": spec.gamma,
            "damage_ratio": spec.damage_ratio,
            "capacity_scale": spec.capacity_scale,
            "fleet_capacity_ratio": spec.fleet_capacity_ratio,
        }
        for size_group, spec, instance_seed, instance in samples
    ]
    with (synthetic_dir / "topology_sample_manifest.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (synthetic_dir / "topology_sample_manifest.json").write_text(
        json.dumps(
            {"selection_seed": selection_seed, "samples": rows},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="统一绘制汶川和合成案例初始路网拓扑")
    parser.add_argument(
        "--mode",
        choices=["wenchuan", "synthetic", "all"],
        default="all",
        help="绘制对象（默认：all）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/figures"),
        help="图片输出目录（默认：outputs/figures）",
    )
    parser.add_argument("--selection-seed", type=int, default=20_260_809)
    parser.add_argument("--instance-seed-min", type=int, default=1)
    parser.add_argument("--instance-seed-max", type=int, default=30)
    parser.add_argument("--dpi", type=int, default=220)
    args = parser.parse_args()
    if args.instance_seed_min > args.instance_seed_max:
        parser.error("--instance-seed-min must not exceed --instance-seed-max")
    if args.dpi < 72:
        parser.error("--dpi must be at least 72")

    if args.mode in {"wenchuan", "all"}:
        png_path, svg_path = save_figure(args.output_dir)
        print(f"Wenchuan PNG: {png_path.resolve()}")
        print(f"Wenchuan SVG: {svg_path.resolve()}")
    if args.mode in {"synthetic", "all"}:
        rows = save_synthetic_figures(
            args.output_dir,
            selection_seed=args.selection_seed,
            instance_seed_min=args.instance_seed_min,
            instance_seed_max=args.instance_seed_max,
            dpi=args.dpi,
        )
        for row in rows:
            print(
                f"{row['size_group']}: {row['case_id']} "
                f"instance_seed={row['instance_seed']} nodes={row['nodes']} "
                f"edges={row['edges']} damaged={row['damaged_edges']}"
            )
        print(
            "Synthetic figures: "
            f"{(args.output_dir / 'synthetic_topology_random').resolve()}"
        )
