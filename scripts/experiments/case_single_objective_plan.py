import networkx as nx
import numpy as np
import random
import copy
import matplotlib.pyplot as plt
import math

# ==========================================
# 1. 数据配置 (User Provided Data)
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

# 基础路网连接 (u, v, travel_time, _) - 第4个参数在raw_edges里有些是0有些是时间，我们将统一处理
# 注意：这里我们主要用前3个参数构建全图
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

# 受损任务详情 (u, v, travel_time, repair_time, task_id)
# 这些是必须修的路，修好前 travel_time 为无穷大
DAMAGED_TASKS = [
    {'u': 1, 'v': 4, 'travel': 16, 'repair': 900, 'id': 1},
    {'u': 13, 'v': 14, 'travel': 22, 'repair': 180, 'id': 2},
    {'u': 28, 'v': 29, 'travel': 28, 'repair': 270, 'id': 3},
    {'u': 30, 'v': 31, 'travel': 28, 'repair': 210, 'id': 4},
    {'u': 34, 'v': 35, 'travel': 100, 'repair': 720, 'id': 5},
    {'u': 19, 'v': 25, 'travel': 32, 'repair': 1080, 'id': 6},
    {'u': 17, 'v': 22, 'travel': 36, 'repair': 180, 'id': 7},
    {'u': 25, 'v': 26, 'travel': 50, 'repair': 270, 'id': 8},
    {'u': 24, 'v': 27, 'travel': 24, 'repair': 810, 'id': 9},
    {'u': 24, 'v': 30, 'travel': 64, 'repair': 270, 'id': 10},
    {'u': 26, 'v': 27, 'travel': 20, 'repair': 720, 'id': 11},
    {'u': 26, 'v': 34, 'travel': 46, 'repair': 1050, 'id': 12},
    {'u': 26, 'v': 28, 'travel': 32, 'repair': 360, 'id': 13},
    {'u': 33, 'v': 34, 'travel': 60, 'repair': 180, 'id': 14},
    {'u': 35, 'v': 37, 'travel': 32, 'repair': 450, 'id': 15},
    {'u': 36, 'v': 37, 'travel': 56, 'repair': 330, 'id': 16},
]

# 算法全局参数
CONFIG = {
    'T_total': 72 * 60,        # 总工期 (分钟) = 72小时
    'eta': 4 * 60,             # 决策时间步长 (分钟) = 4小时，步长越小精度越高
    'teams': [1, 2, 3],        # 抢修队分布: 3支队伍，分别位于节点1, 2, 3
    'repair_cost_factor': 100, # 修复成本系数
    'big_time': 99999,         # 断路惩罚时间
    'pop_size': 50,
    'max_gen': 80,
    'w_p': 1.0                 # 绩效权重
}

# ==========================================
# 2. 环境与图构建 (Environment)
# ==========================================

class Environment:
    def __init__(self):
        self.G = nx.Graph()
        self.suppliers = []
        self.demands = {} # {id: value}
        self.task_map = {} # {task_index: task_dict}
        self.init_data()
        
    def init_data(self):
        # 1. 节点初始化
        for nid, name, ntype, val in RAW_NODES:
            self.G.add_node(nid, name=name, type=ntype, val=val)
            if ntype == 'supply':
                self.suppliers.append(nid)
            elif ntype == 'demand':
                self.demands[nid] = val
                
        # 2. 边初始化 (先加所有边为 Intact)
        for u, v, t in RAW_EDGES:
            # weight: 正常通行时间
            self.G.add_edge(u, v, weight=t, status='intact', normal_time=t)
            
        # 3. 标记受损边 (Damaged)
        for task in DAMAGED_TASKS:
            u, v = task['u'], task['v']
            # 如果边存在，更新属性
            if self.G.has_edge(u, v):
                self.G[u][v]['status'] = 'damaged'
                self.G[u][v]['repair_time'] = task['repair']
                self.G[u][v]['task_id'] = task['id']
                self.G[u][v]['weight'] = CONFIG['big_time'] # 初始状态：断路
            else:
                # 如果raw_edges里漏了，补上
                self.G.add_edge(u, v, weight=CONFIG['big_time'], status='damaged', 
                                normal_time=task['travel'], repair_time=task['repair'], 
                                task_id=task['id'])
            
            # 建立索引: 染色体基因(0-15) -> 任务详情
            # task['id'] 是 1-16，转成 0-15 索引
            self.task_map[task['id'] - 1] = task

    def get_task_info(self, idx):
        return self.task_map[idx]

# ==========================================
# 3. 核心评估逻辑 (Objectives Calculation)
# ==========================================

