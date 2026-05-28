import networkx as nx
import numpy as np
import random
import copy
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import math

# ==========================================
# 1. 数据配置
# ==========================================

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

# 正常通行时间 (weight)
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

CONFIG = {
    'T_total': 72 * 60,        # 总工期
    'eta': 4 * 60,             # 决策步长
    'teams': [1, 2, 3],        # 抢修队初始位置
    'big_time': 99999,         
    'pop_size': 50,
    'max_gen': 60,
    'elite_size': 4,
    'repair_cost_factor': 1,
    'cost_penalty_alpha': 2.0,
    
    # 运力参数
    'fleet_capacity': 1000     # 每6小时运力上限
}

# ==========================================
# 2. Environment
# ==========================================

class Environment:
    def __init__(self):
        self.G = nx.Graph()
        self.suppliers = []
        self.demands = {} 
        self.task_map = {} 
        self.init_data()
        
        # [关键] 预计算距离矩阵：用于计算"赶路时间"
        # 假设抢修队通过基础路网行进
        self.dist_matrix = dict(nx.all_pairs_dijkstra_path_length(self.G, weight='normal_time'))

    def init_data(self):
        for nid, name, ntype, val in RAW_NODES:
            self.G.add_node(nid, name=name, type=ntype, val=val)
            if ntype == 'supply': self.suppliers.append(nid)
            elif ntype == 'demand': self.demands[nid] = val
        
        for u, v, t in RAW_EDGES:
            self.G.add_edge(u, v, weight=t, status='intact', normal_time=t)
            
        for task in DAMAGED_TASKS:
            u, v = task['u'], task['v']
            # 更新边为 damaged
            if self.G.has_edge(u, v):
                self.G[u][v].update({'status': 'damaged', 'repair_time': task['repair'], 
                                     'task_id': task['id'], 'weight': CONFIG['big_time']})
            else:
                self.G.add_edge(u, v, weight=CONFIG['big_time'], status='damaged', 
                                normal_time=task['travel'], repair_time=task['repair'], 
                                task_id=task['id'])
            self.task_map[task['id'] - 1] = task

    def get_distance(self, u, v):
        """查询两点间赶路时间"""
        if u == v: return 0
        try: return self.dist_matrix[u][v]
        except: return 99999

    def get_task_info(self, idx):
        return self.task_map[idx]

# ==========================================
# 3. Fitness 计算 (解决瞬移：加入 Travel Time)
# ==========================================

