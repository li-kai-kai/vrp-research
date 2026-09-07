# 普通 GA 历史复现链

此目录保留早期原模型风格的普通 GA 实验，用于历史复现和参考。其目标与配送模型不同于当前容量三目标 benchmark；正式算法比较使用 `scripts/reproduce/run_benchmark.py`。

| 文件 | 职责 |
|---|---|
| `run_random_experiments.py` | 随机案例实验入口与结果导出 |
| `ga_solver.py` | 普通 GA 编码、遗传操作与求解 |
| `metrics.py` | 旧模型解码、逐期评价与适应度 |
| `dispatch.py` | 旧模型物资配送 |
| `visualize.py` | 旧模型结果绘图 |

共享的 `model.py` 和 `instance_generator.py` 仍放在 `scripts/reproduce/`。依赖方向为 legacy 使用共享模块；当前模型与 benchmark 不依赖 legacy。

在仓库根目录快速检查一例：

```bash
uv run python scripts/legacy/run_random_experiments.py \
  --nodes 25 --gamma 3 --damage 0.1 --eta 8 --seeds 1 \
  --pop-size 4 --generations 2 --output-dir outputs/legacy_ga_smoke
```

也支持 `uv run python -m scripts.legacy.run_random_experiments` 加相同参数。`--config quick` 是历史实验网格，默认仍有 54 组参数组合和较大 GA 预算；检查入口时使用上述显式小参数。

旧模型两项回归测试位于 `tests/legacy/test_baseline.py`，由 `tests/legacy/__init__.py` 保证全量测试自动发现；共享实例生成测试位于 `tests/test_instance_generator.py`。

```bash
uv run python -m unittest discover -s tests
```

原 `scripts/reproduce/` 下五个旧路径已迁移，不保留兼容包装；外部调用需改用此目录。历史文档与旧证据指纹可保留迁移前路径，映射见 `docs/cleanup_inventory.json`。
