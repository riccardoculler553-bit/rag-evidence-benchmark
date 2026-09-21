# FINAL VERDICT — Semantic Capability Materialization 的研究生死裁决

- 生成时间：2026-09-19 16:18:18
- 依据：实验 1（Adaptive，840 cells）× 实验 2（语义特异性反证，含真实 GLM-4.5-Air 微探针）× 实验 3（外部基线 + source drift + prior-art 边界）
- 全部数字由 `make_final.py` 从原始 JSON 程序化抽取，未手抄。

---

## 0. 一句话结论

> **NO — 在当前证据下，Semantic Capability Materialization 不构成独立于 Predicate/UDF Pushdown + Materialized View + Cache + Cost-Based Optimization 的新的 RAG 基础原理。** 它的工程价值成立（Tier 1），研究新颖性不成立（Tier 0）。

---

## 1. 现有结果究竟证明了什么？

1. **Build Position 的因果效应在受控条件下是真实的**：固定 source snapshot / logical plan / capability implementation / model / prompt / schema / batch=1 / T=0，仅改 CapabilityBuild 位置，语义工作量与成本可下降约 63%（v1.2 主实验），且质量逐 query 完全相同（Δ=0）。
2. **在无限持久化存储 + 无 source drift 下，最优物理计划退化成一个不需要任何自适应的固定选择**：『总是 Late-Persistent』相对离线 clairvoyant oracle 的平均 regret 仅 0.00137，且在 60.00% 的 cell 上成本与 oracle 完全相等（残余差异全部来自 validation 开销）。
3. **在线自适应不仅没有增量价值，在多数非优势场景下反而有害**：Adaptive（D）相对教科书式 Simple CBO——成本相同 609 个 cell，更优 72 个（全部集中在 s=75/100，即 oracle 也会选 EAGER 的区域），**更差 159 个**；逐 cell 成本比均值 **1.3961**。D 的平均 regret 0.8507 远高于 CBO 的 0.2615、更远高于平凡策略 C 的 0.00137。
3b. **最优计划本身是可分解的代价比较，而非策略竞赛**：840 cell 中 oracle 逐能力选择 EAGER 378 次、clairvoyant-late 798 次、per-query 784 次；最佳策略标签分布为 {'B': 336, 'C': 342, 'A': 162}。
4. **收益机制与 semantic 无关**：成本严格匹配的 generic expensive UDF 对照下，total_cost 最大绝对差为 **0**（跨 80 个 cell）。
5. **能力捆绑是 sub-additive 且不损失精度**：真实 GLM-4.5-Air 实测 8 字段一次调用 / 8 次单字段调用 = **0.2785**，而广度 1→8 的字段准确率变化为 **0**（无下降）→ 最优规则退化为『按需最大化捆绑』，即 generalized materialized view。
6. **旧的 C/A > 1『边界』是物化作用域/缓存容量的伪影**：workload 级无限作用域下 C/A 均值 0.6056；cell 级作用域下 11.98；容量 10%·LRU 下 11.72；容量 1%·LRU 下 11.96。
7. **增量重建的优势是经典 IVM**：drift=5% 时受影响行重建成本 0.016198 vs 全量重建 5.1682，Adaptive 的选择恒等于 min(full, incremental) = incremental，无决策空间。

---

## 2. 现有结果不能证明什么？

- 不能证明『Late 普遍优于 Eager』：该结论只在**物化作用域跨工作负载且容量充足**时成立。
- 不能证明存在语义特异机制：`k×s<c` 类边界、fan-out 复用、增量重建、缓存键粒度、认证成本，全部可在 relational / UDF / IVM / semantic-caching 框架内解释。
- 不能外推到真实生产负载：本语料的 payload 长度几乎均一（偏斜比 1.021），无法在本语料上检验『成本—长度耦合』的实际决策影响。
- 不能宣称任何与外部系统的比较（未运行 QuWARTS / ReDD / PLOP / LOTUS / Palimpzest / ThalamusDB 等）。
- 不能作为生产级可靠性承诺：capability 认证在 ε=2% 口径下未全部通过（见实验 3 与 `artifacts/certificates/`）。

---

## 3. Late-Persistent 相对 Late-Per-Query / Eager-Persistent 的真实边界

