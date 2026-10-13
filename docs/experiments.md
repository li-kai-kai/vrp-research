# 当前实验与证据索引

实验时间为2026-09-20至2026-09-26。整合日期为2026-10-13；整合检查不计作新增研究实验。

| 研究内容 | 实际完成 | 保留证据 |
|---|---|---|
| 并行 NSGA-II | 4个实例、8个种子、136次运行；全部用满预设预算，同组跨 worker 前沿一致 | `exp/full_budget/results.json`、`results.csv` |
| 机制适用条件 | S025/S050/M100、1120个资源网格单元的跨规模复核 | `outputs/mechanism_probe_audit/`；[报告](mechanism_applicability_report.md) |
| WEN38 天然通行走廊 | 固定决策与60个半真实场景覆盖 | `outputs/ht_natural_corridor_audit/`；[报告](ht_natural_corridor_report.md) |
| 公平准备 | 151条方案诊断，区分路径时序与库存耗尽 | `outputs/handoff_20260925/readiness/`；[报告](research_readiness_report.md) |
| 四模型共同执行 | 56次搜索、1475条回放、42个配对 | `outputs/handoff_20260925/pilot/`；[报告](model_value_pilot_report.md) |
| WEN38预算 | 60次搜索、150000次评价、3063条回放；500/2000/5000均未出现稳定平台 | `outputs/report_reproduction/analysis/`；[报告](wen38_budget_convergence_report.md) |
| 容量与资源审计 | 单边555 PCU使用上界低于960 PCU容量下界；15代表×5变体 | `outputs/report_reproduction/ec_diagnosis/`；[容量审计](wen38_capacity_audit.md)、[资源诊断](wen38_ec_diagnosis.md) |
| 公平准备的算法输入 | 最终修正版S025算法档案及同模型回放 | `outputs/claude_v2_reviewfix2/pilot_algorithm/`、`pilot_algorithm_roundtrip/` |

最后一项是最新公平诊断的必要输入，保留原路径与哈希；其更早修正轮次和已被替代的规划先导已移除。研究报告中保留的反例和被推翻解释用于界定现有结论。

## 并行计算结果

| 实例 | 预算 | 1 worker均时/s | 8 workers均时/s | 加速比 |
|---|---:|---:|---:|---:|
| S025 | 1600 | 77.975 | 22.655 | 3.44 |
| WEN38 | 1600 | 73.133 | 22.654 | 3.23 |
| S050 | 800 | 157.400 | 35.032 | 4.49 |
| M100 | 400 | 247.100 | 50.395 | 4.90 |

WEN38另含8次进程内串行基线，串行均时72.1秒，8 workers相对串行加速3.18倍。原计时来自同一台13核共享机器；运行136次不等于136个独立网络样本。

表格由 `paper/ispa2026/make_tables.py` 从冻结CSV生成。计时复现应写入新目录，禁止覆盖原始计时。跨种子池化的HV/IGD只在同一参考集内比较。

## 尚未完成

- WEN38更高预算稳定性检查及正式预算冻结。
- 多独立网络、配对种子和正式统计方案；模型价值与算法性能分别评价。
- 容量/车型阈值/资源标定及过渡带敏感性。
- 专用大邻域和v2动态滚动扩展。
- 论文作者信息、投稿格式及最终论证审阅。

冻结结果的目录清单、完整性校验和本次代码验证见[整合记录](consolidation.md)。
