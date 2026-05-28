import networkx as nx
import numpy as np
import random
import copy
import matplotlib.pyplot as plt

# ==========================================
# 第一部分：数据准备 (来源于参考文献 [61] 附录)
# ==========================================

# 1. 节点数据 (ID 1-3: 仓库, 4-38: 灾区)
# 注意：Supply/Demand 值用于加权计算绩效
NODES_DATA = {
    1: {'type': 'S', 'val': 3000}, 2: {'type': 'S', 'val': 3000}, 3: {'type': 'S', 'val': 3000},
    4: {'type': 'D', 'val': 342}, 5: {'type': 'D', 'val': 360}, 6: {'type': 'D', 'val': 322},
    7: {'type': 'D', 'val': 361}, 8: {'type': 'D', 'val': 382}, 9: {'type': 'D', 'val': 327},
    10: {'type': 'D', 'val': 361}, 11: {'type': 'D', 'val': 344}, 12: {'type': 'D', 'val': 321},
    13: {'type': 'D', 'val': 363}, 14: {'type': 'D', 'val': 344}, 15: {'type': 'D', 'val': 384},
    16: {'type': 'D', 'val': 251}, 17: {'type': 'D', 'val': 339}, 18: {'type': 'D', 'val': 358},
    19: {'type': 'D', 'val': 302}, 20: {'type': 'D', 'val': 282}, 21: {'type': 'D', 'val': 281},
    22: {'type': 'D', 'val': 205}, 23: {'type': 'D', 'val': 324}, 24: {'type': 'D', 'val': 280},
    25: {'type': 'D', 'val': 241}, 26: {'type': 'D', 'val': 382}, 27: {'type': 'D', 'val': 320},
    28: {'type': 'D', 'val': 262}, 29: {'type': 'D', 'val': 328}, 30: {'type': 'D', 'val': 320},
    31: {'type': 'D', 'val': 268}, 32: {'type': 'D', 'val': 323}, 33: {'type': 'D', 'val': 300},
    34: {'type': 'D', 'val': 282}, 35: {'type': 'D', 'val': 359}, 36: {'type': 'D', 'val': 365},
    37: {'type': 'D', 'val': 302}, 38: {'type': 'D', 'val': 403}
}

# 2. 边连接数据 (起点, 终点, 正常行驶时间min)
# 假设通行能力 Cap 均为 2000
RAW_EDGES = [
    (1,4,16), (1,11,36), (1,13,16), (1,17,28), (2,23,40), (2,21,36), (2,3,50), (3,32,52), (3,36,60),
    (4,5,22), (5,6,18), (6,7,24), (6,10,13), (7,8,34), (8,9,50), (9,10,50), (11,4,40), (11,12,64),
    (11,18,74), (13,17,24), (13,16,24), (13,14,22), (14,15,16), (16,22,42), (16,20,28), (17,19,28),
    (17,22,36), (18,25,180), (19,25,32), (20,21,56), (21,23,48), (22,24,28), (22,23,34), (23,24,16),
    (24,27,24), (24,30,64), (25,26,50), (26,28,32), (26,34,46), (26,27,20), (28,29,28), (30,31,28),
    (31,32,46), (32,33,36), (32,36,56), (33,34,60), (33,36,24), (34,35,100), (35,37,32), (36,37,56),
    (37,38,52)
]

# 3. 受损路段 (ID, 边, 修复时间min)
# 为了模拟模糊性，这里构建三角模糊数 (t*0.9, t, t*1.1)
DAMAGED_INFO = [
    {'id': 0, 'u':1, 'v':17, 't':900}, {'id': 1, 'u':4, 'v':5, 't':180}, {'id': 2, 'u':11, 'v':12, 't':270},
    {'id': 3, 'u':11, 'v':18, 't':210}, {'id': 4, 'u':13, 'v':14, 't':720}, {'id': 5, 'u':17, 'v':19, 't':1080},
    {'id': 6, 'u':17, 'v':22, 't':180}, {'id': 7, 'u':18, 'v':25, 't':270}, {'id': 8, 'u':22, 'v':24, 't':810},
    {'id': 9, 'u':24, 'v':30, 't':270}, {'id': 10, 'u':26, 'v':28, 't':720}, {'id': 11, 'u':26, 'v':34, 't':1050},
    {'id': 12, 'u':28, 'v':29, 't':360}, {'id': 13, 'u':33, 'v':34, 't':180}, {'id': 14, 'u':34, 'v':35, 't':450},
    {'id': 15, 'u':36, 'v':37, 't':330}
]

