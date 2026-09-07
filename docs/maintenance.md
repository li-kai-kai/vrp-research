# 仓库清理与维护

日期：2026-09-07。本轮承接工作区已有的未提交清理，保留研究实现和历史可追溯性。

## 文件去留

| 对象 | 处理与理由 |
|---|---|
| 当前说明 | 统一为 `research.md`、`experiments.md`，由根 README 和脚本指南导航 |
| 旧 proposal、结果报告、审稿轮次与旧交接 | 移至 `archive/`，注明历史状态，退出当前结论入口 |
| 汶川数据、原模型/GA说明、综述正文 | 保留在 `background/`，作为来源和背景 |
| 硬编码 benchmark 示意脚本 | 删除 `plot_benchmark_illustration.py`，避免把构造数值误作实验结果 |
| benchmark 绘图 | 保留 `plot_benchmark_results.py`，显式读取 `runs.csv`，按真实 case ID 和规模绘图 |
| 初始网络图 | `plot_initial_network.py` 复用共享汶川实例和 benchmark 配置，补齐 Linux 中文字体候选 |
| OCR 工具和下载说明 | 输入文献页面/OCR 语料已不在工作区，移除失效入口 |
| 旧 PPT 和构建脚本、仓库内论文写作 skill、重复 PDF | 沿用已有删除，不属于当前可复现研究入口；已跟踪旧版仍可从 Git 历史查阅 |
| 实验和共享模块 | 普通 GA 的五个模块移至 `scripts/legacy/`；容量原型、共享模型/实例、机制、benchmark、消融与分析仍在 `scripts/reproduce/` |
| 旧实验产物 | 72 个文件打包到本地压缩归档，逐文件 SHA-256 与归档 SHA-256 均已核验 |

文档移动映射、被删除脚本原因和旧产物逐文件哈希见 [cleanup_inventory.json](cleanup_inventory.json)。本地归档与新生成的实验产物都在 `outputs/`，不随 Git 克隆分发。

## 测试结构

原 `test_reproduce.py` 与混合职责的 `test_benchmark.py` 已按主题拆分；普通 GA 隔离后，共享实例测试留在主目录，旧模型测试迁入可自动发现的 `tests/legacy/`。通过 AST 比对确认原有 **21 个测试方法内容全部保留**，无删除、重复或断言改写；2026-09-07 全部通过。

| 文件 | 数量 | 重点 |
|---|---:|---|
| `tests/test_instance_generator.py` | 1 | 共享实例种子与规模 |
| `tests/legacy/test_baseline.py` | 2 | 旧模型不可达需求、满足率与维修唯一性 |
| `tests/test_capacity_recovery.py` | 6 | Pareto archive、供给上限、恢复模式、独立消融开关、边容量 |
| `tests/test_dynamic_interaction.py` | 4 | 零偏差安慰剂、状态快照、转场时间、信息改变决策 |
| `tests/test_benchmark.py` | 4 | 算例覆盖、可复现车队、预算、HV/IGD 已知值 |
| `tests/test_model_ablation.py` | 4 | 八组配对、已知效应、缺组拒绝、分片统一参考前沿 |

## 恢复历史产物

归档：`outputs/archive/pre_cleanup_20260907.tar.gz`。归档内部路径不含 `outputs/` 前缀，恢复到独立目录，避免覆盖当前结果：

```bash
mkdir -p outputs/restored_pre_cleanup_20260907
tar -xzf outputs/archive/pre_cleanup_20260907.tar.gz -C outputs/restored_pre_cleanup_20260907
```

归档只包含清单中的 72 个文件，不能恢复旧文档中提到但本地不存在的 Pareto 或 publication 结果。

## 后续约定

- 新实验复用 `scripts/reproduce/`，图表必须读取实际数据；示意内容必须明确标注。
- 原始结果、图和临时日志放入 `outputs/`；版本化文档保存参数、关键结果、证据哈希与结论边界。
- 改变模型、参数或评价口径后，旧结果保留为历史，不能只更新报告日期后继续使用。
- 正式结果必须保存实例/solver 种子、评价预算、参数 manifest 和源文件指纹；只通过 smoke 不等于完成正式实验。

## 普通 GA 隔离补充

`run_random_experiments.py`、`ga_solver.py`、`dispatch.py`、`metrics.py`、`visualize.py` 从 `scripts/reproduce/` 迁至 `scripts/legacy/`，内部导入同步更新，算法和测试方法内容保留。旧入口不留包装，运行方式见 [legacy 指南](../scripts/legacy/README.md)。`tests/legacy/__init__.py` 保证旧模型两项测试仍被标准全量命令发现。当前研究模块不反向依赖 legacy。

`validation_20260907.json` 中的实验源文件指纹记录原实验核验时的路径和内容；不因迁移重写历史指纹。旧路径与新路径映射见 `cleanup_inventory.json`；benchmark/消融 manifest 引用的核心实验源文件未因此移动。
