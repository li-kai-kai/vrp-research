# 脚本说明

本目录保存围绕汶川案例、原论文基线和最新容量渐进恢复 proposal 的 Python 复现代码。

## 主线脚本

| 脚本 | 作用 | 备注 |
|---|---|---|
| `reproduce/capacity_recovery.py` | 道路容量渐进恢复、车型阈值、边—周期 pcu 吞吐和 NSGA-II + ALNS 原型实验 | 最新 proposal 主入口 |
| `reproduce/dynamic_interaction_experiments.py` | 二元/渐进、open-loop/rolling 对照，输出容量指标、进度预测误差和维修效率实现 | 机制验证主入口 |
| `reproduce/dynamic_interaction_grid.py` | 运行多种子 × 12 组资源设置并生成四机制配对汇总，支持容量与维修效率敏感性 | 网格复现入口 |
| `reproduce/run_model_ablation.py` | 对渐进恢复、异质车型阈值和边—周期容量约束运行完整 `2^3` 配对消融 | 模型 factorial 入口 |
| `reproduce/model_ablation_analysis.py` | 合并消融分片，重算统一 pooled HV/IGD，并估计主效应、二阶交互及配对统计 | 正式消融分析入口 |
| `reproduce/stage_visualization.py` | 按周期绘制道路、需求、维修队快照，并输出维修与配送决策时序图 | 阶段状态展示入口 |
| `reproduce/run_random_experiments.py` | 论文随机算例与普通 GA 实验，输出 CSV/JSON/PNG | 基线和对照入口 |
| `reproduce/model.py` 等模块 | 实例、调度、配送、指标、求解和可视化 | 主线共享实现 |
| `plot_initial_network.py` | 绘制初始路网、供给点、需求点和受损路段 | 用于检查表格数据和网络结构 |

早期单目标、二元道路和展示型实验已删除。后续新增实验应作为 `reproduce/` 的配置、基线或消融组实现，避免再次复制整套数据与求解逻辑。

## 工具脚本

| 脚本 | 作用 | 定位 |
|---|---|---|
| `tools/ocr_xju_downloads.py` | 对 `downloads/xju/pdfbox/<fid>/page_*.jpg` 执行 OCR，并写入 `downloads/xju/ocr/` | 本地资料处理工具，不属于算法复现实验 |

## 运行方式

在项目根目录运行：

```bash
uv sync
uv run python scripts/plot_initial_network.py
uv run python scripts/reproduce/run_random_experiments.py --config quick
uv run python scripts/reproduce/run_random_experiments.py --nodes 50 --gamma 4 --damage 0.3 --eta 8 --seeds 5
uv run python scripts/reproduce/capacity_recovery.py --scenario both --seeds 1 --sim-nodes 25 --pop-size 24 --generations 20 --alns-iterations 8 --output-dir outputs/capacity_recovery
uv run python scripts/reproduce/dynamic_interaction_experiments.py --scenario wenchuan --seeds 5 --repair-scale 2 --crews 2 --capacity-scale 0.05 --repair-efficiency-deviation 0.30 --output-dir outputs/dynamic_interaction_uncertain_s8
uv run python scripts/reproduce/dynamic_interaction_grid.py --seed 1 --seeds 5 --capacity-scale 0.05 --repair-efficiency-deviation 0.30 --output-dir outputs/dynamic_grid_uncertain
uv run python scripts/reproduce/run_model_ablation.py --suite smoke --output-dir outputs/model_ablation_smoke
uv run python scripts/reproduce/stage_visualization.py --scenario wenchuan --mechanism progressive_rolling --seed 1 --repair-scale 2 --crews 2 --capacity-scale 0.05 --repair-efficiency-deviation 0.30 --crew-transfer-time-scale 1.0 --crew-min-access-progress 0.30 --output-dir outputs/stage_visualization_s8_v7
uv run python scripts/tools/ocr_xju_downloads.py
```

如果只想快速验证随机算例框架，可以给复现实验入口追加较小的 GA 参数，例如 `--pop-size 10 --generations 3`。
如果只想快速验证容量恢复原型，可以给 `capacity_recovery.py` 设置 `--pop-size 8 --generations 3 --alns-iterations 3`。
效率目标中的维修作业工时权重可通过 `--repair-time-weight` 调整，默认值为 0.05；启用转场后，该权重作用于现场维修工时与转场时间之和，转场时间本身由 `--crew-transfer-time-scale` 控制。
容量恢复实验会保存 `pareto_front_runs.csv`（每次运行的非支配 archive）、`pareto_front.csv`（跨运行合并后仍然非支配的全局近似前沿）、`pareto_solutions.json`（完整染色体决策）、`experiment_manifest.json`（全部运行参数）和 `pareto_front.png`（三目标前沿图）。前沿来自跨代外部 archive，而不再局限于最终种群中的单一代表解。
模型消融入口固定使用 benchmark 的 `nsga2_alns` 求解器；同一实例与求解种子下的八个组合共享评价预算，并按实例汇总所有组合和重复形成 pooled reference front。输出包括 `model_ablation.csv`、`pareto_points.csv`、`pooled_reference_front.csv` 和 `experiment_manifest.json`。

