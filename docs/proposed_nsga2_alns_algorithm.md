# 拟研究算法文档：NSGA-II + ALNS 混合多目标算法

> 本文参考 `docs/genetic_algorithm.md` 的写法，描述拟研究的算法创新：设计嵌入自适应大邻域搜索（ALNS）的 NSGA-II 混合算法，求解考虑道路容量渐进恢复与异质车辆通行约束的灾后道路修复-救援配送协同优化问题。

## 1. 为什么需要混合算法

拟研究模型同时包含：

- 道路修复顺序；
- 维修队分配；
- 道路修复进度和容量恢复；
- 多车型车辆选择；
- 多周期配送路径；
- 需求满足公平性。

这些决策高度耦合。标准 GA 或标准 NSGA-II 可以做全局搜索，但对路径和排班的局部结构利用不足；ALNS 擅长对路径、分配和序列问题做局部强化。因此建议采用：

```text
NSGA-II 负责全局多目标搜索
ALNS 负责对候选解做局部改进
```

## 2. 算法总体框架

```text
初始化种群
    -> 解码每个个体，生成修复排班和多周期配送方案
    -> 计算多目标值
    -> 非支配排序和拥挤距离计算
    -> 选择、交叉、变异产生子代
    -> 对部分优秀个体或新个体执行 ALNS 局部强化
    -> 合并父代和子代，保留 Pareto 优秀个体
    -> 重复迭代
输出 Pareto 解集
```

## 3. 染色体编码

在原论文三段式染色体基础上扩展。

```text
染色体 =
[第 1 段：受损道路修复优先序列 |
 第 2 段：维修队分配 |
 第 3 段：配送组合优先级 |
 第 4 段：车型选择偏好]
```

| 染色体段 | 内容 | 作用 |
|---|---|---|
| 第 1 段 | 受损道路排列 | 决定先修哪些道路 |
| 第 2 段 | 维修队编号序列 | 决定每条受损道路由哪支维修队负责 |
| 第 3 段 | 供给点-需求点组合优先级 | 决定配送服务顺序 |
| 第 4 段 | 车辆类型优先级或车辆分配偏好 | 决定在当前道路容量下优先使用哪类车 |

如果希望控制复杂度，第一版可以不显式增加第 4 段，而是在解码时根据道路恢复程度和车辆可通行阈值自动选择车型。这样染色体仍保持三段式，算法实现更稳。

推荐第一版编码：

```text
染色体 = [修复顺序 | 维修队分配 | 配送组合优先级]
车型选择在解码阶段由启发式规则决定。
```

## 4. 解码流程

解码是算法核心，因为道路容量渐进恢复会影响每一期配送。

### 4.1 解码道路修复排班

输入：

- 修复顺序段；
- 维修队分配段；
- 受损道路修复时间；
- 周期长度。

输出：

- 每支维修队的维修序列；
- 每条受损道路每个周期的累计维修时间；
- 每条受损道路每个周期的修复进度。

```text
修复顺序 + 维修队分配
    -> 维修队任务表
    -> 周期维修时间分配
    -> p_a^t
```

### 4.2 生成动态路网

对每个周期 `t`：

```text
p_a^t -> g(p_a^t) -> C_a^t -> y_a,v^t -> tau_a,v^t
```

得到车辆类型相关的动态路网：

```text
Graph(t, v)
```

即每个周期、每类车都有一张不同的可通行路网。

### 4.3 解码配送方案

根据配送组合优先级依次尝试：

```text
供给点 m -> 需求点 i -> 车辆类型 v
```

检查条件：

1. 供给点是否还有物资；
2. 需求点是否还有未满足需求；
3. 车辆类型是否还有可用车辆；
4. 当前周期 `Graph(t, v)` 是否存在可通路径；
5. 路径通行时间是否满足周期约束。

如果全部满足，则分配物资并更新：

```text
供给剩余量
需求剩余量
车辆剩余量
路段流量或占用
需求满足率
```

## 5. NSGA-II 主流程

### 5.1 初始化

采用混合初始化：

| 个体类型 | 生成方式 |
|---|---|
| 随机个体 | 随机修复顺序、随机维修队分配、随机配送优先级 |
| 启发式个体 | 优先修复连接供给点和高需求点的道路 |
| 可达性优先个体 | 优先修复能最大提升路网可达性的道路 |
| 紧急度优先个体 | 优先服务需求量大或满足率低的需求点 |

这样可以让初始种群既有多样性，也有一定质量。

### 5.2 目标评价

每个个体解码后计算：

