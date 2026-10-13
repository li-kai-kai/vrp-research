# 灾后道路恢复与救援物流：当前研究

本分支整合 v2 模型机制研究与并行 NSGA-II 论文，基于 `70540c9`（2026-09-26）。仅支持 v2 评价语义；普通 GA、旧动态实现、旧评价语义、被替代的报告及实验结果已移出当前树。

当前成果：PR/HT/EC 机制适用条件诊断、汶川共同执行与预算审计、136 次并行运行、ISPA 论文源稿。并行实验验证固定预算下结果一致与计算加速；500–5000 次评价的 WEN38 搜索仍未达到稳定平台。正式模型效应统计、专用大邻域与 v2 动态研究尚未完成。

## 阅读入口

- [研究问题与边界](docs/research.md)
- [当前实验与证据索引](docs/experiments.md)
- [v2 模型合同](docs/model_v2_contract.md)
- [运行指南](scripts/README.md)
- [论文源稿](paper/ispa2026/main.tex)与[已编译PDF](paper/ispa2026/main.pdf)
- [整合清单与验证](docs/consolidation.md)

## 运行

Python 3.12+；并行入口使用 Linux/WSL 的 fork 进程模型。

```bash
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv run python scripts/reproduce/run_benchmark.py --suite smoke --cases S020 --instance-seeds 1 --solver-repeats 1 --algorithms nsga2 --max-evaluations 12 --pop-size 4 --output-dir outputs/local_smoke
uv run python exp/parallel_nsga2.py --validate-only
```

当前研究的所有实例和实验入口默认 v2；旧模型版本会报错。结果目录中的快照、参数和原始目标保持原样，来源哈希不改写。新运行使用新的输出目录。版本控制中的结果是冻结证据，不使用新计时覆盖。

| 目录 | 内容 |
|---|---|
| `scripts/reproduce/` | v2 模型、共享求解器、机制诊断、方案回放和统计分析 |
| `scripts/plot_*.py` | 从实际数据生成图表 |
| `exp/` | 并行入口与冻结的136次运行 |
| `outputs/` | 仍被当前结论引用的最终证据集 |
| `paper/ispa2026/` | 论文、模板、数据生成的表格 |
| `tests/` | 当前模型、搜索、回放与证据回归 |
| `references/` | 原始参考文献 |