正式消融使用 `publication` 配置。合成案例以“实例种子”为统计单位，先平均同一实例上的配对 solver 重复；汶川案例是固定网络，只运行一个实例副本并以 solver 重复为统计单位，避免把同一网络改名后当作独立实例。建议按“案例 × 实例种子”分片，每个分片保留完整 30 次 solver 重复，例如：

```bash
uv run python scripts/reproduce/run_model_ablation.py --suite publication --cases S025 --instance-seeds 1 --solver-repeats 30 --output-dir outputs/model_ablation_publication_shards/S025_i01
uv run python scripts/reproduce/model_ablation_analysis.py --input-root outputs/model_ablation_publication_shards --output-dir outputs/model_ablation_publication
```

如果还需按 solver 重复拆分，可用 `--solver-repeat-start` 指定起点；最终必须通过 `model_ablation_analysis.py` 合并，因为它会使用所有分片的 Pareto 点重新计算每个实例统一的 pooled reference front。正式分析另外输出 `model_summary.csv`、`factor_effects_raw.csv`、`factor_effects.csv`、`factorial_completeness.csv` 和 `analysis_manifest.json`。主效应与二阶交互采用效应编码的配对对比，报告实例级（汶川为 solver 级）均值、标准差、中位数、IQR、95% BCa bootstrap 区间、双侧符号翻转随机化检验和按“案例 × 指标”进行的 Holm 校正。

## 维护建议

`capacity_scale=1.0` 保留项目估算容量；更低数值仅用于压力测试，不代表汶川现场实测容量。当前车型单车当量 1.0/1.5/2.0/2.5 同样是待标定场景值。后续实验应复用 `reproduce/` 中的公共数据结构和评价函数，并优先补齐 proposal 要求的基线、消融、多种子统计与完整 Pareto 前沿输出。
维修效率偏差使用共同随机数：同一种子下四种机制面对相同的 `xi_a^t`。`repair-efficiency-deviation=0` 用于验证没有新信息时 open-loop 与 rolling 不应产生虚假优势。
动态实验目录中的 `repair_efficiency_realizations.csv` 保存每个周期、每条受损道路的实际效率，便于独立审计共同随机数与复现实验。
阶段可视化会生成 `stage_00.png` 至 `stage_09.png`、`stage_overview.png`、`delivery_timeline.png`、`operation_sequence.png` 和 `stage_states.json`。需求点填色表示累计满足率，青色描边和节点大小表示本期新增配送；未配送点统一为白底橙圈，不在地图上额外标记不可达状态。每支维修队使用独立颜色和符号，彩色点线表示本期转场路径。`dispatch_routes/` 保存每个 Stage 的物资配送路线图，需求点旁按供应来源标注本期吨位；`dispatch_manifest.csv` 逐条保存供应点、需求点、吨位、车型、趟数、运输时间和完整路径。

`--crew-transfer-time-scale 1.0` 按物理路网最短时间估算受损路段中点之间的转场，并从周期维修工时中扣除；设为 `0` 可复现原来的无转场假设，设为大于 `1` 可表达拥堵、路况恶化或保守转场时间。周期图展示的是一个 8 小时周期末的累计状态，并非需求点在期初瞬间得到满足。

`--crew-min-access-progress 0.30` 要求维修队转场路径上的受损道路至少达到临时通行状态。维修队到达尚未打通的目标路段后会保留实际进入端点；在该路段达到通行阈值前，不能从另一端穿越到更深的待修路段。每期还会计算“本期实际修复后配送”与“保持期初道路状态、不实施本期修复”的反事实配送，报告修复新增吨位和新增可达点。

渐进恢复状态的默认含义为：`blocked`（进度 0–30%，容量和速度为 0）、`temporary`（30–60%，临时便道，容量/速度恢复到 30%）、`one_lane`（60–80%，单车道通行，恢复到 60%）、`basic`（80–100%，基本恢复，恢复到 80%）和 `full`（100%，完全恢复）。车型仍需同时满足自身进度阈值 30%、50%、70% 和 80% 才能通行。
