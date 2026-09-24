"""Stage-report infographic: WEN38 key transport roads (page 13, network panel).

The network panel only -- the comparison table and the takeaway lines belong to
the slide, so they are deliberately not baked into the image.

The picture makes one point and nothing else:

    17--22 and 1--17 are not the network's only connections, yet more
    supply-demand transport depends on them than on the 4--5 bridge.

So: the full network sits back in pale grey, three roads carry all the weight,
and every other annotation that a paper figure would want (detour routes,
betweenness, the stranded lobe behind 4--5) is left out on purpose.

Data is read from the WEN38 builder the natural-corridor audit used and from
the audit's own ``wen38_edge_structure.csv``; nothing is re-simulated, and the
script reports -- never silently absorbs -- any disagreement with the brief.

Outputs ``figures/wen38_key_transport_corridors_v2.png`` and ``.svg``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.reproduce.capacity_recovery import build_wenchuan_instance
from scripts.reproduce.ht_natural_corridor import topology_fingerprint

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = REPO_ROOT / "outputs" / "ht_natural_corridor_audit"
EDGE_STRUCTURE_CSV = AUDIT_DIR / "wen38_edge_structure.csv"
MANIFEST_JSON = AUDIT_DIR / "manifest.json"
FIGURE_DIR = REPO_ROOT / "figures"

# Canvas: close to 4:3 so the panel drops into the left ~65% of a 16:9 slide.
FIG_W, FIG_H = 9.6, 7.2

# Regions in figure fractions: (x, y, w, h).
REGION_MAP = (0.010, 0.105, 0.980, 0.885)

# The three highlighted roads, as (marker, (u, v)).
KEY_ROADS = [("①", (17, 22)), ("②", (1, 17)), ("③", (4, 5))]

# Expectations stated in the report brief, checked against the CSV at run time.
BRIEF_EXPECTATION = {
    (17, 22): {"is_bridge": False, "dependency": 46},
    (1, 17): {"is_bridge": False, "dependency": 39},
    (4, 5): {"is_bridge": True, "dependency": 18},
}

# ---------------------------------------------------------------------------
# Two greys and two hues. Nothing else. The blue marks "heavily used, but not
# the only way through"; the orange marks the actual cut edge. Validated in
# light mode (blue<->orange CVD dE 24.7, both above 3:1 on white), and the page
# never leans on hue alone: the key roads are also 5x thicker, and the 是否唯一
# distinction is written out in the slide's own table.
# ---------------------------------------------------------------------------
C_ROAD = "#c3c9d1"        # every other road, recessive
C_ROAD_ALPHA = 0.45
C_NODE = "#9aa5b2"        # demand nodes
C_SUPPLY = "#1b3a5c"      # supply nodes
C_NONUNIQUE = "#2a78d6"   # (1) (2)
C_UNIQUE = "#eb6834"      # (3)
C_INK_2 = "#6b7580"
C_INK_3 = "#a7afb8"

# Approximate display coordinates carried over from scripts/plot_initial_network.py.
# WEN38's own definition stores no geometry: edges are (u, v, free_time,
# capacity) only. These positions are fixed (no spring_layout, so the picture is
# identical every run), follow the real township locations, are NOT survey data,
# and set no travel time.
DISPLAY_POS = {
    1: (103.62, 30.99), 13: (103.65, 31.00), 16: (103.70, 31.01), 17: (103.66, 31.08),
    4: (103.54, 30.98), 5: (103.52, 30.94), 6: (103.54, 30.89), 7: (103.55, 30.82),
    8: (103.58, 30.78), 9: (103.62, 30.82), 10: (103.63, 30.90), 11: (103.58, 31.04),
    12: (103.52, 31.07), 14: (103.69, 30.96), 15: (103.70, 30.90), 18: (103.60, 31.11),
    19: (103.70, 31.10), 20: (103.76, 30.96), 2: (103.99, 30.95), 21: (103.86, 30.97),
    22: (103.82, 31.02), 23: (103.96, 31.04), 24: (103.94, 31.12), 25: (103.80, 31.18),
    26: (103.90, 31.22), 27: (103.95, 31.19), 28: (103.84, 31.27), 29: (103.86, 31.33),
    34: (103.98, 31.28), 30: (104.00, 31.14), 31: (104.06, 31.15), 32: (104.12, 31.16),
    33: (104.08, 31.24), 3: (104.16, 31.10), 35: (104.10, 31.33), 36: (104.15, 31.26),
    37: (104.13, 31.39), 38: (104.15, 31.46),
}

# WEN38 has no Wenchuan node; its three supply points are these.
NODE_NAMES = {1: "都江堰", 2: "彭州", 3: "什邡"}

# Margin around the node bounding box, in degrees. The left edge is wider so ③'s
# label has somewhere to sit. Everything else stays tight: the network should
# fill the frame, not float in it.
MARGIN_LON = (0.072, 0.028)
MARGIN_LAT = (0.030, 0.030)

# Road labels, as an offset in points from that road's midpoint: (dx, dy, ha, va).
# Each one is placed in genuinely empty space beside its road: ② runs out to the
# left because node 17 sits just above its midpoint and a centred label would
# cover the road, and ③ goes right, into the gap north of the 青城山 lobe.
ROAD_LABELS = {
    (17, 22): (7, 12, "left", "bottom"),
    (1, 17): (-8, 16, "right", "bottom"),
    (4, 5): (12, -2, "left", "center"),
}

# 都江堰 sits hard against the 1--17 road, so its name goes out to the west.
SUPPLY_LABELS = {1: (-11, 5, "right"), 2: (0, 12, "center"), 3: (0, 12, "center")}

plt.rcParams["font.sans-serif"] = [
    "Hiragino Sans GB", "Arial Unicode MS", "STHeiti", "Songti SC", "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["svg.fonttype"] = "path"  # embed glyphs: the SVG renders anywhere


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def load_graph():
    """Load WEN38 and confirm it is the exact network the audit fingerprinted."""
    instance = build_wenchuan_instance().base
    wrapper = type("_Wrap", (), {"base": instance})()
    fingerprint = topology_fingerprint(wrapper)
    expected = None
    if MANIFEST_JSON.exists():
        expected = json.loads(MANIFEST_JSON.read_text())["wen38_topology_fingerprint"]
    return instance, instance.graph, fingerprint, expected


def load_edge_structure():
    """Read the audit's per-damaged-edge structure table."""
    with EDGE_STRUCTURE_CSV.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    table = {}
    for row in rows:
        key = (int(row["u"]), int(row["v"]))
        table[key] = {
            "is_bridge": row["is_bridge"] == "True",
            "dependency": int(row["od_shortest_path_dependency_count"]),
            "od_pairs_total": int(row["od_pairs_total"]),
        }
    return table


