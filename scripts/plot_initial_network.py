

# import networkx as nx
# import matplotlib.pyplot as plt
# import matplotlib.patheffects as path_effects

# # ================= 0. 字体设置 (适配 macOS/Windows) =================
# # 优先使用 macOS/Windows 通用中文字体
# plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Microsoft YaHei', 'SimHei', 'sans-serif']
# plt.rcParams['axes.unicode_minus'] = False

# # ================= 1. 节点数据 =================
# pos = {
#     # --- 左下区域 (都江堰) ---
#     1:  (103.62, 30.99), # 都江堰
#     13: (103.65, 31.00), # 幸福
#     16: (103.70, 31.01), # 胥家
#     17: (103.66, 31.08), # 蒲阳
    
#     # 周边节点
#     4:  (103.54, 30.98), # 玉堂
#     5:  (103.52, 30.94), # 中兴
#     6:  (103.54, 30.89), # 青城山
#     7:  (103.55, 30.82), # 大观
#     8:  (103.58, 30.78), # 安龙
#     9:  (103.62, 30.82), # 石羊
#     10: (103.63, 30.90), # 翠月湖
#     11: (103.58, 31.04), # 紫坪铺
#     12: (103.52, 31.07), # 龙池 (深山)
#     14: (103.69, 30.96), # 聚源
#     15: (103.70, 30.90), # 崇义
#     18: (103.60, 31.11), # 虹口
#     19: (103.70, 31.10), # 向娥

#     # --- 中部过渡区域 (彭州西) ---
#     20: (103.76, 30.96), # 天马
#     2:  (103.99, 30.95), # 彭州市区
#     21: (103.86, 30.97), # 丽春
#     22: (103.82, 31.02), # 桂花
#     23: (103.96, 31.04), # 隆丰

#     # --- 中部及深山 (龙门山脉) ---
#     24: (103.94, 31.12), # 丹景山 
#     25: (103.80, 31.18), # 磁峰
#     26: (103.90, 31.22), # 通济
#     27: (103.95, 31.19), # 新兴
#     28: (103.84, 31.27), # 小鱼洞
#     29: (103.86, 31.33), # 龙门山
#     34: (103.98, 31.28), # 白鹿

#     # --- 右侧区域 (什邡及沿线) ---
#     30: (104.00, 31.14), # 葛仙山
#     31: (104.06, 31.15), # 红岩
#     32: (104.12, 31.16), # 师古
#     33: (104.08, 31.24), # 湔底
    
#     3:  (104.16, 31.10), # 什邡市区
#     35: (104.10, 31.33), # 八角
#     36: (104.15, 31.26), # 洛水
#     37: (104.13, 31.39), # 莹华
#     38: (104.15, 31.46), # 红白
# }


# # ================= 2. 节点中文名称 =================
# labels_map = {
#     1: '都江堰', 2: '彭州', 3: '什邡',
#     4: '玉堂', 5: '中兴', 6: '青城山', 7: '大观', 8: '安龙', 9: '石羊', 10: '翠月湖',
#     11: '紫坪铺', 12: '龙池', 13: '幸福', 14: '聚源', 15: '崇义', 16: '胥家', 17: '蒲阳',
#     18: '虹口', 19: '向娥', 20: '天马',
#     21: '丽春', 22: '桂花', 23: '隆丰', 24: '丹景山', 25: '磁峰', 26: '通济', 27: '新兴',
#     28: '小鱼洞', 29: '龙门山', 30: '葛仙山', 31: '红岩', 32: '师古', 33: '湔底', 34: '白鹿',
#     35: '八角', 36: '洛水', 37: '莹华', 38: '红白'
# }
# # ================= 3. 数据整合 =================