def calculate_fitness(chromosome, env):
    sub1, sub2 = chromosome
    
    # 1. 任务分组
    team_tasks = {i: [] for i in range(len(CONFIG['teams']))}
    for i, task_idx in enumerate(sub1):
        if 0 <= task_idx < len(env.task_map):
            team_tasks[sub2[i]].append(env.get_task_info(task_idx))
        
    team_time = {i: 0 for i in range(len(CONFIG['teams']))} 
    team_loc = {i: CONFIG['teams'][i] for i in range(len(CONFIG['teams']))} # 初始在供应点
    
    repair_schedule = {} 
    actual_repair_cost = 0 
    
    # 2. 模拟【连续】施工 (自动找最近 + 计算赶路时间)
    for team_id in range(len(CONFIG['teams'])):
        pending_tasks = team_tasks[team_id]
        
        while pending_tasks:
            curr_loc = team_loc[team_id]
            
            # 贪婪策略：找离当前位置最近的任务端点
            best_task = None
            min_dist = float('inf')
            target_node = None # 决定去 u 端还是 v 端
            
            for task in pending_tasks:
                du = env.get_distance(curr_loc, task['u'])
                dv = env.get_distance(curr_loc, task['v'])
                
                if du < min_dist: min_dist = du; best_task = task; target_node = task['u']
                if dv < min_dist: min_dist = dv; best_task = task; target_node = task['v']
            
            # 如果没有可行任务
            if best_task is None: break

            # [关键] 计算时间
            travel_time = min_dist                # 赶路耗时 (不再是0!)
            repair_duration = best_task['repair'] # 维修耗时
            
            start_travel = team_time[team_id]
            start_repair = start_travel + travel_time
            finish_repair = start_repair + repair_duration
            
            # 只有不超时才执行
            if finish_repair <= CONFIG['T_total']:
                team_time[team_id] = finish_repair
                # 更新位置到任务的另一端 (因为修路是从一端修到另一端)
                team_loc[team_id] = best_task['v'] if target_node == best_task['u'] else best_task['u']
                
                repair_schedule[best_task['id']] = finish_repair
                actual_repair_cost += repair_duration * CONFIG['repair_cost_factor']
                # 赶路也有成本 (可选)
                actual_repair_cost += travel_time * 0.1
            else:
                # 超时，后面的任务也来不及了(因为按距离排的)
                break
                
            pending_tasks.remove(best_task)

    # 3. 计算绩效 U (累积可达性)
    cumulative_U = 0
    steps = int(CONFIG['T_total'] / CONFIG['eta'])
    
    current_G = env.G.copy()
    for u, v, d in current_G.edges(data=True):
        if d.get('status') == 'damaged': current_G[u][v]['weight'] = CONFIG['big_time']
    prev_od = {}
    for s in env.suppliers:
        try: prev_od[s] = nx.single_source_dijkstra_path_length(current_G, s, weight='weight')
        except: prev_od[s] = {}
            
    for step in range(1, steps + 1):
        sim_time = step * CONFIG['eta']
        step_G = env.G.copy()
        
        # 更新路网状态
        for u, v, d in step_G.edges(data=True):
            if d.get('status') == 'damaged':
                tid = d.get('task_id')
                if repair_schedule.get(tid, 999999) <= sim_time:
                    step_G[u][v]['weight'] = d['normal_time']
                else:
                    step_G[u][v]['weight'] = CONFIG['big_time']
        
        curr_od = {}
        for s in env.suppliers:
            try: curr_od[s] = nx.single_source_dijkstra_path_length(step_G, s, weight='weight')
            except: curr_od[s] = {}
        
        remaining = CONFIG['T_total'] - sim_time
        gain = 0
        for s in env.suppliers:
            for d_node, d_val in env.demands.items():
                t1 = prev_od[s].get(d_node, CONFIG['big_time'])
                t2 = curr_od[s].get(d_node, CONFIG['big_time'])
                if t1 > CONFIG['big_time']: t1 = CONFIG['big_time']
                if t2 > CONFIG['big_time']: t2 = CONFIG['big_time']
                
                delta = t1 - t2
                if delta > 0 and t2 < CONFIG['big_time']:
                    gain += d_val * delta * remaining
        
        cumulative_U += gain
        prev_od = curr_od
        
    fitness = cumulative_U - (CONFIG['cost_penalty_alpha'] * actual_repair_cost)
    return fitness, cumulative_U, actual_repair_cost

# ==========================================
# 4. 遗传算法
# ==========================================

def generate_population(n_tasks, n_teams, size):
    pop = []
    for _ in range(size):
        sub1 = list(range(n_tasks))
        random.shuffle(sub1)
        sub2 = [random.randint(0, n_teams-1) for _ in range(n_tasks)]
        pop.append([sub1, sub2])
    return pop

def genetic_ops(population, num_teams, elite_pop):
    new_pop = []
    new_pop.extend(copy.deepcopy(elite_pop))
    while len(new_pop) < len(population):
        p1 = random.choice(population)
        p2 = random.choice(population)
        pt = random.randint(1, len(p1[0])-1)
        c1_s1 = p1[0][:pt] + [x for x in p2[0] if x not in p1[0][:pt]]
        c1_s2 = p1[1][:pt] + p2[1][pt:]
        if random.random() < 0.2:
            i, j = random.sample(range(len(c1_s1)), 2)
            c1_s1[i], c1_s1[j] = c1_s1[j], c1_s1[i]
            c1_s2[i] = random.randint(0, num_teams-1)
        new_pop.append([c1_s1, c1_s2])
    return new_pop[:len(population)]

# ==========================================
# 5. 终极可视化 (集成所有修复)
# ==========================================

# 设置中文字体 (防止方框乱码)
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'Microsoft YaHei', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

