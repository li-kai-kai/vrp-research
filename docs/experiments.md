# 实验进展与结果

核验日期：2026-09-07（legacy 证据，下文 §「legacy 历史证据」）；v2 诊断更新：2026-09-20。
当前模型、算法对照、消融统计和动态机制均可运行，**正式 publication 实验尚未完成**。
本页只将本地可核验产物列为当前证据；旧报告中的数值保留在历史归档。

> **版本边界**：本页 §「legacy 历史证据」及其后的数值全部在 **legacy 评价语义**下产生，
> 保留为历史回归证据，**不得与 v2 结果汇总**。v2 的新诊断见
> [v2 小预算诊断报告](pilot_v2_report.md) 与[模型 v2 合同](model_v2_contract.md)；
> 两者的配给政策、时间轴和当期到货规则不同，数值不可直接比较。

## 证据总览

| 工作 | 当前完成情况 | 证据与限制 |
|---|---|---|
| 回归测试 | 基线 21/21 通过；v2 后 63/63 通过 | 主线与 legacy 测试；覆盖实现约束，不证明模型现实有效性 |
| 算法对照 | 3 个合成规模 × 4 算法，共 12 行结果 | 每例 1 个实例种子、1 次求解，搜索评价预算 12，种群 4 |
| 模型消融 | 3 个规模 × 8 个模型，共 24 行结果 | 每块八组合完整且配对；每案例只有 1 个统计单位 |
| 动态 S8 | 四机制 × 5 个扰动种子，共 20 行结果 | 重新运行后三份 CSV 与现有产物字节一致 |
| Pareto 决策导出 | 回归测试验证 archive、完整决策与 manifest | 旧 2026-08-09 三种子实验仅剩报告，当前本地产物与旧归档中未找到对应结果集 |
| 正式 benchmark/模型消融 | 运行和分片分析入口已实现 | 未发现完整 publication 产物，不能宣称已经完成或排名稳定 |
| 12 组动态资源网格 | 入口保留，旧结果已归档 | 当前口径的多偏差、多种子网格尚待运行 |
| 绘图 | 当前 benchmark CSV 和共享汶川实例可生成图片 | 已移除硬编码性能示意入口 |

本地结果根目录：`outputs/validation_20260907/`。版本化的[核验摘要与 SHA-256](validation_20260907.json)保存关键数值、源文件指纹和产物指纹。benchmark 与消融沿用清理前已生成的当日验证产物，其 manifest 中的源文件哈希全部匹配当前代码；本轮未将它们重新标记为新运行。动态 S8 已独立重跑核验。

原始 CSV、完整参数 manifest、图和历史压缩包都被 Git 忽略；克隆仓库后须运行下列命令重建。摘要 JSON 便于审计当前文档，但不能替代完整原始产物。

## 动态 S8：已重跑的五种子结果

参数：固定汶川网络；`repair_scale=2`、维修队 2、`capacity_scale=0.05`、效率偏差 `delta=0.30`；场景种子 1–5，对应效率种子 40001–40005。维修队转场时间缩放和通行进度限制均为 **0**。因此这些结果不能用于声称已经验证有转场约束的收益。

CUA 为累计未满足比例—周期，越低越好。下表均为五次运行的算术平均：

| 机制 | CUA | 最终总满足率 | 最终最低满足率 | 平均可达率 |
|---|---:|---:|---:|---:|
| binary_static | 4.193459 | 0.598234 | 0.000000 | 0.708571 |
| progressive_static | 2.947983 | 0.797307 | 0.797307 | 0.885714 |
| progressive_openloop | 2.598613 | 0.788972 | 0.637845 | 0.916190 |
| progressive_rolling | 2.545638 | 0.797307 | 0.797307 | 0.923810 |

以 `openloop CUA - rolling CUA` 为正向改善，五个配对差依次为 **0.028253、0、0、0.208368、0.028253**，均值 **0.052975**。即 3 次改善、2 次持平；有限种子的单一资源情景只能说明新信息可改变决策与绩效，不能推断普遍优势或统计显著性。零偏差时的 open-loop/rolling 一致性由回归测试检查。

原始证据：`dynamic_s8/mechanism_summary.csv`、`period_dynamics.csv`、`repair_efficiency_realizations.csv`。

```bash
uv run python scripts/reproduce/dynamic_interaction_experiments.py \
  --scenario wenchuan --seeds 5 --seed-start 1 \
  --repair-scale 2 --crews 2 --capacity-scale 0.05 \
  --repair-efficiency-deviation 0.30 \
  --crew-transfer-time-scale 0 --crew-min-access-progress 0 \
  --output-dir outputs/validation_20260907/dynamic_s8
```

## 算法 smoke：只验证对照流程

每个实例 seed=1，solver seed 起点 50000，随机算法各重复 1 次；种群 4、最大评价 12，SPT 只做 1 次构造评价。实际 solver seed 及运行参数见 `benchmark/runs.csv` 和 `experiment_manifest.json`。

