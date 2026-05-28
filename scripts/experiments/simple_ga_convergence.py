import networkx as nx
import numpy as np
import random
import copy
import matplotlib.pyplot as plt
import math

# ==========================================
# 1. 汶川地震案例数据 (用户提供)
# ==========================================

# 节点 (ID, Name, Type, Value)
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

# 基础路网 (u, v, travel_time, repair_time)
# 注意：travel_time 是正常通行时间，repair_time 如果是0代表路没断
RAW_EDGES = [
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

# 算法配置
CONFIG = {
    'T_total': 72 * 60,     # 总工期 72小时 (分钟)
    'eta': 60,              # 计算积分的时间粒度 (1小时算一次积分，精度高)
    'report_step': 6 * 60,  # 报告输出间隔 (6小时)
    'teams': [1, 2, 3],     # 3支队伍，分别从供应点1, 2, 3出发
    'big_time': 9999,       # 断路惩罚时间
    'pop_size': 100,        # 种群
    'max_gen': 200,         # 迭代次数
    'pc': 0.9,              # 交叉率
    'pm': 0.2               # 变异率
}

# ==========================================
# 2. 环境构建
# ==========================================

class Environment:
    def __init__(self):
        self.G = nx.Graph()
        self.suppliers = []
        self.demands = {} 
        self.damaged_tasks = [] # 存储受损路段详情
        self.nodes_map = {}
        
        self._init_data()
        
    def _init_data(self):
        # 初始化节点
        for nid, name, ntype, val in RAW_NODES:
            self.G.add_node(nid, name=name, type=ntype, val=val)
            self.nodes_map[nid] = name
            if ntype == 'supply':
                self.suppliers.append(nid)
            elif ntype == 'demand':
                self.demands[nid] = val
        
        # 初始化边和受损任务
        task_id_counter = 0
        for u, v, travel, repair in RAW_EDGES:
            # 基础属性
            status = 'intact' if repair == 0 else 'damaged'
            weight = travel if repair == 0 else CONFIG['big_time']
            
            self.G.add_edge(u, v, weight=weight, normal_time=travel, 
                            repair_time=repair, status=status)
            
            if repair > 0:
                self.damaged_tasks.append({
                    'id': task_id_counter,
                    'u': u, 'v': v,
                    'repair': repair,
                    'travel': travel
                })
                # 记录边的task_id方便查找
                self.G[u][v]['task_id'] = task_id_counter
                task_id_counter += 1

    def get_node_name(self, nid):
        return self.nodes_map.get(nid, str(nid))

# ==========================================
# 3. 核心算法逻辑 (单目标 GA)
# ==========================================

def calculate_schedule_and_performance(chromosome, env):
    """
    计算两件事：
    1. 真实的修复时间表 (Schedule)
    2. 抢修绩效 U (Performance)
    """
    sub1, sub2 = chromosome # sub1: 任务顺序, sub2: 队伍分配
    
    # --- 1. 计算排班表 ---
    # team_free_time: 队伍什么时候有空 {team_idx: minutes}
    team_free_time = {i: 0 for i in range(len(CONFIG['teams']))}
    
    # repair_schedule: {task_id: finish_time}
    repair_schedule = {}
    
    # 记录每个任务是谁修的，什么时候开始，什么时候结束（用于后续报告）
    task_log = {} 
    
    for i, task_idx in enumerate(sub1):
        team_idx = sub2[i]
        task = env.damaged_tasks[task_idx]
        
        # 简化：假设队伍修完一个瞬间到达下一个（忽略路途时间，只算纯抢修时间）
        # 如果要更真实，这里应该加上 Dijkstra 算出从上一任务点到当前点的路程
        start_time = team_free_time[team_idx]
        finish_time = start_time + task['repair']
        
        if finish_time <= CONFIG['T_total']:
            team_free_time[team_idx] = finish_time
            repair_schedule[task_idx] = finish_time
            task_log[task_idx] = {
                'team': CONFIG['teams'][team_idx],
                'start': start_time,
                'end': finish_time
            }
        else:
            # 超时任务，放弃修复
            pass
            
    # --- 2. 计算绩效 U ---
    # U = Sum ( 需求量 * 缩短时间 * 剩余受益时间 )
    cumulative_U = 0
    
    # 初始状态路网 (全断)
    curr_G = env.G.copy()
    for u, v, d in curr_G.edges(data=True):
        if d['status'] == 'damaged':
            curr_G[u][v]['weight'] = CONFIG['big_time']
            
    # 计算初始OD矩阵 (基准)
    prev_od = {}
    for s in env.suppliers:
        try:
            prev_od[s] = nx.single_source_dijkstra_path_length(curr_G, s, weight='weight')
        except:
            prev_od[s] = {}
            
    # 离散时间积分 (步长 eta)
    steps = int(CONFIG['T_total'] / CONFIG['eta'])
    
    for step in range(1, steps + 1):
        sim_time = step * CONFIG['eta']
        
        # A. 检查此刻哪些路通了
        updated = False
        for tid, finish_t in repair_schedule.items():
            # 如果这任务刚在这一步之前修好，更新路网
            if finish_t <= sim_time and finish_t > (sim_time - CONFIG['eta']):
                task = env.damaged_tasks[tid]
                curr_G[task['u']][task['v']]['weight'] = task['travel'] # 恢复正常通行时间
                updated = True
                
        # B. 如果路网变了，重新计算OD；没变就复用上一轮结果（加速）
        curr_od = prev_od
        if updated:
            curr_od = {}
            for s in env.suppliers:
                try:
                    curr_od[s] = nx.single_source_dijkstra_path_length(curr_G, s, weight='weight')
                except:
                    curr_od[s] = {}
        
        # C. 累加绩效
        benefit_duration = CONFIG['T_total'] - sim_time
        
        for s in env.suppliers:
            for d, demand_val in env.demands.items():
                t_old = prev_od[s].get(d, CONFIG['big_time'])
                t_new = curr_od[s].get(d, CONFIG['big_time'])
                
                # 限制最大值
                if t_old > CONFIG['big_time']: t_old = CONFIG['big_time']
                if t_new > CONFIG['big_time']: t_new = CONFIG['big_time']
                
                delta_t = t_old - t_new
                
                # 只有当路从“不通”变成“通”，或者时间缩短了，才算绩效
                if delta_t > 0 and t_new < CONFIG['big_time']:
                    cumulative_U += demand_val * delta_t * benefit_duration
        
        prev_od = curr_od # 迭代
        
    return cumulative_U, repair_schedule, task_log

# GA 辅助函数
def create_ind(n_tasks, n_teams):
    s1 = list(range(n_tasks))
    random.shuffle(s1)
    s2 = [random.randint(0, n_teams-1) for _ in range(n_tasks)]
    return [s1, s2]

def run_ga():
    env = Environment()
    n_tasks = len(env.damaged_tasks)
    n_teams = len(CONFIG['teams'])
    
    # 初始种群
    pop = [create_ind(n_tasks, n_teams) for _ in range(CONFIG['pop_size'])]
    best_fitness_history = []
    global_best_sol = None
    global_best_fit = -1
    
    print(f"🚀 开始优化... (Tasks: {n_tasks}, Teams: {n_teams})")
    
    for gen in range(CONFIG['max_gen']):
        # 评估
        fitnesses = []
        for ind in pop:
            fit, _, _ = calculate_schedule_and_performance(ind, env)
            fitnesses.append(fit)
            
            if fit > global_best_fit:
                global_best_fit = fit
                global_best_sol = copy.deepcopy(ind)
        
        best_fitness_history.append(global_best_fit)
        
        # 简单打印
        if gen % 20 == 0:
            print(f"Gen {gen}: Best Performance U = {global_best_fit/1e8:.4f}e8")
            
        # 选择 (锦标赛)
        next_pop = []
        # 精英保留
        elite_idx = np.argmax(fitnesses)
        next_pop.append(pop[elite_idx])
        
        while len(next_pop) < CONFIG['pop_size']:
            # 选父代
            p1, p2 = random.choices(pop, k=2, weights=fitnesses) # 轮盘赌简化
            
            # 交叉
            if random.random() < CONFIG['pc']:
                c1, c2 = copy.deepcopy(p1), copy.deepcopy(p2)
                # PMX 模拟
                pt = random.randint(1, n_tasks-1)
                c1[0] = p1[0][:pt] + [x for x in p2[0] if x not in p1[0][:pt]]
                c1[1] = p1[1][:pt] + p2[1][pt:]
                child = c1
            else:
                child = p1
                
            # 变异
            if random.random() < CONFIG['pm']:
                i, j = random.sample(range(n_tasks), 2)
                child[0][i], child[0][j] = child[0][j], child[0][i]
                child[1][i] = random.randint(0, n_teams-1)
                
            next_pop.append(child)
            
        pop = next_pop
        
    return best_fitness_history, global_best_sol, env

# ==========================================
# 4. 详细推演报告 (每6小时)
# ==========================================

def simulate_final_plan(sol, env):
    _, repair_schedule, task_log = calculate_schedule_and_performance(sol, env)
    
    print("\n" + "="*60)
    print(f"🛑 抢修方案详细推演 (每 {CONFIG['report_step']/60} 小时一报)")
    print("="*60)
    
    # 模拟时间轴
    total_steps = int(CONFIG['T_total'] / CONFIG['report_step'])
    
    # 初始化图
    curr_G = env.G.copy()
    for u, v, d in curr_G.edges(data=True):
        if d['status'] == 'damaged':
            curr_G[u][v]['weight'] = CONFIG['big_time']
            
    for step in range(total_steps + 1):
        curr_time = step * CONFIG['report_step'] # 分钟
        
        print(f"\n🕒 时间: T = {curr_time/60:.0f} 小时")
        print("-" * 30)
        
        # 1. 更新路网状态 & 打印刚修好的路
        newly_repaired = []
        for tid, info in task_log.items():
            # 刚好在这个时间段修好 (上一时刻 < end <= 当前时刻)
            # 为了简化展示，我们打印所有当前已修好的
            if info['end'] <= curr_time and curr_G[env.damaged_tasks[tid]['u']][env.damaged_tasks[tid]['v']]['weight'] > 10000:
                u, v = env.damaged_tasks[tid]['u'], env.damaged_tasks[tid]['v']
                curr_G[u][v]['weight'] = env.damaged_tasks[tid]['travel']
                newly_repaired.append(f"{env.get_node_name(u)}-{env.get_node_name(v)}")
        
        if newly_repaired:
            print(f"  ✅ 累计已抢通关键路段: {', '.join(newly_repaired)}")
        else:
            print(f"  ⚪ 无新增抢通，抢修进行中...")
            
        # 2. 打印抢修队状态
        print("  👷 抢修队状态:")
        working_teams = []
        for tid, info in task_log.items():
            if info['start'] <= curr_time < info['end']:
                u_name = env.get_node_name(env.damaged_tasks[tid]['u'])
                v_name = env.get_node_name(env.damaged_tasks[tid]['v'])
                working_teams.append(f"队{info['team']}正在抢修 [{u_name}-{v_name}] (预计T={info['end']/60:.1f}h完工)")
        
        if working_teams:
            for w in working_teams: print(f"     {w}")
        else:
            print("     所有队伍待命或已完工")

        # 3. 打印物流可达性 (随机抽样几个重要灾区)
        print("  🚚 物资配送能力:")
        targets = [38, 29, 28, 4] # 红白, 龙门山, 小鱼洞, 玉堂
        
        reachable_count = 0
        for target in targets:
            try:
                # 计算从都江堰(1) 或 彭州(2) 出发的最短路
                path = nx.shortest_path(curr_G, source=2, target=target, weight='weight')
                time_cost = nx.shortest_path_length(curr_G, source=2, target=target, weight='weight')
                
                if time_cost < CONFIG['big_time']:
                    path_names = [env.get_node_name(n) for n in path]
                    print(f"     -> 到 {env.get_node_name(target)}: 通畅! 耗时{time_cost}分")
                    # print(f"        路线: {'->'.join(path_names)}")
                    reachable_count += 1
                else:
                    print(f"     -> 到 {env.get_node_name(target)}: ❌ 阻断")
            except:
                print(f"     -> 到 {env.get_node_name(target)}: ❌ 阻断")
                
        # 计算全网通达率
        total_reachable = 0
        for s in env.suppliers:
            try:
                lens = nx.single_source_dijkstra_path_length(curr_G, s, weight='weight')
                # 过滤掉不可达的
                valid_d = [k for k,v in lens.items() if v < CONFIG['big_time'] and k in env.demands]
                total_reachable = max(total_reachable, len(valid_d)) # 取最好的那个仓库的覆盖面
            except: pass
            
        print(f"  📊 全网物资覆盖率: {total_reachable}/{len(env.demands)} 个灾区可达")

# ==========================================
# 7. 绘图
# ==========================================
def plot_convergence(history):
    plt.figure(figsize=(10, 5))
    plt.plot(history, 'r-', linewidth=2)
    plt.title('Optimization Convergence: Repair Performance U')
    plt.xlabel('Generations')
    plt.ylabel('Performance U (Higher is better)')
    plt.grid(True)
    plt.show()

if __name__ == "__main__":
    # 1. 运行优化
    hist, best_sol, env = run_ga()
    
    # 2. 画收敛图 (证明模型有效，绩效在变好)
    plot_convergence(hist)
    
    # 3. 详细推演最优方案
    simulate_final_plan(best_sol, env)