```text
F1 = 累计未满足需求
F2 = 总配送与抢修时间
F3 = 公平性损失或 -最小满足率
```

如果使用 NSGA-II 的最小化形式，可以把最大化最小满足率改写为：

```text
F3 = - min_i 满足率_i
```

### 5.3 非支配排序

按 NSGA-II 标准流程：

1. 根据多目标值进行非支配排序；
2. 得到不同 Pareto fronts；
3. 对同一 front 内个体计算拥挤距离；
4. 优先保留 front 等级低、拥挤距离大的个体。

### 5.4 交叉与变异

| 染色体段 | 交叉 | 变异 |
|---|---|---|
| 修复顺序 | 顺序交叉 OX 或两点交叉修复 | swap、insert、reverse |
| 维修队分配 | 单点或均匀交叉 | 随机重分配维修队 |
| 配送组合优先级 | 顺序交叉 OX | swap、relocate、reverse |

需要保证排列段不重复，维修队编号在合法范围内。

## 6. ALNS 局部强化

ALNS 不对所有个体都执行，建议只对以下个体执行：

- 每代 Pareto front 1 中的部分个体；
- 新生成子代中质量较好的个体；
- 每隔若干代随机选择一部分个体。

这样可以控制计算时间。

## 7. ALNS 破坏算子

破坏算子用于从当前解中移除部分结构，制造重新优化空间。

### 7.1 道路修复破坏算子

| 算子 | 含义 |
|---|---|
| random_remove_repair | 随机移除若干受损道路的维修位置 |
| worst_remove_repair | 移除对目标贡献较低的维修任务 |
| related_remove_repair | 移除空间上相邻或同一关键路径上的维修任务 |
| crew_balance_remove | 移除导致维修队负载不平衡的任务 |

### 7.2 配送路径破坏算子

| 算子 | 含义 |
|---|---|
| random_remove_demand | 随机移除若干需求点配送安排 |
| worst_remove_demand | 移除配送时间长或收益低的需求点 |
| low_satisfaction_remove | 移除低满足率区域周边安排，重新分配 |
| route_segment_remove | 移除一段车辆路径，重新插入 |

### 7.3 车型选择破坏算子

| 算子 | 含义 |
|---|---|
| vehicle_type_reset | 重置部分配送任务车型 |
| heavy_to_light_remove | 将不可通或低效重型车任务移除，尝试小型车替代 |
| light_to_heavy_merge | 道路恢复后，将多个小车任务合并为大车任务 |

## 8. ALNS 修复算子

修复算子用于将移除的任务重新插入解中。

### 8.1 道路修复插入算子

| 算子 | 含义 |
|---|---|
| earliest_recovery_insert | 优先插入能最早形成通路的道路 |
| max_capacity_gain_insert | 优先插入容量恢复收益最大的道路 |
| high_demand_access_insert | 优先插入通往高需求节点的道路 |
| crew_nearest_insert | 将任务插入距离维修队当前位置最近的位置 |

### 8.2 配送插入算子

| 算子 | 含义 |
|---|---|
| shortest_time_insert | 插入到当前最短通行时间路径 |
| max_satisfaction_insert | 优先提高最低满足率 |
| capacity_aware_insert | 根据当前道路容量和车辆阈值选择路径 |
| regret_insert | 使用 regret-k 规则减少后续插入损失 |

### 8.3 车型修复算子

| 算子 | 含义 |
|---|---|
| feasible_vehicle_first | 选择当前可通且容量最大的车型 |
| urgent_light_vehicle | 对紧急需求优先使用小型车抢送 |
| recovered_heavy_vehicle | 道路基本恢复后改用大车集中配送 |

## 9. 自适应权重更新

ALNS 中每个算子都有权重。表现好的算子权重提高，表现差的算子权重降低。

可采用分数规则：

| 情况 | 分数 |
|---|---:|
| 产生新的非支配解 | 5 |
| 改善当前个体目标值 | 3 |
| 解可行但未改善 | 1 |
| 产生不可行解 | 0 |

权重更新：

```text
weight_o = (1 - lambda) * weight_o + lambda * score_o
```

其中 `lambda` 是平滑参数，例如 `0.1`。

## 10. 接受准则

ALNS 生成新解后，可以采用以下接受准则：

1. 如果新解支配旧解，接受；
2. 如果新解与旧解互不支配，按一定概率接受；
3. 如果新解被旧解支配，仅在模拟退火概率下接受。

模拟退火概率：

```text
P = exp(-delta / Temp)
```

这样可以避免局部搜索过早陷入局部最优。

## 11. 混合算法伪代码

