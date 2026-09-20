# 脚本说明

本目录保存围绕汶川案例、原论文基线和容量渐进恢复研究 的 Python 复现代码。

当前模型口径见[研究说明](../docs/research.md)，已核验结果见[实验进展](../docs/experiments.md)。`capacity_recovery.py` 的固定概率局部强化与 benchmark 的自适应实现不同，不能混用算法名称或评价预算。

## 主线脚本

| 脚本 | 作用 | 备注 |
|---|---|---|
| `reproduce/run_benchmark.py` | SPT、VND、NSGA-II、均匀局部搜索 NSGA-II、自适应 NSGA-II + ALNS 的同预算算法比较 | 算法对照主入口；`--model-version`、`--resume` |
| `reproduce/replay_solutions.py` | 重算已保存决策：`--execution-model saved` 校验同模型可重建，`full` 在共同执行环境中重放规划决策 | 回放入口 |
| `reproduce/solution_io.py` | 实例快照、生效配置、完整决策的共享序列化与原子写入，运行指纹与完整性校验 | 所有入口共用，不重复实现 |
| `reproduce/mechanism_applicability.py` | 固定决策的 PR/HT/EC 暴露度、资源网格、供给/车队/容量放宽对照、维修时长扫描、桥接诊断 | 机制适用条件诊断；不运行优化器 |
| `reproduce/mechanism_zone_search.py` | 按 (场景, 种子) 标定不绑定/过渡/绑定三个分区，在其上做小预算搜索与统一 Full 回放 | 机制诊断阶段 2/3；保存完整三段决策 |
| `reproduce/build_mechanism_audit.py` | 把 `outputs/mechanism_probe/` 的宽表汇总为可审计证据集与 manifest | 只做投影与聚合，不重新推导机制结果 |
| `reproduce/plot_pilot_diagnostics.py` | 只读真实 CSV 与运行记录绘制 v2 小预算诊断图 | 无硬编码数值 |
| `plot_benchmark_results.py` | 显式读取 benchmark `runs.csv` 绘图 | 不含硬编码实验数值 |
| `reproduce/capacity_recovery.py` | 道路容量渐进恢复、车型阈值、边—周期 pcu 吞吐和 NSGA-II + ALNS 原型实验 | 决策/Pareto 原型入口；`EvaluationConfig` 定义 legacy/v2 语义 |
| `reproduce/dynamic_interaction_experiments.py` | 二元静态、渐进静态、渐进 open-loop/rolling 对照，输出容量指标、进度预测误差和维修效率实现 | 机制验证主入口；本轮显式沿用 legacy |
| `reproduce/dynamic_interaction_grid.py` | 运行多种子 × 12 组资源设置并生成四机制配对汇总，支持容量与维修效率敏感性 | 网格复现入口 |
| `reproduce/run_model_ablation.py` | 对渐进恢复、异质车型阈值和边—周期容量约束运行配对消融 | `--model-ids` 子集只出描述性汇总，不做显著性 |
| `reproduce/model_ablation_analysis.py` | 合并消融分片，重算统一 pooled HV/IGD，并估计主效应、二阶交互及配对统计 | 正式消融分析入口（完整 `2^3` + `nsga2_alns`） |
| `reproduce/stage_visualization.py` | 按周期绘制道路、需求、维修队快照，并输出维修与配送决策时序图 | 阶段状态展示入口 |
| `reproduce/model.py` 等模块 | 实例、调度、配送、指标、求解和可视化 | 主线共享实现 |
| `plot_initial_network.py` | 绘制初始路网、供给点、需求点和受损路段 | 用于检查表格数据和网络结构 |

过时的独立展示入口已清理，原模型/普通 GA 与二元机制仍保留为基线。后续新增实验应作为 `reproduce/` 的配置、基线或消融组实现，避免再次复制整套数据与求解逻辑。

## 历史复现

普通 GA 链已迁至 [legacy/](legacy/README.md)，包含实验入口、求解器、旧配送/评价和绘图五个模块；共享实例与数据结构留在 `reproduce/`。它用于历史参考，当前算法对照使用 `reproduce/run_benchmark.py`。旧模型测试继续参与全量测试。

## 运行方式

在项目根目录运行：