def visualize_final(env, best_solution):
    sub1, sub2 = best_solution
    
    # --- A. 重新运行贪婪调度 (获取详细时间数据) ---
    task_schedule = {} 
    schedule_log = [] 
    
    team_tasks = {i: [] for i in range(len(CONFIG['teams']))}
    for i, task_idx in enumerate(sub1):
        if 0 <= task_idx < len(env.task_map):
            team_tasks[sub2[i]].append(env.get_task_info(task_idx))
            
    team_time = {i: 0 for i in range(len(CONFIG['teams']))} 
    team_loc = {i: CONFIG['teams'][i] for i in range(len(CONFIG['teams']))}
    
    for team_id in range(len(CONFIG['teams'])):
        pending = team_tasks[team_id]
        while pending:
            curr = team_loc[team_id]
            best, min_d, target = None, float('inf'), None
            for task in pending:
                du = env.get_distance(curr, task['u'])
                dv = env.get_distance(curr, task['v'])
                if du < min_d: min_d = du; best = task; target = task['u']
                if dv < min_d: min_d = dv; best = task; target = task['v']
            
            if best is None: break
            
            travel = min_d
            repair = best['repair']
            s_travel = team_time[team_id]
            s_repair = s_travel + travel
            end = s_repair + repair
            
            if end <= CONFIG['T_total']:
                team_time[team_id] = end
                team_loc[team_id] = best['v'] if target == best['u'] else best['u']
                info = {
                    'start_travel': s_travel, 'start_repair': s_repair, 'end': end,
                    'team': team_id + 1, 'u': best['u'], 'v': best['v'], 'id': best['id'],
                    'prev_loc': curr, 'target_loc': target
                }
                task_schedule[best['id']] = info
                schedule_log.append(info)
            else: break
            pending.remove(best)

    # --- B. 绘图循环 ---
    snapshot_times = list(range(0, CONFIG['T_total'] + 1, 6 * 60))
    satisfied_history = set() # 累积满足
    
    print(f"\n--- 生成全景演变图 ---")
    
    for current_time in snapshot_times:
        plt.figure(figsize=(12, 10))
        ax = plt.gca()
        
        # 1. 物理路网
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
                    elif current_time >= sched['start_repair'] and current_time < sched['end']:
                        status = 'working'; weight = CONFIG['big_time']
                    elif current_time >= sched['start_travel'] and current_time < sched['start_repair']:
                        status = 'traveling_target'; weight = CONFIG['big_time']
                    else:
                        status = 'broken'; weight = CONFIG['big_time']
            display_G[u][v]['weight'] = weight
            if status == 'repaired': repaired.append((u, v))
            elif status == 'working': working.append((u, v))
            elif status in ['broken', 'traveling_target']: damaged.append((u, v))
            else: intact.append((u, v))

        # 2. 物流计算 (修复 T=0 Bug)
        active_routes = set()
        reachable_candidates = []
        
        try:
            dists, paths = nx.multi_source_dijkstra(display_G, sources=env.suppliers, weight='weight')
            for n, t in dists.items():
                # [关键] 必须路通 且 车开到了
                if t < CONFIG['big_time'] and t <= current_time:
                    reachable_candidates.append(n)
        except: pass
        
        # 过滤 (修复 KeyError)
        pending = [n for n in reachable_candidates if n not in satisfied_history and n in env.demands]
        pending.sort(key=lambda n: dists[n])
        
        # 运力分配
        cap = CONFIG.get('fleet_capacity', 2500)
        waiting = []
        for n in pending:
            req = env.demands[n]
            if cap >= req:
                cap -= req
                satisfied_history.add(n)
            else:
                waiting.append(n)
                
        # 提取路径
        for n in satisfied_history:
            if n in paths:
                path = paths[n]
                for i in range(len(path)-1):
                    active_routes.add(tuple(sorted((path[i], path[i+1]))))

        # 3. 绘制基础层
        if intact: nx.draw_networkx_edges(display_G, POS, edgelist=intact, edge_color='#e0e0e0', width=1, ax=ax)
        if damaged: nx.draw_networkx_edges(display_G, POS, edgelist=damaged, edge_color='black', style='dashed', alpha=0.3, width=1, ax=ax)
        if working: nx.draw_networkx_edges(display_G, POS, edgelist=working, edge_color='#ff9900', width=5, alpha=1.0, ax=ax)
        if repaired: nx.draw_networkx_edges(display_G, POS, edgelist=repaired, edge_color='#2ca02c', width=2, alpha=0.5, ax=ax)
        if active_routes: nx.draw_networkx_edges(display_G, POS, edgelist=list(active_routes), edge_color='#1f77b4', width=2.5, alpha=0.5, ax=ax)

        # 4. 节点绘制
        green = list(satisfied_history)
        yellow = waiting
        red = [n for n in env.demands if n not in green and n not in yellow]
        
        def get_sizes(nodes): return [100 + (env.demands[n]/500)*300 for n in nodes]
        
        nx.draw_networkx_nodes(display_G, POS, nodelist=env.suppliers, node_color='red', node_shape='*', node_size=350, ax=ax, label='Supply')
        if green: nx.draw_networkx_nodes(display_G, POS, nodelist=green, node_color='#98df8a', node_size=get_sizes(green), edgecolors='green', ax=ax)
        if yellow: nx.draw_networkx_nodes(display_G, POS, nodelist=yellow, node_color='#fdbf6f', node_size=get_sizes(yellow), edgecolors='orange', linewidths=2, ax=ax)
        if red: nx.draw_networkx_nodes(display_G, POS, nodelist=red, node_color='#ff9896', node_size=get_sizes(red), edgecolors='red', ax=ax)

        # 5. 队伍动态 (修复乱码)
        for t_info in schedule_log:
            # 抢修中
            if t_info['start_repair'] <= current_time < t_info['end']:
                mx = (POS[t_info['u']][0] + POS[t_info['v']][0])/2
                my = (POS[t_info['u']][1] + POS[t_info['v']][1])/2
                text = f"队{t_info['team']}\n抢修"
                ax.text(mx, my, text, fontsize=9, fontweight='bold', color='white', ha='center', va='center',
                        bbox=dict(boxstyle="round,pad=0.2", fc="#ff9900", ec="black"))
            
            # 赶路中
            elif t_info['start_travel'] <= current_time < t_info['start_repair']:
                dur = t_info['start_repair'] - t_info['start_travel']
                done = current_time - t_info['start_travel']
                ratio = done / dur if dur > 0 else 1.0
                
                sx, sy = POS[t_info['prev_loc']]
                ex, ey = POS[t_info['target_loc']]
                cx = sx + (ex - sx) * ratio
                cy = sy + (ey - sy) * ratio
                
                text = f"队{t_info['team']}\n赶路"
                ax.text(cx, cy, text, fontsize=8, color='white', ha='center', va='center',
                        bbox=dict(boxstyle="round,pad=0.2", fc="#555555", ec="none", alpha=0.8))
                ax.annotate("", xy=(ex, ey), xytext=(sx, sy), arrowprops=dict(arrowstyle="->", color="gray", linestyle="dotted", lw=1.5))

        # 6. 图例
        legend = [
            mlines.Line2D([], [], color='#1f77b4', lw=2.5, label='物流路径'),
            mlines.Line2D([], [], color='#ff9900', lw=4, label='抢修施工'),
            mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#98df8a', markeredgecolor='green', markersize=10, label='已送达'),
            mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#fdbf6f', markeredgecolor='orange', markersize=10, label='等待运力'),
            mlines.Line2D([], [], marker='o', color='w', markerfacecolor='#ff9896', markeredgecolor='red', markersize=10, label='未送达'),
            mlines.Line2D([], [], marker='s', color='w', markerfacecolor='#555555', markersize=10, label='队伍赶路'),
        ]
        plt.legend(handles=legend, loc='lower right', fontsize=9)
        
        hour = current_time / 60
        sat_val = sum(env.demands[n] for n in green)
        
        title = f"时刻: {hour:.1f}h | 累计已满足: {len(green)}点"
        ax.set_title(title, fontsize=12, loc='left', fontweight='bold')
        ax.axis('off')
        plt.tight_layout()
        plt.show()
        plt.close()

