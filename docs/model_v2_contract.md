# 模型 v2 评价语义合同

本文件冻结第一轮 v2 评价语义。它只描述**已决定并已实现**的模型约定，不是实验结果页，也不证明模型能刻画真实现场。
基准提交：`1a1a5d5`（2026-09-07）。状态与验收记录见[执行状态表](execution_status_v2.md)。

## 1. 为什么需要 v2

legacy 口径保留了三处与研究问题不一致的隐性约定，它们会让搜索算法的比较被模型缺陷污染：

1. **全局供需比硬上限**。每个需求点的本期目标被 `min(1, total_supply / total_demand)` 压制，即使某个点永久不可达、其余可配送资源闲置，可达点也拿不到超过该比例的量。
2. **期末状态发货**。第 t 期按 `time = t*eta` 的期末路况计算配送，本期施工形成的能力被提前用于本期配送。
3. **没有当期到货的时间可行性检查**。单程时间超过一个周期时长的路径仍然扣减库存、车辆额度与边容量并计入本期到货。

v2 修正这三处。它**不是**"更真实的物理仿真"，而是在同一套粗离散近似下的时间语义一致性修正。

## 2. 版本与配置

单一共享评价实现，不复制 `capacity_recovery.py`，也不引入第二套配送器。评价行为由 `EvaluationConfig` 决定：

| 字段 | 取值 | legacy | v2 |
|---|---|---|---|
| `model_version` | `legacy` / `v2` | `legacy` | `v2` |
| `fair_share_cap` | 是否按全局供需比限制每点目标 | `True` | `False` |
| `dispatch_timing` | `period_end_legacy` / `period_start` | `period_end_legacy` | `period_start` |
| `enforce_within_period_arrival` | 超期运输不得计入本期到货 | `False` | `True` |
| `fleet_semantics` | 第一轮固定 | `exogenous_period_trip_budget` | `exogenous_period_trip_budget` |

`fleet_semantics` 在第一轮是不可切换的常量，写入合同以便 manifest 与报告显式记录。

**入口默认值**：`run_benchmark.py`、`run_model_ablation.py`、`replay_solutions.py` 的默认 `--model-version` 为 `legacy`，新诊断命令一律显式传 `--model-version v2`。
动态入口（`dynamic_interaction_experiments.py`）在第一轮显式沿用 legacy，不静默迁移；其旧结果不得与 v2 结果汇总。

## 3. 配给政策

### 3.1 legacy

保留原实现：`fair_ceiling = min(1, total_supply / total_demand)`，两轮分配都用它作为逐点上限。

### 3.2 v2

1. **取消逐点全局供需比硬上限**。每个需求点的上限只由**自身需求**决定（`remaining_demand`）。
2. **保留公平优先阶段**：第一阶段仍按最大化最小满足率求解 `target_level`，但 `target_level` 不再被 `fair_ceiling` 截断。
3. **第二阶段对剩余可服务需求继续分配**：目标为 `remaining_demand`，仍受车辆趟次、车型通行阈值、边容量、供应点剩余库存约束。
4. **不因某点永久不可达而静默停机**：只要仍有可配送资源与可达需求点，分配器继续工作。

**两轮 targets 语义（关键不变式）**：`_allocate_vehicle_aware()` 内部用**本期 `delivered`** 扣减目标，因此两轮传入的 `targets` 都是"**本期总目标**"（累计口径），不是"本轮增量"。第二轮不能先减一次本期配送再由分配器重复扣减。

> 该政策是**新的明确配给政策**，不是"修好了一个 bug"。它需要独立诊断；不能把政策变化带来的收益全部归功于搜索算法。

## 4. 时间轴与当期到货

### 4.1 期定义

第 t 期为 `[(t-1)*eta, t*eta]` 分钟闭区间。

### 4.2 规则

- 本期所有配送依据**期初**进度（`(t-1)*eta` 时刻的路况）。
- 本期施工形成的新增道路能力**下期**才能使用。
- 候选路径必须满足**单程运输时间 ≤ eta**，才允许扣减库存、车辆额度、边容量并计入本期到货。
- **超时路径不扣任何资源、不计入满足率**。该排除发生**在分配决策处**，不是在最终汇总时对数值做剪裁。

### 4.3 道路容量

道路容量仍是**期总吞吐**约束（PCU·期），第一轮不建模排队与精确流入时间。这是时间语义一致的**粗离散近似**，不是精确交通仿真。

### 4.4 车辆额度

同一期的车辆额度是**外生的共享运输趟次预算**：每种车型的额度最多使用一次，**不按供应点分别复制**。第一轮不模拟同一实体车队的下一期空间位置与返程。

## 5. 目标与指标

第一轮保留三目标顺序与主要定义：

```text
F1 = sum_t (1 - total_satisfaction_at_period_end[t])     单位：比例—周期
F2 = vehicle_travel_minutes
     + repair_time_weight * (repair_work_minutes + crew_transfer_minutes)   单位：加权分钟
F3 = -final_min_satisfaction
```

三目标均为**最小化**。v2 第一轮 `crew_transfer_minutes = 0`。

新增与保留的辅助指标：

| 指标 | 含义 |
|---|---|
| `unmet_ratio_hours` | `F1 * eta_hours`；**离散**期末采样指标，不是按精确到货时间积分的连续剥夺成本 |
| `zero_service_ratio` | 服务量为 0 的需求点占比 |
| `remaining_supply` | 期末各供应点剩余库存 |
| `period_delivered` | 分期配送量 |
| 时间可行性统计 | 被**当期时长**约束拒绝的候选数，独立命名，不与拓扑可达率混用 |
| `average_reachable_ratio` | 保留原含义（拓扑可达），不得把 9 小时路径报告成 8 小时内可服务 |

**不得**把维修总工时描述为维修 makespan。未来若改变时间步长，必须同时固定资源强度并用正确单位比较，不能直接比较原始 F1。

## 6. 第一轮明确简化（不得声称已验证）

- **无维修队转场时间**（`crew_transfer_time_scale = 0`）。
- **无同路网维修队可达性约束**（`crew_min_access_progress = 0`）。

v2 在接收到**非零**上述设置时**显式报错**，不静默忽略。后续统一约束后才能解除限制。不得把这一简化描述为"已经验证真实维修队可达性"。

## 7. 配置传播与隔离

- `model_factor_variant()` **完整继承**版本与评价配置，只改变指定的模型因素；不得漏传新字段，不得原地修改基础实例。
- manifest 记录**实际生效的配置**，不只记录字符串 `v2`。
- 任何研究性覆盖都需要独立配置指纹；默认不启用组合自由覆盖。
- 合法研究性覆盖**不得**跨版本混用或与 legacy 结果汇总。

## 8. 指纹

| 指纹 | 覆盖内容 |
|---|---|
| `physical_instance_hash` | 共同物理场景快照（节点、边、旅行时间、容量、受损道路与维修时长、供需、维修队、车型、恢复阶段、eta、horizon）。同一基础场景的四个规划模型共享 |
| `model_fingerprint` | 规划/评价假设、车型阈值变体、版本与评价配置 |
| `decision_hash` | 三段完整决策 |
| `run_key` | 实例 + 模型 + 算法 + solver seed + 预算 + 代码版本 |

序列化规则：标准 JSON；目标与模型参数必须**有限**，不得写 `NaN`/`Infinity`；允许无限的展示字段（如拥挤距离）写 `null` 并说明。无向边排序、节点标识类型及浮点序列化规则固定，保证指纹可重建。
