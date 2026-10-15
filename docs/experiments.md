# 当前实验与证据索引

实验时间为2026-09-20至2026-10-14。

| 研究内容 | 实际完成 | 证据 |
|---|---|---|
| 并行 NSGA-II | 4个实例、8个种子、136次运行；全部用满预设预算，同组跨 worker 前沿一致 | `exp/full_budget/results.json`、`results.csv` |
| 机制适用条件 | S025/S050/M100、1120个资源网格单元的跨规模复核 | `outputs/mechanism_probe_audit/`；[报告](mechanism_applicability_report.md) |
| WEN38 天然通行走廊 | 固定决策与60个半真实场景覆盖 | `outputs/ht_natural_corridor_audit/`；[报告](ht_natural_corridor_report.md) |
| WEN38预算 | 60次搜索、150000次评价、3063条回放；500/2000/5000均未出现稳定平台 | `outputs/report_reproduction/analysis/`；[报告](wen38_budget_convergence_report.md) |
| 容量与资源审计 | 单边555 PCU使用上界低于960 PCU容量下界；15代表×5变体 | `outputs/report_reproduction/ec_diagnosis/`；[容量审计](wen38_capacity_audit.md)、[资源诊断](wen38_ec_diagnosis.md) |
| 算法档案与回放 | 最终修正版S025算法档案及同模型回放 | `outputs/claude_v2_reviewfix2/pilot_algorithm/`、`pilot_algorithm_roundtrip/` |
| WEN38 预算阶梯重跑与冻结 | 500–20000 五档、100 次运行；平台判据未达成（增益不随预算收缩），模型对照自 5000 档起稳定；正式预算冻结为 10000 | `outputs/budget_convergence_rerun/`；[报告](wen38_budget_freeze_report.md) |
| 正式模型价值实验 | 模型轨 744 次运行 + 敏感性轨 240 次（同一源码指纹）；执行侧：忽略 PR/HT 显著有代价（Holm 校正），HT 依附 PR（交互=主效应），EC 标定区精确为零、绑定区 12/12 有代价 | `outputs/formal/`；[报告](formal_experiment_report.md) |

最后一项保留原路径与哈希，供 `replay_solutions.py` 回放核对及 `summarize_replay.py` 的默认输入使用。研究报告中的反例和被推翻解释用于界定现有结论。

## 并行计算结果

| 实例 | 预算 | 1 worker均时/s | 8 workers均时/s | 加速比 |
|---|---:|---:|---:|---:|
| S025 | 1600 | 77.975 | 22.655 | 3.44 |
| WEN38 | 1600 | 73.133 | 22.654 | 3.23 |
| S050 | 800 | 157.400 | 35.032 | 4.49 |
| M100 | 400 | 247.100 | 50.395 | 4.90 |

WEN38另含8次进程内串行基线，串行均时72.1秒，8 workers相对串行加速3.18倍。原计时来自同一台13核共享机器；运行136次不等于136个独立网络样本。

计时复现应写入新目录，禁止覆盖原始计时。跨种子池化的HV/IGD只在同一参考集内比较。

## 尚未完成

- 容量/车型阈值/资源的现场标定（模拟敏感性与处境条件化已完成，见[报告](formal_experiment_report.md)）。
- 专用大邻域算法与v2动态滚动扩展（正式算法优越性不在本轮范围）。
