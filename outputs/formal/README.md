# 正式实验（套餐 B）

日期：2026-10-14。按 `docs/formal_experiment_protocol.md` 的套餐 B 执行：实例 S025 1–15 / S050 1–9 / M100 1–6 + WEN38 单例；每实例 3 个求解种子（`90000 + 实例×10000 + repeat`，repeat 0–2）；8 个模型组合 × `nsga2`；预算 10000/5000/2000/10000。

## 内容

- `protocol.json`：跑前声明（含源码指纹与计划量：744 次运行、5,208,000 次评价）。
- `model_track_commands.sh`：744 条命令，S025 → S050 → M100 → WEN38 排序；单模型 RunStore，12 并发。
- `model_track.log`：运行日志。
- `model_track/<case>_i<inst>_s<seed>_<model>/`：RunStore（每运行一个目录）。

敏感性轨（20 格子 × 12 单元 = 240 次运行）：四个轴的覆写入口均已实现并测试（`--capacity-scale`、`--threshold-scale`、`--node-role-strategy`、`--repair-crews`、`--repair-duration-scale`、`--fleet-scale`、`--supply-scale`），命令待生成。

## 执行记录

- 首次启动（2026-10-14）在跑出 16 个运行后停止：覆写开关的实现改动了源码，导致新旧进程的源码指纹不同（16 个为 `bbf64bd3…`）；同一次实验必须单一源码版本，故整轨在**最终版本**（指纹 `644784087ed278ff`）上从头重启，旧部分封存在 `model_track_superseded_bbf64bd3/`（部分、不进入分析）。

分析入口：`scripts/reproduce/model_ablation_analysis.py --input-root outputs/formal/model_track`（要求每个 (案例, 实例, 种子) 的 8 组合块完整）。

## 分析产物与执行侧检验

- `analysis_<档>/`：规划侧正式统计（factor_effects 等，`model_ablation_analysis.py`）。
- `exec_<档>/`：共同执行回放（`common_execution_analysis.py`，四模型屏幕）。
- `exec_tests/`：执行侧配对检验的**校正版结果**（`scripts/reproduce/execution_side_analysis.py` 生成）：家族预声明（每档 3 简化模型 × 2 指标 = 6 检验、档内 Holm）、`execution_tests.csv`（原始与校正 p）、`magnitude_context.csv`（执行超体积与代表 F1 的量级参照）、`analysis_manifest.json`（抽样数 20000、种子 20260831、家族声明）。超体积按共同参照前沿归一化，**同档内可比、跨档不可比**。
- `exec_all/`：八组合（2³）全量共同执行回放（`common_execution_analysis.py --factorial`，744 个店、14554 条决策）。
- `exec_factorial/`：执行侧 **2³ 因子效应**（`scripts/reproduce/execution_2x3_analysis.py`）：主效应 + 交互项，7 个执行侧指标，Holm 家族为每（档, 指标）的 7 项。关键结构结果：**HT 的主效应与 PR×HT 交互效应精确相等**——因为二值恢复下车型阈值不起作用（HT 的价值完全来自 PR 制造的部分恢复状态）。