# 4. 配置参数
CONFIG = {
    'T_total': 72 * 60,     # 总时长 (分钟) = 72小时
    'eta': 6 * 60,          # 决策更新步长 (分钟) = 8小时
    'num_teams': 5,         # 假设有5支抢修队 (分布在3个仓库)
    'repair_cost_factor': 100, # 单位时间修复成本系数
    'big_time': 10000,      # 路断时的惩罚时间
    'pop_size': 1000,         # 种群大小
    'max_gen': 100          # 迭代代数
}

# ==========================================
# 第二部分：基础类与工具函数
# ==========================================

class FuzzyNumber:
    def __init__(self, val):
        self.a = val * 0.9
        self.b = val
        self.c = val * 1.1
    def expected(self):
        return (self.a + 2*self.b + self.c) / 4

class Environment:
    def __init__(self):
        self.G = nx.Graph()
        self._init_graph()
        self.suppliers = [k for k, v in NODES_DATA.items() if v['type']=='S']
        self.demands = [k for k, v in NODES_DATA.items() if v['type']=='D']
        self.damaged_tasks = []
        self._init_damage()

    def _init_graph(self):
        for u, v, t in RAW_EDGES:
            self.G.add_edge(u, v, weight=t, status='intact', capacity=2000)
    
    def _init_damage(self):
        for item in DAMAGED_INFO:
            u, v = item['u'], item['v']
            if self.G.has_edge(u, v):
                self.G[u][v]['status'] = 'damaged'
                # 存储模糊数对象
                self.G[u][v]['repair_obj'] = FuzzyNumber(item['t'])
                self.G[u][v]['damage_id'] = item['id']
                self.damaged_tasks.append(item['id'])

    def get_repair_time(self, damage_id):
        # 查找对应边的维修时间(去模糊化)
        for u, v, data in self.G.edges(data=True):
            if data.get('damage_id') == damage_id:
                return data['repair_obj'].expected()
        return 0

# ==========================================
# 第三部分：核心解码与评估函数 (最关键！)
# ==========================================

