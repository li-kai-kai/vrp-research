# WEN38 天然 HT threshold-sensitive corridor 诊断

日期：2026-09-20。基准 HEAD：`502bede`。
本报告回答一个问题：**真实 WEN38 路网及其半真实覆盖中，是否天然存在 threshold-sensitive corridor，
使部分恢复状态下的车型通行集合差异真正改变救援配送与目标。**

> **未修改 WEN38。** 拓扑、道路旅行时间、容量、车型阈值、v2 时间语义、`FullExecutionProfile`
> 与搜索算法全部原样读取。本轮的 overlay 只重采样**业务角色**与**受损边**，
> 并且每次运行都断言拓扑指纹未变（`topology_fingerprint`）。
> 也没有为了让 HT 生效而调维修时间、阈值或人工放置 corridor。

## 0. 四个层次

结论必须分层陈述，不能把任一层直接写成"HT 有效"：

| 层次 | 判据 | 本轮 WEN38 |
|---|---|---|
| **结构存在** | 存在受损边，删除它会**严格**延长或切断某个 (supplier, demand) 的路线 | 16 条受损边中 **15** 条 |
| **动态 exposure** | 某周期期初的恢复进度只放行**真非空真子集**的车型 | 16 条（20 个决策中共 **5–21** 个边—周期/决策） |
| **dispatch participation** | HT on/off 下同一决策的 canonical allocation 集合不同 | **19 / 20** 个决策 |
| **objective effect** | 两者在 `V2_PRECISION.key()` 下不同 | **19 / 20** 个决策 |

**WEN38 落在"存在完整链路"。**

## 1. 结构扫描：最高依赖的受损边不是桥

16 条受损边按 OD 依赖度排序（`od_shortest_path_dependency_count` = 删除后路线变长或断开的 OD 对数）：

| 排名 | 边 | 是否桥 | OD 依赖 | 绕行比均值 | 绕行比最大 | 切断 OD 数 | repair/eta |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | **17-22** | **否** | **46** | 1.097 | 1.49 | 0 | 0.38 |
| 2 | **1-17** | **否** | **39** | 1.079 | 1.43 | 0 | 1.88 |
| 3 | 4-5 | 是 | 18 | — | — | 18 | 0.38 |
| 4 | 22-24 | 否 | 11 | 1.072 | 1.24 | 0 | 1.69 |
| 5 | 36-37 | 否 | 8 | 1.559 | 2.38 | 0 | 0.69 |
| … | （其余 11 条，依赖 1–6） | | | | | | |

**前两名是普通道路，不是桥。** 5 条受损桥的依赖度反而更低（18 / 6 / 6 / 3 / 3），
而且它们**切断**其 OD（绕行比记为 `inf`，单列 `detour_ratio_infinite_count`），
不是延长路线——所以桥的"绕行比均值"是空值而不是 1.000：把受影响与不受影响的 OD 混在一起平均，
会让桥看起来无害，正是需要避免的读数。

`detour_ratio_mean` 只对**该边实际影响的 OD**取平均。`supplier_demand_od_count` 与
`od_shortest_path_dependency_count` 的区分见 `scripts/reproduce/ht_natural_corridor.py` 的文档字符串：
前者是"最短路经过"（用 `d(s,u)+t+d(v,d)==d(s,d)` 精确判定，无需打破并列），
后者是"删除后严格变差"，分类使用后者。

## 2. 动态 exposure 与四级分类

每条受损边独立给出四个标记，**不合并成单一标签**：

| 类别 | 条数 |
|---|---:|
| 结构 corridor（依赖 > 0） | 15 |
| 动态 threshold corridor | 16 |
| operational corridor | 16 |
| objective-binding corridor | 16 |

**其中 11 条是非桥道路，且全部 11 条都是 operational + objective-binding。**
5 条桥也全部如此。所以：

> **HT 在 WEN38 上不依赖桥。** 非桥高依赖边同样形成 threshold-sensitive corridor，
> 且按 OD 依赖度排序时它们占据首位。

### 2.1 一个必须说明的归因限制

`dispatch_changed_decisions` / `objective_changed_decisions` 是**条件计数**：
在"该边被判定为 threshold-sensitive"的那些决策里，有多少个决策的 dispatch / 目标发生了变化。
它是定义清楚的量，**不是因果归因**——目标是整个决策的全局量，不可能属于某一条边。

