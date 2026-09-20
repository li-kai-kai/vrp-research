# v2 执行状态表

状态只允许四种取值：**待执行**、**执行中**、**通过**、**阻塞**。
最后更新：2026-09-20。

基准 HEAD：`1a1a5d5dd47d000556b107984ca5fa112f86bad0`（与本任务书基准一致，无差异）。
基线测试：`uv run python -m unittest discover -s tests -v` → **21 个测试，21 通过，0 失败，0 错误**（其中 `tests/legacy/` 2 个被 discover 发现，单独运行亦通过）。

## 阶段状态

| 阶段 | 内容 | 状态 | 证据 |
|---|---|---|---|
| P0 | 基线核验与范围冻结 | 通过 | 本节；[模型合同](model_v2_contract.md)；`outputs/claude_v2/baseline_legacy/` |
| P1 | 公平配给、时间轴与守恒 | 待执行 | — |
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

## 保护的用户已有改动

工作树中未提交文件：`vrp_research_claude_execution_plan.md`（本任务书本身）。
未执行 `git reset --hard`、未清理用户产物、未强制推送、未合并到 `main`。