def evaluate_solution(chromosome, env):
    """
    输入: 染色体 (Sub1: 任务顺序, Sub2: 队伍分配)
    输出: (obj1: -抢修绩效, obj2: 修复成本) -> NSGA-II 默认求最小化
    """
    sub1, sub2 = chromosome # sub1是任务ID排列, sub2是对应的队伍ID
    
    # --- 1. 计算修复时间表 (Schedule) ---
    team_free_time = {i: 0 for i in range(CONFIG['num_teams'])} # 记录每个队伍的空闲时间
    repair_schedule = {} # {damage_id: finish_time}
    
    # 记录实际产生的修复成本（只计算修了的路）
    total_repair_cost = 0
    
    for i, task_id in enumerate(sub1):
        team_id = sub2[i]
        cost_time = env.get_repair_time(task_id)
        
        # 任务开始时间 = 队伍空闲时间 (简化：忽略队伍路途移动时间，假设瞬移)
        start_time = team_free_time[team_id]
        finish_time = start_time + cost_time
        
        # 核心逻辑：只修能在 T_total 内修完的路
        # 这就是“引导模型选择部分修复”的关键！
        if finish_time <= CONFIG['T_total']:
            team_free_time[team_id] = finish_time
            repair_schedule[task_id] = finish_time
            
            # 累加成本 (目标2)
            total_repair_cost += cost_time * CONFIG['repair_cost_factor']
        else:
            # 时间不够了，这个任务被放弃，不产生成本，但也贡献不了绩效
            pass

    # --- 2. 计算抢修绩效 U (目标1) ---
    # 公式：Sum ( Demand * Delta_Time * Remaining_Time )
    cumulative_performance = 0
    
    # 预计算基准：所有路都断的时候的OD时间
    # 为了速度，我们只在时间步更新时计算
    
    steps = int(CONFIG['T_total'] / CONFIG['eta'])
    
    # 缓存上一阶段的OD时间，用于计算 Delta T
    # 初始状态：路全是断的
    current_G = env.G.copy()
    for u, v, data in current_G.edges(data=True):
        if data.get('status') == 'damaged':
            current_G[u][v]['weight'] = CONFIG['big_time']
    
    # 计算初始OD矩阵
    prev_od_times = {}
    for s in env.suppliers:
        try:
            prev_od_times[s] = nx.single_source_dijkstra_path_length(current_G, s, weight='weight')
        except:
            prev_od_times[s] = {}

    # 按时间步推演
    for step in range(1, steps + 1):
        sim_time = step * CONFIG['eta'] # 当前时刻，如 8h, 16h...
        
        # A. 更新路网
        step_G = env.G.copy()
        for u, v, data in step_G.edges(data=True):
            if data.get('status') == 'damaged':
                dmg_id = data.get('damage_id')
                # 如果这会儿还没修好(或被放弃了)，设为断路
                if repair_schedule.get(dmg_id, 99999) > sim_time:
                    step_G[u][v]['weight'] = CONFIG['big_time']
                else:
                    # 修好了，weight保持原值(正常通行时间)
                    pass
        
        # B. 计算当前OD时间
        curr_od_times = {}
        for s in env.suppliers:
            try:
                curr_od_times[s] = nx.single_source_dijkstra_path_length(step_G, s, weight='weight')
            except:
                curr_od_times[s] = {}
        
        # C. 累加绩效
        benefit_duration = CONFIG['T_total'] - sim_time # 剩余受益时间
        
        step_u = 0
        for s in env.suppliers:
            for d in env.demands:
                demand_val = NODES_DATA[d]['val']
                
                t_old = prev_od_times[s].get(d, CONFIG['big_time'])
                t_new = curr_od_times[s].get(d, CONFIG['big_time'])
                
                delta_t = t_old - t_new
                
                # 只有路通了(t_new < big)且时间缩短了才算分
                if delta_t > 0 and t_new < CONFIG['big_time']:
                    step_u += demand_val * delta_t * benefit_duration
        
        cumulative_performance += step_u
        
        # 更新基准
        prev_od_times = curr_od_times

    # 返回两个目标
    # Obj1: -绩效 (求最小化，负负得正)
    # Obj2: 成本 (求最小化)
    return (-cumulative_performance, total_repair_cost)

# ==========================================
# 第四部分：NSGA-II 算法逻辑
# ==========================================

def fast_non_dominated_sort(values):
    """ 快速非支配排序 """
    S = [[] for _ in range(len(values))]
    n = [0] * len(values)
    rank = [0] * len(values)
    fronts = [[]]

    for p in range(len(values)):
        for q in range(len(values)):
            # p dominates q? (Minimization)
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
    return fronts[:-1] # Remove empty last front

def crowding_distance(values, front):
    """ 拥挤度距离计算 """
    distance = {i: 0 for i in front}
    l = len(front)
    for m in range(2): # 2 objectives
        # Sort by objective m
        sorted_front = sorted(front, key=lambda x: values[x][m])
        distance[sorted_front[0]] = float('inf')
        distance[sorted_front[-1]] = float('inf')
        
        obj_range = values[sorted_front[-1]][m] - values[sorted_front[0]][m]
        if obj_range == 0: obj_range = 1.0
        
        for i in range(1, l-1):
            distance[sorted_front[i]] += (values[sorted_front[i+1]][m] - values[sorted_front[i-1]][m]) / obj_range
    return distance

