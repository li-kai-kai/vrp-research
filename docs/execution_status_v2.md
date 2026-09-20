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
| P2 | 完整决策保存、恢复和同模型回放 | 待执行 | — |
| P3 | 搜索档案、预算与评分修正 | 待执行 | — |
| P4 | 不同规划模型统一执行回放 | 待执行 | — |
| P5 | 小预算诊断与交付 | 待执行 | — |
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

## 保护的用户已有改动

工作树中未提交文件：`vrp_research_claude_execution_plan.md`（本任务书本身）。
未执行 `git reset --hard`、未清理用户产物、未强制推送、未合并到 `main`。