| 案例 | 算法 | HV ↑ | IGD ↓ |
|---|---|---:|---:|
| S020 | SPT | 0.038671 | 0.734123 |
| S020 | VND | 1.228229 | 0.214486 |
| S020 | NSGA-II | 0.257412 | 0.423535 |
| S020 | NSGA-II + ALNS | 0.246339 | 0.385846 |
| M060 | SPT | 0.009007 | 1.199264 |
| M060 | VND | 0.155005 | 0.706854 |
| M060 | NSGA-II | 1.160109 | 0.083959 |
| M060 | NSGA-II + ALNS | 0.585070 | 0.341658 |
| L120 | SPT | 0.013328 | 0.761456 |
| L120 | VND | 0.022417 | 0.712722 |
| L120 | NSGA-II | 0.403992 | 0.371190 |
| L120 | NSGA-II + ALNS | 0.218144 | 0.473477 |

HV 使用每个实例 pooled reference front 的归一化目标，参考点 `(1.1, 1.1, 1.1)`，因此 HV 可以大于 1。不同实例的归一化范围不同，不能把跨规模 HV 直接当成难度变化。当前样本中混合算法没有稳定优于对照；12 次评价远不足以检验收敛或算法优越性。

```bash
uv run python scripts/reproduce/run_benchmark.py \
  --suite smoke --instance-seeds 1 --solver-repeats 1 \
  --solver-seed-start 50000 --max-evaluations 12 --pop-size 4 \
  --output-dir outputs/validation_20260907/benchmark
uv run python scripts/plot_benchmark_results.py \
  --input outputs/validation_20260907/benchmark/runs.csv \
  --output-dir outputs/validation_20260907/figures/benchmark
```

## 模型消融 smoke：八因素组合完整

案例 S020/M060/L120，各实例 seed=1、solver seed=60000；固定 `nsga2_alns`，预算 12、种群 4。三个二元因素为 PR（渐进恢复）、HT（异质通行阈值）和 EC（边容量），每个配对块包含全部八组合，`factorial_completeness.csv` 三行均为 `complete=1`。

已产出原始目标、Pareto 点、pooled reference front、模型汇总、主效应和二阶交互表。每案例只有 **1 个独立统计单位**，不能把八个因素组合视作八个独立样本，也不能将这些 smoke 效应表用作正式显著性结论。

```bash
uv run python scripts/reproduce/run_model_ablation.py \
  --suite smoke --instance-seeds 1 --solver-repeats 1 \
  --solver-seed-start 50000 --max-evaluations 12 --pop-size 4 \
  --bootstrap-samples 5000 --permutation-samples 20000 --analysis-seed 20260831 \
  --output-dir outputs/validation_20260907/model_ablation
```

该入口按实例 seed 加偏移生成实际 solver seed，因此 50000 起点对应此处 60000；复核应以 manifest 与 CSV 为准。

## v2 诊断（2026-09-20）

v2 评价语义下的首轮小预算诊断已完成，入口为 `--model-version v2`。为避免与上表混淆，全部结果单独记录在
[v2 小预算诊断报告](pilot_v2_report.md)，本页不再重复其数值。要点：

- 算法诊断（S025、2 实例种子 × 3 solver 重复、预算 500 × 3 算法）显示 `nsga2_ls` 与 `nsga2_alns`
  的**算子偏好**明显不同，但这不构成性能优势证据。
- 模型价值诊断显示，在 S025 与 `capacity_scale=0.05` 下**异质阈值与边容量不改变任何目标**；
  绑定的资源是车队趟次预算。这是标定问题，需要先在下一轮定位机制绑定边界。
- 467 + 152 个已保存决策的同模型与统一 Full 执行回放均 0 失败。

## 历史结果怎么使用

- [2026-08-09 Pareto 报告](archive/pareto_experiment_analysis_20260809.md)记录过基础/压力场景各三个种子的前沿数值，但对应 CSV/manifest 当前不在本地，保留为历史报告，不纳入当前证据表。
- 旧动态 CSV 和阶段图共 72 个文件位于 `outputs/archive/pre_cleanup_20260907.tar.gz`；逐文件校验通过。它们包含更早的模型口径，不能与当前 S8 数值混合汇总。
- 旧报告内的“八项测试”“ALNS 尚无自适应”“基线与消融尚未实现”等完成状态已过时；当前实际实现以[研究说明](research.md)为准。

恢复命令与去留清单见[维护记录](maintenance.md)。

## 下一轮研究任务

1. 固定模型假设、时间与公平目标口径，明确是否启用转场和可达性限制；记录真实数据与压力参数的区别。
2. 动态实验在偏差 0/0.15/0.30、多个种子和 12 个资源设置上重跑，保留共同随机数；另外设计关键断联网络，检验适用边界。
3. 正式算法对照增加评价预算和重复。汶川固定网络必须单独使用 `--cases WEN38 --instance-seeds 1`；合成网络使用多个实例种子，不能把同一汶川网络重复命名当作独立实例。
4. 正式三因素消融按“案例 × 实例种子”分片，每片保留配对的 30 次 solver 重复；使用统一分析入口重算 pooled HV/IGD，再报告效应、区间和校正后的检验结果。
5. 保存完整运行环境、种子、预算和产物指纹后更新本页；不以新图或 smoke 完成替代正式研究完成。

正式分片和阶段可视化命令见[脚本指南](../scripts/README.md)。