def create_individual(num_tasks, num_teams):
    # Sub1: 任务顺序 (排列)
    sub1 = list(range(num_tasks))
    random.shuffle(sub1)
    # Sub2: 队伍分配 (0 ~ num_teams-1)
    sub2 = [random.randint(0, num_teams-1) for _ in range(num_tasks)]
    return [sub1, sub2]

def crossover(p1, p2):
    # Sub1: PMX (Partial Mapped Crossover) - 简化版: 保持片段
    size = len(p1[0])
    cxpoint1 = random.randint(0, size - 2)
    cxpoint2 = random.randint(cxpoint1 + 1, size - 1)
    
    c1_sub1 = [-1] * size
    c2_sub1 = [-1] * size
    
    # Copy slice
    c1_sub1[cxpoint1:cxpoint2] = p1[0][cxpoint1:cxpoint2]
    c2_sub1[cxpoint1:cxpoint2] = p2[0][cxpoint1:cxpoint2]
    
    # Fill remaining (simple logic)
    def fill(child, parent):
        p_idx = 0
        for i in range(size):
            if child[i] == -1:
                while parent[p_idx] in child:
                    p_idx += 1
                child[i] = parent[p_idx]
        return child
        
    c1_sub1 = fill(c1_sub1, p2[0])
    c2_sub1 = fill(c2_sub1, p1[0])
    
    # Sub2: Uniform Crossover
    c1_sub2, c2_sub2 = [], []
    for i in range(size):
        if random.random() < 0.5:
            c1_sub2.append(p1[1][i])
            c2_sub2.append(p2[1][i])
        else:
            c1_sub2.append(p2[1][i])
            c2_sub2.append(p1[1][i])
            
    return [c1_sub1, c1_sub2], [c2_sub1, c2_sub2]

def mutate(ind, num_teams):
    # Swap mutation for order
    if random.random() < 0.2:
        idx1, idx2 = random.sample(range(len(ind[0])), 2)
        ind[0][idx1], ind[0][idx2] = ind[0][idx2], ind[0][idx1]
    
    # Point mutation for team
    if random.random() < 0.2:
        idx = random.randint(0, len(ind[1])-1)
        ind[1][idx] = random.randint(0, num_teams-1)
    return ind

# ==========================================
# 第五部分：主程序执行
# ==========================================