# ==========================================
# 6. Main
# ==========================================

def main():
    env = Environment()
    num_tasks = len(env.task_map)
    num_teams = len(CONFIG['teams'])
    
    print("开始优化 (含 Travel Time & 贪婪连续调度)...")
    pop = generate_population(num_tasks, num_teams, CONFIG['pop_size'])
    
    for gen in range(CONFIG['max_gen']):
        evals = [calculate_fitness(ind, env) for ind in pop]
        
        combined = []
        for i in range(len(pop)):
            fit, u, cost = evals[i]
            combined.append({'chrom': pop[i], 'fit': fit, 'u': u, 'cost': cost})
        
        combined.sort(key=lambda x: x['fit'], reverse=True)
        best_now = combined[0]
        
        if gen % 10 == 0:
            print(f"Gen {gen}: Fit={best_now['fit']:.2e} | U={best_now['u']:.2e} | Cost={best_now['cost']:.0f}")
            
        sorted_chroms = [x['chrom'] for x in combined]
        elites = sorted_chroms[:CONFIG['elite_size']]
        mating = sorted_chroms[:int(CONFIG['pop_size']*0.6)]
        
        pop = genetic_ops(mating, num_teams, elites)
        while len(pop) < CONFIG['pop_size']:
            pop.append(generate_population(num_tasks, num_teams, 1)[0])
            
    best_chrom = sorted_chroms[0]
    fit, u, cost = calculate_fitness(best_chrom, env)
    print(f"\n最优方案: U={u:.2e}, Repair Cost={cost:.0f}")
    
    # 运行最终可视化
    visualize_final(env, best_chrom)

if __name__ == "__main__":
    main()