反例就在表里：边 **18-25** 的 OD 依赖为 **0**（不是结构 corridor），
却仍然是 operational + objective-binding，因为它在 20 个决策里恰好都处于敏感状态。
要真正判定"某条边是否 objective-binding"，需要**逐边消融**（只放开该边的阈值限制），
本轮没有做，因此不做这一宣称。

## 3. WEN38 原始场景的固定决策结果

20 个固定决策（SPT + 19 个固定随机决策）：

| 指标 | 值 |
|---|---:|
| 有动态 exposure 的决策 | 20 / 20 |
| 有 dispatch participation | 19 / 20 |
| 有 objective effect | 19 / 20 |
| ΔF2 相对变化（HT off 相对 HT on） | 平均 **−6.9%**，最大 −23.3% |
| 最大 \|ΔF2\| | 41 909 分钟 |

**唯一不触发的是 SPT**：它有动态 exposure（6 个边—周期、59 个 OD—周期），
但 dispatch 与目标都不变——暴露而没有参与，正是分层要保留的情形。

### 3.1 机制已验证，不只是统计量

以 `random_0` 为例，车型使用量：

| | 车型 1（阈值 0.30，5 t） | 车型 2（0.50，10 t） | 车型 3（0.70，15 t） | 车型 4（0.80，20 t） |
|---|---:|---:|---:|---:|
| HT **on** 趟次 | 310 | 220 | 174 | 152 |
| HT **off** 趟次 | 160 | 220 | 213 | 160 |
| HT on 吨位 | 1528.7 | 2145.0 | 2472.9 | 2853.3 |
| HT off 吨位 | 784.7 | 2145.0 | 3051.9 | 3018.3 |

关闭 HT 后，阈值统一为 0.30，大型车不再被部分恢复的道路挡住，于是小型车（1 型）的趟次从 310 降到 160，
3/4 型接替运量。**同样的送达总量（9000 t = 供给上限），更少的趟次与更短的总时间。**

> 由此两点必须写清：
> 1. **符号是解析确定的**。HT off 是 HT on 的**严格放宽**（统一 0.30 放行的车型集合是原集合的超集，
>    由 `test_ht_off_is_a_relaxation_of_ht_on` 固定），所以 F2 只会下降。经验部分是**幅度**，不是方向。
> 2. **HT 在 WEN38 上绑定的是成本，不是覆盖**。两种设定下 `remaining_supply` 都为 0、
>    送达量相同；F1 变化很小，效应集中在 F2（加权分钟）。

## 4. 半真实覆盖（60 个 overlay）

保持 WEN38 拓扑、旅行时间、容量、车型系统与阈值不变：

- **SR-A（20）** 只重采样 supplier / demand 节点与需求量；数量与总量保持不变。
  注意 WEN38 是 38 节点 / 3 supplier / 35 demand，需求点几乎是 supplier 的补集，
  所以 SR-A 的自由度主要是"哪 3 个节点成为供应点"。
- **SR-B（20）** 只重采样受损边：从 51 条边中**均匀**抽 16 条，原维修时间多重集重新指派。
- **SR-C（20）** 两者同时重采样。

**均匀性是被测量而不是被声称的**：200 次抽样中，抽中桥的比例均值 **0.153**，
与网络自身的桥比例 **0.157** 一致（`within_base_rate_band: true`）。
若 overlay 在挑桥，这个数会显著高于基线。

### 4.1 结果：60 个 overlay 里没有一个"不活跃"

| 分层（5 个固定决策中目标变化的个数） | overlay 数 |
|---|---:|
| inactive（0） | **0** |
| natural-active（1–2） | 2 |
| strong-natural-active（3–5） | **58** |

分层阈值在跑任何 overlay **之前**就写死在代码里（`SCENARIO_STRATA`），不是事后选的。
**60 个 overlay × 5 个固定决策 = 300 个决策中，目标发生变化的有 246 个，为 0 的一个也没有。**

后果之一：本轮**没有天然的 inactive 场景**可作对照，因此 §4.2 的搜索只覆盖了两个活跃分层。
这本身是结果，不是缺陷——但它意味着"HT 何时不绑定"这个问题在 WEN38 系列上无法用 inactive overlay 回答。

### 4.2 小预算搜索：忽略 HT 的规划代价

在没有 inactive 分层的情况下，对两个存在的分层各取一个代表 overlay 跑
`nsga2`（200 次评价、种群 16、配对 solver seeds 70001/70002）：