def run_optimization():
    env = Environment()
    num_tasks = len(env.damaged_tasks)
    
    # 1. 初始化种群
    population = [create_individual(num_tasks, CONFIG['num_teams']) for _ in range(CONFIG['pop_size'])]
    
    print(f"开始优化: 种群{CONFIG['pop_size']}, 代数{CONFIG['max_gen']}, 受损点{num_tasks}个")
    print("-" * 50)
    
    for gen in range(CONFIG['max_gen']):
        # 评估
        obj_values = [evaluate_solution(ind, env) for ind in population]
        
        # 非支配排序
        fronts = fast_non_dominated_sort(obj_values)
        
        # 打印进度
        if gen % 10 == 0:
            best_U = -min([v[0] for v in obj_values]) # 取最大绩效
            min_Cost = min([v[1] for v in obj_values])
            print(f"Gen {gen}: Max绩效={best_U/1e6:.2f}M, Min成本={min_Cost}")
            
        # 选择下一代 (Elitism)
        new_pop = []
        for front in fronts:
            if len(new_pop) + len(front) <= CONFIG['pop_size']:
                # 整个层级保留
                for idx in front:
                    new_pop.append(population[idx])
            else:
                # 拥挤度筛选
                dist = crowding_distance(obj_values, front)
                sorted_front = sorted(front, key=lambda x: dist[x], reverse=True)
                needed = CONFIG['pop_size'] - len(new_pop)
                for i in range(needed):
                    new_pop.append(population[sorted_front[i]])
                break
        
        # 繁衍 (锦标赛选择 + 交叉变异)
        mating_pool = new_pop # 简单处理：精英保留后直接作为父母
        offspring = []
        while len(offspring) < CONFIG['pop_size']:
            p1, p2 = random.sample(mating_pool, 2)
            c1, c2 = crossover(p1, p2)
            offspring.append(mutate(c1, CONFIG['num_teams']))
            offspring.append(mutate(c2, CONFIG['num_teams']))
            
        population = offspring # 替换 (标准NSGA-II应合并父子代，此处简化为代际替换)

    # --- 结果展示 ---
    final_objs = [evaluate_solution(ind, env) for ind in population]
    plot_pareto_advanced(final_objs)
    # 取反绩效以便绘图 (变成正值)
    plot_x = [v[1] for v in final_objs] # Cost
    plot_y = [-v[0] for v in final_objs] # Performance
    
    plt.figure(figsize=(10, 6))
    plt.scatter(plot_x, plot_y, c='blue', alpha=0.6)
    plt.xlabel('Repair Cost (Lower is better)')
    plt.ylabel('Repair Performance U (Higher is better)')
    plt.title('Pareto Front: Repair Performance vs. Cost')
    plt.grid(True)
    plt.show()
    
    # 打印几个典型解
    print("\n====== 典型Pareto解 (建议方案) ======")
    # 按成本排序
    best_perf_idx = np.argmin([v[0][0] for v in zip(final_objs, population)]) # 绩效是负的，取最小就是最大
    best_sol = population[best_perf_idx]

    # 取一个为了修完而修完的笨解 (按成本排序后的最后一个)
    sorted_sols = sorted(zip(plot_x, plot_y, population), key=lambda x: x[0])
    worst_full_sol = sorted_sols[-1][2]
    
    # 绘制甘特图对比
    plot_gantt_comparison(env, best_sol, worst_full_sol)
    
    # 3. 绘制最佳方案的路网图
    plot_network_status(env, best_sol)
        
def plot_gantt_comparison(env, sol_best, sol_other):
    """
    绘制两个方案的甘特图对比 (对比优化后的调度和全修方案)
    """
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    titles = ["Optimized Schedule (Best Performance)", "Comparison Schedule (Higher Cost/Random)"]
    sols = [sol_best, sol_other]

    for i, ax in enumerate(axes):
        sub1, sub2 = sols[i]
        team_free_time = {t: 0 for t in range(CONFIG['num_teams'])}
        
        # 解码并绘图
        for idx, task_id in enumerate(sub1):
            team_id = sub2[idx]
            duration = env.get_repair_time(task_id)
            start = team_free_time[team_id]
            
            if start + duration <= CONFIG['T_total']:
                # 绘制任务条
                color = 'tab:green' if i == 0 else 'tab:gray'
                ax.broken_barh([(start, duration)], (team_id - 0.4, 0.8), 
                              facecolors=color, edgecolors='black', alpha=0.8)
                # 标注任务ID
                ax.text(start + duration/2, team_id, f"{task_id}", 
                        ha='center', va='center', color='white', fontsize=8)
                team_free_time[team_id] += duration
        
        ax.set_ylabel('Team ID')
        ax.set_title(titles[i])
        ax.set_yticks(range(CONFIG['num_teams']))
        ax.grid(True, axis='x', linestyle=':', alpha=0.6)
        ax.set_xlim(0, CONFIG['T_total'])

    plt.xlabel('Time (minutes)')
    plt.tight_layout()
    plt.show()