| 对比 | 结论 | 边界条件 |
|---|---|---|
| Late-Persistent vs Late-Per-Query | 严格更优（省去重复构建），但需付 validation 开销 | reuse ≥ 2；且 validation 开销 < 省下的构建成本（否则 B 更优，见 optimal_label_counts={'B': 336, 'C': 342, 'A': 162}） |
| Late-Persistent vs Eager-Persistent | **C/A 均值 = 0.6056（workload 作用域）**，即 Late-Persistent 恒不劣于 Eager | 物化作用域 = 工作负载且容量充足时，survivor 并集 ⊆ 全表 ⇒ 构建量 ≤ 全表 |
| 反例 | C/A 可达 11.98（cell 级作用域）甚至 11.96（容量 1%） | 持久化作用域被查询/cell 边界切断，或缓存容量受限 → 退化为经典缓存命中率问题 |

---

## 4. `k × s < c` 是否足够？

不够，但缺的都不是语义特异的项：

1. **必须加入物化作用域与容量**：本实验直接证明，作用域从 workload 缩到 cell 会让 C/A 从 0.6056 跳到 11.98。这是决定性的第一阶因素。
2. **必须加入 validation/certification 的固定开销**：reuse 很小时『完全不物化』才是最优（optimal_label_counts = {'B': 336, 'C': 342, 'A': 162}）。
3. **必须加入能力个数与 bundle 形状**：多能力下构建量分解为各能力并集之和（实验 1 的 oracle 已按能力可分解），且捆绑成本 sub-additive（实测比 0.2785）→ 应最大化捆绑。
4. **成本模型应条件化到过滤后总体**：真实探针测得成本与输入规模线性相关（0.6451 tokens/char，pearson 0.9533）。但**本语料 payload 长度过均一**，该修正的决策影响无法在本数据上验证（属未决项，对应 SIGMOD 2026 的语义查询基数估计方向）。
5. **必须加入 source drift**：drift 使『并集一次构建』不再成立，需增量维护（IVM）。

---

## 5. Adaptive 是否只是传统 CBO？

**是，而且在多数场景下是一个更差的 CBO。** 证据：
- Adaptive ≡ Simple CBO，在 609/840 个 cell 上成本完全相同。
- 其唯一增益来源是把 EAGER 纳入计划空间：72 个更优 cell 全部落在 s=75/100，即 oracle 也会选 EAGER 的区域——这正是 CBO 的『扩大计划空间』，不是新方法。
- 代价是覆盖度估计器误触发：159 个 cell 更差，平均贵 1.3961 倍，最差 regret 达 18.67（相对 oracle）。
- 给 Adaptive 额外注入真实视界 R（诊断组 D+）后 regret 由 0.8507 降到 0.7186——视界估计只解释其中一小部分，两者都仍远差于平凡策略 C（0.00137）。
- 其额外规划分支（覆盖度感知 EAGER）只是把 oracle 已含的 EAGER 计划纳入搜索空间，属 CBO 计划空间扩张，不构成新方法。

---

## 6. semantic capability 是否表现出 generic UDF 没有的性质？

| 候选性质 | 实测结果 | 是否构成独立机制 |
|---|---|---|
| 成本严格匹配下的调度收益 | delta_cost = 0 | ❌ 完全同构 |
| 能力捆绑 sub-additive（共享读数） | 成本比 0.2785，精度变化 0 | ❌ 无成本-精度张力 ⇒ 退化为『最大化捆绑』= generalized view |
| 成本 ∝ payload 规模 | slope 0.6451 tokens/char | ⚠️ 真实但非特异（data-dependent UDF cost / 语义查询基数估计已在处理） |
| 语义等价 ⇒ 答案不变但句法键失效 | 答案稳定率 1 vs 键稳定率 0 | ❌ semantic caching 已完整覆盖 |
| 需要统计认证（输出有误差） | 认证开销占 oracle 5.90% | ❌ ReDD/SCAPE 已覆盖；且这是**额外成本**而非节省 |
| 能力依赖（部分物化） | partial/full = 0.3733 | ❌ view dependency graph / IVM |
| 自适应调度机制本身 | D 相对 CBO 平均贵 40%，相对平凡策略 C 的 regret 高两个数量级 | ❌ 负结果：机制本身有害 |

**结论：没有任何一项通过『generic UDF 无法复现』的门槛；自适应机制甚至有害。**

---

## 7. 与 QuWARTS / ReDD / Sema / DASE / LOTUS / TADA / Palimpzest 等工作的真正边界

详见 `experiment3_external_baseline/literature_matrix.md`。核心边界：

