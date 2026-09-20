# v2 执行状态表

状态只允许四种取值：**待执行**、**执行中**、**通过**、**阻塞**。
最后更新：2026-09-20（文档一致性清理轮）。当前基准 HEAD：`7c7a6ab`。

**当前状态**：全量测试 `uv run python -m unittest discover -s tests -v` → **130 个，130 通过，0 失败，0 错误**。
**当前结论依据目录**：`outputs/claude_v2_reviewfix2/`。`outputs/claude_v2/`（首轮）与
`outputs/claude_v2_reviewfix/`（第一轮修正后）**仅作为修复历史与前后对照**，不再作为当前结果。

下文各阶段条目中标注的测试数字是**该阶段当时**的实际值，保留为历史记录，不等于当前总数。
基线（`1a1a5d5`）测试为 **21 个，21 通过**，其中 `tests/legacy/` 2 个被 discover 发现，单独运行亦通过。

## 阶段状态

| 阶段 | 内容 | 状态 | 证据 |
|---|---|---|---|
| P0 | 基线核验与范围冻结 | 通过 | 本节；[模型合同](model_v2_contract.md)；`outputs/claude_v2/baseline_legacy/` |
| P1 | 公平配给、时间轴与守恒 | 通过 | `tests/test_model_contract.py` M01–M11（12 个用例）；`EvaluationConfig`；见下 |
| P2 | 完整决策保存、恢复和同模型回放 | 通过 | `scripts/reproduce/solution_io.py`、`replay_solutions.py`；`tests/test_solution_io.py`（当前 13 个用例） |
| P3 | 搜索档案、预算与评分修正 | 通过 | `benchmark_algorithms.py`；`tests/test_search_contract.py`（当前 14 个用例） |
| P4 | 不同规划模型统一执行回放 | 通过 | `run_model_ablation.py` 子集入口、`replay_solutions.py --execution-model full`；`tests/test_common_execution.py`（8 个用例） |
| R1–R5 | 复审修正第一轮（精度、目录约定、Full 校验、报告、加载） | 通过 | 见下；[v2 小预算诊断报告](pilot_v2_report.md) §10 |
| 复审第二轮 | 坐标空间与 Full 曲线校验 | 通过 | 见下；[v2 小预算诊断报告](pilot_v2_report.md) §11 |
| P5 | 小预算诊断与交付 | 通过（已按两轮复审修正重跑） | **`outputs/claude_v2_reviewfix2/`**；[v2 小预算诊断报告](pilot_v2_report.md) |
| P6 | 正式实验方案与运行 | 待执行（本轮不启动） | — |
| P7 | 专用大邻域与动态扩展 | 待执行（本轮不实现） | — |

## P0 基线与证据

环境：Python 3.12.11（`.python-version` = 3.12），uv 0.11.15，macOS (darwin 27.0.0)。
`uv sync` 退出码 0（Resolved 19 packages / Checked 18 packages）。

基线 legacy smoke（不覆盖 `outputs/validation_20260907/`）：

```bash
uv run python scripts/reproduce/run_benchmark.py \
  --suite smoke --cases S020 --instance-seeds 101 \
  --solver-repeats 1 --algorithms spt nsga2 \
  --max-evaluations 12 --pop-size 4 \
  --output-dir outputs/claude_v2/baseline_legacy
```

退出码 0。产物：`runs.csv`、`pareto_points.csv`、`convergence.csv`、`instances.csv`、
`aggregate_by_size.csv`、`experiment_manifest.json`。
该运行使用当时入口的默认值，即 legacy 语义；它不是 v2 结果，也不用于任何 v2 结论。

## P1 实现与验收

新增 `EvaluationConfig`（`scripts/reproduce/capacity_recovery.py`），固定 `legacy` / `v2` 两套一致的评价档案；
混合档案（如 `model_version="v2"` + `fair_share_cap=True`）直接报错，不接受半迁移配置。

- **配给**：v2 取消 `fair_ceiling` 逐点硬上限，需求点只受自身剩余需求限制；公平优先阶段与第二阶段保留。
- **时间轴**：v2 在期初 `(t-1)*eta` 采样路况，本期施工下期才可用。
- **当期到货**：单程时间超过 `eta` 的候选在分配处被拒绝，不扣库存、车辆额度与边容量，不计入满足率；
  被拒候选单独计数为 `time_infeasible_candidates`，与拓扑 `average_reachable_ratio` 分开命名。
- **新增指标**：`unmet_ratio_hours`、`zero_service_ratio`、`remaining_supply`、`total_delivered`、
  `min/max_period_delivered`、`time_feasible_demand_periods`。
- **车型阈值**：统一使用 `PROGRESS_TOLERANCE = 1e-9` 判断边界。

测试记录：`uv run python -m unittest discover -s tests` → **33 个测试，33 通过，0 失败，0 错误**
（基线 21 + 新增 `tests/test_model_contract.py` 12）。legacy 历史行为全部保留，未删除或放宽任何旧断言。

合同测试中发现的既有实现特征（非本轮修改，已固化为回归断言）：
车辆额度按**趟次**计，一次分配无论载重都消耗一整趟，因此单车型 60 吨、1 辆时只能服务一个需求点。