def plot_pareto_advanced(final_objs):
    """
    绘制带有标注的帕累托前沿图
    """
    # 数据准备
    costs = [v[1] / 10000 for v in final_objs]  # 换算成“万元”
    perfs = [-v[0] / 1e11 for v in final_objs]  # 换算成 10^11 量级，取正
    
    plt.figure(figsize=(10, 6))
    plt.style.use('seaborn-v0_8-whitegrid') # 使用学术风格背景
    
    # 绘制散点
    scatter = plt.scatter(costs, perfs, c=perfs, cmap='viridis', s=80, alpha=0.8, edgecolors='grey')
    plt.colorbar(scatter, label='Performance Score')
    
    # 找出关键点
    # 1. 最高绩效点
    max_p_idx = np.argmax(perfs)
    # 2. 最低成本点
    min_c_idx = np.argmin(costs)
    # 3. 甜点 (假设在中间某处，这里简单取绩效前3中成本最低的)
    top_3_perf = sorted(range(len(perfs)), key=lambda i: perfs[i], reverse=True)[:3]
    sweet_idx = sorted(top_3_perf, key=lambda i: costs[i])[0]

    # 添加标注 (Annotations)
    points = [
        (min_c_idx, "Conservative\n(Partial Repair)", 'red'),
        (max_p_idx, "Aggressive\n(Full Repair)", 'green'),
        (sweet_idx, "Sweet Spot\n(High Efficiency)", 'orange')
    ]
    
    for idx, label, color in points:
        x, y = costs[idx], perfs[idx]
        plt.scatter([x], [y], color=color, s=150, zorder=10, marker='*')
        plt.annotate(label, (x, y), xytext=(x+2, y-0.3),
                     arrowprops=dict(facecolor='black', arrowstyle='->'),
                     fontsize=10, fontweight='bold')

    plt.xlabel('Repair Cost (10k RMB)', fontsize=12)
    plt.ylabel('Performance U (x1e11)', fontsize=12)
    plt.title('Trade-off: Cost vs. Rescue Performance', fontsize=14)
    plt.tight_layout()
    plt.show()
    
def plot_network_status(env, solution):
    """
    绘制最终的路网修复状态
    """
    # 1. 解码找出修了哪些路
    repaired_ids = []
    sub1, sub2 = solution
    tf = {t:0 for t in range(CONFIG['num_teams'])}
    for idx, task_id in enumerate(sub1):
        team = sub2[idx]
        t = env.get_repair_time(task_id)
        if tf[team] + t <= CONFIG['T_total']:
            tf[team] += t
            repaired_ids.append(task_id)
            
    # 2. 绘图设置
    plt.figure(figsize=(10, 8))
    pos = nx.spring_layout(env.G, seed=42) # 固定种子保证每次图形状一样
    
    # 绘制节点
    # 仓库(Supply)
    nx.draw_networkx_nodes(env.G, pos, nodelist=env.suppliers, node_color='red', node_shape='^', node_size=150, label='Depot')
    # 灾区(Demand)
    nx.draw_networkx_nodes(env.G, pos, nodelist=env.demands, node_color='skyblue', node_size=100, label='Demand')
    
    # 绘制边
    # 正常路段
    intact_edges = [(u, v) for u, v, d in env.G.edges(data=True) if d.get('status') != 'damaged']
    nx.draw_networkx_edges(env.G, pos, edgelist=intact_edges, edge_color='grey', alpha=0.3)
    
    # 已修复路段 (Green)
    repaired_edges = []
    broken_edges = []
    for u, v, d in env.G.edges(data=True):
        if d.get('status') == 'damaged':
            if d.get('damage_id') in repaired_ids:
                repaired_edges.append((u, v))
            else:
                broken_edges.append((u, v))
                
    nx.draw_networkx_edges(env.G, pos, edgelist=repaired_edges, edge_color='green', width=2.5, label='Repaired')
    nx.draw_networkx_edges(env.G, pos, edgelist=broken_edges, edge_color='black', style='dashed', width=2, label='Abandoned')
    
    # 标签
    nx.draw_networkx_labels(env.G, pos, font_size=8)
    
    plt.title(f"Final Network Status: {len(repaired_edges)} Repaired, {len(broken_edges)} Abandoned")
    plt.legend()
    plt.axis('off')
    plt.show()

if __name__ == "__main__":
    run_optimization()