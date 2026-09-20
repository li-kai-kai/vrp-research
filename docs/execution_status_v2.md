# v2 执行状态表

状态只允许四种取值：**待执行**、**执行中**、**通过**、**阻塞**。
最后更新：2026-09-20。

基准 HEAD：`1a1a5d5dd47d000556b107984ca5fa112f86bad0`（与本任务书基准一致，无差异）。
基线测试：`uv run python -m unittest discover -s tests -v` → **21 个测试，21 通过，0 失败，0 错误**（其中 `tests/legacy/` 2 个被 discover 发现，单独运行亦通过）。

## 阶段状态

| 阶段 | 内容 | 状态 | 证据 |
|---|---|---|---|
| P0 | 基线核验与范围冻结 | 通过 | 本节；[模型合同](model_v2_contract.md)；`outputs/claude_v2/baseline_legacy/` |
| P1 | 公平配给、时间轴与守恒 | 通过 | `tests/test_model_contract.py` M01–M11（12 个用例）；`EvaluationConfig`；见下 |
| P2 | 完整决策保存、恢复和同模型回放 | 通过 | `scripts/reproduce/solution_io.py`、`replay_solutions.py`；`tests/test_solution_io.py`（9 个用例） |
| P3 | 搜索档案、预算与评分修正 | 通过 | `benchmark_algorithms.py`；`tests/test_search_contract.py`（13 个用例） |
| P4 | 不同规划模型统一执行回放 | 通过 | `run_model_ablation.py` 子集入口、`replay_solutions.py --execution-model full`；`tests/test_common_execution.py`（8 个用例） |
| R1–R5 | 复审修正（精度、目录约定、Full 校验、报告、加载） | 通过 | 见下；[v2 小预算诊断报告](pilot_v2_report.md) §10 |
| P5 | 小预算诊断与交付 | 通过（已按 R1–R5 重跑） | `outputs/claude_v2/`；[v2 小预算诊断报告](pilot_v2_report.md) |
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

## P5 执行记录

最终测试：`uv run python -m unittest discover -s tests -v` → **63 个，63 通过，0 失败，0 错误**。
执行的诊断命令、评价预算核对、算法与模型诊断结果、产物路径与限制全部见
[v2 小预算诊断报告](pilot_v2_report.md)。

关键诊断结论（限于 S025 与 `capacity_scale=0.05`，不外推）：

- 同模型回放 467 个决策，最大绝对/相对误差均为 0.0。
- 统一 Full 执行回放 152 个决策，0 失败；Full 组自身规划目标与执行回放逐位一致。
- 该标定下**异质阈值与边容量不改变任何目标**，绑定资源是车队趟次预算；这是需要下一轮定位的标定问题。
- 四模型子集未输出任何主效应或交互显著性结果。

## R1–R5 复审修正

首轮 P0–P5 交付后审读提出的五项问题**全部复现属实**并已修复，回归用例 110 个全通过。
结论依据已改为 `outputs/claude_v2_reviewfix/`；修正前产物保留在 `outputs/claude_v2/` 作对照。

| 项 | 问题 | 修复 | 回归 |
|---|---|---|---|
| R1 | 目标以原始浮点比较，1e-13 噪声决定代表方案（18/18 运行） | 固定服务分辨率 + 量化比较键，贯通支配/档案/去重/拥挤距离/代表/质量指标；进入 model_fingerprint | `test_objective_precision.py` 17 例 |
| R2 | run key 不碰撞 ≠ 目录不混用 | 目录级 `experiment_contract.json` 写入前校验；汇总与回放共用目录运行集合 | `test_experiment_contract.py` 9 例 |
| R3 | `--execution-model full` 只查物理哈希 | 强制校验 v2/PR/HT/EC 并重新计算而非信任标签；同哈希不可换模型；同模型必须逐位复现 | `test_full_execution_validation.py` 11 例 |
| R4 | "HT 完全无效" 与组均值当逐方案最大变化 | 新增 `summarize_replay.py`：运行内先归纳、三类结果分开汇报、给出非零数与最大差出处 | `test_replay_summary.py` 5 例 |
| R5 | `int()` 静默截断；`distinct_evaluated` 名不副实 | 严格类型与完整排列校验；拆出 `actual_evaluations`/`evaluation_snapshots`/`unique_decisions` | `test_solution_io.py`/`test_search_contract.py` |

修正带来的实质变化：代表方案 F1 均值 4.1244 → 3.7933，前沿点数 467 → 81（量化合并亚分辨率点）。

## 保护的用户已有改动

工作树中未提交文件：`vrp_research_claude_execution_plan.md`（本任务书本身）。
未执行 `git reset --hard`、未清理用户产物、未强制推送、未合并到 `main`。
