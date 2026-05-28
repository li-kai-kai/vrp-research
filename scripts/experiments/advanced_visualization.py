import networkx as nx
import numpy as np
import random
import copy
import matplotlib.pyplot as plt
import math

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Microsoft YaHei', 'SimHei', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# 1. 数据配置 (保持不变)
# ==========================================

# 节点数据 (ID, Name, Type, Value)
RAW_NODES = [
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

# 坐标数据
POS = {
    1: (103.62, 30.99), 13: (103.65, 31.00), 16: (103.70, 31.01), 17: (103.66, 31.08),
    4: (103.54, 30.98), 5: (103.52, 30.94), 6: (103.54, 30.89), 7: (103.55, 30.82),
    8: (103.58, 30.78), 9: (103.62, 30.82), 10: (103.63, 30.90), 11: (103.58, 31.04),
    12: (103.52, 31.07), 14: (103.69, 30.96), 15: (103.70, 30.90), 18: (103.60, 31.11),
    19: (103.70, 31.10), 20: (103.76, 30.96), 2: (103.99, 30.95), 21: (103.86, 30.97),
    22: (103.82, 31.02), 23: (103.96, 31.04), 24: (103.94, 31.12), 25: (103.80, 31.18),
    26: (103.90, 31.22), 27: (103.95, 31.19), 28: (103.84, 31.27), 29: (103.86, 31.33),
    34: (103.98, 31.28), 30: (104.00, 31.14), 31: (104.06, 31.15), 32: (104.12, 31.16),
    33: (104.08, 31.24), 3: (104.16, 31.10), 35: (104.10, 31.33), 36: (104.15, 31.26),
    37: (104.13, 31.39), 38: (104.15, 31.46)
}

# 基础路网连接
RAW_EDGES = [
    (1, 4, 16), (1, 11, 36), (1, 13, 16), (1, 17, 28), (2, 3, 50), (2, 21, 36), (2, 23, 40),
    (3, 32, 52), (3, 36, 60), (4, 5, 22), (4, 11, 40), (5, 6, 18), (6, 7, 24), (6, 10, 13),
    (7, 8, 34), (8, 9, 50), (9, 10, 50), (11, 12, 64), (11, 18, 74), (13, 14, 22),
    (13, 16, 24), (13, 17, 24), (14, 15, 16), (16, 20, 28), (16, 22, 42), (17, 19, 28),
    (17, 22, 36), (18, 25, 180), (19, 25, 32), (20, 21, 56), (21, 23, 48), (22, 23, 34),
    (22, 24, 28), (23, 24, 16), (24, 27, 24), (24, 30, 64), (25, 26, 50), (26, 27, 20),
    (26, 28, 32), (26, 34, 46), (28, 29, 28), (30, 31, 28), (31, 32, 46), (32, 33, 36),
    (32, 36, 56), (33, 34, 60), (33, 36, 24), (34, 35, 100), (35, 37, 32), (36, 37, 56),
    (37, 38, 52)
]

# 受损任务详情
DAMAGED_TASKS = [
    {'u': 1, 'v': 4, 'travel': 16, 'repair': 1200, 'id': 1},
    {'u': 13, 'v': 14, 'travel': 22, 'repair': 360, 'id': 2},
    {'u': 28, 'v': 29, 'travel': 28, 'repair': 420, 'id': 3},
    {'u': 30, 'v': 31, 'travel': 28, 'repair': 300, 'id': 4},
    {'u': 34, 'v': 35, 'travel': 100, 'repair': 810, 'id': 5},
    {'u': 19, 'v': 25, 'travel': 32, 'repair': 1080, 'id': 6},
    {'u': 17, 'v': 22, 'travel': 36, 'repair': 360, 'id': 7},
    {'u': 25, 'v': 26, 'travel': 50, 'repair': 200, 'id': 8},
    {'u': 24, 'v': 27, 'travel': 24, 'repair': 810, 'id': 9},
    {'u': 24, 'v': 30, 'travel': 64, 'repair': 400, 'id': 10},
    {'u': 26, 'v': 27, 'travel': 20, 'repair': 720, 'id': 11},
    {'u': 26, 'v': 34, 'travel': 46, 'repair': 1050, 'id': 12},
    {'u': 26, 'v': 28, 'travel': 32, 'repair': 360, 'id': 13},
    {'u': 33, 'v': 34, 'travel': 60, 'repair': 360, 'id': 14},
    {'u': 35, 'v': 37, 'travel': 32, 'repair': 450, 'id': 15},
    {'u': 36, 'v': 37, 'travel': 56, 'repair': 360, 'id': 16},
]

# 算法全局参数
CONFIG = {
    'T_total': 72 * 60,        # 总工期
    'eta': 6 * 60,             # 决策时间步长
    'teams': [1, 2, 3],        # 抢修队
    'big_time': 99999,         # 断路惩罚时间
    'pop_size': 50,
    'max_gen': 500,
    'fleet_capacity': 1000,
    
    # === 新增/修改的参数 ===
    'repair_cost_factor': 1,   # 成本系数 (这里设为1，表示成本=工时)
    'cost_penalty_alpha': 5.0, # 成本惩罚权重 (关键参数：数值越大，越倾向于省钱；数值越小，越倾向于不计代价抢通)
    'elite_size': 4            # 精英保留数量
}

# ==========================================
# 2. 环境与图构建 (保持不变)
# ==========================================

class Environment:
    def __init__(self):
        self.G = nx.Graph()
        self.suppliers = []
        self.demands = {} 
        self.task_map = {} 
        self.init_data()
        
    def init_data(self):
        # 1. 节点初始化
        for nid, name, ntype, val in RAW_NODES:
            self.G.add_node(nid, name=name, type=ntype, val=val)
            if ntype == 'supply':
                self.suppliers.append(nid)
            elif ntype == 'demand':
                self.demands[nid] = val
                
        # 2. 边初始化
        for u, v, t in RAW_EDGES:
            self.G.add_edge(u, v, weight=t, status='intact', normal_time=t)
            
        # 3. 标记受损边
        for task in DAMAGED_TASKS:
            u, v = task['u'], task['v']
            if self.G.has_edge(u, v):
                self.G[u][v]['status'] = 'damaged'
                self.G[u][v]['repair_time'] = task['repair']
                self.G[u][v]['task_id'] = task['id']
                self.G[u][v]['weight'] = CONFIG['big_time']
            else:
                self.G.add_edge(u, v, weight=CONFIG['big_time'], status='damaged', 
                                normal_time=task['travel'], repair_time=task['repair'], 
                                task_id=task['id'])
            
            self.task_map[task['id'] - 1] = task

    def get_task_info(self, idx):
        return self.task_map[idx]

# ==========================================
# 3. 改进的评估逻辑 (单目标 Fitness)
# ==========================================

def calculate_fitness(chromosome, env):
    """
    输入: 染色体
    输出: 综合得分 (Fitness) = 绩效收益 - alpha * 成本
    """
    sub1, sub2 = chromosome
    num_tasks = len(env.task_map)
    
    # --- A. 模拟修路过程 ---
    team_time = {i: 0 for i in range(len(CONFIG['teams']))} 
    repair_schedule = {} 
    
    actual_repair_cost = 0 
    
    for i in range(num_tasks):
        task_idx = sub1[i]
        team_idx = sub2[i]
        task_info = env.get_task_info(task_idx)
        repair_t = task_info['repair']
        
        start_t = team_time[team_idx]
        finish_t = start_t + repair_t
        
        if finish_t <= CONFIG['T_total']:
            team_time[team_idx] = finish_t
            repair_schedule[task_info['id']] = finish_t
            actual_repair_cost += repair_t * CONFIG['repair_cost_factor']
        
    # --- B. 计算抢修绩效 U ---
    cumulative_U = 0
    steps = int(CONFIG['T_total'] / CONFIG['eta'])
    
    # 初始路网状态
    current_G = env.G.copy()
    for u, v, d in current_G.edges(data=True):
        if d.get('status') == 'damaged':
            current_G[u][v]['weight'] = CONFIG['big_time']
            
    # 初始OD矩阵
    prev_od = {}
    for s in env.suppliers:
        try:
            prev_od[s] = nx.single_source_dijkstra_path_length(current_G, s, weight='weight')
        except:
            prev_od[s] = {}
            
    # 时间切片循环
    for step in range(1, steps + 1):
        sim_time = step * CONFIG['eta']
        
        # 1. 更新路网状态
        step_G = env.G.copy()
        for u, v, d in step_G.edges(data=True):
            if d.get('status') == 'damaged':
                tid = d.get('task_id')
                if repair_schedule.get(tid, 999999) <= sim_time:
                    step_G[u][v]['weight'] = d['normal_time']
                else:
                    step_G[u][v]['weight'] = CONFIG['big_time']
        
        # 2. 计算当前OD
        curr_od = {}
        for s in env.suppliers:
            try:
                curr_od[s] = nx.single_source_dijkstra_path_length(step_G, s, weight='weight')
            except:
                curr_od[s] = {}
                
        # 3. 积分绩效
        remaining_time = CONFIG['T_total'] - sim_time
        step_gain = 0
        
        for s in env.suppliers:
            for d_node, demand_val in env.demands.items():
                t_old = prev_od[s].get(d_node, CONFIG['big_time'])
                t_new = curr_od[s].get(d_node, CONFIG['big_time'])
                
                if t_old > CONFIG['big_time']: t_old = CONFIG['big_time']
                if t_new > CONFIG['big_time']: t_new = CONFIG['big_time']
                
                delta_t = t_old - t_new
                
                if delta_t > 0 and t_new < CONFIG['big_time']:
                    # 修改建议：使用 demand_val 的平方来放大核心节点的重要性
                    # 如果你只想要“性价比”，这里公式不变也行，重点是后面的惩罚项
                    step_gain += demand_val * delta_t * remaining_time
        
        cumulative_U += step_gain
        prev_od = curr_od 
        
    # --- C. 计算综合 Fitness ---
    # Fitness = U - alpha * Cost
    # 注意：U 通常很大 (e.g. 1e7)，Cost 较小 (e.g. 5000)，所以 alpha 需要调整或 U/Cost 需要归一化
    # 这里直接使用简单的加权减法。
    
    fitness = cumulative_U - (CONFIG['cost_penalty_alpha'] * actual_repair_cost)
    
    return fitness, cumulative_U, actual_repair_cost

# ==========================================
# 4. 单目标遗传算法引擎
# ==========================================

def generate_population(n_tasks, n_teams, size):
    pop = []
    for _ in range(size):
        sub1 = list(range(n_tasks))
        random.shuffle(sub1)
        sub2 = [random.randint(0, n_teams-1) for _ in range(n_tasks)]
        pop.append([sub1, sub2])
    return pop

def genetic_ops_single_obj(population, num_teams, elite_pop):
    """
    单目标遗传操作：保留精英 + 锦标赛选择 + 交叉 + 变异
    """
    new_pop = []
    
    # 1. 精英保留 (直接复制)
    new_pop.extend(copy.deepcopy(elite_pop))
    
    # 2. 生成剩余个体
    while len(new_pop) < len(population):
        # 锦标赛选择 (随机抽2个，选Fitness高的)
        p1 = random.choice(population)
        p2 = random.choice(population)
        
        # 假设 population 列表里存的是 [chromo, fitness_val]
        # 这里为了简化，我们在外部已经把 population 排好序了，但这函数接收的是纯染色体列表
        # 所以我们这里简单随机选父母（因为已经在主循环里做了筛选）
        # 或者更严谨一点，直接随机选两个
        
        parent1 = random.choice(population)
        parent2 = random.choice(population)
        
        # 交叉
        pt = random.randint(1, len(parent1[0])-1)
        # 顺序交叉 (Order Crossover) for sub1
        c1_s1 = parent1[0][:pt] + [x for x in parent2[0] if x not in parent1[0][:pt]]
        # 简单交叉 for sub2
        c1_s2 = parent1[1][:pt] + parent2[1][pt:]
        
        # 变异
        if random.random() < 0.15: # 增加一点变异率防止早熟
            i, j = random.sample(range(len(c1_s1)), 2)
            c1_s1[i], c1_s1[j] = c1_s1[j], c1_s1[i]
            c1_s2[i] = random.randint(0, num_teams-1)
            
        new_pop.append([c1_s1, c1_s2])
        
    return new_pop[:len(population)]

# ==========================================
# 5. 可视化函数 (保持不变)
# ==========================================

def plot_network_plan(env, solution, title="Optimal Repair Plan"):
    sub1, sub2 = solution
    repaired_edges = []
    team_time = {i: 0 for i in range(len(CONFIG['teams']))}
    
    # 计算实际修了哪些路
    for i, task_idx in enumerate(sub1):
        team_id = sub2[i]
        task = env.get_task_info(task_idx)
        fin = team_time[team_id] + task['repair']
        if fin <= CONFIG['T_total']:
            team_time[team_id] = fin
            repaired_edges.append((task['u'], task['v']))
            
    plt.figure(figsize=(10, 8))
    nx.draw_networkx_nodes(env.G, POS, node_size=200, node_color='lightgray')
    nx.draw_networkx_nodes(env.G, POS, nodelist=env.suppliers, node_size=400, node_color='red', label='Supply')
    nx.draw_networkx_edges(env.G, POS, edge_color='gray', alpha=0.3)
    
    # 虚线画没修的
    damaged_uv = [(t['u'], t['v']) for t in DAMAGED_TASKS]
    unrepaired = [e for e in damaged_uv if e not in repaired_edges and (e[1], e[0]) not in repaired_edges]
    nx.draw_networkx_edges(env.G, POS, edgelist=unrepaired, edge_color='black', style='dashed', width=1.5, label='Unrepaired')
    
    # 绿线画修了的
    nx.draw_networkx_edges(env.G, POS, edgelist=repaired_edges, edge_color='green', width=2.5, label='Repaired')
    
    labels = {n: f"{n}" for n in env.G.nodes()}
    nx.draw_networkx_labels(env.G, POS, labels=labels, font_size=8)
    
    plt.title(title)
    plt.legend()
    plt.axis('off')
    plt.show()

import matplotlib.patches as mpatches

# def visualize_evolution(env, best_solution):
#     """
#     可视化最优解随时间演变的全过程
#     """
#     sub1, sub2 = best_solution
    
#     # --- 1. 预计算：解析调度时间表 ---
#     # 我们需要知道每个任务具体的 [开始时间, 结束时间, 负责队伍]
#     task_schedule = {} # {task_id: {'start': t, 'end': t, 'team': id, 'u': u, 'v': v}}
#     team_time = {i: 0 for i in range(len(CONFIG['teams']))} # 队伍当前空闲时间
#     team_loc = {i: CONFIG['teams'][i] for i in range(len(CONFIG['teams']))} # 队伍初始位置
    
#     # 记录每个时间步队伍的位置
#     # 格式: schedule_events = [(start_time, end_time, task_info, team_id), ...]
#     schedule_log = []

#     for i, task_idx in enumerate(sub1):
#         team_id = sub2[i]
#         task = env.get_task_info(task_idx)
#         repair_duration = task['repair']
        
#         start_t = team_time[team_id]
#         finish_t = start_t + repair_duration
        
#         if finish_t <= CONFIG['T_total']:
#             team_time[team_id] = finish_t
            
#             info = {
#                 'start': start_t,
#                 'end': finish_t,
#                 'team': team_id + 1, # 显示为 Team 1-3
#                 'u': task['u'],
#                 'v': task['v'],
#                 'id': task['id']
#             }
#             task_schedule[task['id']] = info
#             schedule_log.append(info)
            
#     # --- 2. 时间步进回放 ---
#     total_steps = int(CONFIG['T_total'] / CONFIG['eta'])
    
#     # 设置画图布局
#     # 如果想生成动图，可以在这里开启 plt.ion()，但我建议先生成静态子图方便查看
#     # 为了不生成太多图，我们每隔几个步长画一张，或者画出关键帧
#     # 这里演示：画出 0, 12h, 24h, 36h, 48h, 60h, 72h 的状态
    
#     snapshot_times = range(0, 73*60, CONFIG['eta'])
    
#     # 动态调整子图行数
#     rows = math.ceil(len(snapshot_times) / 2)
#     fig, axes = plt.subplots(rows, 2, figsize=(15, 6 * rows))
#     axes = axes.flatten()
    
#     print("\n--- 开始生成演变过程图 ---")
    
#     for idx, current_time in enumerate(snapshot_times):
#         ax = axes[idx] if idx < len(axes) else None
#         if ax is None: break
        
#         # A. 构建当前时刻的图状态
#         display_G = env.G.copy()
        
#         repaired_edges = []
#         working_edges = []
#         damaged_edges = []
        
#         # 分类边的状态
#         for u, v, d in display_G.edges(data=True):
#             if d.get('status') == 'damaged':
#                 tid = d.get('task_id')
#                 sched = task_schedule.get(tid)
                
#                 if not sched:
#                     # 永远不修的
#                     damaged_edges.append((u, v))
#                     display_G[u][v]['weight'] = CONFIG['big_time']
#                 else:
#                     if current_time >= sched['end']:
#                         # 已修好
#                         repaired_edges.append((u, v))
#                         display_G[u][v]['weight'] = d['normal_time']
#                     elif current_time >= sched['start'] and current_time < sched['end']:
#                         # 正在修 (算作不通)
#                         working_edges.append((u, v))
#                         display_G[u][v]['weight'] = CONFIG['big_time']
#                     else:
#                         # 还没开始修
#                         damaged_edges.append((u, v))
#                         display_G[u][v]['weight'] = CONFIG['big_time']
        
#         # B. 计算可达性 (哪些点通过了)
#         reachable_nodes = set()
#         for s in env.suppliers:
#             try:
#                 # 只有路权 < big_time 才算通
#                 paths = nx.single_source_dijkstra_path_length(display_G, s, weight='weight')
#                 for node, dist in paths.items():
#                     if dist < CONFIG['big_time']:
#                         reachable_nodes.add(node)
#             except:
#                 pass
                
#         # C. 绘图
        
#         # 1. 画节点
#         # 供应点
#         nx.draw_networkx_nodes(display_G, POS, nodelist=env.suppliers, 
#                                node_color='red', node_size=300, ax=ax, label='Supply')
#         # 已通的需求点
#         demand_reached = [n for n in reachable_nodes if n not in env.suppliers]
#         nx.draw_networkx_nodes(display_G, POS, nodelist=demand_reached, 
#                                node_color='skyblue', node_size=150, ax=ax, label='Reached')
#         # 未通的孤岛
#         demand_unreached = [n for n in env.G.nodes() if n not in reachable_nodes and n not in env.suppliers]
#         nx.draw_networkx_nodes(display_G, POS, nodelist=demand_unreached, 
#                                node_color='lightgray', node_shape='x', node_size=100, ax=ax, label='Unreached')
        
#         # 2. 画边
#         # 基础路网 (浅灰)
#         base_edges = [e for e in env.G.edges() if env.G.edges[e].get('status') == 'intact']
#         nx.draw_networkx_edges(display_G, POS, edgelist=base_edges, edge_color='#cccccc', ax=ax)
#         # 受损未修 (黑虚线)
#         nx.draw_networkx_edges(display_G, POS, edgelist=damaged_edges, 
#                                edge_color='black', style='dashed', alpha=0.5, ax=ax)
#         # 正在修 (橙色醒目)
#         nx.draw_networkx_edges(display_G, POS, edgelist=working_edges, 
#                                edge_color='orange', width=4, ax=ax)
#         # 已修好 (绿色)
#         nx.draw_networkx_edges(display_G, POS, edgelist=repaired_edges, 
#                                edge_color='green', width=3, ax=ax)
        
#         # 3. 画队伍位置 (简单的文本标注)
#         # 找出当前时刻队伍在哪里
#         team_positions = {}
#         for t_info in schedule_log:
#             # 如果正在工作
#             if t_info['start'] <= current_time < t_info['end']:
#                 # 在边的中点
#                 mid_x = (POS[t_info['u']][0] + POS[t_info['v']][0]) / 2
#                 mid_y = (POS[t_info['u']][1] + POS[t_info['v']][1]) / 2
#                 ax.text(mid_x, mid_y, f"T{t_info['team']}🛠️", fontsize=12, fontweight='bold', color='darkblue')
#             # 如果工作刚结束不久 (显示在这里)
#             elif current_time >= t_info['end']:
#                  # 简化处理：假设队伍停留在任务的终点 v (或者 u，因为是无向图)
#                  # 这里不做复杂的状态机追踪，仅显示正在工作的
#                  pass

#         # 4. 图例与标题
#         hour = current_time / 60
#         status_text = f"Time: {hour:.1f}h / 72h\n"
#         status_text += f"Repaired: {len(repaired_edges)} | Working: {len(working_edges)}\n"
#         status_text += f"Connected Nodes: {len(reachable_nodes)}/{len(env.G.nodes())}"
        
#         ax.set_title(status_text, fontsize=10, loc='left')
#         ax.axis('off')

#     # 创建自定义图例
#     legend_elements = [
#         mpatches.Patch(color='green', label='Repaired Road'),
#         mpatches.Patch(color='orange', label='Under Repair (Work in Progress)'),
#         mpatches.Patch(color='skyblue', label='Connected Demand'),
#         mpatches.Patch(color='lightgray', label='Unreachable Demand')
#     ]
#     fig.legend(handles=legend_elements, loc='upper center', ncol=4)
#     plt.tight_layout()
#     plt.show()
import matplotlib.lines as mlines

def visualize_evolution_advanced(env, best_solution):
    """
    高级可视化：包含路网修复状态、物资配送路线流、需求满足情况
    """
    sub1, sub2 = best_solution
    
    # --- 1. 预计算：解析调度时间表 ---
    task_schedule = {} 
    team_time = {i: 0 for i in range(len(CONFIG['teams']))} 
    schedule_log = [] # 记录正在修路的状态

    for i, task_idx in enumerate(sub1):
        team_id = sub2[i]
        task = env.get_task_info(task_idx)
        repair_duration = task['repair']
        
        start_t = team_time[team_id]
        finish_t = start_t + repair_duration
        
        if finish_t <= CONFIG['T_total']:
            team_time[team_id] = finish_t
            info = {
                'start': start_t,
                'end': finish_t,
                'team': team_id + 1, 
                'u': task['u'], 
                'v': task['v'],
                'id': task['id']
            }
            task_schedule[task['id']] = info
            schedule_log.append(info)
            
    # --- 2. 设置快照时间点 ---
    # 每 12 小时一张图
    snapshot_times = [0, 12*60, 24*60, 36*60, 48*60, 60*60, 72*60]
    
    rows = math.ceil(len(snapshot_times) / 2)
    fig, axes = plt.subplots(rows, 2, figsize=(16, 7 * rows))
    axes = axes.flatten()
    
    print("\n--- 生成物流与修复演变图 ---")
    
    for idx, current_time in enumerate(snapshot_times):
        ax = axes[idx] if idx < len(axes) else None
        if ax is None: break
        
        # === A. 构建当前物理路网 ===
        display_G = env.G.copy()
        
        repaired_edges = []   # 已修好
        working_edges = []    # 正在修
        damaged_edges = []    # 坏的
        intact_edges = []     # 原本好的
        
        # 1. 确定每条边的物理状态
        for u, v, d in display_G.edges(data=True):
            status = 'intact'
            weight = d['normal_time']
            
            if d.get('status') == 'damaged':
                tid = d.get('task_id')
                sched = task_schedule.get(tid)
                
                if not sched: # 弃修
                    status = 'broken'
                    weight = CONFIG['big_time']
                else:
                    if current_time >= sched['end']:
                        status = 'repaired'
                        weight = d['normal_time']
                    elif current_time >= sched['start'] and current_time < sched['end']:
                        status = 'working'
                        weight = CONFIG['big_time'] # 施工中不可通行
                    else:
                        status = 'broken'
                        weight = CONFIG['big_time']
            
            # 更新图权重用于寻路
            display_G[u][v]['weight'] = weight
            
            # 分类用于画图
            if status == 'repaired': repaired_edges.append((u, v))
            elif status == 'working': working_edges.append((u, v))
            elif status == 'broken': damaged_edges.append((u, v))
            else: intact_edges.append((u, v))

        # === B. 计算物流配送路线 (Logistics Flow) ===
        # 使用多源 Dijkstra 计算从任意 Supply 到所有节点的路径
        # networkx 的 multi_source_dijkstra 会自动找最近的供应点
        active_routes_edges = set() # 存储被配送征用的路段
        reachable_demands = []      # 已满足的需求点
        unreachable_demands = []    # 未满足的需求点
        
        try:
            dists, paths = nx.multi_source_dijkstra(display_G, sources=env.suppliers, weight='weight')
            
            for node in env.demands.keys():
                if node in dists and dists[node] < CONFIG['big_time']:
                    reachable_demands.append(node)
                    # 提取路径上的所有边
                    path = paths[node]
                    for i in range(len(path) - 1):
                        # 无论方向如何，统一存为 tuple(sorted((u,v))) 防止重复
                        edge = tuple(sorted((path[i], path[i+1])))
                        active_routes_edges.add(edge)
                else:
                    unreachable_demands.append(node)
        except Exception as e:
            # 初期可能完全不通
            unreachable_demands = list(env.demands.keys())

        active_routes_list = list(active_routes_edges)

        # === C. 绘图层级 ===
        
        # Layer 1: 基础底图 (所有原本好的路，浅灰)
        nx.draw_networkx_edges(display_G, POS, edgelist=intact_edges, 
                               edge_color='#e0e0e0', width=1, ax=ax)
        
        # Layer 2: 物理修复状态
        # 坏路 (虚线)
        nx.draw_networkx_edges(display_G, POS, edgelist=damaged_edges, 
                               edge_color='black', style='dashed', alpha=0.4, width=1, ax=ax)
        # 正在修 (橙色粗线)
        nx.draw_networkx_edges(display_G, POS, edgelist=working_edges, 
                               edge_color='#ff9900', width=4, alpha=0.9, ax=ax)
        # 已修好 (绿色中线)
        nx.draw_networkx_edges(display_G, POS, edgelist=repaired_edges, 
                               edge_color='#2ca02c', width=2, alpha=0.6, ax=ax)

        # Layer 3: 物流配送流 (蓝色流动线)
        # 这些是物资实际走的路，叠加在上面
        nx.draw_networkx_edges(display_G, POS, edgelist=active_routes_list, 
                               edge_color='#1f77b4', width=2.5, alpha=0.7, ax=ax)

        # Layer 4: 节点状态
        # 供应点 (红色五角星)
        nx.draw_networkx_nodes(display_G, POS, nodelist=env.suppliers, 
                               node_color='red', node_shape='*', node_size=400, ax=ax, label='Supply')
        
        # 需求点 (根据需求量大小画圈)
        # 归一化节点大小: 最小100，最大400
        def get_node_sizes(nodes):
            vals = [env.demands[n] for n in nodes]
            if not vals: return []
            return [100 + (v/500)*300 for v in vals]

        # 已满足需求 (绿色圆点)
        if reachable_demands:
            nx.draw_networkx_nodes(display_G, POS, nodelist=reachable_demands, 
                                   node_color='#98df8a', node_size=get_node_sizes(reachable_demands), 
                                   edgecolors='green', ax=ax, label='Satisfied')
            
        # 未满足需求 (红色空心圈 or 灰色)
        if unreachable_demands:
            nx.draw_networkx_nodes(display_G, POS, nodelist=unreachable_demands, 
                                   node_color='#ff9896', node_size=get_node_sizes(unreachable_demands), 
                                   edgecolors='red', ax=ax, label='Pending')

        # Layer 5: 队伍位置标注
        for t_info in schedule_log:
            if t_info['start'] <= current_time < t_info['end']:
                mid_x = (POS[t_info['u']][0] + POS[t_info['v']][0]) / 2
                mid_y = (POS[t_info['u']][1] + POS[t_info['v']][1]) / 2
                # 给队伍加个白底框，防止看不清
                ax.text(mid_x, mid_y, f"T{t_info['team']}", fontsize=10, fontweight='bold', 
                        color='white', bbox=dict(boxstyle="round,pad=0.3", fc="orange", ec="none", alpha=0.9))

        # 统计信息标题
        hour = current_time / 60
        demand_covered_val = sum(env.demands[n] for n in reachable_demands)
        total_demand_val = sum(env.demands.values())
        percent = (demand_covered_val / total_demand_val) * 100
        
        title_info = f"TIME: {hour}h / 72h\n"
        title_info += f"Coverage: {percent:.1f}% ({len(reachable_demands)}/{len(env.demands)} Nodes)\n"
        title_info += f"Active Routes: {len(active_routes_list)} segments"
        
        ax.set_title(title_info, fontsize=11, loc='left', fontfamily='monospace')
        ax.axis('off')

    # 图例
    legend_handles = [
        mlines.Line2D([], [], color='#1f77b4', linewidth=3, label='Active Logistics Route'),
        mlines.Line2D([], [], color='#ff9900', linewidth=3, label='Repairing (Blocked)'),
        mlines.Line2D([], [], color='#2ca02c', linewidth=2, label='Repaired (Idle)'),
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#98df8a', markeredgecolor='green', markersize=10, label='Satisfied Demand'),
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#ff9896', markeredgecolor='red', markersize=10, label='Unsatisfied Demand'),
    ]
    fig.legend(handles=legend_handles, loc='upper center', ncol=5, fontsize=10)
    plt.tight_layout()
    plt.subplots_adjust(top=0.92) # 留出标题空间
    plt.show()


def visualize_step_by_step_with_legend(env, best_solution):
    """
    分步可视化 (带中文图例)：
    生成一系列独立的图片，每 6 小时一张，包含详细的中文说明。
    """
    sub1, sub2 = best_solution
    
    # --- 预计算：解析调度时间表 ---
    task_schedule = {} 
    team_time = {i: 0 for i in range(len(CONFIG['teams']))} 
    schedule_log = [] 

    for i, task_idx in enumerate(sub1):
        team_id = sub2[i]
        task = env.get_task_info(task_idx)
        repair_duration = task['repair']
        
        start_t = team_time[team_id]
        finish_t = start_t + repair_duration
        
        if finish_t <= CONFIG['T_total']:
            team_time[team_id] = finish_t
            info = {
                'start': start_t,
                'end': finish_t,
                'team': team_id + 1, 
                'u': task['u'], 
                'v': task['v'],
                'id': task['id']
            }
            task_schedule[task['id']] = info
            schedule_log.append(info)
            
    # --- 设定时间点 (每6小时一张) ---
    snapshot_times = list(range(0, CONFIG['T_total'] + 1, 6 * 60))
    
    print(f"\n--- 开始生成演变过程 (共 {len(snapshot_times)} 张图，带中文图例) ---")
    
    for current_time in snapshot_times:
        plt.figure(figsize=(11, 9)) # 稍微加大一点画布
        ax = plt.gca()
        
        # === A. 构建当前物理路网 ===
        display_G = env.G.copy()
        
        repaired_edges = []   # 已修好
        working_edges = []    # 正在修
        damaged_edges = []    # 坏的
        intact_edges = []     # 原本好的
        
        for u, v, d in display_G.edges(data=True):
            status = 'intact'
            weight = d['normal_time']
            
            if d.get('status') == 'damaged':
                tid = d.get('task_id')
                sched = task_schedule.get(tid)
                
                if not sched: # 弃修
                    status = 'broken'
                    weight = CONFIG['big_time']
                else:
                    if current_time >= sched['end']:
                        status = 'repaired'
                        weight = d['normal_time']
                    elif current_time >= sched['start'] and current_time < sched['end']:
                        status = 'working'
                        weight = CONFIG['big_time'] 
                    else:
                        status = 'broken'
                        weight = CONFIG['big_time']
            
            display_G[u][v]['weight'] = weight
            
            if status == 'repaired': repaired_edges.append((u, v))
            elif status == 'working': working_edges.append((u, v))
            elif status == 'broken': damaged_edges.append((u, v))
            else: intact_edges.append((u, v))

        # === B. 计算物流配送路线 ===
        active_routes_edges = set()
        reachable_demands = []
        unreachable_demands = []
        
        try:
            dists, paths = nx.multi_source_dijkstra(display_G, sources=env.suppliers, weight='weight')
            
            for node in env.demands.keys():
                if node in dists and dists[node] < CONFIG['big_time']:
                    reachable_demands.append(node)
                    path = paths[node]
                    for i in range(len(path) - 1):
                        edge = tuple(sorted((path[i], path[i+1])))
                        active_routes_edges.add(edge)
                else:
                    unreachable_demands.append(node)
        except:
            unreachable_demands = list(env.demands.keys())

        active_routes_list = list(active_routes_edges)

        # === C. 绘图层级 ===
        
        # Layer 1: 基础底图 (浅灰)
        if intact_edges:
            nx.draw_networkx_edges(display_G, POS, edgelist=intact_edges, 
                                   edge_color='#e0e0e0', width=1, ax=ax)
        
        # Layer 2: 物理修复状态
        if damaged_edges:
            nx.draw_networkx_edges(display_G, POS, edgelist=damaged_edges, 
                                   edge_color='black', style='dashed', alpha=0.3, width=1, ax=ax)
        if working_edges:
            nx.draw_networkx_edges(display_G, POS, edgelist=working_edges, 
                                   edge_color='#ff9900', width=4, alpha=0.9, ax=ax)
        if repaired_edges:
            nx.draw_networkx_edges(display_G, POS, edgelist=repaired_edges, 
                                   edge_color='#2ca02c', width=2, alpha=0.4, ax=ax)

        # Layer 3: 物流配送流 (蓝色)
        if active_routes_list:
            nx.draw_networkx_edges(display_G, POS, edgelist=active_routes_list, 
                                   edge_color='#1f77b4', width=2.5, alpha=0.8, ax=ax)

        # Layer 4: 节点状态
        # 供应点
        nx.draw_networkx_nodes(display_G, POS, nodelist=env.suppliers, 
                               node_color='red', node_shape='*', node_size=350, ax=ax, label='Supply')
        
        def get_node_sizes(nodes):
            return [100 + (env.demands[n]/500)*300 for n in nodes]

        # 已满足需求 (绿色)
        if reachable_demands:
            nx.draw_networkx_nodes(display_G, POS, nodelist=reachable_demands, 
                                   node_color='#98df8a', node_size=get_node_sizes(reachable_demands), 
                                   edgecolors='green', ax=ax)
            
        # 未满足需求 (红色)
        if unreachable_demands:
            nx.draw_networkx_nodes(display_G, POS, nodelist=unreachable_demands, 
                                   node_color='#ff9896', node_size=get_node_sizes(unreachable_demands), 
                                   edgecolors='red', ax=ax)

        # Layer 5: 队伍位置
        for t_info in schedule_log:
            if t_info['start'] <= current_time < t_info['end']:
                mid_x = (POS[t_info['u']][0] + POS[t_info['v']][0]) / 2
                mid_y = (POS[t_info['u']][1] + POS[t_info['v']][1]) / 2
                ax.text(mid_x, mid_y, f"T{t_info['team']}", fontsize=10, fontweight='bold', 
                        color='white', bbox=dict(boxstyle="round,pad=0.2", fc="#ff9900", ec="none", alpha=1.0))

        # === D. 添加中文图例 (Legend) ===
        # 创建自定义的 Handle
        legend_handles = [
            mlines.Line2D([], [], color='#1f77b4', linewidth=2.5, label='物流运输路径 (通畅)'),
            mlines.Line2D([], [], color='#ff9900', linewidth=4, label='抢修进行中 (T1-T3)'),
            mlines.Line2D([], [], color='#2ca02c', linewidth=2, label='已修复道路'),
            mlines.Line2D([], [], color='black', linestyle='--', label='受损/未通道路'),
            mlines.Line2D([], [], color='red', marker='*', linestyle='None', markersize=10, label='物资供应中心'),
            mlines.Line2D([], [], color='white', marker='o', markerfacecolor='#98df8a', markeredgecolor='green', markersize=10, label='需求已满足 (物资送达)'),
            mlines.Line2D([], [], color='white', marker='o', markerfacecolor='#ff9896', markeredgecolor='red', markersize=10, label='需求未满足 (孤岛)'),
        ]
        
        # 将图例放在右下角
        plt.legend(handles=legend_handles, loc='lower right', fontsize=10, framealpha=0.9, title="图例说明")

        # 标题与统计
        hour = current_time / 60
        demand_covered_val = sum(env.demands[n] for n in reachable_demands)
        total_demand_val = sum(env.demands.values())
        percent = (demand_covered_val / total_demand_val) * 100
        
        title_text = f"时刻: {hour:.0f}小时 / 72小时\n"
        title_text += f"需求覆盖率: {percent:.1f}% (已通: {len(reachable_demands)} / 总: {len(env.demands)} 个节点)"
        
        ax.set_title(title_text, fontsize=14, loc='left', fontweight='bold')
        ax.axis('off')

        plt.tight_layout()
        plt.show()
        plt.close()

FLEET_CAPACITY_PER_STEP = 1000 

def visualize_with_fleet_constraint(env, best_solution):
    """
    累积满足模式可视化：
    1. 记住已满足的节点，不再重复消耗运力。
    2. 每轮的新运力只服务由于路网扩展而新加入，或之前在排队的节点。
    """
    sub1, sub2 = best_solution
    
    sub1, sub2 = best_solution
    
    # --- 1. 预计算调度 (保持原有的简单逻辑，忽略转场) ---
    task_schedule = {} 
    team_time = {i: 0 for i in range(len(CONFIG['teams']))} 
    schedule_log = [] 

    for i, task_idx in enumerate(sub1):
        team_id = sub2[i]
        task = env.get_task_info(task_idx)
        repair_duration = task['repair']
        
        # 简单逻辑：上一任务结束就是下一任务开始 (瞬移)
        start_t = team_time[team_id]
        finish_t = start_t + repair_duration
        
        if finish_t <= CONFIG['T_total']:
            team_time[team_id] = finish_t
            info = {
                'start': start_t, 'end': finish_t, 'team': team_id + 1, 
                'u': task['u'], 'v': task['v'], 'id': task['id']
            }
            task_schedule[task['id']] = info
            schedule_log.append(info)
            
    snapshot_times = list(range(0, CONFIG['T_total'] + 1, 6 * 60))
    satisfied_history = set() 
    
    print(f"\n--- 生成演变图 (已修复T=0瞬移Bug) ---")
    
    for current_time in snapshot_times:
        plt.figure(figsize=(12, 10))
        ax = plt.gca()
        
        # A. 构建物理路网
        display_G = env.G.copy()
        repaired, working, damaged, intact = [], [], [], []
        
        for u, v, d in display_G.edges(data=True):
            status = 'intact'
            weight = d['normal_time']
            if d.get('status') == 'damaged':
                tid = d.get('task_id')
                sched = task_schedule.get(tid)
                if not sched:
                    status = 'broken'; weight = CONFIG['big_time']
                else:
                    if current_time >= sched['end']:
                        status = 'repaired'; weight = d['normal_time']
                    elif current_time >= sched['start'] and current_time < sched['end']:
                        status = 'working'; weight = CONFIG['big_time'] 
                    else:
                        status = 'broken'; weight = CONFIG['big_time']
            display_G[u][v]['weight'] = weight
            if status == 'repaired': repaired.append((u, v))
            elif status == 'working': working.append((u, v))
            elif status == 'broken': damaged.append((u, v))
            else: intact.append((u, v))

        # === B. 物流计算 (核心修复在此) ===
        active_routes = set()
        reachable_candidates = []
        
        try:
            dists, paths = nx.multi_source_dijkstra(display_G, sources=env.suppliers, weight='weight')
            for n, t in dists.items():
                # [修复点 1]：必须同时满足：
                # 1. 路通了 (t < big_time)
                # 2. 车开到了 (t <= current_time) -> 解决T=0瞬移问题
                if t < CONFIG['big_time'] and t <= current_time:
                    reachable_candidates.append(n)
        except: pass
        
        # [修复点 2]：过滤掉Supply点，解决KeyError
        pending_logistics = [n for n in reachable_candidates if n not in satisfied_history and n in env.demands]
        
        # 按距离排序分配运力
        pending_logistics.sort(key=lambda n: dists[n])
        cap = CONFIG['fleet_capacity']
        waiting = []
        
        for n in pending_logistics:
            if cap >= env.demands[n]:
                cap -= env.demands[n]
                satisfied_history.add(n)
            else:
                waiting.append(n)

        # 提取路径
        for n in satisfied_history:
            if n in paths:
                path = paths[n]
                for i in range(len(path)-1):
                    active_routes.add(tuple(sorted((path[i], path[i+1]))))

        # C. 绘图
        if intact: nx.draw_networkx_edges(display_G, POS, edgelist=intact, edge_color='#e0e0e0', width=1, ax=ax)
        if damaged: nx.draw_networkx_edges(display_G, POS, edgelist=damaged, edge_color='black', style='dashed', alpha=0.3, width=1, ax=ax)
        if working: nx.draw_networkx_edges(display_G, POS, edgelist=working, edge_color='#ff9900', width=5, alpha=1.0, ax=ax)
        if repaired: nx.draw_networkx_edges(display_G, POS, edgelist=repaired, edge_color='#2ca02c', width=2, alpha=0.5, ax=ax)
        if active_routes: nx.draw_networkx_edges(display_G, POS, edgelist=list(active_routes), edge_color='#1f77b4', width=2.5, alpha=0.5, ax=ax)

        # 节点
        green = list(satisfied_history)
        yellow = waiting
        red = [n for n in env.demands if n not in green and n not in yellow]
        
        def get_sizes(nodes): return [100 + (env.demands[n]/500)*300 for n in nodes]
        
        nx.draw_networkx_nodes(display_G, POS, nodelist=env.suppliers, node_color='red', node_shape='*', node_size=350, ax=ax, label='Supply')
        if green: nx.draw_networkx_nodes(display_G, POS, nodelist=green, node_color='#98df8a', node_size=get_sizes(green), edgecolors='green', ax=ax)
        if yellow: nx.draw_networkx_nodes(display_G, POS, nodelist=yellow, node_color='#fdbf6f', node_size=get_sizes(yellow), edgecolors='orange', linewidths=2, ax=ax)
        if red: nx.draw_networkx_nodes(display_G, POS, nodelist=red, node_color='#ff9896', node_size=get_sizes(red), edgecolors='red', ax=ax)

        # 队伍位置
        for t_info in schedule_log:
            if t_info['start'] <= current_time < t_info['end']:
                mx = (POS[t_info['u']][0] + POS[t_info['v']][0])/2
                my = (POS[t_info['u']][1] + POS[t_info['v']][1])/2
                ax.text(mx, my, f"T{t_info['team']}", fontsize=11, fontweight='bold', color='white', 
                        bbox=dict(boxstyle="round,pad=0.2", fc="#ff9900", ec="black"))

        # D. 图例
        legend = [
            mlines.Line2D([], [], color='#1f77b4', lw=2.5, label='物流路径'),
            mlines.Line2D([], [], color='#ff9900', lw=4, label='施工中'),
            mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#98df8a', markeredgecolor='green', markersize=10, label='已满足'),
            mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#fdbf6f', markeredgecolor='orange', markersize=10, label='等待运力'),
            mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#ff9896', markeredgecolor='red', markersize=10, label='未送达'),
        ]
        plt.legend(handles=legend, loc='lower right', fontsize=9)
        
        hour = current_time / 60
        sat_val = sum(env.demands[n] for n in green)
        
        title = f"时刻: {hour:.1f}h | 累计已满足: {len(green)}点 ({sat_val:.0f})"
        ax.set_title(title, fontsize=12, loc='left', fontweight='bold')
        ax.axis('off')
        plt.tight_layout()
        plt.show()
        plt.close()

# ==========================================
# 6. 主程序 (单目标逻辑)
# ==========================================

def main():
    env = Environment()
    num_tasks = len(env.task_map)
    num_teams = len(CONFIG['teams'])
    
    # 初始化种群
    pop = generate_population(num_tasks, num_teams, CONFIG['pop_size'])
    print(f"开始单目标优化 (Task Priority w/ Cost Penalty)...")
    
    history_best = []
    
    for gen in range(CONFIG['max_gen']):
        # 1. 评估所有个体
        # results: [(fitness, U, cost), ...]
        eval_results = [calculate_fitness(ind, env) for ind in pop]
        
        # 2. 组合数据以便排序: [(ind, fitness, U, cost), ...]
        combined = []
        for i in range(len(pop)):
            fit, u, cost = eval_results[i]
            combined.append({
                'chrom': pop[i],
                'fit': fit,
                'u': u,
                'cost': cost
            })
            
        # 3. 排序 (按 Fitness 从大到小)
        combined.sort(key=lambda x: x['fit'], reverse=True)
        
        # 4. 记录最佳
        best_ind = combined[0]
        history_best.append(best_ind['fit'])
        
        if gen % 10 == 0:
            print(f"Gen {gen}: Fitness={best_ind['fit']:.2e} | Performance={best_ind['u']:.2e} | Cost={best_ind['cost']}")
            
        # 5. 生成下一代
        # 提取排序后的纯染色体列表
        sorted_chroms = [item['chrom'] for item in combined]
        
        # 精英: 取前 N 个
        elites = sorted_chroms[:CONFIG['elite_size']]
        
        # 剩下用于繁殖的种群 (可以是全部，也可以是前50%)
        mating_pool = sorted_chroms[:int(CONFIG['pop_size'] * 0.6)]
        
        # 进化
        pop = genetic_ops_single_obj(mating_pool, num_teams, elites)
        
        # 补齐数量 (如果操作后数量略有偏差)
        while len(pop) < CONFIG['pop_size']:
             pop.append(generate_population(num_tasks, num_teams, 1)[0])
             
    # --- 最终结果 ---
    # 重新评估最后一代的最佳个体
    best_chrom = sorted_chroms[0]
    fit, u, cost = calculate_fitness(best_chrom, env)
    
    print(f"\n最优方案找到:")
    print(f"综合得分: {fit:.2f}")
    print(f"路网绩效: {u:.2f}")
    print(f"修复成本: {cost}")
    
    # 绘制收敛曲线
    plt.figure()
    plt.plot(history_best)
    plt.xlabel('迭代次数')
    plt.ylabel('得分')
    plt.title('迭代收敛图')
    plt.show()
    
    # 绘制路网图
    # plot_network_plan(env, best_chrom, title=f"High Efficiency Repa   ir Plan (Cost:{cost})")
    # visualize_evolution(env, best_chrom)
    # visualize_evolution_advanced(env, best_chrom)
    # visualize_step_by_step_with_legend(env, best_chrom)
    visualize_with_fleet_constraint(env, best_chrom)
if __name__ == "__main__":
    main()