def calculate_objectives(chromosome, env):
    """
    输入: 染色体 [任务顺序, 队伍分配]
    输出: (-抢修绩效U, 修复成本Cost) -> NSGA-II 默认最小化
    """
    sub1, sub2 = chromosome
    num_tasks = len(env.task_map)
    
    # --- A. 模拟修路过程 (Scheduling) ---
    # 队伍状态: {team_idx: free_time}
    team_time = {i: 0 for i in range(len(CONFIG['teams']))} 
    repair_schedule = {} # {task_id: finish_time}
    
    actual_repair_cost = 0 # 目标2
    
    for i in range(num_tasks):
        task_idx = sub1[i]      # 任务索引 0-15
        team_idx = sub2[i]      # 队伍索引 0-2 (对应供应点1,2,3)
        
        task_info = env.get_task_info(task_idx)
        repair_t = task_info['repair']
        
        # 任务开始 = 队伍空闲
        # (此处简化: 忽略队伍从驻地赶往现场的路上时间，假设瞬移或包含在repair中)
        start_t = team_time[team_idx]
        finish_t = start_t + repair_t
        
        # 核心引导机制：只有在 72小时内能修完的才修
        if finish_t <= CONFIG['T_total']:
            team_time[team_idx] = finish_t
            repair_schedule[task_info['id']] = finish_t
            actual_repair_cost += repair_t * CONFIG['repair_cost_factor']
        else:
            # 超过时间的任务被放弃 (成本为0，但也贡献不了绩效)
            pass
            
    # --- B. 计算抢修绩效 U (目标1) ---
    # U = Sum [ (Q * W) * Delta_T * Remaining_Time ]
    
    cumulative_U = 0
    steps = int(CONFIG['T_total'] / CONFIG['eta'])
    
    # 初始路网状态 (全断)
    current_G = env.G.copy()
    # 确保 damaged 边是断的
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
                # 如果已修好
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
                
                # 限制最大时间，防止溢出
                if t_old > CONFIG['big_time']: t_old = CONFIG['big_time']
                if t_new > CONFIG['big_time']: t_new = CONFIG['big_time']
                
                delta_t = t_old - t_new
                
                # 只有路通了(小于big_time)且时间优化了才算分
                if delta_t > 0 and t_new < CONFIG['big_time']:
                    # 距离/时间越短，可达性越好。这里简化为时间缩短量 * 需求量
                    step_gain += demand_val * delta_t * remaining_time
        
        cumulative_U += step_gain
        prev_od = curr_od # 迭代
        
    return (-cumulative_U, actual_repair_cost) # NSGA-II 最小化

# ==========================================
# 4. NSGA-II 算法引擎
# ==========================================

def fast_non_dominated_sort(values):
    S = [[] for _ in range(len(values))]
    n = [0] * len(values)
    rank = [0] * len(values)
    fronts = [[]]

    for p in range(len(values)):
        for q in range(len(values)):
            if (values[p][0] <= values[q][0] and values[p][1] <= values[q][1]) and \
               (values[p][0] < values[q][0] or values[p][1] < values[q][1]):
                S[p].append(q)
            elif (values[q][0] <= values[p][0] and values[q][1] <= values[p][1]) and \
                 (values[q][0] < values[p][0] or values[q][1] < values[p][1]):
                n[p] += 1
        if n[p] == 0:
            rank[p] = 0
            fronts[0].append(p)
    i = 0
    while fronts[i]:
        next_front = []
        for p in fronts[i]:
            for q in S[p]:
                n[q] -= 1
                if n[q] == 0:
                    rank[q] = i + 1
                    next_front.append(q)
        i += 1
        fronts.append(next_front)
    return fronts[:-1]

def crowding_distance(values, front):
    distance = {i: 0 for i in front}
    for m in range(2):
        sorted_front = sorted(front, key=lambda x: values[x][m])
        distance[sorted_front[0]] = float('inf')
        distance[sorted_front[-1]] = float('inf')
        r = values[sorted_front[-1]][m] - values[sorted_front[0]][m]
        if r == 0: r = 1.0
        for i in range(1, len(front)-1):
            distance[sorted_front[i]] += (values[sorted_front[i+1]][m] - values[sorted_front[i-1]][m]) / r
    return distance

def generate_population(n_tasks, n_teams, size):
    pop = []
    for _ in range(size):
        sub1 = list(range(n_tasks))
        random.shuffle(sub1)
        sub2 = [random.randint(0, n_teams-1) for _ in range(n_tasks)]
        pop.append([sub1, sub2])
    return pop

def genetic_ops(population, num_teams):
    # 锦标赛选择 + 交叉 + 变异
    new_pop = []
    pop_len = len(population)
    while len(new_pop) < pop_len:
        # 简单随机选择
        p1, p2 = random.sample(population, 2)
        
        # 交叉 (单点交叉模拟)
        pt = random.randint(1, len(p1[0])-1)
        c1_s1 = p1[0][:pt] + [x for x in p2[0] if x not in p1[0][:pt]]
        c2_s1 = p2[0][:pt] + [x for x in p1[0] if x not in p2[0][:pt]]
        c1_s2 = p1[1][:pt] + p2[1][pt:]
        c2_s2 = p2[1][:pt] + p1[1][pt:]
        
        # 变异
        if random.random() < 0.1:
            i, j = random.sample(range(len(c1_s1)), 2)
            c1_s1[i], c1_s1[j] = c1_s1[j], c1_s1[i]
            c1_s2[i] = random.randint(0, num_teams-1)
            
        new_pop.extend([[c1_s1, c1_s2], [c2_s1, c2_s2]])
        
    return new_pop[:pop_len]