```text
Input: nodes, edges, damaged_links, vehicles, repair_crews, recovery_stages
Output: Pareto solution set

Initialize population P
Evaluate P by decoding repair schedule and delivery routes

for generation = 1 to MaxGen:
    Rank P by non-dominated sorting
    Compute crowding distance
    Select parents by binary tournament
    Generate offspring Q by crossover and mutation

    for each selected individual q in Q:
        q' = ALNS(q)
        if q' is accepted:
            replace q with q'

    Evaluate Q
    R = P union Q
    Rank R by non-dominated sorting
    P = select best PopSize individuals from R

return non-dominated solutions in P
```

ALNS 子程序：

```text
ALNS(solution s):
    s_best = s
    s_current = s

    for iter = 1 to MaxALNS:
        choose destroy operator d by adaptive weights
        choose repair operator r by adaptive weights
        s_removed = d(s_current)
        s_new = r(s_removed)
        decode and evaluate s_new

        if accept(s_new, s_current):
            s_current = s_new

        if s_new improves s_best:
            s_best = s_new

        update operator weights

    return s_best
```

## 12. 与模型创新的对应关系

| 模型创新 | 算法处理 |
|---|---|
| 道路容量渐进恢复 | 解码时每期更新 `p_a^t`, `C_a^t`, `tau_a,v^t` |
| 车型通行阈值 | 配送插入算子必须检查 `p_a^t >= theta_v` |
| 小车先通、大车后通 | 车型修复算子在不同恢复阶段选择不同车辆 |
| 多目标权衡 | NSGA-II 输出 Pareto 解集 |
| 路径和修复序列复杂 | ALNS 用破坏/修复算子做局部强化 |

## 13. 对比算法设计

建议至少设置以下对比：

| 算法 | 用途 |
|---|---|
| HSSPGA/普通 GA | 对照原论文遗传算法思路 |
| 标准 NSGA-II | 验证 ALNS 强化是否有效 |
| ALNS-only | 验证全局多目标搜索是否必要 |
| NSGA-II + ALNS | 拟研究主算法 |

如果时间充足，可加入：

| 算法 | 用途 |
|---|---|
| MOEA/D | 多目标分解算法对比 |
| 逻辑 Benders 分解 | 小规模算例验证或获得下界 |

不建议第一版同时把 MOEA/D、Benders 和强化学习都作为主算法，否则论文主线会散。

## 14. 实验指标

| 指标 | 含义 |
|---|---|
| `F1` 累计未满足需求 | 救援效果 |
| `F2` 总配送与抢修时间 | 救援效率 |
| `F3` 最小满足率或公平性损失 | 公平性 |
| Hypervolume | Pareto 解集质量 |
| Spread | Pareto 解集分布 |
| 收敛曲线 | 算法稳定性 |
| 运行时间 | 应急场景可用性 |
| 可行解比例 | 约束处理效果 |

## 15. 消融实验

为了证明两个创新点都有贡献，建议做消融：

| 实验 | 目的 |
|---|---|
| 二元道路状态 + NSGA-II | 原始基准 |
| 容量渐进恢复 + NSGA-II | 验证模型创新 |
| 容量渐进恢复 + NSGA-II + 普通局部搜索 | 验证局部搜索必要性 |
| 容量渐进恢复 + NSGA-II + ALNS | 验证完整算法 |

还可以测试车辆通行阈值：

| 实验 | 目的 |
|---|---|
| 不区分车型通行阈值 | 看容量恢复本身的效果 |
| 区分车型通行阈值 | 看“小车先通、大车后通”的效果 |

## 16. 推荐论文表述

算法创新可以写成：

> 针对道路修复排班与多车型救援配送高度耦合、解空间复杂的问题，设计一种嵌入自适应大邻域搜索的 NSGA-II 混合多目标算法。该算法以 NSGA-II 进行全局 Pareto 搜索，并通过面向道路修复序列、维修队分配、车辆路径和车型选择的 ALNS 破坏-修复算子对候选解进行局部强化，从而提高解质量和收敛效率。

## 17. 第一版实现建议

为了尽快跑通实验，第一版建议：

1. 使用三段式染色体，不单独增加车型段。
2. 车型选择放在解码和 ALNS 修复算子中处理。
3. 先实现标准 NSGA-II。
4. 再加入 3 类 ALNS 算子：修复顺序、配送路径、车型替换。
5. 先使用容量折减通行时间，后续再换 BPR 函数。
6. 先做 9 周期汶川案例，再扩展随机算例。

这样可以保证算法创新可实现、可调试、可对比。
