# 脚本说明

本目录保存围绕汶川案例、原论文基线和最新容量渐进恢复 proposal 的 Python 复现代码。

## 主线脚本

| 脚本 | 作用 | 备注 |
|---|---|---|
| `reproduce/capacity_recovery.py` | 道路容量渐进恢复、车型阈值、边—周期 pcu 吞吐和 NSGA-II + ALNS 原型实验 | 最新 proposal 主入口 |
| `reproduce/dynamic_interaction_experiments.py` | 二元/渐进、open-loop/rolling 对照，输出容量指标、进度预测误差和维修效率实现 | 机制验证主入口 |
| `reproduce/dynamic_interaction_grid.py` | 运行多种子 × 12 组资源设置并生成四机制配对汇总，支持容量与维修效率敏感性 | 网格复现入口 |
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
uv run python scripts/tools/ocr_xju_downloads.py
```

如果只想快速验证随机算例框架，可以给复现实验入口追加较小的 GA 参数，例如 `--pop-size 10 --generations 3`。
如果只想快速验证容量恢复原型，可以给 `capacity_recovery.py` 设置 `--pop-size 8 --generations 3 --alns-iterations 3`。
效率目标中的维修作业工时权重可通过 `--repair-time-weight` 调整，默认值为 0.05；该参数不表示维修队移动时间。

## 维护建议

`capacity_scale=1.0` 保留项目估算容量；更低数值仅用于压力测试，不代表汶川现场实测容量。当前车型单车当量 1.0/1.5/2.0/2.5 同样是待标定场景值。后续实验应复用 `reproduce/` 中的公共数据结构和评价函数，并优先补齐 proposal 要求的基线、消融、多种子统计与完整 Pareto 前沿输出。
维修效率偏差使用共同随机数：同一种子下四种机制面对相同的 `xi_a^t`。`repair-efficiency-deviation=0` 用于验证没有新信息时 open-loop 与 rolling 不应产生虚假优势。
动态实验目录中的 `repair_efficiency_realizations.csv` 保存每个周期、每条受损道路的实际效率，便于独立审计共同随机数与复现实验。
