# WEN38 预算阶梯重跑（当前源码）

日期：2026-10-14。本目录是在 2026-10-13 的 consolidation 重构（09754fa）之后，用当前源码版本重跑的 WEN38 预算筛检完整阶梯：预算 500/2000/5000/10000，80 次搜索、350000 次评价，4 个规划模型 × 5 个配对 solver seed。

追加（同日）：5000→10000 一步经预声明判据判定未通过（0/5，HV 中位 +6.5%）后，按协议预先声明的 confirmation budget 追加 20000 档：20 次搜索、400000 次评价。

Phase 2 执行说明：为缩短回合时间，20000 档采用**每个（种子 × 模型）一个单模型 RunStore** 的布局（`budget_20000/seed_60000_PR1_HT1_EC1/` 等），最多 20 个并发（超过本容器 13 核 CPU 配额，该档的 runtime 因此被抬高，仅作运行记录）；前三档仍为每种子一个含 4 模型的 store、最多 8 并发。分析脚本对目录布局无要求。首次尝试按每种子一个 store 启动，3 分钟后、**无任何运行完成**时重启为当前布局，未丢弃已完成的证据；`protocol.json` 保持跑前声明原样（其 `runtime_scope` 描述的是 phase 1 的执行方式）。四档分析结果保留在 `analysis_phase1/`，五档分析写入 `analysis/`。

## 为什么是重跑而不是续跑

- 冻结的 500/2000/5000 运行产自源码版本 7ee2cec（指纹 f55a7149…），其 RunStore 未随仓库分发（见 `outputs/report_reproduction/input_roots.json` 记录的原始 Mac 路径）；
- 当前源码的指纹为 a5942f81…：09754fa 改动了 8 个指纹文件（model.py、capacity_recovery.py、objective_precision.py、run_benchmark.py、benchmark_suite.py、benchmark_algorithms.py、run_model_ablation.py、model_ablation_analysis.py）；
- 分析脚本要求同一筛检内所有运行共享同一源码指纹，新旧运行无法并入同一次分析。

本目录是一次独立重跑，不修改、不替代 `outputs/report_reproduction/` 的冻结证据。

## 设计（跑前声明）

与冻结协议相同：WEN38 / instance seed 1 / nsga2 / pop 32 / 交叉 0.90 / 变异 0.20 / solver seeds 60000–60004（repeat 0–4）。判据相同：每配对 HV 相对变化 ≤1% 且 IGD 绝对变化 ≤0.01，每模型 ≥4/5 对，四模型连续两步。confirmation_budget 预先声明为 20000。详见 `protocol.json`。

## 运行环境

本机 128 核 Linux；最多 8 个独立 store 并发；runtime 仅作描述性记录。搜索命令见 `commands.sh`，分析命令见 `analyze.sh`。

产物：`budget_<B>/seed_<S>/` 为 RunStore；`analysis/` 为判定输出（`budget_decision.json` 等）。