```bash
uv sync
uv run python scripts/plot_initial_network.py --mode wenchuan
uv run python scripts/reproduce/run_benchmark.py --suite smoke --max-evaluations 12 --pop-size 4 --output-dir outputs/benchmark_smoke
uv run python scripts/plot_benchmark_results.py --input outputs/benchmark_smoke/runs.csv --output-dir outputs/figures/benchmark_smoke
uv run python scripts/legacy/run_random_experiments.py --config quick
uv run python scripts/legacy/run_random_experiments.py --nodes 50 --gamma 4 --damage 0.3 --eta 8 --seeds 5
uv run python scripts/reproduce/capacity_recovery.py --scenario both --seeds 1 --sim-nodes 25 --pop-size 24 --generations 20 --alns-iterations 8 --output-dir outputs/capacity_recovery
uv run python scripts/reproduce/dynamic_interaction_experiments.py --scenario wenchuan --seeds 5 --repair-scale 2 --crews 2 --capacity-scale 0.05 --repair-efficiency-deviation 0.30 --output-dir outputs/dynamic_interaction_uncertain_s8
uv run python scripts/reproduce/dynamic_interaction_grid.py --seed 1 --seeds 5 --capacity-scale 0.05 --repair-efficiency-deviation 0.30 --output-dir outputs/dynamic_grid_uncertain
uv run python scripts/reproduce/run_model_ablation.py --suite smoke --output-dir outputs/model_ablation_smoke
uv run python scripts/reproduce/stage_visualization.py --scenario wenchuan --mechanism progressive_rolling --seed 1 --repair-scale 2 --crews 2 --capacity-scale 0.05 --repair-efficiency-deviation 0.30 --crew-transfer-time-scale 1.0 --crew-min-access-progress 0.30 --output-dir outputs/stage_visualization_s8_v7
```

如果只想快速验证随机算例框架，可以给复现实验入口追加较小的 GA 参数，例如 `--pop-size 10 --generations 3`。
如果只想快速验证容量恢复原型，可以给 `capacity_recovery.py` 设置 `--pop-size 8 --generations 3 --alns-iterations 3`。
效率目标中的维修作业工时权重可通过 `--repair-time-weight` 调整，默认值为 0.05；启用转场后，该权重作用于现场维修工时与转场时间之和，转场时间本身由 `--crew-transfer-time-scale` 控制。
容量恢复实验会保存 `pareto_front_runs.csv`（每次运行的非支配 archive）、`pareto_front.csv`（跨运行合并后仍然非支配的全局近似前沿）、`pareto_solutions.json`（完整染色体决策）、`experiment_manifest.json`（全部运行参数）和 `pareto_front.png`（三目标前沿图）。前沿来自跨代外部 archive，而不再局限于最终种群中的单一代表解。
模型消融入口**支持通过 `--algorithm` 指定求解器**（可选 `spt`/`vnd`/`nsga2`/`nsga2_ls`/`nsga2_alns`）；
同一实例与求解种子下的各组合共享评价预算，并按实例汇总所有组合和重复形成 pooled reference front。
输出包括 `model_ablation.csv`、`pareto_points.csv`、`pooled_reference_front.csv` 和 `experiment_manifest.json`。

> **不要混淆"入口支持某算法"与"正式实验固定某算法"**：
> - 入口支持任意受支持算法，用于诊断；
> - 四模型诊断当前使用 **`nsga2`**，目的是隔离模型效应、不与尚未验证的混合方法捆绑；
> - **完整正式 `2^3` factorial 的既定统计设计定义在 `nsga2_alns` 上**，
>   并且要求全部八组合齐备；子集或换算法时 `factor_effects*.csv` 只写 `not_applicable` 与原因，不输出显著性。

## 评价版本与运行产物

`run_benchmark.py` 与 `run_model_ablation.py` 都接受 `--model-version {legacy,v2}`；默认 `legacy` 以保持历史回归，
新诊断一律显式传 `v2`。`--algorithms` 现包含 `nsga2_ls`（与 `nsga2_alns` 同算子、同调用概率，但**均匀**选择、不更新权重）
作为自适应选择的对照。`run_model_ablation.py --model-ids` 可选择八组合的任意子集，此时只输出描述性与回放汇总，
`factor_effects*.csv` 等表写入 `not_applicable` 与原因，不计算主效应或交互显著性。

