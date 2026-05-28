# VRP Research: 灾后道路修复与救援物流联动优化

本项目围绕论文 `s10479-018-3037-2.pdf` 整理汶川地震案例数据、模型结构、遗传算法思路和若干 Python 复现实验脚本。

主参考文献：

> Li, S., & Teo, K. L. (2019). *Post-disaster multi-period road network repair: work scheduling and relief logistics optimization*. Annals of Operations Research, 283, 1345-1385. https://doi.org/10.1007/s10479-018-3037-2

## 项目结构

```text
.
├── references/
│   └── s10479-018-3037-2.pdf
├── docs/
│   ├── wenchuan_case_model_inputs.md
│   ├── algorithm_flow.md
│   ├── genetic_algorithm.md
│   ├── presentation_narrative_plan.md
│   └── project_inventory.md
├── scripts/
│   ├── README.md
│   ├── nsga2_multiobjective.py
│   ├── plot_initial_network.py
│   └── experiments/
│       ├── simple_ga_convergence.py
│       ├── case_single_objective_plan.py
│       ├── advanced_visualization.py
│       └── fleet_constraint_visualization.py
└── presentations/
    ├── build_summary_deck.mjs
    └── s10479-018-3037-2_summary_presentation.pptx
```

## 文档导读

- [汶川案例模型输入数据](docs/wenchuan_case_model_inputs.md)：整理论文附录表 16-18，包括供需节点、路网、受损路段、车辆、维修队与周期参数。
- [模型与算法流程](docs/algorithm_flow.md)：说明多周期双层模型如何把修路排班和救援配送联动起来。
- [遗传算法实现说明](docs/genetic_algorithm.md)：解释 HSSPGA 的染色体编码、解码、选择、交叉和变异。
- [演示文稿叙事提纲](docs/presentation_narrative_plan.md)：面向汇报场景的论文叙事结构。
- [项目清单与整理说明](docs/project_inventory.md)：说明当前文件职责、命名规则和后续整理建议。

## 代码导读

当前代码以探索性复现为主，不是完整论文级复现。更详细的脚本说明见 [scripts/README.md](scripts/README.md)。

- `scripts/nsga2_multiobjective.py`：主线 NSGA-II 风格多目标实验，评估累计抢修绩效和修复成本。
- `scripts/plot_initial_network.py`：绘制汶川案例初始道路网络与受损边。
- `scripts/experiments/`：保留不同阶段的实验脚本，用于对比单目标 GA、运力约束、可视化和调度假设。

## 运行环境

项目使用 Python 3.12 和 `uv` 管理依赖：

```bash
uv sync
```

运行示例：

```bash
uv run python scripts/nsga2_multiobjective.py
uv run python scripts/plot_initial_network.py
```

这些脚本会打开 Matplotlib 图窗；在无图形界面的环境中运行时，需要改用非交互后端或把图保存为文件。

## 当前整理状态

- 原始论文 PDF 已放入 `references/`。
- 论文相关 Markdown 已归入 `docs/`。
- 演示文稿及构建脚本已归入 `presentations/`。
- 原 `main*.py` 与 `figure.py` 已按用途归入 `scripts/` 与 `scripts/experiments/`。
- `test.js` 和 `test.ts` 已被标记为删除，当前项目没有发现它们与论文复现主线的直接关系。

## 后续建议

下一步如果要把项目从“整理和探索”推进到“可复现实验包”，建议抽取统一数据模块，例如 `scripts/data/wenchuan_case.py`，把多个脚本里重复的节点、边、受损路段和参数集中维护。
