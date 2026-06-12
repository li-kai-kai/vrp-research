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
│   ├── literature_review_supporting_two_innovations.md
│   ├── proposed_capacity_recovery_model.md
│   ├── proposed_nsga2_alns_algorithm.md
│   ├── capacity_recovery_experiment_notes.md
│   ├── presentation_narrative_plan.md
│   └── project_inventory.md
├── scripts/
│   ├── README.md
│   ├── nsga2_multiobjective.py
│   ├── plot_initial_network.py
│   ├── tools/
│   │   └── ocr_xju_downloads.py
│   ├── reproduce/
│   │   ├── capacity_recovery.py
│   │   └── run_random_experiments.py
│   └── experiments/
│       ├── simple_ga_convergence.py
│       ├── case_single_objective_plan.py
│       ├── advanced_visualization.py
│       └── fleet_constraint_visualization.py
├── presentations/
│   ├── build_summary_deck.mjs
│   └── s10479-018-3037-2_summary_presentation.pptx
└── downloads/
    └── xju/
        └── README.md
```

## 文档导读

- [汶川案例模型输入数据](docs/wenchuan_case_model_inputs.md)：整理论文附录表 16-18，包括供需节点、路网、受损路段、车辆、维修队与周期参数。
- [模型与算法流程](docs/algorithm_flow.md)：说明多周期双层模型如何把修路排班和救援配送联动起来。
- [遗传算法实现说明](docs/genetic_algorithm.md)：解释 HSSPGA 的染色体编码、解码、选择、交叉和变异。
- [支撑两个创新点的文献综述稿](docs/literature_review_supporting_two_innovations.md)：围绕“道路容量渐进恢复”和“NSGA-II + ALNS”整理研究缺口和可直接写入论文的综述段落。
- [拟研究数据文档](docs/proposed_capacity_recovery_data.md)：说明容量渐进恢复模型需要的数据结构、字段和仿真/汶川算例来源。
- [拟研究模型文档](docs/proposed_capacity_recovery_model.md)：描述道路容量随修复进度逐步恢复、车型通行阈值和多目标函数。
- [拟研究算法文档](docs/proposed_nsga2_alns_algorithm.md)：描述 NSGA-II + ALNS 混合算法、编码、解码和局部搜索算子。
- [道路容量渐进恢复实验记录](docs/capacity_recovery_experiment_notes.md)：记录仿真算例和汶川路网的原型实验结果。
- [演示文稿叙事提纲](docs/presentation_narrative_plan.md)：面向汇报场景的论文叙事结构。
- [项目清单与整理说明](docs/project_inventory.md)：说明当前文件职责、命名规则和后续整理建议。

## 代码导读

当前代码以探索性复现为主，不是完整论文级复现。更详细的脚本说明见 [scripts/README.md](scripts/README.md)。

- `scripts/nsga2_multiobjective.py`：主线 NSGA-II 风格多目标实验，评估累计抢修绩效和修复成本。
- `scripts/reproduce/run_random_experiments.py`：论文随机算例复现实验入口，生成随机路网、运行简化 GA、输出 CSV/JSON 和 PNG 图。
- `scripts/reproduce/capacity_recovery.py`：道路容量渐进恢复 + 多车型通行阈值 + NSGA-II/ALNS 原型实验入口。
- `scripts/plot_initial_network.py`：绘制汶川案例初始道路网络与受损边。
- `scripts/experiments/`：保留不同阶段的实验脚本，用于对比单目标 GA、运力约束、可视化和调度假设。
- `scripts/tools/ocr_xju_downloads.py`：对新疆大学 WebVPN reader 导出的页面图片执行 OCR，输出到 `downloads/xju/ocr/`。
- `downloads/xju/`：本地下载与 OCR 资料区；大体量图片和 OCR 输出默认不纳入 Git，只保留说明文档。

## 运行环境

项目使用 Python 3.12 和 `uv` 管理依赖：

```bash
uv sync
```

运行示例：

```bash
uv run python scripts/nsga2_multiobjective.py
uv run python scripts/plot_initial_network.py
uv run python scripts/reproduce/run_random_experiments.py --config quick
uv run python scripts/reproduce/capacity_recovery.py --scenario both --seeds 1 --sim-nodes 25 --pop-size 24 --generations 20 --alns-iterations 8 --output-dir outputs/capacity_recovery
```

这些脚本会打开 Matplotlib 图窗；在无图形界面的环境中运行时，需要改用非交互后端或把图保存为文件。
随机算例复现实验默认将结果写入 `outputs/random_experiments/`，包括 `runs.csv`、`period_metrics.csv`、`solutions.json` 和若干 PNG 图。

## 当前整理状态

- 原始论文 PDF 已放入 `references/`。
- 论文相关 Markdown 已归入 `docs/`。
- 演示文稿及构建脚本已归入 `presentations/`。
- 原 `main*.py` 与 `figure.py` 已按用途归入 `scripts/` 与 `scripts/experiments/`。
- 资料处理脚本已归入 `scripts/tools/`，下载/OCR 产物统一放在 `downloads/xju/`。
- `test.js` 和 `test.ts` 已被标记为删除，当前项目没有发现它们与论文复现主线的直接关系。

## 后续建议

下一步如果要把项目从“整理和探索”推进到“可复现实验包”，建议抽取统一数据模块，例如 `scripts/data/wenchuan_case.py`，把多个脚本里重复的节点、边、受损路段和参数集中维护。