def verify(graph, graph_bridges, table):
    """Check the three highlighted roads against the CSV and the live graph.

    Any disagreement with the brief is returned as a discrepancy and the CSV or
    graph value wins -- nothing is hard-coded to make the slide match a draft.
    """
    records, discrepancies = [], []
    for marker, (u, v) in KEY_ROADS:
        if (u, v) not in table:
            raise SystemExit(f"road {u}-{v} is absent from {EDGE_STRUCTURE_CSV.name}")
        row = table[(u, v)]
        live_bridge = frozenset((u, v)) in graph_bridges
        if row["is_bridge"] != live_bridge:
            discrepancies.append(
                f"{u}-{v}: CSV is_bridge={row['is_bridge']} but the WEN38 graph says "
                f"{live_bridge}; drawing the graph value"
            )
        brief = BRIEF_EXPECTATION[(u, v)]
        if brief["is_bridge"] != row["is_bridge"] or brief["dependency"] != row["dependency"]:
            discrepancies.append(
                f"{u}-{v}: brief said bridge={brief['is_bridge']} "
                f"dependency={brief['dependency']}; CSV says "
                f"bridge={row['is_bridge']} dependency={row['dependency']}"
            )
        records.append({
            "marker": marker,
            "edge": (u, v),
            "is_bridge": live_bridge,
            "dependency": row["dependency"],
            "od_pairs_total": row["od_pairs_total"],
        })
    return records, discrepancies


def node_bounds(graph):
    """Bounding box of the drawn node positions, plus the label margins."""
    xs = [DISPLAY_POS[n][0] for n in graph.nodes()]
    ys = [DISPLAY_POS[n][1] for n in graph.nodes()]
    xlim = (min(xs) - MARGIN_LON[0], max(xs) + MARGIN_LON[1])
    ylim = (min(ys) - MARGIN_LAT[0], max(ys) + MARGIN_LAT[1])
    return xlim, ylim