两个入口都支持 `--resume`：只跳过条件**完全一致**且完整的已完成运行。这里的"不一致就换目录"**不限于代码版本**——
目录级 `experiment_contract.json` 固定以下全部条件，任一项变化都必须使用新目录，否则入口直接报错：

- `model_version` 与完整评价档案（`evaluation` / `evaluation_fingerprint`）
- 预算（`max_evaluations` / `pop_size` 等全部 `BenchmarkBudget` 字段）
- 源码指纹（含 `pyproject.toml` 与 `uv.lock`）
- 入口类型与 `suite`
- 消融入口还把 `algorithm` 视为固定条件（混用两个求解器会破坏配对设计）

**可声明扩展的维度**（允许在同一目录内追加）：算法、模型组、案例、实例种子、solver 起始种子与重复数。
汇总、manifest 与回放都从**目录运行集合**再生，因此追加后三者始终一致。

运行目录结构（`solution_io.py` 统一维护）：

```text
<output-dir>/
  experiment_manifest.json     实际生效配置、模型版本、代码指纹、计划/完成/跳过运行数
  instances/<model_fp>.json    每个规划模型变体的完整实例快照
  executions/<physical_hash>.json  四规划组共享的 Full 执行环境
  runs/<run_key>.json          完整运行单元：决策、目标、指标、收敛、预算、诊断计数、完整性校验
  runs.csv                     每次运行的汇总（含评价数、预算、终止原因、算子调用次数与搜索诊断）
  solutions.jsonl              每个非支配决策一行，含完整三段决策
  pareto_points.csv
  convergence.csv
```

`solutions.jsonl` 与各汇总 CSV 都可以从 `runs/` 的完整运行文件再生。回放：

```bash
uv run python scripts/reproduce/replay_solutions.py \
  --input-root outputs/local_v2_pilot/pilot_algorithm --execution-model saved \
  --output-dir outputs/local_v2_pilot/pilot_algorithm_roundtrip
uv run python scripts/reproduce/replay_solutions.py \
  --input-root outputs/local_v2_pilot/pilot_planning --execution-model full \
  --output-dir outputs/local_v2_pilot/pilot_common_execution
```

`saved` 必须逐位复现原目标（默认容差 `abs_tol=1e-8, rel_tol=1e-8`），不一致即非零退出；
`full` 在共同执行环境中重放规划决策，差值写入 `replay_results.csv`（原始有符号差，三目标均为最小化）。
`--execution-model full` 会校验执行环境确实是约定的 v2 Full（评价档案、PR/HT/EC 曲线与阈值），
拒绝把 legacy 或降级模型的快照当作 Full 回放。

> **示例中的输出目录用 `outputs/local_v2_pilot/`**。**已发布的审计结果位于 `outputs/claude_v2_reviewfix2/`**
> （另有 `outputs/claude_v2/`、`outputs/claude_v2_reviewfix/` 作为修复历史），它们是版本控制中的证据，
> 普通复现请使用新的本地输出目录，不要覆盖审计目录。
v2 语义与单位见[模型 v2 合同](../docs/model_v2_contract.md)，已执行诊断见[v2 小预算诊断报告](../docs/pilot_v2_report.md)。

```bash
uv run python scripts/reproduce/run_benchmark.py \
  --suite benchmark --cases S025 --model-version v2 \
  --instance-seeds 101 102 --solver-repeats 3 --solver-seed-start 50000 \
  --algorithms nsga2 nsga2_ls nsga2_alns \
  --max-evaluations 500 --pop-size 32 \
  --output-dir outputs/local_v2_pilot/pilot_algorithm
uv run python scripts/reproduce/plot_pilot_diagnostics.py
```

> ⚠ **正式 publication 暂不运行。** 先完成机制适用条件（PR/HT/EC binding boundary）诊断并锁定场景与参数，
> 再启动正式批次 —— 在机制是否参与决策尚未确定之前扩大统计规模，只会得到无法解释的效应表。

正式消融使用 `publication` 配置。**必须显式传 `--model-version v2`**：入口默认是 `legacy`，省略会静默产出
另一套语义的结果。合成案例以“实例种子”为统计单位，先平均同一实例上的配对 solver 重复；汶川案例是固定网络，
只运行一个实例副本并以 solver 重复为统计单位，避免把同一网络改名后当作独立实例。
建议按“案例 × 实例种子”分片，每个分片保留完整 30 次 solver 重复，例如：