# # 3.1 基础连线 (u, v, default_travel_time)
# # 这里包含所有存在的物理连接。如果受损列表中有，会被覆盖；如果没有，则默认为正常。
# base_edges = [
#     (1, 4, 16), (1, 11, 36), (1, 13, 16), (1, 17, 28),
#     (2, 3, 50), (2, 21, 36), (2, 23, 40),
#     (3, 32, 52), (3, 36, 60),
#     (4, 5, 22), (4, 11, 40),
#     (5, 6, 18), (6, 7, 24), (6, 10, 13),
#     (7, 8, 34), (8, 9, 50), (9, 10, 50),
#     (11, 12, 64), (11, 18, 74),
#     (13, 14, 22), (13, 16, 24), (13, 17, 24),
#     (14, 15, 16), (16, 20, 28), (16, 22, 42),
#     (17, 19, 28), (17, 22, 36),
#     (18, 25, 180), (19, 25, 32),
#     (20, 21, 56), (21, 23, 48),
#     (22, 23, 34), (22, 24, 28), (23, 24, 16),
#     (24, 27, 24), (24, 30, 64),
#     (25, 26, 50), (26, 27, 20), (26, 28, 32), (26, 34, 46),
#     (28, 29, 28),
#     (30, 31, 28), (31, 32, 46),
#     (32, 33, 36), (32, 36, 56),
#     (33, 34, 60), (33, 36, 24),
#     (34, 35, 100), (35, 37, 32),
#     (36, 37, 56), (37, 38, 52),
# ]

# # 3.2 受损路段详情 (u, v, travel_time, repair_time, task_id)
# # 这些数据将覆盖 base_edges 中的属性
# damaged_edges_with_id = [
#     (1, 4, 16, 900, 1),
#     (13, 14, 22, 180, 2),
#     (28, 29, 28, 270, 3),
#     (30, 31, 28, 210, 4),
#     (34, 35, 100, 720, 5),
#     (19, 25, 32, 1080, 6),
#     (17, 22, 36, 180, 7),
#     (25, 26, 50, 270, 8),
#     (24, 27, 24, 810, 9),
#     (24, 30, 64, 270, 10),
#     (26, 27, 20, 720, 11),
#     (26, 34, 46, 1050, 12),
#     (26, 28, 32, 360, 13),
#     (33, 34, 60, 180, 14),
#     (35, 37, 32, 450, 15),
#     (36, 37, 56, 330, 16),
# ]

# # ================= 4. 构建图 =================
# G = nx.Graph()
# G.add_nodes_from(pos.keys())

# # 第一步：添加所有基础边，默认状态为正常
# for u, v, t_time in base_edges:
#     G.add_edge(u, v, travel_time=t_time, repair_time=0, task_id=None, status='normal')

# # 第二步：更新受损边属性
# for u, v, t_time, r_time, t_id in damaged_edges_with_id:
#     # 如果边不存在（例如base中漏了），则添加；如果存在，则更新
#     G.add_edge(u, v, travel_time=t_time, repair_time=r_time, task_id=t_id, status='damaged')

# # ================= 5. 绘图 (浅色模式) =================
# plt.figure(figsize=(16, 14), facecolor='white')
# ax = plt.gca()
# ax.set_facecolor('white')

# # --- 5.1 绘制边 ---
# normal_edges = [(u, v) for u, v, d in G.edges(data=True) if d['status'] == 'normal']
# damaged_edges = [(u, v) for u, v, d in G.edges(data=True) if d['status'] == 'damaged']

# # 正常边: 深灰色
# nx.draw_networkx_edges(G, pos, edgelist=normal_edges, edge_color='#888888', width=1.5, alpha=0.6)
# # 受损边: 红色虚线
# nx.draw_networkx_edges(G, pos, edgelist=damaged_edges, edge_color='#d32f2f', style='dashed', width=2.5, alpha=1.0)

# # --- 5.2 绘制节点 ---
# supply_nodes = [1, 2, 3]
# demand_nodes = [n for n in G.nodes if n not in supply_nodes]

# nx.draw_networkx_nodes(G, pos, nodelist=supply_nodes, node_size=650, 
#                        node_shape='^', node_color='#ff9800', edgecolors='#333333', label='供应中心')
# nx.draw_networkx_nodes(G, pos, nodelist=demand_nodes, node_size=250, 
#                        node_color='#81d4fa', edgecolors='#333333', label='受灾点')

# # --- 5.3 绘制信息标注 (核心优化) ---
# halo_white = [path_effects.withStroke(linewidth=3, foreground='white')]

# for u, v, d in G.edges(data=True):
#     # 计算中点
#     x_mid = (pos[u][0] + pos[v][0]) / 2
#     y_mid = (pos[u][1] + pos[v][1]) / 2
    
