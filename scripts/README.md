# 脚本说明

本目录保存围绕汶川案例和论文 MP-NRWSRLP 模型的 Python 探索脚本。

## 主线脚本

| 脚本 | 作用 | 备注 |
|---|---|---|
| `nsga2_multiobjective.py` | NSGA-II 风格多目标实验，目标包括累计抢修绩效和修复成本 | 当前最适合作为主线入口 |
| `plot_initial_network.py` | 绘制初始路网、供给点、需求点和受损路段 | 用于检查表格数据和网络结构 |

## 实验脚本

| 脚本 | 作用 | 定位 |
|---|---|---|
| `experiments/simple_ga_convergence.py` | 单目标 GA 收敛与分时抢修推演 | 早期简化版本 |
| `experiments/case_single_objective_plan.py` | 单目标/成本绩效折中实验 | 方案对比版本 |
| `experiments/advanced_visualization.py` | 更复杂的过程可视化和成本惩罚实验 | 可视化增强版本 |
| `experiments/fleet_constraint_visualization.py` | 加入运力约束和维修队行进时间的实验 | 更接近业务约束的版本 |

## 运行方式

在项目根目录运行：

```bash
uv sync
uv run python scripts/nsga2_multiobjective.py
uv run python scripts/plot_initial_network.py
```

如果只想快速检查算法流程，可以优先运行 `scripts/experiments/simple_ga_convergence.py`，它的输出更偏向分时叙事。

## 维护建议

目前多个脚本内重复维护节点、边和受损路段数据。后续建议把公共数据抽到统一模块，再让各实验脚本只保留算法差异和参数差异。