def region_aspect(region, xlim, ylim):
    """The display aspect that makes the data box exactly fill *region*.

    Derived rather than chosen: the network is what has to fill the frame, so
    the scale follows from the frame. The implied anamorphic stretch is reported
    by main() so it is never a silent distortion.
    """
    _, _, rw, rh = region
    region_h_over_w = (rh * FIG_H) / (rw * FIG_W)
    return region_h_over_w * (xlim[1] - xlim[0]) / (ylim[1] - ylim[0])


# ---------------------------------------------------------------------------
# drawing
# ---------------------------------------------------------------------------
def draw_network(ax, graph, instance, records):
    # Every road first, recessive: thin and half-transparent, so the three
    # highlighted ones are what the eye lands on.
    for u, v in graph.edges():
        xa, ya = DISPLAY_POS[u]
        xb, yb = DISPLAY_POS[v]
        ax.plot([xa, xb], [ya, yb], color=C_ROAD, linewidth=0.9,
                alpha=C_ROAD_ALPHA, solid_capstyle="round", zorder=1)

    demands = [n for n in graph.nodes() if n not in instance.suppliers]
    ax.scatter([DISPLAY_POS[n][0] for n in demands],
               [DISPLAY_POS[n][1] for n in demands],
               s=17, marker="o", facecolor=C_NODE, edgecolor="white",
               linewidth=0.7, alpha=0.9, zorder=2)

    # The three roads, full opacity on top.
    for record in records:
        u, v = record["edge"]
        colour = C_UNIQUE if record["is_bridge"] else C_NONUNIQUE
        xa, ya = DISPLAY_POS[u]
        xb, yb = DISPLAY_POS[v]
        ax.plot([xa, xb], [ya, yb], color=colour, linewidth=4.6,
                solid_capstyle="round", zorder=4)

    ax.scatter([DISPLAY_POS[n][0] for n in instance.suppliers],
               [DISPLAY_POS[n][1] for n in instance.suppliers],
               s=125, marker="s", facecolor=C_SUPPLY, edgecolor="white",
               linewidth=1.0, zorder=5)

    # Short labels pinned to their own road by a point offset, so they track the
    # road instead of floating in whatever space happens to be free. No leaders,
    # no borders -- just a translucent white pill so the grey mesh stays legible
    # underneath.
    pill = dict(boxstyle="round,pad=0.25", facecolor="white",
                edgecolor="none", alpha=0.85)
    for record in records:
        u, v = record["edge"]
        colour = C_UNIQUE if record["is_bridge"] else C_NONUNIQUE
        mid = ((DISPLAY_POS[u][0] + DISPLAY_POS[v][0]) / 2.0,
               (DISPLAY_POS[u][1] + DISPLAY_POS[v][1]) / 2.0)
        dx, dy, ha, va = ROAD_LABELS[record["edge"]]
        ax.annotate(f"{record['marker']} {u}–{v}｜{record['dependency']}",
                    xy=mid, xytext=(dx, dy), textcoords="offset points",
                    ha=ha, va=va, fontsize=12.5, color=colour, fontweight="bold",
                    bbox=pill, zorder=6)
        if record["is_bridge"]:
            # The one place the word is worth repeating: it is why this shorter
            # bar still matters.
            ax.annotate("唯一通道", xy=mid, xytext=(dx + 3, dy - 19),
                        textcoords="offset points", ha=ha, va="top", fontsize=10.5,
                        color=colour, bbox=pill, zorder=6)

    # Place names only: dark grey and small, so they never compete with the
    # road labels. Node ids are dropped entirely -- the road labels carry the
    # only numbers the page needs.
    for node, name in NODE_NAMES.items():
        x, y = DISPLAY_POS[node]
        dx, dy, ha = SUPPLY_LABELS[node]
        ax.annotate(name, (x, y), xytext=(dx, dy), textcoords="offset points",
                    ha=ha, va="center" if ha == "right" else "bottom",
                    fontsize=10.5, color=C_INK_2, zorder=6)

    ax.set_axis_off()