1. **PLOP（arXiv 2604.09944）** 已做『语义算子的基于代价的位置选择』，并明确用 pull-up + 函数缓存解释收益（4.18–4.29× 成本下降）——**本研究的 build position 实验是它的一个受控实例**。
2. **QuWARTS（VLDB 2026）** 已提出用历史查询负载指导**离线**结构化抽取，显式权衡精度与延迟——**本研究所谓『workload-aware/Adaptive』是它的问题特例**。
3. **ReDD（VLDB 2026, SCAPE）** 提供统计校准的误差检测与覆盖保证——**本研究的 Capability Certificate 与其同构**。
4. **Semantic caching**（Redis / Azure / Upstash / GPTCache）已把『语义等价键 + 失效』产品化——覆盖本研究的 P3 发现。
5. **LOTUS / Palimpzest / Abacus / FlockMTL / ThalamusDB** 覆盖声明式语义算子、批处理、模型级联、代价化物理计划、AQP 精度-成本权衡。
6. 本研究**未能**运行上述系统（沙箱无可用实现），故不给出任何性能比较。

---

## 8. 最终是否存在独立研究贡献？

```
NO
```

（Tier 0：No Independent Contribution。若必须以工程视角评价，可给 Tier 1 —— 『Useful Semantic Systems Optimization』；但作为 RAG 基础原理，判定为 NO。）

逐条实验依据：
- 依据 1（F1/F2 触发）：Adaptive ≡ Simple CBO（609/840 相同，0 更优）。
- 依据 2（F3 触发）：全部结论可由 selectivity × reuse × 物化作用域 × 固定 validation 开销 解释。
- 依据 3（F4 触发）：oracle 与『总是 Late-Persistent』的差距 = 40.00% 的 cell 非零，但差距仅来自 validation 而非调度智能。
- 依据 4：generic UDF 对照 delta_cost = 0。
- 依据 5：捆绑无成本-精度张力（精度变化 0）。
- 依据 6：C/A>1 被证明是作用域/容量伪影（11.98 → 0.6056）。

---

## 9. 如果 NO：哪个最接近的已有技术已经解释了当前结果？

按解释力从高到低：

1. **PLOP（cost-based placement of semantic operators + pull-up + function caching）** —— 解释 build position、缓存复用、以及『把语义过滤推到关系算子之后/之前』的全部收益。
2. **QuWARTS（workload-aware offline relational table synthesis）** —— 解释『工作负载感知的物化抉择』与精度-延迟权衡。
3. **经典 CBO + 物化视图选择（含 generalized view / data cube）** —— 解释 Adaptive、generalized 捆绑与计划空间扩张；并解释『把 EAGER 加入计划空间』是其唯一增益来源。
4. **经典 IVM** —— 解释 source drift 下的增量重建优势。
5. **Semantic caching** —— 解释语义等价键与过度失效。
6. **ReDD/SCAPE、LOTUS 的统计精度保证** —— 解释能力认证与误差-成本权衡。

---

## 10. 如果 YES：属于哪一种新意？

不适用（判定为 NO）。

为保持可证伪性，以下列出**唯一未被完全排除、但仍不足以支撑 YES 的候选**，以及把它提升为 POTENTIAL 所需的实验：

| 候选 | 现状 | 提升为 POTENTIAL 所需的实验 |
|---|---|---|
| 成本与过滤谓词**统计相关**（survivor 总体系统性更贵） | 机制已验证（0.6451 tokens/char），但本语料长度均一，决策影响不可检验 | 构造 μ/σ 跨 5× 量级的 payload 长度分布，证明条件化成本模型相对朴素模型的 regret 差异 ≥ 10%（并能被 SIGMOD 2026 的语义基数估计反驳） |
| 语义等价性驱动的**零重建**失效 | 实测答案稳定率 1.0 / 键稳定率 0.0 | 证明可在**不引入新语义 oracle** 的前提下判定等价（否则是自举问题，非新机制） |

---

## 附：本研究真正剩余的、可交付的价值

1. **一个受控的负结果**：在单因子因果隔离下证明『Build Position 的独立贡献 = 0』，并给出旧结论 C/A>1 的伪影解释——这可以**阻止后续工作继续在该方向上投入**。
2. **一个可复用的评测夹具**：fixed-items hash、capability certificate（Clopper–Pearson 单侧上界）、payload hash 一致性、Replay equality、all-primary-model-only 断言。
3. **一条成本校准数据**：GLM-4.5-Air 下的真实 per-row 语义成本、捆绑 sub-additivity 曲线、输入长度-成本斜率（tokens/char），可用于后续任何语义执行引擎的代价模型标定。
