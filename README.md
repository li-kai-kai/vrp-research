# 灾后道路修复与救援物流联动优化

以 Li & Teo (2019) 的多周期道路修复与救援物流研究为基础，使用汶川案例与合成路网，研究道路渐进恢复、异质车辆通行和修复—配送反馈，以及 NSGA-II 与自适应邻域搜索的求解方法。

当前已经实现模型、动态机制、算法对照和完整三因素消融框架；已核验的最新实验仍是小预算验证，尚未完成正式多实例、多重复性能实验。
评价语义自 2026-09-20 起显式版本化为 **legacy / v2**：legacy 保留原配给上限与期末路况语义用于历史回归，
v2 使用期初路况、当期到货时间检查与新的配给政策。两套语义不可混用，详细状态更新于 **2026-09-25**。

2026-09-25 本地交接复现已完成：58 次小预算搜索、29,000 次搜索评价；共同执行 1,475 条方案回放无失败，224 项测试通过。仍属先导，不代表正式收敛或统计结论。

## 从这里开始

- [本轮范围与长期路线](docs/research_scope.md)：两份交接文档的取舍、当前代码核对与后续门槛。
- [公平准备诊断](docs/research_readiness_report.md)：151 条准备样本、零服务原因与公平权衡。
- [四模型共同执行先导报告](docs/model_value_pilot_report.md)：本地新实测、回放审计、配对质量和服务图。
- [研究说明](docs/research.md)：问题、数据、实际目标函数、算法和实现边界。
- [实验进展与结果](docs/experiments.md)：已核验数值、证据位置、复现命令和待完成工作（legacy 证据）。
- [模型 v2 合同](docs/model_v2_contract.md)：v2 的配给政策、时间轴、单位、指标与指纹规则。
- [v2 小预算诊断报告](docs/pilot_v2_report.md)：v2 已执行的测试、算法诊断与模型价值诊断。
- [v2 执行状态表](docs/execution_status_v2.md)：各阶段状态与验收证据。
- [机制适用条件诊断](docs/mechanism_applicability_report.md)：PR / HT / EC 在什么条件下真正参与决策，
  含不绑定区、过渡区与绑定区；区分机制暴露 / 配送参与 / 目标效应三个层次，
  并记录已被实验推翻的旧结论。跨规模复核覆盖 S025 / S050 / M100。
- [WEN38 天然 HT corridor 诊断](docs/ht_natural_corridor_report.md)：真实路网中是否天然存在
  threshold-sensitive corridor，含半真实 overlay 与四级证据链。
- [脚本指南](scripts/README.md)：实验入口、参数和输出。
- [清理记录](docs/maintenance.md)：文件去留、测试分组和历史产物恢复方法。
- [汶川输入资料](docs/background/wenchuan_case_model_inputs.md)：原论文数据背景。
- [历史文档索引](docs/archive/README.md)：旧 proposal、报告和审稿过程，仅用于追溯。

## 运行

Python 3.12+，使用 `uv`，在仓库根目录执行：

```bash
uv sync
uv run python -m unittest discover -s tests
uv run python scripts/reproduce/run_benchmark.py --suite smoke --max-evaluations 12 --pop-size 4 --output-dir outputs/benchmark_smoke
uv run python scripts/reproduce/run_model_ablation.py --suite smoke --max-evaluations 12 --pop-size 4 --output-dir outputs/model_ablation_smoke
```

小预算只检查流程。正式实验的预算、种子和分析单位见[实验进展](docs/experiments.md)。

## 目录

| 目录 | 职责 |
|---|---|
| `scripts/reproduce/` | 共享数据、调度、配送、目标评价、求解器、实验与统计分析 |
| `scripts/legacy/` | 普通 GA 历史复现链，保留运行和回归测试 |
| `scripts/plot_*.py` | 从共享实例或真实实验 CSV 绘图 |
| `tests/` | 共享实例、容量模型、动态机制、算法对照、模型消融及 legacy 回归测试 |
| `docs/` | 当前研究说明、实验状态、维护记录；`background/` 为背景，`archive/` 为历史 |
| `references/` | 原始参考文献 |
| `outputs/` | 实验产物；除 `outputs/claude_v2/`（v2 诊断的可审计结果集）外均不纳入 Git |

原始文献：Li, S., & Teo, K. L. (2019). *Post-disaster multi-period road network repair: work scheduling and relief logistics optimization*. Annals of Operations Research, 283, 1345–1385. DOI: `10.1007/s10479-018-3037-2`。
