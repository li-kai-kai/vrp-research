> 历史归档（2026-09-07）：保留研究演变记录；其中计划、数值和完成状态不代表当前实现。当前口径见 [研究说明](../research.md) 和 [实验进展](../experiments.md)。

# 项目清单与整理说明

本文档记录 `s10479-018-3037-2.pdf` 相关资料、最新 proposal 与复现代码的职责边界。

## 当前主线

```text
论文 PDF
    -> 汶川案例数据与原模型
    -> 原论文/普通 GA 基线
    -> 道路容量渐进恢复与异质车辆模型
    -> NSGA-II + ALNS
    -> 对照、消融、多种子与 Pareto 实验
```

## 核心文件

| 类别 | 文件 | 作用 |
|---|---|---|
| 原始文献 | `references/s10479-018-3037-2.pdf` | 原模型和汶川案例的主来源 |
| 案例数据 | `docs/wenchuan_case_model_inputs.md` | 供需节点、路网、受损道路、车辆和维修队数据 |
| 原模型 | `docs/algorithm_flow.md` | 多周期道路修复与救援配送联动逻辑 |
| 原算法 | `docs/genetic_algorithm.md` | HSSPGA 编码、解码和遗传操作 |
| 拟研究数据 | `docs/proposed_capacity_recovery_data.md` | 最新 proposal 所需字段与数据来源 |
| 拟研究模型 | `docs/proposed_capacity_recovery_model.md` | 容量渐进恢复、车型阈值和三目标模型 |
| 拟研究算法 | `docs/proposed_nsga2_alns_algorithm.md` | NSGA-II + ALNS 编码、解码和算子 |
| 原型记录 | `docs/capacity_recovery_experiment_notes.md` | 当前实现范围、结果和限制 |
| 主线实验 | `scripts/reproduce/capacity_recovery.py` | 最新 proposal 的可运行原型 |
| 基线实验 | `scripts/reproduce/run_random_experiments.py` | 原论文/普通 GA 和随机算例 |
| 自动测试 | `tests/test_reproduce.py` | 实例、配送、指标和汶川数据检查 |

## 目录职责

| 目录 | 职责 |
|---|---|
| `references/` | 原始论文和参考 PDF |
| `docs/` | 数据、模型、算法、综述、审稿记录和实验记录 |
| `scripts/reproduce/` | 主线实验入口与共享求解模块 |
| `scripts/tools/` | OCR 等资料处理工具，不参与算法实验 |
| `tests/` | 复现框架的自动检查 |
| `presentations/` | 汇报产物与构建脚本 |
| `downloads/` | 本地下载/OCR 资料说明；大体量产物不提交 |
| `outputs/` | 实验生成结果；默认不作为源文件维护 |

## 本次清理

已删除以下过时实验：

- 独立的双目标 `scripts/nsga2_multiobjective.py`；
- 早期单目标 GA 收敛实验；
- 成本惩罚和单目标方案实验；
- 以展示为主的高级过程可视化实验；
- 旧的运力约束/维修队行进可视化实验。

这些脚本采用二元道路状态、单目标或早期双目标口径，并重复硬编码汶川数据。其有效职责已由 `scripts/reproduce/` 的基线与容量恢复原型覆盖。

保留 `scripts/plot_initial_network.py`，因为它仍是案例数据的独立可视化检查入口。保留原模型和原算法文档，因为它们是最新 proposal 的理论基线，不属于过时实验。

## 维护规则

1. 新实验复用 `scripts/reproduce/` 的实例、调度、配送和指标模块。
2. 模型差异通过配置或明确的基线/消融入口表达，不复制整套脚本。
3. 所有论文级结果记录随机种子、参数、运行时间和输出目录。
4. 生成结果统一写入 `outputs/`，源数据与生成数据分离。
5. 新增模型行为时同步增加测试。

## 下一步优先级

1. 导出完整 Pareto 前沿和不同偏好的代表解。
2. 实现“二元道路 + NSGA-II”“渐进恢复 + NSGA-II”“渐进恢复 + NSGA-II/ALNS”三组对照与消融。
3. 对随机算例和汶川案例执行多随机种子实验，报告均值、标准差和显著性。
4. 标定单车 pcu 与路段容量并完成容量尺度敏感性；取得普通交通 OD 后再加入 BPR。
5. 增加公平性导向 ALNS 算子和关键行为测试。
