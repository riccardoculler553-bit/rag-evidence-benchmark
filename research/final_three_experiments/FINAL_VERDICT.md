# FINAL VERDICT — v1.3

- 档位：**Engineering-only**
- 依据：Tier 0 真实 GLM（237,580 tokens / ¥0.106683）+ Tier 1 mock 机制（1,512 boundary cells）+ Tier 2 prior-art proxy（4 workloads）

---

## Q1. What exactly, if anything, is new beyond pushdown, caching, materialization and CBO？

**答案：在本轮证据中，没有。**

1. 收益机制与 generic expensive UDF **完全同构**：matched control 下 total_cost 最大绝对差 = **0**（Tier 1，80 cells）。
2. PLOP-like 代价规划器（{Eager, Late, PerQuery} 中 argmin）在全部工作负载上与 Late-Persistent 同解 （Table C）→ 「自适应」= 普通 CBO。
3. QuWARTS-like（历史 workload → 离线物化）在 warm/high-reuse 下与 Late-Persistent 同量级；DASE-like 的优势来自上游 deterministic prefilter（成本归因到 pruning）。
4. Source drift 的增量重建恒 ≤ 全量重建且近似线性于 drift 率（Table D）→ 等价于 IVM。
5. 缓存摊销收益在 cache OFF 时归零 → 来源是 artifact reuse，而非 Late Materialization 算法本身。

---

## Q2. Under what workload conditions does CapabilityBuild as a physical state actually create measurable value？

**已量化的成立条件（Tier 1/2）：**

1. 必须有 **跨查询持久化作用域**：WORKLOAD scope 下 C/A ≤ 1 恒成立；CELL scope 下 C/A 可达 **[13.76259, 0.00795, 99.91665]**。
2. 必须有 **reuse ≥ 2**：reuse=1 时 C 相对 B 的收益被 validation 抵消。
3. 收益随 selectivity 上升而衰减：C/A 从 s=1% 到 s=100% 单调趋近 1（Figure 1）。
4. 语义侧的可测价值只剩**捆绑结构**：V8/SEP8 成本比 0.3722（ecom）/ 0.3601（finproc），且准确率不低于分次调用（Tier 0）。

---

## Q3. Fail Rules 汇总

```text
F1_C_vs_B_no_cost_benefit: not triggered
F2_quality_non_inferior: not triggered
F3_late_only_helps_at_low_selectivity: not triggered
F4_TADA_matched_removes_benefit: not triggered
F5_prior_art_explains_all: TRIGGERED
F6_validation_eats_benefit: not triggered
```

---

## Q4. 逐条 Claim 判定

| Claim | 判定 | 绑定证据 |
|---|---|---|
| Capability Persistence 有独立成本价值 | **Supported** | 实验 1，C/B ratio，WORKLOAD scope，CI 见 FINAL_REPORT §2.1 |
| Late-Persistent 普遍优于 Eager | **Unsupported** | 实验 1，C/A 在 CAP_10PCT / CELL scope > 1 |
| Late-Persistent 在作用域充足时优于 Eager | **Supported** | 实验 1，C/A ≤ 1（756 cells） |
| 语义能力存在 generic UDF 无法复现的机制 | **Unsupported** | 实验 2，Tier 1 matched UDF delta=0 |
| 捆绑降低成本且不损质量 | **Supported（含保留）** | 实验 2 Tier 0；逐字段有退化，见 Table B |
| 收益超出 Prior Art | **Unsupported** | 实验 3 Tier 2 proxy，Table C |
| 增量维护优势 | **Supported 但非新机制** | 实验 3 Table D = IVM |
| TADA-matched 后收益是否消失 | **Not Tested** | 本轮未重复该实验（不引用旧数字） |

---

## Q5. 后续建议（不得扩架构）

1. 若继续，只允许做**一件事**：在 `mu/sigma 跨 5× 量级` 的 payload 长度分布上，验证
   「成本需条件化到过滤后总体」是否带来 ≥10% 的 regret 改善（这是唯一未被排除的候选，
   且须先排除 SIGMOD 2026 语义基数估计方向的反驳）。
2. 不得以增加模块（Graph / Memory / Agent / Reranker / 多模型）解释任何负结果。
3. 若主张工程价值，应写作「语义算子的可持久化物化 + 代价化位置选择」的系统集成工作，
   并在 Related Work 中显式承认 PLOP / QuWARTS / ReDD / semantic caching / IVM 的优先权。