```bash
uv run python scripts/reproduce/run_model_ablation.py --suite publication --model-version v2 \
  --cases S025 --instance-seeds 1 --solver-repeats 30 \
  --output-dir outputs/model_ablation_publication_shards/S025_i01
uv run python scripts/reproduce/model_ablation_analysis.py --input-root outputs/model_ablation_publication_shards --output-dir outputs/model_ablation_publication
```

如果还需按 solver 重复拆分，可用 `--solver-repeat-start` 指定起点；最终必须通过 `model_ablation_analysis.py` 合并，因为它会使用所有分片的 Pareto 点重新计算每个实例统一的 pooled reference front。正式分析另外输出 `model_summary.csv`、`factor_effects_raw.csv`、`factor_effects.csv`、`factorial_completeness.csv` 和 `analysis_manifest.json`。主效应与二阶交互采用效应编码的配对对比，报告实例级（汶川为 solver 级）均值、标准差、中位数、IQR、95% BCa bootstrap 区间、双侧符号翻转随机化检验和按“案例 × 指标”进行的 Holm 校正。

## 维护建议

`capacity_scale=1.0` 保留项目估算容量；更低数值仅用于压力测试，不代表汶川现场实测容量。当前车型单车当量 1.0/1.5/2.0/2.5 同样是待标定场景值。后续实验应复用 `reproduce/` 中的公共数据结构和评价函数，现已具备基线、消融、统计分析和 Pareto 输出框架；正式多实例、多重复运行仍待完成。
维修效率偏差使用共同随机数：同一种子下四种机制面对相同的 `xi_a^t`。`repair-efficiency-deviation=0` 用于验证没有新信息时 open-loop 与 rolling 不应产生虚假优势。
动态实验目录中的 `repair_efficiency_realizations.csv` 保存每个周期、每条受损道路的实际效率，便于独立审计共同随机数与复现实验。
阶段可视化会生成 `stage_00.png` 至 `stage_09.png`、`stage_overview.png`、`delivery_timeline.png`、`operation_sequence.png` 和 `stage_states.json`。需求点填色表示累计满足率，青色描边和节点大小表示本期新增配送；未配送点统一为白底橙圈，不在地图上额外标记不可达状态。每支维修队使用独立颜色和符号，彩色点线表示本期转场路径。`dispatch_routes/` 保存每个 Stage 的物资配送路线图，需求点旁按供应来源标注本期吨位；`dispatch_manifest.csv` 逐条保存供应点、需求点、吨位、车型、趟数、运输时间和完整路径。

`--crew-transfer-time-scale 1.0` 按物理路网最短时间估算受损路段中点之间的转场，并从周期维修工时中扣除；设为 `0` 可复现原来的无转场假设，设为大于 `1` 可表达拥堵、路况恶化或保守转场时间。周期图展示的是一个 8 小时周期末的累计状态，并非需求点在期初瞬间得到满足。

`--crew-min-access-progress 0.30` 要求维修队转场路径上的受损道路至少达到临时通行状态。维修队到达尚未打通的目标路段后会保留实际进入端点；在该路段达到通行阈值前，不能从另一端穿越到更深的待修路段。每期还会计算“本期实际修复后配送”与“保持期初道路状态、不实施本期修复”的反事实配送，报告修复新增吨位和新增可达点。

渐进恢复状态的默认含义为：`blocked`（进度 0–30%，容量和速度为 0）、`temporary`（30–60%，临时便道，容量/速度恢复到 30%）、`one_lane`（60–80%，单车道通行，恢复到 60%）、`basic`（80–100%，基本恢复，恢复到 80%）和 `full`（100%，完全恢复）。车型仍需同时满足自身进度阈值 30%、50%、70% 和 80% 才能通行。

正式算法 benchmark 使用 `--suite publication`，同样**必须显式传 `--model-version v2`**。汶川应单独指定 `--cases WEN38 --instance-seeds 1`，否则该入口会遍历默认实例种子而重复同一固定网络；合成案例按默认多实例运行。SPT 仅一次构造评价，其余搜索受 `max-evaluations` 上限约束。benchmark 汇总与绘图先平均实例内 solver 重复，图中误差条为实例间标准差；固定汶川实例的零误差条不表示求解器没有随机波动，应另查看各 solver 运行。