| 规划模型 | 决策数 | 目标改变 | 均值 \|ΔF2\| | 最大 \|ΔF2\| |
|---|---:|---:|---:|---:|
| Full（自回放） | 92 | **0** | 0.0 | 0.0 |
| No-HT | 96 | **74** | 5 500 | 36 591 |

**Full 自回放恒等检查：92 个决策，最大绝对误差 0.00e+00。**
No-HT 规划出的决策一旦放入统一 Full 环境执行，目标大量改变——即忽略 HT 的规划代价是真实的，
不只是固定决策下的重算差异。

## 5. dispatch ↔ objective 两个方向

| 方向 | WEN38 原始（20 决策） | overlay（300 决策） |
|---|---:|---:|
| objective 变 ⇒ dispatch 变（必要性） | 0 反例 | 0 反例 |
| dispatch 变 ⇒ objective 变（充分性） | 0 反例 | 0 反例 |

**在 WEN38 及其全部覆盖上，两个方向都零反例。** 这与合成网络 M100 形成对照——
M100 上充分性方向破了 3 例（关闭 HT 使车型可互换，配送器对平局作出不同选择而目标逐位相同）。
WEN38 上不存在这种平局：阈值差异在这里确实改变了可行路径集合。

## 6. 结论

> **在 WEN38 真实拓扑及其 60 个半真实业务/损伤覆盖中，异质车型阈值的作用并不要求受损道路是图论意义上的割边。**
> 16 条受损边中有 15 条是结构 corridor，其中 **11 条不是桥**；按 OD 依赖度排序，
> 前两名（17-22、1-17）都是普通道路。桥是这一条件的**极端情形**（它切断而非延长路线），
> 而高依赖、高绕行的非桥道路同样形成 threshold-sensitive corridor。
>
> 该机制在 WEN38 上**绑定的是配送成本而非覆盖**：关闭阈值异质性使 F2（加权分钟）平均下降 6.9%、
> 最多 23.3%，而送达总量与 F1 几乎不变。忽略 HT 的规划决策在统一 Full 执行下 74/96 改变目标，
> 均值 \|ΔF2\| 5 500 分钟。

### 不得据此宣称的结论

- 不得把四个层次中的任一层直接写成"HT 有效"。
- 不得把 per-edge 的 `objective_changed_decisions` 写成对该边的因果归因（见 §2.1）。
- 不得把 F2 的方向写成经验发现：符号由"HT off 是严格放宽"解析决定，经验部分是幅度。
- 不得说"HT 在 WEN38 很重要，所以在其他路网也重要"——本轮只有一张真实路网。
- 不得把 60 个 overlay 称为 60 张独立路网：它们是**同一物理拓扑上的情景覆盖**。
- 不得声称已定位"HT 何时不绑定"：本轮 60 个 overlay 中没有 inactive 情形。

## 7. 产物

```bash
uv run python scripts/reproduce/ht_natural_corridor.py \
  --random-decisions 19 --overlay-seeds 20 \
  --search --max-evaluations 200 --pop-size 16 --solver-seeds 70001 70002 \
  --output-dir outputs/ht_natural_corridor_audit
```

| 产物 | 内容 |
|---|---|
| `wen38_edge_structure.csv` | 16 条受损边的桥/介数/OD 依赖/绕行比/维修时长 |
| `wen38_ht_exposure.csv` | 边—周期级动态 exposure（决策 × 周期 × 受损边） |
| `wen38_ht_od_exposure.csv` | **仅敏感**的 OD—周期（可行性分裂 / 短路分裂） |
| `wen38_ht_fixed_decision_effect.csv` | 20 个决策的 dispatch 与目标效应 |
| `wen38_ht_corridor_ranking.csv` | 逐边四级分类与依赖度排序 |
| `semi_real_overlay_manifest.csv` | 60 个 overlay 的类型/种子/分层/拓扑指纹 |
| `semi_real_ht_summary.csv` | 逐 overlay 汇总 |
| `semi_real_ht_decisions.csv` | 逐 overlay 决策明细（供核对汇总） |
| `wen38_ht_search_replay.csv` | Full / No-HT 规划 + 统一 Full 回放（含完整决策） |
| `manifest.json` | git sha、源码哈希、拓扑指纹、阈值、eta/horizon、抽样检查、预算与种子 |

`manifest.json` 明确记录 `statistical_unit = "scenario overlays on one common physical topology;
not independent road networks"`，并记录 `topology_invariant_across_overlays: true`。
