# 交接文档：ISPA 2026 正式 full-budget 并行 NSGA-II 实验

> 状态（2026-09-26）：旧 2 核 VM 上 31/39 个 run 已完成并验证通过，
> 剩余 8 个 M100 run 因 /tmp 被清空而中断。新机器上**直接重跑全部**即可
> （随机种子固定，前沿结果确定性一致，只有 wall-clock 时间会变）。

## 1. 要跑什么

`exp/parallel_nsga2.py` —— 对论文 RQ3/RQ4 的正式实验：

- **RQ3**：WEN38 实例，budget=1600 评估 / pop=32，solver seeds {11,22,33} ×
  workers {0,1,2,4,8} = 15 runs。验证跨 worker 前沿/HV/IGD 逐位一致 + wall-clock 加速比。
  workers=0 为串行路径（仓库原生 NSGA-II 的忠实复刻，用于一致性基线）。
- **RQ4**：WEN38/S025/S050/M100 × workers {1,2,4,8}，seeds {11,22} = 24 runs。
  budgets：WEN38 1600 / S025 1600 / S050 800 / M100 400，pop 均为 32。

设计要点（与论文 §4 master-worker 协议一致）：

- 仅 offspring 的 fitness evaluation 并行；选择/交叉/变异/RNG/档案/预算会计
  全部集中在 master 进程。
- **RNG 消耗顺序与仓库 `_solve_nsga` 逐位一致**（每代先创建全部 offspring
  再批量评估；evaluation 本身不消耗 RNG，local search 关闭）。
- **必须保留的细节**：`_Evaluator.evaluate` 有 objective-cache 逻辑——
  无 crossover 且 `_mutate` 未改变的 clone 会直接复用父代目标值、**不消耗预算**。
  脚本里已按原逻辑镜像（`child.objectives is not None` → cache hit）。
  漏掉这一点会导致串行路径与仓库结果不一致（曾实测 front 19 vs 18）。
- Worker 进程用 fork 继承父进程已构建好的 instance（copy-on-write），
  不需要每个 candidate 重建 instance。任务按代切分、按原始 index 回装，
  保证 candidate 顺序与调度无关。

## 2. 已验证的结论（旧机器实测，可直接写入论文）

- `--validate-only`：串行路径与仓库 `solve_benchmark_algorithm('nsga2')`
  在 budget=320/pop=16/seed=11 下**前沿逐位一致**（19 点，320 次评估）。
- 并行路径 W=2 在小预算下前沿与串行逐位一致，cache 命中数一致（13/13）。
- 31 个正式 run 中，**同一 (case, seed) 的前沿大小跨 workers 完全一致**：
  - WEN38：seed11→56 点，seed22→41 点，seed33→35 点（W=0/1/2/4/8 全同）
  - S025：seed11→2 点，seed22→6 点（W=1/2/4/8 全同）
  - S050：seed11/22→10 点（W=1/2/4/8 全同）
- 旧 2 核共享 VM 上加速比（WEN38，1600 评估）：
  W=1 ≈0.99x，W=2 ≈1.48x，W=4 ≈1.44x，W=8 ≈1.40x。
  W≥4 无提升是因为 2 核被超订（oversubscription）——新机器上这个数字会好看很多，
  这正是换机器的意义。**不要引用旧机器的加速比作为最终结论**。

## 3. 新机器运行步骤

```bash
# 1. 准备仓库（你的 vrp-research，需包含 scripts/reproduce/ 下的 benchmark 代码）
# 2. Python 依赖：networkx, numpy（pip install networkx numpy 即可；仓库本身用 uv，但脚本只用系统 python）
pip install networkx numpy

# 3. 指向你的仓库路径（默认 /tmp/vrp-research）
export VRP_RESEARCH_REPO=/path/to/vrp-research

# 4. 先跑快速校验（约 1 分钟）：必须看到 [validate] OK
python3 exp/parallel_nsga2.py --validate-only

# 5. 跑全量（39 runs；M100 单次评估约 0.86s，多核机器上预计 1-2 小时）
nohup python3 exp/parallel_nsga2.py > exp/full_budget_run.log 2>&1 &
```

输出：

- `exp/full_budget/results.json` —— 每个 run 的完整前沿（原始目标值三元组）、
  runtime、评估数、cache 命中数、pooled HV/IGD、与串行基线的前沿一致性标记
- `exp/full_budget/results.csv` —— 同上摘要
- 控制台尾部直接打印 RQ3 表、RQ4 加速比表（speedup vs W=1，seeds 11/22 均值）、
  一致性检查（`non-identical fronts` 必须为 0）

HV/IGD 计算：复用仓库 `run_benchmark.py` 的 `pooled_quality_indicators`，
按 case 把全部 run 的前沿 pool 成 reference front，在 V2 精度量化坐标下归一化。
跨 worker 前沿逐位一致 ⇒ HV/IGD 必然一致，表中如实报告即可。

## 4. 跑完之后（论文收尾）

1. 把 `results.csv` 的 RQ3/RQ4 表填进 `main.tex`，替换当前的 in-progress 表述
   （旧微实验表格保留作为 pilot，或删掉二选一）。
2. 重编 PDF：`cd ~/workspace/ispa2026 && pdflatex main.tex`（IEEEtran.cls 已在目录下）。
3. 投稿前仍待办：作者/单位信息（tex 中 TODO）、M200（可选）、Related Work 引文补强、
   ISPA 2026 页数限制复核。

## 5. 旧机器部分结果存档（full_budget_run.log，31 runs）

| case | seed | W=0 | W=1 | W=2 | W=4 | W=8 | front |
|------|------|-----|-----|-----|-----|-----|-------|
| WEN38 | 11 | 95.9s | 96.9s | 64.5s | 65.5s | 67.1s | 56 |
| WEN38 | 22 | 96.3s | 95.9s | 65.3s | 68.7s | 69.7s | 41 |
| WEN38 | 33 | 96.9s | 97.3s | 65.7s | 66.7s | 69.1s | 35 |
| S025 | 11 | – | 105.4s | 71.9s | 72.9s | 73.5s | 2 |
| S025 | 22 | – | 106.8s | 73.0s | 73.4s | 73.6s | 6 |
| S050 | 11 | – | 217.7s | 147.0s | 152.5s | 150.8s | 10 |
| S050 | 22 | – | 223.1s | 151.7s | 155.5s | 156.3s | 10 |
| M100 | 11/22 | – | 未完成 | 未完成 | 未完成 | 未完成 | – |

（evals：WEN38/S025=1600，S050=800；M100=400 未跑。时间仅供参考，不要进论文。）
