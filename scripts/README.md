# 当前研究运行指南

在仓库根目录使用 Python 3.12+ 和锁定依赖。所有模型入口仅支持 v2。

```bash
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv run python scripts/reproduce/run_benchmark.py --suite smoke --cases S020 --instance-seeds 1 --solver-repeats 1 --algorithms nsga2 --max-evaluations 12 --pop-size 4 --output-dir outputs/local_smoke
uv run python scripts/reproduce/run_model_ablation.py --suite smoke --cases S020 --instance-seeds 1 --solver-repeats 1 --algorithm nsga2 --max-evaluations 12 --pop-size 4 --model-ids PR1_HT1_EC1 PR0_HT1_EC1 PR1_HT0_EC1 PR1_HT1_EC0 --output-dir outputs/local_ablation
uv run python scripts/reproduce/replay_solutions.py --input-root outputs/local_ablation --execution-model full --output-dir outputs/local_replay
```

SPT、VND、NSGA-II、均匀/自适应局部搜索共用评价器与预算。四模型诊断使用NSGA-II。正式完整三因素统计要求既定的八组合与NSGA-II协议（`FORMAL_ALGORITHM = "nsga2"`，冻结于[正式实验协议](../docs/formal_experiment_protocol.md)）；子集只出描述性结果。

## 当前证据复核

```bash
uv run python scripts/reproduce/replay_solutions.py --input-root outputs/claude_v2_reviewfix2/pilot_algorithm --execution-model saved --output-dir outputs/check_algorithm
```

共享RunStore记录完整三段决策、实例/执行快照、参数、种子和指纹。`--resume`只接受同一合同下的完整运行。源码变化后，新搜索必须选择新目录；冻结档案仍可回放。报告中的原机器绝对路径是来源记录，不是当前运行路径。

## 并行实验

```bash
uv run python exp/parallel_nsga2.py --validate-only
uv run python exp/parallel_nsga2.py --output-dir outputs/parallel_new
```

并行入口使用Linux/WSL的fork；进程内串行与多个worker共用随机数、预算和缓存规则。`exp/full_budget/`是冻结的136次计时与目标前沿；脚本拒绝将新实验写入此目录。新输出默认在 `outputs/parallel_nsga2/`。

## 诊断与分析模块

| 模块 | 用途 |
|---|---|
| capacity_recovery、model、instance_generator | 共享v2评价与实例数据 |
| benchmark_algorithms、run_benchmark | 统一预算求解与算法对照 |
| run_model_ablation、model_ablation_analysis | 配对模型消融及统计 |
| solution_io、replay_solutions、summarize_replay | 完整方案保存、恢复和回放汇总 |
| mechanism_applicability、mechanism_zone_search、build_mechanism_audit | 暴露/参与/目标诊断、分区标定、证据投影 |
| ht_natural_corridor | WEN38天然通行走廊与半真实场景 |
| service_diagnostics、common_execution_analysis | 服务轨迹与共同执行 |
| execution_side_analysis | 执行侧配对检验（家族预声明 + Holm 校正；正式实验用） |
| budget_convergence_analysis | 预算稳定性及资源审计 |
| plot_initial_network、plot_benchmark_results、plot_common_execution、plot_budget_convergence、plot_wen38_key_corridors | 从实际结果绘图 |

各入口的参数使用 `--help` 查询；新的长实验先冻结方案并指定新输出目录。[当前实验索引](../docs/experiments.md)列出已有结论及限制。