#     t_val = d['travel_time']
    
#     if d['status'] == 'normal':
#         # 1. 正常路段：只显示 T:xx
#         label = f"T:{t_val}"
#         txt = plt.text(x_mid, y_mid, label, color='#555555', fontsize=7, 
#                        ha='center', va='center', zorder=15)
#         txt.set_path_effects(halo_white)
        
#     else:
#         # 2. 受损路段：显示任务ID圆圈 + 修复时间 + 通行时间
        
#         # A. 绘制圆圈背景 (代表任务ID的牌子)
#         # 在中点画一个白色圆点，带红色边框
#         plt.plot(x_mid, y_mid, 'o', markersize=16, markerfacecolor='white', markeredgecolor='#d32f2f', markeredgewidth=1.5, zorder=25)
        
#         # B. 在圆圈里写任务ID
#         plt.text(x_mid, y_mid, str(d['task_id']), color='#d32f2f', fontsize=8, fontweight='bold',
#                  ha='center', va='center', zorder=30)
        
#         # C. 在圆圈旁边/下方显示时间信息
#         # 偏移一点位置，防止挡住圆圈
#         r_val = d['repair_time']
#         info_label = f"R:{r_val}\nT:{t_val}"
#         # 向下偏移 y-0.015
#         txt = plt.text(x_mid, y_mid - 0.015, info_label, color='#d32f2f', fontsize=7, fontweight='bold',
#                        ha='center', va='top', zorder=20)
#         txt.set_path_effects(halo_white)

# # --- 5.4 绘制节点名称 ---
# # 节点ID (节点内部)
# nx.draw_networkx_labels(G, pos, font_size=8, font_color='black', font_weight='bold') 

# # 中文地名 (节点下方)
# label_pos = {k: (v[0], v[1]-0.015) for k, v in pos.items()}
# txt_items = nx.draw_networkx_labels(G, label_pos, labels=labels_map, font_color='#333333', font_size=9)
# for _, t in txt_items.items():
#     t.set_path_effects(halo_white)

# # --- 5.5 图例与标题 ---
# from matplotlib.lines import Line2D
# legend_elements = [
#     Line2D([0], [0], marker='^', color='w', label='供应中心', markerfacecolor='#ff9800', markeredgecolor='#333333', markersize=10),
#     Line2D([0], [0], marker='o', color='w', label='受灾点', markerfacecolor='#81d4fa', markeredgecolor='#333333', markersize=8),
#     Line2D([0], [0], color='#888888', lw=1.5, label='正常道路 (T:通行时间)'),
#     Line2D([0], [0], color='#d32f2f', lw=2.5, linestyle='--', label='受损道路 (R:修复时间)'),
#     Line2D([0], [0], marker='o', color='w', label='受损任务编号', markerfacecolor='white', markeredgecolor='#d32f2f', markersize=10),
# ]
# plt.legend(handles=legend_elements, loc='upper right', facecolor='white', edgecolor='#cccccc', labelcolor='black', framealpha=1.0)

# plt.title("汶川地震物流网络 - 受损任务与修复时间图", color='black', fontsize=16)
# plt.axis('off')
# plt.tight_layout()
# plt.show()


import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects

# ================= 0. 字体设置 =================
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Microsoft YaHei', 'SimHei', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# ================= 1. 节点数据 (ID, Name, Type, Quantity) =================
nodes_data = [
    (1, "都江堰", "supply", 3000), (2, "彭州", "supply", 3000), (3, "什邡", "supply", 3000),
    (4, "玉堂", "demand", 342), (5, "中兴", "demand", 360), (6, "青城山", "demand", 322),
    (7, "大观", "demand", 361), (8, "安龙", "demand", 382), (9, "石羊", "demand", 327),
    (10, "翠月湖", "demand", 361), (11, "紫坪铺", "demand", 344), (12, "龙池", "demand", 321),
    (13, "幸福", "demand", 363), (14, "聚源", "demand", 344), (15, "崇义", "demand", 384),
    (16, "胥家", "demand", 251), (17, "蒲阳", "demand", 339), (18, "虹口", "demand", 358),
    (19, "向娥", "demand", 302), (20, "天马", "demand", 282), (21, "丽春", "demand", 281),
    (22, "桂花", "demand", 205), (23, "隆丰", "demand", 324), (24, "丹景山", "demand", 280),
    (25, "磁峰", "demand", 241), (26, "通济", "demand", 382), (27, "新兴", "demand", 320),
    (28, "小鱼洞", "demand", 262), (29, "龙门山", "demand", 328), (30, "葛仙山", "demand", 320),
    (31, "红岩", "demand", 268), (32, "师古", "demand", 323), (33, "湔底", "demand", 300),
    (34, "白鹿", "demand", 282), (35, "八角", "demand", 359), (36, "洛水", "demand", 365),
    (37, "莹华", "demand", 302), (38, "红白", "demand", 403),
]
# 转字典方便调用
node_info = {item[0]: {'name': item[1], 'type': item[2], 'val': item[3]} for item in nodes_data}