## P5 执行记录（当前状态，取自 `outputs/claude_v2_reviewfix2/`）

当前全量测试：`uv run python -m unittest discover -s tests -v` → **130 个，130 通过，0 失败，0 错误**。
执行的诊断命令、评价预算核对、算法与模型诊断结果、产物路径与限制全部见
[v2 小预算诊断报告](pilot_v2_report.md)。

关键诊断结论（限于 S025 与 `capacity_scale=0.05`，不外推）：

- 最新算法同模型回放（`--execution-model saved`）：**86 个决策，0 失败**，最大绝对误差 0.0。
- 最新规划模型统一 Full 回放：**37 个决策，0 失败**；其中 9 个的规划模型即执行模型、28 个为降级规划模型。
- Full 同模型恒等检查**无误差**（规划指纹等于执行指纹时逐位复现）。
- 在当前 S025 标定下，**HT/EC 在固定 SPT 决策及本轮保存前沿中没有观察到系统性目标影响**；
  本轮证据**不足以判断二者一般无效**。HT 与 EC 是否重要取决于前沿中有哪些决策，这属于标定问题。
- 车队趟次比道路容量更紧**只能作为待验证解释**，不是结论：本轮未做资源放宽对照。
- 四模型子集未输出任何主效应或交互显著性结果。

## R1–R5 复审修正

首轮 P0–P5 交付后审读提出的五项问题**全部复现属实**并已修复。
该轮完成时回归用例为 110 个（当时值）；当前总数为 130 个。
本轮结论依据当时为 `outputs/claude_v2_reviewfix/`，现已被第二轮取代。

| 项 | 问题 | 修复 | 回归（当前用例数） |
|---|---|---|---|
| R1 | 目标以原始浮点比较，1e-13 噪声决定代表方案（18/18 运行） | 固定服务分辨率 + 量化比较键，贯通支配/档案/去重/拥挤距离/代表/质量指标；进入 model_fingerprint | `test_objective_precision.py` 22 例 |
| R2 | run key 不碰撞 ≠ 目录不混用 | 目录级 `experiment_contract.json` 写入前校验；汇总与回放共用目录运行集合 | `test_experiment_contract.py` 9 例 |
| R3 | `--execution-model full` 只查物理哈希 | 强制校验 v2/PR/HT/EC 并重新计算而非信任标签；同哈希不可换模型；同模型必须逐位复现 | `test_full_execution_validation.py` 当前 19 例 |
| R4 | "HT 完全无效" 与组均值当逐方案最大变化 | 新增 `summarize_replay.py`：运行内先归纳、三类结果分开汇报、给出非零数与最大差出处 | `test_replay_summary.py` 5 例 |
| R5 | `int()` 静默截断；`distinct_evaluated` 名不副实 | 严格类型与完整排列校验；拆出 `actual_evaluations`/`evaluation_snapshots`/`unique_decisions` | `test_solution_io.py`/`test_search_contract.py` |

修正带来的实质变化：代表方案 F1 均值 4.1244 → 3.7933，前沿点数 467 → 81（量化合并亚分辨率点）。

## 复审修正第二轮（坐标空间与 Full 曲线）

`65c1014` 复审指出两处未封闭：质量指标与拥挤距离仍在原始浮点坐标上度量；Full 谓词只查标签不查其下的数据。
均已复现、修复并重跑。

| 项 | 问题（已复现） | 修复 | 回归 |
|---|---|---|---|
| A | 同键两点得不同 HV（1.331 vs 0.847）、参考前沿重复计数、raw 抖动可改变拥挤距离 | 去重/参考前沿/归一化上下界/距离坐标/拥挤排序与端点全部改用整型量化键；原始值仍原样存档 | `test_objective_precision.py` 的 pooled 用例 + 复审包 5 例 |
| A | `model_ablation_analysis.py` 未传精度，静默退回 EXACT | 显式推导精度，并拒绝跨版本池化 | 同上 |
| B | `PR=True` + 二元阶段表、`HT=True` + 统一阈值都能通过 Full 校验且哈希自洽 | 场景声明可追溯的 `FullExecutionProfile`，逐项比对曲线与阈值；二元曲线结构性拒绝 | `test_full_execution_validation.py` 新增 8 例 + 复审包 2 例 |
| B | 从降级实例直接重新打开开关会继续携带降级数据 | `model_factor_variant` 从声明档案恢复；无档案可恢复时显式报错 | 同上 |

本轮起结论依据为 `outputs/claude_v2_reviewfix2/`；`outputs/claude_v2/` 与 `outputs/claude_v2_reviewfix/` 保留为对照。
当前全量测试 **130 个全通过**。第二轮的两项修复（量化坐标、Full 曲线校验）已纳入上方阶段表的
「复审第二轮」一行，属于**当前验收状态**。

## 保护的用户已有改动

工作树中未跟踪文件：`vrp_research_claude_execution_plan.md`、`claude_post_p5_fix_plan.md`（任务书本身）。
未执行 `git reset --hard`、未清理用户产物、未强制推送。