# ==========================================
# 5. 可视化函数
# ==========================================

def plot_network_plan(env, solution, title="Optimal Repair Plan"):
    sub1, sub2 = solution
    
    # 解码得到哪些路修了
    repaired_edges = []
    team_time = {i: 0 for i in range(len(CONFIG['teams']))}
    
    for i, task_idx in enumerate(sub1):
        team_id = sub2[i]
        task = env.get_task_info(task_idx)
        fin = team_time[team_id] + task['repair']
        if fin <= CONFIG['T_total']:
            team_time[team_id] = fin
            repaired_edges.append((task['u'], task['v']))
            
    plt.figure(figsize=(12, 10))
    
    # 1. 画所有点
    nx.draw_networkx_nodes(env.G, POS, node_size=300, node_color='lightgray')
    
    # 2. 画特定点 (Supply)
    nx.draw_networkx_nodes(env.G, POS, nodelist=env.suppliers, node_size=500, node_color='red', label='Supply')
    
    # 3. 画所有边 (底图)
    nx.draw_networkx_edges(env.G, POS, edge_color='gray', alpha=0.3)
    
    # 4. 画受损未修的边 (虚线)
    damaged_uv = [(t['u'], t['v']) for t in DAMAGED_TASKS]
    unrepaired = [e for e in damaged_uv if e not in repaired_edges and (e[1], e[0]) not in repaired_edges]
    nx.draw_networkx_edges(env.G, POS, edgelist=unrepaired, edge_color='black', style='dashed', width=2, label='Unrepaired')
    
    # 5. 画已修复的边 (绿色实线)
    nx.draw_networkx_edges(env.G, POS, edgelist=repaired_edges, edge_color='green', width=3, label='Repaired')
    
    # 6. 标签
    labels = {n: f"{n}" for n in env.G.nodes()}
    nx.draw_networkx_labels(env.G, POS, labels=labels, font_size=8)
    
    plt.title(title)
    plt.legend()
    plt.axis('off')
    plt.show()

# ==========================================
# 6. 主程序
# ==========================================

def main():
    env = Environment()
    num_tasks = len(env.task_map)
    num_teams = len(CONFIG['teams'])
    
    # 初始化
    pop = generate_population(num_tasks, num_teams, CONFIG['pop_size'])
    print(f"开始优化... (Tasks: {num_tasks}, Teams: {num_teams})")
    
    for gen in range(CONFIG['max_gen']):
        # 评估
        objs = [calculate_objectives(ind, env) for ind in pop]
        
        # 排序
        fronts = fast_non_dominated_sort(objs)
        
        # 简单打印
        if gen % 10 == 0:
            best_perf = -min(o[0] for o in objs)
            min_cost = min(o[1] for o in objs)
            print(f"Gen {gen}: Best Performance U={best_perf/1e7:.2f}e7, Min Cost={min_cost}")
            
        # 精英保留 & 生成新种群
        next_pop = []
        for front in fronts:
            if len(next_pop) + len(front) <= CONFIG['pop_size']:
                for idx in front: next_pop.append(pop[idx])
            else:
                dists = crowding_distance(objs, front)
                sorted_front = sorted(front, key=lambda i: dists[i], reverse=True)
                for i in range(CONFIG['pop_size'] - len(next_pop)):
                    next_pop.append(pop[sorted_front[i]])
                break
        
        pop = genetic_ops(next_pop, num_teams)
        
    # --- 结果分析 ---
    final_objs = [calculate_objectives(ind, env) for ind in pop]
    x_cost = [o[1] for o in final_objs]
    y_perf = [-o[0] for o in final_objs]
    
    # 1. 绘制 Pareto 前沿
    plt.figure(figsize=(8, 6))
    plt.scatter(x_cost, y_perf, c='blue')
    plt.xlabel('Repair Cost (Minimize)')
    plt.ylabel('Performance U (Maximize)')
    plt.title('Pareto Front: Cost vs Performance')
    plt.grid(True)
    plt.show()
    
    # 2. 选一个“高性价比”方案展示 (中间位置)
    # 排序：按成本
    zipped = sorted(zip(x_cost, y_perf, pop), key=lambda x: x[0])
    mid_idx = len(zipped) // 2
    best_sol = zipped[mid_idx][2]
    
    print(f"\n展示推荐方案 (平衡点):")
    print(f"成本: {zipped[mid_idx][0]}, 绩效: {zipped[mid_idx][1]:.2e}")
    plot_network_plan(env, best_sol, title="Balanced Restoration Plan")

if __name__ == "__main__":
    main()