# ================= 2. 坐标数据 =================
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
raw_edges = [
    (1, 4, 16, 900), (1, 11, 36, 0), (1, 13, 16, 0), (1, 17, 28, 0),
    (2, 3, 50, 0), (2, 21, 36, 0), (2, 23, 40, 0),
    (3, 32, 52, 0), (3, 36, 60, 0),
    (4, 5, 22, 0), (4, 11, 40, 0),
    (5, 6, 18, 0), (6, 7, 24, 0), (6, 10, 13, 0),
    (7, 8, 34, 0), (8, 9, 50, 0), (9, 10, 50, 0),
    (11, 12, 64, 0), (11, 18, 74, 0),
    (13, 14, 22, 180), (13, 16, 24, 0), (13, 17, 24, 0),
    (14, 15, 16, 0), (16, 20, 28, 0), (16, 22, 42, 0),
    (17, 19, 28, 0), (17, 22, 36, 180),
    (18, 25, 180, 0), (19, 25, 32, 1080),
    (20, 21, 56, 0), (21, 23, 48, 0),
    (22, 23, 34, 0), (22, 24, 28, 0), (23, 24, 16, 0),
    (24, 27, 24, 810), (24, 30, 64, 270),
    (25, 26, 50, 270),
    (26, 27, 20, 720), (26, 28, 32, 360), (26, 34, 46, 1050),
    (28, 29, 28, 270),
    (30, 31, 28, 210), (31, 32, 46, 0),
    (32, 33, 36, 0), (32, 36, 56, 0),
    (33, 34, 60, 180), (33, 36, 24, 0),
    (34, 35, 100, 720),
    (35, 37, 32, 450),
    (36, 37, 56, 330), (37, 38, 52, 0),
]

# B. 受损任务ID映射 (u, v, repair_time, task_id)
damaged_tasks = [
    (1, 4, 16, 900, 1), (13, 14, 22, 180, 2), (28, 29, 28, 270, 3), (30, 31, 28, 210, 4),
    (34, 35, 100, 720, 5), (19, 25, 32, 1080, 6), (17, 22, 36, 180, 7), (25, 26, 50, 270, 8),
    (24, 27, 24, 810, 9), (24, 30, 64, 270, 10), (26, 27, 20, 720, 11), (26, 34, 46, 1050, 12),
    (26, 28, 32, 360, 13), (33, 34, 60, 180, 14), (35, 37, 32, 450, 15), (36, 37, 56, 330, 16),
]

# 构建图并合并数据
G = nx.Graph()
G.add_nodes_from(pos.keys())

# 1. 先添加所有基础边 (默认状态 normal)
for u, v, t_time, r_time in raw_edges:
    G.add_edge(u, v, travel_time=t_time, repair_time=r_time, status='normal', task_id=None)

# 2. 用受损任务数据覆盖 (状态 damaged)
for u, v, t_time, r_time, t_id in damaged_tasks:
    # 如果raw_edges里漏了某条受损边，这里会自动补上
    G.add_edge(u, v, travel_time=t_time, repair_time=r_time, status='damaged', task_id=t_id)


# ================= 4. 绘图 =================
plt.figure(figsize=(18, 16), facecolor='white') # 加大画布，防止密集
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
plt.title("初始路网状态", fontsize=16, y=0.9)
plt.axis('off')
plt.tight_layout()
plt.show()