def build_figure(graph, instance, records, xlim, ylim, aspect):
    fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor="white")

    # The axes *is* the region: no set_aspect here on purpose. set_aspect would
    # shrink the box to honour a ratio and leave the network floating in dead
    # space, which is exactly the look this revision is fixing. Filling the
    # frame is the priority; `aspect` is computed only to report the stretch.
    ax = fig.add_axes(REGION_MAP)
    ax.set_facecolor("white")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    draw_network(ax, graph, instance, records)

    handles = [
        Line2D([], [], color=C_ROAD, linewidth=1.3, alpha=0.9, label="普通道路"),
        Line2D([], [], color=C_NONUNIQUE, linewidth=3.4, label="高运输依赖道路"),
        Line2D([], [], color=C_UNIQUE, linewidth=3.4, label="唯一连接通道"),
        Line2D([], [], marker="s", color="none", markerfacecolor=C_SUPPLY,
               markeredgecolor="none", markersize=9, label="物资供应点"),
        Line2D([], [], marker="o", color="none", markerfacecolor=C_NODE,
               markeredgecolor="none", markersize=6.5, label="受灾需求点"),
    ]
    legend = ax.legend(handles=handles, loc="lower center",
                       bbox_to_anchor=(0.5, -0.052), ncol=5, frameon=False,
                       fontsize=10, handlelength=2.0, columnspacing=1.9,
                       handletextpad=0.6)

    fig.text(0.5, 0.022, "网络拓扑示意图，节点位置不代表实际地理位置。",
             fontsize=8.5, color=C_INK_3, ha="center", va="bottom")

    return fig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--outdir", type=Path, default=FIGURE_DIR)
    args = parser.parse_args()

    instance, graph, fingerprint, expected = load_graph()
    bridges = {frozenset(edge) for edge in nx.bridges(graph)}
    table = load_edge_structure()
    records, discrepancies = verify(graph, bridges, table)
    od_pairs_total = next(iter(table.values()))["od_pairs_total"]
    manifest = json.loads(MANIFEST_JSON.read_text())

    xlim, ylim = node_bounds(graph)
    aspect = region_aspect(REGION_MAP, xlim, ylim)
    true_aspect = 1.0 / math.cos(math.radians(31.0))  # equal-distance view at WEN38's latitude

    print("=" * 70)
    print("WEN38 key transport corridor infographic -- data check")
    print("=" * 70)
    print(f"topology fingerprint : {fingerprint}")
    print(f"manifest fingerprint : {expected}")
    print(f"match                : {fingerprint == expected}")
    print(f"nodes / edges        : {graph.number_of_nodes()} / {graph.number_of_edges()}")
    print(f"bridges              : {len(bridges)} "
          f"(manifest graph_bridge_count={manifest['network']['graph_bridge_count']})")
    print(f"suppliers / demands  : {len(instance.suppliers)} / {len(instance.demands)}")
    print(f"OD pairs total       : {od_pairs_total}")
    print("-" * 70)
    for record in records:
        u, v = record["edge"]
        print(f"{record['marker']} {u:>2}-{v:<2}  bridge={str(record['is_bridge']):<5} "
              f"dependency={record['dependency']:>3}/{od_pairs_total}")
    print("-" * 70)
    print(f"map frame            : lon {xlim[0]:.3f}..{xlim[1]:.3f}  "
          f"lat {ylim[0]:.3f}..{ylim[1]:.3f}")
    print(f"canvas               : {FIG_W} x {FIG_H} in "
          f"({FIG_W / FIG_H:.2f}:1), {args.dpi} dpi")
    print(f"data aspect          : {aspect:.3f} vs true {true_aspect:.3f} "
          f"-> {true_aspect / aspect:.2f}x horizontal stretch (schematic)")
    print("-" * 70)
    if discrepancies:
        print("DISCREPANCIES vs the brief (CSV/graph value used):")
        for line in discrepancies:
            print(f"  ! {line}")
    else:
        print("No discrepancy: the CSV agrees with the brief on all three roads.")
    print("=" * 70)

    fig = build_figure(graph, instance, records, xlim, ylim, aspect)
    args.outdir.mkdir(parents=True, exist_ok=True)
    png = args.outdir / "wen38_key_transport_corridors_v2.png"
    svg = args.outdir / "wen38_key_transport_corridors_v2.svg"
    fig.savefig(png, dpi=args.dpi, facecolor="white")
    fig.savefig(svg, facecolor="white")
    plt.close(fig)
    print(f"wrote {png.relative_to(REPO_ROOT)}")
    print(f"wrote {svg.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
