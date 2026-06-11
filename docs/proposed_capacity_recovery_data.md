# 拟研究数据文档：道路容量渐进恢复与异质车辆

> 本文基于 `docs/wenchuan_case_model_inputs.md` 的汶川案例数据扩展，用于支撑拟研究方向：考虑道路容量渐进恢复的灾后道路修复与救援配送协同优化。本文重点说明新增哪些数据字段、这些字段如何从现有数据构造，以及后续程序实现时建议拆成哪些数据表。

## 1. 数据设计目标

原始 Li & Teo (2019) 案例已经包含节点、供需量、道路通行时间、受损道路、维修队和车辆数据。拟研究不改变这些基础数据，而是在其上增加两个关键数据层：

1. **道路容量渐进恢复层**：道路不再只有“不可达/可达”两种状态，而是随修复进度逐步恢复容量。
2. **异质车辆通行层**：不同救援车辆对道路恢复程度有不同通行要求，小型车可以更早进入，重型车需要道路恢复到更高水平。

因此，新的数据逻辑是：

```text
基础路网 + 受损道路 + 修复时间
        -> 修复进度 p_a^t
        -> 道路恢复阶段 r_a^t
        -> 当前容量 C_a^t
        -> 车型可通行性 y_a,v^t
        -> 配送路径和通行时间
```

## 2. 沿用的原始数据

| 数据表 | 来源文档 | 是否沿用 | 作用 |
|---|---|---|---|
| `nodes` | `wenchuan_case_model_inputs.md` 表 1 | 是 | 供给点、需求点、供给量、需求量 |
| `edges` | `wenchuan_case_model_inputs.md` 表 1b | 是 | 路段连接关系、基础通行时间、估算正常容量 |
| `damaged_links` | `wenchuan_case_model_inputs.md` 表 2 | 是 | 受损路段、端点、修复时间 |
| `vehicles` | `wenchuan_case_model_inputs.md` 表 3 | 是，但需扩展 | 车辆容量、数量、道路占用 |
| `repair_crews` | `wenchuan_case_model_inputs.md` 表 4 | 是 | 维修队工作站、初始节点、修复能力 |
| `planning` | `algorithm_flow.md` | 是 | 72 小时、8 小时一个周期、9 个周期 |

## 3. 新增数据表 1：道路恢复阶段

为表达“抢通”和“完全修复”的差别，建议将每条受损路段的恢复过程拆成 4-5 个阶段。这里给出一个可复现实验用的默认表。

| 恢复阶段编号 | 修复进度区间 `p_a^t` | 道路状态 | 容量恢复系数 `g(p_a^t)` | 管理含义 |
|---:|---|---|---:|---|
| 0 | `[0, 0.30)` | 完全中断 | 0.00 | 车辆不可通行 |
| 1 | `[0.30, 0.60)` | 临时抢通 | 0.30 | 小型救援车可低速通行 |
| 2 | `[0.60, 0.80)` | 单车道限行 | 0.60 | 小型车和中型车可通行 |
| 3 | `[0.80, 1.00)` | 基本恢复 | 0.80 | 大部分货车可通行 |
| 4 | `1.00` | 完全恢复 | 1.00 | 全部车辆按正常容量通行 |

说明：

- `p_a^t` 表示路段 `a` 在周期 `t` 结束时的累计修复进度，取值范围为 `[0, 1]`。
- `g(p_a^t)` 是容量恢复函数，用于计算当前道路容量。
- 分段阈值 `0.30/0.60/0.80/1.00` 是可调场景参数，后续可以做敏感性分析。

## 4. 新增数据表 2：车辆通行阈值

原论文车辆表只有容量、数量和道路占用。为了让道路容量恢复影响配送路径，需要为每类车辆增加最低通行阈值、速度折减敏感系数等字段。

| 车辆类型 | 原单车容量（吨） | 原车辆数量 | 原占用 OD（pcu/h） | 最低通行进度 `theta_v` | 建议车型解释 |
|---:|---:|---:|---:|---:|---|
| 1 | 5 | 150 | 300 | 0.30 | 小型救援车 |
| 2 | 10 | 110 | 500 | 0.50 | 中型货车 |
| 3 | 15 | 70 | 800 | 0.70 | 大型货车 |
| 4 | 20 | 40 | 1000 | 0.80 | 重型货车 |

建议新增字段：

| 字段 | 含义 | 用途 |
|---|---|---|
| `vehicle_type` | 车辆类型编号 | 与原车辆表一致 |
| `capacity_ton` | 单车载重 | 控制配送量 |
| `available_count` | 车辆数量 | 控制车队规模 |
| `pcu_impact` | 道路占用系数 | 用于路段流量或拥堵计算 |
| `min_recovery_progress` | 最低道路修复进度 `theta_v` | 判断该车型能否通过路段 |
| `speed_factor` | 灾后速度折减基准 | 可用于区分不同车辆速度 |

车辆可通行规则：

```text
如果 p_a^t >= theta_v，则车辆 v 可通过路段 a；
如果 p_a^t < theta_v，则车辆 v 不可通过路段 a。
```

这个规则可以表达：

```text
同一条路在临时抢通阶段，小型车能走，重型车不能走。
```

