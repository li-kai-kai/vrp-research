# VRP Research: 灾后道路修复与救援物流联动优化

本项目以 Li & Teo (2019) 的灾后多周期道路修复与救援物流模型为基础，整理汶川案例数据，并研究“道路容量渐进恢复 + 异质车辆通行阈值 + NSGA-II/ALNS”的扩展方案。

主参考文献：

> Li, S., & Teo, K. L. (2019). *Post-disaster multi-period road network repair: work scheduling and relief logistics optimization*. Annals of Operations Research, 283, 1345-1385. https://doi.org/10.1007/s10479-018-3037-2

## 当前主线

```text
原论文与汶川数据
    -> 原模型/普通 GA 基线
    -> 道路容量渐进恢复与异质车辆模型
    -> NSGA-II + ALNS 混合算法
    -> 基线、消融、多种子与 Pareto 实验
```

最新 proposal 对应：

- [拟研究数据](docs/proposed_capacity_recovery_data.md)
- [拟研究模型](docs/proposed_capacity_recovery_model.md)
- [拟研究算法](docs/proposed_nsga2_alns_algorithm.md)
- [原型实验记录](docs/capacity_recovery_experiment_notes.md)
- [动态交互机制实验摘要](docs/dynamic_interaction_experiment_results.md)
- [动态交互数值实验详细报告](docs/dynamic_interaction_experiment_report_detailed.md)
- [研究交接文档](docs/HANDOFF.md)

## 项目结构

```text
.
├── references/                 # 原始论文与参考资料
├── docs/                       # 数据、模型、算法、综述和实验记录
├── scripts/
│   ├── README.md
│   ├── plot_initial_network.py
│   ├── reproduce/              # 主线实验与共享实现
│   │   ├── capacity_recovery.py
│   │   ├── run_random_experiments.py
│   │   ├── model.py
│   │   ├── ga_solver.py
│   │   └── ...
│   └── tools/                  # OCR 等资料处理工具
├── tests/                      # 复现框架测试
├── presentations/              # 汇报稿和构建脚本
└── downloads/                  # 本地下载/OCR 资料说明
```

## 文档导读

- [汶川案例模型输入数据](docs/wenchuan_case_model_inputs.md)：原论文案例中的供需节点、路网、受损路段、车辆和维修队数据。
- [原模型与算法流程](docs/algorithm_flow.md)：多周期修复排班与救援配送的联动逻辑。
- [原遗传算法说明](docs/genetic_algorithm.md)：HSSPGA 的编码、解码和遗传操作，作为基线参考。
- [最新容量恢复模型](docs/proposed_capacity_recovery_model.md)：分阶段道路容量、多车型阈值和三目标模型。
- [最新 NSGA-II + ALNS 算法](docs/proposed_nsga2_alns_algorithm.md)：混合算法编码、解码、局部搜索和对比设计。
- [项目清单](docs/project_inventory.md)：文件职责和后续实验优先级。

## 代码导读

- `scripts/reproduce/capacity_recovery.py`：最新 proposal 主入口，实现容量渐进恢复、多车型通行阈值和 NSGA-II + ALNS 原型。
- `scripts/reproduce/dynamic_interaction_experiments.py`：二元/渐进恢复与滚动修复—路径反馈机制实验。
- `scripts/reproduce/run_random_experiments.py`：原论文/普通 GA 基线和随机算例入口。
- `scripts/reproduce/` 其余模块：共享实例、调度、配送、指标、求解和可视化逻辑。
- `scripts/plot_initial_network.py`：检查汶川案例路网、供需节点和受损边。
- `scripts/tools/ocr_xju_downloads.py`：处理本地下载文献页面，不属于算法实验。

早期单目标、二元道路和展示型独立实验已清除。新增实验应优先作为 `scripts/reproduce/` 的配置、基线或消融组实现。

## 运行

项目使用 Python 3.12 和 `uv`：

```bash
uv sync
uv run python -m unittest discover -s tests
```

快速运行基线：

```bash
uv run python scripts/reproduce/run_random_experiments.py --config quick
```

运行最新 proposal 原型：

```bash
uv run python scripts/reproduce/capacity_recovery.py \
  --scenario both \
  --seeds 1 \
  --sim-nodes 25 \
  --pop-size 24 \
  --generations 20 \
  --alns-iterations 8 \
  --capacity-scale 1.0 \
  --repair-time-weight 0.05 \
  --output-dir outputs/capacity_recovery
```

当前原型已经同时执行车型通行阈值和边—周期救援车辆吞吐约束：每辆车按 `pcu_per_vehicle` 占用路径容量，每辆车每周期最多执行一趟；容量不足时会在残余容量路网中重算路径。`--capacity-scale` 用于容量压力敏感性，默认 1.0；0.05 和 0.02 可作为机制检查档位，但属于假设性压力参数。

实验输出默认写入 `outputs/`。容量恢复入口保存跨代外部 archive 中的完整非支配解、完整决策 JSON、参数 manifest 和 Pareto 前沿图。当前实现仍是可运行原型，不应直接作为论文最终结果；下一步需要补齐基线/消融组、多随机种子统计、车型 pcu 标定和车辆跨期周转。普通交通 OD 与流量驱动 BPR 拥堵仍未纳入。

动态交互实验支持逐期揭示的维修效率偏差：`--repair-efficiency-deviation 0.30` 表示 `xi~U(0.7,1.3)`。open-loop 按期望状态在期初制定全期计划，rolling 在每期观测实际道路修复进度后重规划；相同种子下各机制共享同一随机实现，并将逐道路、逐周期样本写入 `repair_efficiency_realizations.csv`。