## 5. 新增数据表 3：受损道路修复进度

原始受损道路表只有总修复时间 `sd`。拟研究需要把修复过程展开到每个周期。

建议字段：

| 字段 | 含义 |
|---|---|
| `damaged_link_id` | 受损道路编号 |
| `edge_id` | 对应路段编号 |
| `repair_time_min` | 完全修复所需时间 |
| `assigned_crew_id` | 当前分配维修队 |
| `start_period` | 开始维修周期 |
| `worked_time_by_period` | 各周期累计维修时间 |
| `progress_by_period` | 各周期累计修复进度 |
| `recovery_stage_by_period` | 各周期恢复阶段 |

修复进度计算：

```text
p_a^t = min(1, 累计维修时间_a^t / 完全修复时间_a)
```

如果周期长度为 8 小时，即 480 分钟，一条道路完全修复时间为 900 分钟，则：

```text
第 1 期维修 480 分钟：p = 480 / 900 = 0.533
第 2 期再维修 420 分钟：p = 1.000
```

在该例中，第 1 期结束时道路已进入“临时抢通/低容量”状态，不必等到第 2 期完全修复才允许部分车辆通行。

## 6. 新增数据表 4：周期路网状态

每个周期都需要生成一张动态路网状态表，供下层配送路径计算使用。

| 字段 | 含义 |
|---|---|
| `period` | 周期编号 |
| `edge_id` | 路段编号 |
| `base_travel_time_min` | 正常基础通行时间 |
| `base_capacity_pcu_h` | 正常道路容量 |
| `recovery_progress` | 当前修复进度 |
| `recovery_stage` | 当前恢复阶段 |
| `current_capacity_pcu_h` | 当前道路容量 |
| `vehicle_type` | 车辆类型 |
| `is_passable` | 该车型当前是否可通 |
| `travel_time_min` | 当前车型通过该路段的实际通行时间 |

当前容量计算：

```text
C_a^t = C_a^0 * g(p_a^t)
```

当前通行时间可先使用简化规则：

```text
如果车辆不可通行：travel_time = INF
如果车辆可通行：travel_time = t_a^0 / max(g(p_a^t), epsilon)
```

后续升级为 BPR 函数：

```text
t_a^t = t_a^0 * [1 + alpha * (f_a^t / C_a^t)^beta]
```

## 7. 建议程序数据结构

建议后续将数据抽成以下模块：

```text
scripts/data/wenchuan_case.py
scripts/data/recovery_policy.py
scripts/data/vehicle_profiles.py
```

核心表结构：

| 数据表 | 建议字段 |
|---|---|
| `nodes` | `node_id`, `name`, `type`, `supply`, `demand` |
| `edges` | `edge_id`, `from_node`, `to_node`, `travel_time_min`, `capacity_pcu_h` |
| `damaged_links` | `damaged_link_id`, `edge_id`, `repair_time_min`, `endpoint_a`, `endpoint_b` |
| `repair_crews` | `crew_id`, `station_node_id`, `initial_node_id`, `repair_speed_km_h` |
| `vehicles` | `vehicle_type`, `capacity_ton`, `available_count`, `pcu_impact`, `min_recovery_progress`, `speed_factor` |
| `recovery_stages` | `stage_id`, `progress_lower`, `progress_upper`, `capacity_ratio`, `description` |
| `period_edge_state` | `period`, `edge_id`, `recovery_progress`, `capacity_ratio`, `current_capacity`, `vehicle_type`, `is_passable`, `travel_time` |

## 8. 数据缺口与处理建议

| 缺口 | 处理建议 |
|---|---|
| 真实道路等级和车道数 | 先沿用现有容量估算，后续可用道路等级数据替换 |
| 不同车型真实限载限宽要求 | 先用 `theta_v` 构造场景参数，做敏感性分析 |
| 修复过程中的阶段性抢通时间 | 由总修复时间按比例拆分，例如 30%、60%、80%、100% |
| 灾后动态需求 | 第一版先固定需求，后续再加入滚动更新 |
| 普通交通流 | 第一版暂不纳入，避免模型过大 |

## 9. 与创新点的对应关系

| 创新点 | 数据支撑 |
|---|---|
| 道路状态不只是二元可达，而是容量随修复进度逐步恢复 | `recovery_stages`, `period_edge_state`, `recovery_progress`, `current_capacity` |
| 不同车辆类型与道路恢复程度匹配 | `vehicles.min_recovery_progress`, `period_edge_state.is_passable` |
| NSGA-II + ALNS 混合算法 | 数据需支持染色体解码、周期路网更新、局部搜索路径重算 |

## 10. 第一版实验推荐口径

为了让模型可实现、可解释，第一版建议采用：

1. 原汶川案例节点、需求、路网、车辆和维修队数据。
2. 受损道路使用原论文修复时间。
3. 道路容量使用现有估算容量。
4. 容量恢复采用 5 阶段分段函数。
5. 车辆通行阈值采用 4 类车默认参数。
6. 需求量先固定，后续再扩展为滚动更新。

这样可以把创新集中在“道路容量渐进恢复 + 车辆类型通行约束”，避免同时引入过多不确定因素。
