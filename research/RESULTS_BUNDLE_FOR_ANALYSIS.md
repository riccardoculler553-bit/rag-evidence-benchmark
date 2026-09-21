# Evidence-Native / Semantic Materialization 最终三实验 — 结果数据包

- 生成时间：2026-09-19 16:20:23（由 `research/make_analysis_bundle.py` 自动生成）
- 本文件**自包含**：所有数字均内联，无需访问仓库即可分析。机读版：`research/analysis_bundle.json`。
- 标注约定：**实验1/2(mock部分)/3 全部为 0-token 的 deterministic-mock 仿真**；
  **真实模型数据仅来自 2 次 GLM-4.5-Air 微探针（合计 108,361 tokens / ¥0.078）**；
  早期 v1.2 主实验与真实 GLM 精简矩阵标注为「事实基线」。

---

## 0. 结论（供对照，不要直接采信，请独立复核）

```text
FINAL: NO (Tier 0)
含义：Semantic Capability Materialization 不构成独立于
      Predicate/UDF Pushdown + Materialized View + Cache + CBO 的新 RAG 基础原理；
      工程价值成立（Tier 1），研究新颖性不成立。
```

- 平凡策略 C（总是 Late-Persistent）相对离线 clairvoyant oracle 的平均 regret = **0.00137**（0.14%）
- 自适应策略 D 的平均 regret = **0.8507**，Simple CBO = **0.2615**
- D vs CBO：相同 609 / 更优 72 / 更差 159 个 cell，成本比均值 1.3961

---

## 1. 实验设置与因果隔离（固定项）

| 固定项 | 值 |
|---|---|
| model_id / revision | deterministic-mock-semantic / mock-det-v1 |
| model_hash | e96217acdf756b13 |
| temperature / decoding | 0.0 / greedy |
| tokenizer | char4-bpe-proxy |
| batch_size（主实验强制） | 1 |
| capability_impl_revision | cap-impl-v1.2 |
| prompt_hash（3 个任务） | {"issue_classification": "d86497291a2ae783", "clause_classification": "2b5f4f299dac7217", "amount_extraction": "1d353b9345ea0e2e"} |
| schema_hash（3 个任务） | {"issue_classification": "bfc919f20f0101a4", "clause_classification": "bfc919f20f0101a4", "amount_extraction": "bcad0a9f16eed0ec"} |
| pricing_version | mock-2026.09 |
| pricing（元/1K tok 等） | {"pricing_version": "mock-2026.09", "input_per_1k": 0.002, "output_per_1k": 0.006, "per_call_overhead": 2e-05, "retrieval_per_row": 5e-07, "validation_per_row": 8e-07, "synthesis_input_per_1k": 0.002, "synthesis_output_per_1k": 0.006} |
| source snapshot | "7da34d5f450ee09f0f1cba46c5bd4661" |

**因果隔离纪律**：策略只改变「在什么位置、对哪些行、是否持久化地调用 CapabilityBuild」，
prompt / schema / parser / tokenizer / 价格 / 快照 / 模型 全部不变；同一 `(capability, row)` 的
单位成本在所有策略下完全相同（同一 unit 表）。

---

## 2. 实验 1：Adaptive Semantic Materialization（840 cells，0 token）

- 矩阵：domains=['ecom', 'finproc']，selectivity=[1, 5, 10, 25, 50, 75, 100]，reuse=[1, 10, 50, 100]，predicate patterns=['PRED_SHARED', 'PRED_DISTINCT', 'PRED_NESTED', 'PRED_OVERLAP', 'PRED_MUTEX']，capability breadth=[1, 2, 4]
- 策略：['A', 'B', 'C', 'CBO', 'D', 'O', 'D_plus']；运行时长 446.2 s

### 2.1 逐 cell 成本比（所有 840 个 cell 的分布）

| 指标 | mean | min | max |
|---|---|---|---|
| A Eager 的 regret | 9.038 | 0 | 120.8 |
| B Per-Query 的 regret | 17.26 | 0 | 98.59 |
| C Late-Persistent 的 regret | 0.00137 | 0 | 0.0042 |
| Simple CBO 的 regret | 0.2615 | 0 | 0.9968 |
| D Adaptive 的 regret | 0.8507 | 0 | 18.67 |
| D+ 诊断组（额外知道真实视界）的 regret | 0.7186 | 0 | 17.68 |
| C/A 成本比 | 0.6132 | 0.0082 | 1 |
| C/B 成本比 | 0.4902 | 0.01 | 1.004 |
| D/CBO 成本比 | 1.396 | 0.5008 | 9.984 |
| D/oracle 成本比 | 1.851 | 1 | 19.67 |
| A/oracle 成本比 | 10.04 | 1 | 121.8 |
| B/oracle 成本比 | 18.26 | 1 | 99.59 |

### 2.2 自适应机制的有效性判定（核心）

| 检验 | 结果 |
|---|---|
| D 与 CBO 成本完全相同的 cell | **609 / 840** |
| D 严格优于 CBO 的 cell | **72**（全部 s=75/100，即 oracle 也选 EAGER 的区域）|
| D 严格劣于 CBO 的 cell | **159** |
| D/CBO 成本比均值 | **1.3961** |
| D 的 EAGER / LATE_PERSIST / PER_QUERY 决策次数 | {"EAGER": 22, "LATE_PERSIST": 4973, "PER_QUERY": 1445} |
| D 与 D+ 的平均 regret 差 | 0.13204（视界估计只解释一小部分）|

### 2.3 最优计划与策略标签分布

- 最佳策略标签（含 oracle 作为下界）计数：{"B": 336, "C": 342, "A": 162}
- oracle 逐能力选择次数：{"PER_QUERY": 784, "CLAIRVOYANT_LATE": 798, "EAGER": 378}
  （逐能力可分解：能力之间无共享成本，故 oracle = 各能力 min 之和）

### 2.4 按维度的分解

**按选择性 s**

| s | C/A mean | A/oracle mean | D regret mean |
|---|---|---|---|
| 1% | 0.1765 | 48.95 | 0.1606 |
| 5% | 0.3706 | 10.04 | 2.795 |
| 10% | 0.47 | 5.286 | 1.463 |
| 25% | 0.6067 | 2.396 | 0.8414 |
| 50% | 0.7886 | 1.426 | 0.4512 |
| 75% | 0.8923 | 1.152 | 0.2304 |
| 100% | 0.9876 | 1.018 | 0.01313 |

**按谓词模式**

| pattern | C/A mean | D regret mean | CBO regret mean |
|---|---|---|---|
| PRED_SHARED | 0.3805 | 2.864 | 0.7336 |
| PRED_DISTINCT | 0.7384 | 0.1419 | 0.2883 |
| PRED_NESTED | 0.4971 | 1.083 | 0.04033 |
| PRED_OVERLAP | 0.6728 | 0.1651 | 0.2452 |
| PRED_MUTEX | 0.7772 | 0.00025 | 0 |

**按能力广度 c**

| c | D regret mean | D/oracle mean |
|---|---|---|
| 1 | 0.8399 | 1.84 |
| 2 | 0.8531 | 1.853 |
| 4 | 0.859 | 1.859 |

### 2.5 物化作用域 / 缓存容量消融（解释旧结论 C/A > 1）

| 作用域口径 | C/A mean | C/A min | C/A max |
|---|---|---|---|
| workload 级（跨查询无限持久） | 0.6056 | 0.0082 | 1 |
| cell 级（每 query 重置 = 旧实验口径） | 11.98 | 0.0082 | 99.84 |
| LRU 容量 10%（跨查询持久，容量受限） | 11.72 | 0.0082 | 99.84 |
| LRU 容量 1%（跨查询持久，强抖动） | 11.96 | 0.0082 | 99.84 |

共 160 个消融 cell（2 domains × 4 s × 4 reuse × 5 patterns × breadth=2）。
**结论：C/A > 1 只在物化作用域被切断或缓存容量受限时出现，是缓存命中率现象，不是语义性质。**

---

## 3. 实验 2：Semantic-Specificity Isolation（反证实验）

### 3.1 真实 GLM-4.5-Air 微探针（唯一消耗真实 token 的部分）

| 项 | 值 |
|---|---|
| 总 token | **108361**（计划上限 800,000；总配额 64,000,000） |
| 总费用 | **¥0.077576** |
| 全部来自主模型（无 fallback 混入） | **True** |
| 模型/参数 | glm-4.5-air, temperature=0, greedy, thinking=disabled, batch_size=1 |
| P1 成本-长度 pearson | 0.9533 |
| P1 label 准确率 | 1 |
| P2 4 字段捆绑 / 4 次单字段调用 成本比 | **0.4752** |
| P2 准确率明细 | {"V1_label": 1, "V2_label": 1, "V4_label": 1, "V2_amount": 1, "V4_amount": 1, "V4_parse_ok": 1} |
| P3 语义保持扰动：答案稳定率 / 句法 hash 稳定率 | **1 / 0** |
| P4 依赖上下文成本增量 | 27.83% |
| P2b 8 字段捆绑 prompt tokens / 8 次单字段 | {"V1": 103.83, "V2": 117.83, "V4": 157.82, "V8": 218.82, "SEP8": 785.6} |
| P2b 成本比（V8 vs 8 calls） | **0.2785** |
| P2b 广度 1→8 的字段准确率变化 | **0（0 = 无下降）** |
| P2b 各变体总体字段准确率 | {"V1": 1, "V2": 1, "V4": 1, "V8": 1, "SEP8": 0.8821} |
| 输入长度-成本斜率 | 0.6451 tokens/char （= +64.51 tokens / 100 chars）|
| 长度阶梯实测 | {"1": {"n": 16, "mean_len": 69.8, "mean_pt": 98, "mean_ct": 12}, "4": {"n": 16, "mean_len": 162.8, "mean_pt": 158, "mean_ct": 12.75}, "16": {"n": 16, "mean_len": 534.8, "mean_pt": 398, "mean_ct": 13}} |

### 3.2 2A：成本严格匹配的 generic expensive UDF 对照

- 对照 cell 数：**80**；`total_cost` 最大绝对差：**0**
- semantic capability 实测质量（mock）：{"issue_classification": 0.97, "amount_extraction_ecom": 0.9857}
- UDF 质量 = 1.0；认证成本 / oracle 成本 = **5.90%**（149 行 × 2 能力）
- 长度偏斜工作负载实测长度比：**1.021**（本语料 payload 长度过于均一 → 该机制在本语料上不可检验）
- 长度偏斜下的 regret（条件化 vs 全局均值成本模型）：2.675 vs 2.675

### 3.3 2B：跨算子复用（fan-out）

- 共享工件 / 独立调用 成本比：**0.3334**（cells=12）
- generic UDF 结构匹配对照是否完全相同：**True**
- 需求异质性 → 泛化物化因子（实测 V4/V1 prompt tokens）：1.52

### 3.4 2C：能力依赖 / 部分物化

- 依赖上下文成本增量（实测）：27.83%
- 最优策略分布：{"FULL": 3, "PARTIAL": 9}
- partial/full 均值：**0.3733**

---

## 4. 实验 3：External Baseline + Source Drift + Prior-Art 边界

### 4.1 Baseline-0..4 在实验 1 全矩阵（840 cell）上的表现

| Baseline | 策略 | 成为最优（含 oracle）的 cell 占比 | 成本 mean | regret mean |
|---|---|---|---|---|
| B0_naive_per_query | B | **0.4** | 63.86 | 17.26 |
| B1_eager_persistent | A | **0.1929** | 5.581 | 9.038 |
| B2_late_persistent | C | **0.4071** | 3.422 | 0.00137 |
| B3_simple_cbo | CBO | **0** | 4.333 | 0.2615 |
| B4_adaptive | D | **0** | 4.417 | 0.8507 |
| O_oracle | O | **0** | - | 0 |

- **C（Late-Persistent）与 oracle 完全相等的 cell 占比：0.6**
- 矩阵 cell 总数：840

### 4.2 三种匹配工作负载

| workload | baseline | 成本 | regret | 物化覆盖率 | P95(ms) | 语义行数 |
|---|---|---|---|---|---|---|
| A_query_driven | B0_naive_per_query | 8.097 | 37.68 | 0 | 9043 | 33440 |
| A_query_driven | B1_eager_persistent | 19.278 | 91.09 | 1 | 21.4 | 80000 |
| A_query_driven | B2_late_persistent | 0.20933 | 0 | 0.01045 | 21.4 | 836 |
| A_query_driven | B3_simple_cbo | 0.4116 | 0.9662 | 0.01045 | 21.4 | 1672 |
| A_query_driven | B4_adaptive | 0.4116 | 0.9662 | 0.01045 | 21.4 | 1672 |
| B_batch_analytics | B0_naive_per_query | 385.69 | 49.34 | 0 | 3.027e+05 | 1597954 |
| B_batch_analytics | B1_eager_persistent | 19.288 | 1.518 | 1 | 21.4 | 80000 |
| B_batch_analytics | B2_late_persistent | 7.6613 | 0 | 0.3948 | 3875 | 31582 |
| B_batch_analytics | B3_simple_cbo | 7.7346 | 0.00956 | 0.3948 | 3946 | 31886 |
| B_batch_analytics | B4_adaptive | 13.895 | 0.8136 | 0.6982 | 3736 | 56160 |
| C_mixed | B0_naive_per_query | 18.517 | 4.776 | 0 | 3.449e+04 | 75416 |
| C_mixed | B1_eager_persistent | 19.279 | 5.014 | 1 | 21.4 | 80000 |
| C_mixed | B2_late_persistent | 3.2059 | 0 | 0.1595 | 1.355e+04 | 12764 |
| C_mixed | B3_simple_cbo | 3.5273 | 0.1003 | 0.1595 | 1.38e+04 | 14149 |
| C_mixed | B4_adaptive | 11.808 | 2.683 | 0.618 | 1.453e+04 | 50827 |

### 4.3 Source Drift

| drift | policy | rebuild 成本 | phase1 成本 | total 成本 | rebuild/full |
|---|---|---|---|---|---|
| 0% | Eager_full_rebuild | 5.1682 | 0.27839 | 5.4466 | 1 |
| 0% | Late_affected_rows_rebuild | 0 | 0.27839 | 0.27839 | 0 |
| 0% | Adaptive_pick_min | 0 | 0.27839 | 0.27839 | 0 |
| 1% | Eager_full_rebuild | 5.1682 | 0.27839 | 5.4466 | 1 |
| 1% | Late_affected_rows_rebuild | 0.002116 | 0.27839 | 0.2805 | 0.00041 |
| 1% | Adaptive_pick_min | 0.002116 | 0.27839 | 0.2805 | 0.00041 |
| 5% | Eager_full_rebuild | 5.1682 | 0.27839 | 5.4466 | 1 |
| 5% | Late_affected_rows_rebuild | 0.016198 | 0.27839 | 0.29458 | 0.00313 |
| 5% | Adaptive_pick_min | 0.016198 | 0.27839 | 0.29458 | 0.00313 |
| 10% | Eager_full_rebuild | 5.1682 | 0.27839 | 5.4466 | 1 |
| 10% | Late_affected_rows_rebuild | 0.027598 | 0.27839 | 0.30599 | 0.00534 |
| 10% | Adaptive_pick_min | 0.027598 | 0.27839 | 0.30599 | 0.00534 |
| 25% | Eager_full_rebuild | 5.1682 | 0.27839 | 5.4466 | 1 |
| 25% | Late_affected_rows_rebuild | 0.064918 | 0.27839 | 0.34331 | 0.01256 |
| 25% | Adaptive_pick_min | 0.064918 | 0.27839 | 0.34331 | 0.01256 |

_在无限存储下，受影响行重建（IVM 式增量）恒 ≤ 全量重建；Adaptive 的『选择』退化为 min(full, incremental)=incremental，即经典 incremental view maintenance，无需任何 workload-aware 决策。_

**句法缓存键的过度失效（语义等价改写）**

- 探针实测答案稳定率：None
- 首行：句法键失效 = 全量 union 重建；语义等价改写下的真实需要 = 0.000000（探针测得答案不变率 1）；过度失效倍数 = 274606000000.0x

---

## 5. 早期事实基线（v1.2 主实验 + 真实 GLM 精简矩阵，作为参照）

| 指标 | A Eager | B Late-Per-Query | Δ/比值 |
|---|---|---|---|
| quality_score | 0.9529 | 0.9529 | Δ=0 |
| answer_correct | 0.4 | 0.4 | - |
| 语义工作量下降 | - | - | 63.22% |
| 总成本下降 | - | - | 63.18% |
| Cost/CorrectQuery 下降 | - | - | 63.16% |
| EXPERIMENT_INVALID 数 | - | - | 0 |
| Replay equality | - | - | True |

- 真实 GLM 精简矩阵统一口径总成本：A=¥0.221048，B=¥3.29075，C=¥1.04588；C/B=0.3178，C/A=4.731
- query 总数：312；对应 tokens：A=137165，B=2.04643e+06，C=651091
- 口径说明：统一口径：执行整个矩阵（24 cells / 全部 query）时的总成本。A=每域一次性 eager 构建 + 全量复用；B=逐 query 重建；C=每 cell 首次构建+增量复用。

- Capability Certificate（PASS = Clopper–Pearson 单侧上界 ≤ ε=2%，δ=5%）：**legacy 校准集 0/4 PASS（旧判据 Wilson≤20% 下 4/4 PASS）**；group-stratified 集 1/4 PASS；0 失败所需 n ≥ 149

| capability | legacy err | legacy CP_upper95 | legacy Wilson(旧) | 新判定 | group err | 独立 source group 数 |
|---|---|---|---|---|---|---|
| issue_classification | 0.0267 | 0.0476 | 0.0517 | FAIL | 0 | 153 |
| amount_extraction_ecom | 0.0333 | 0.0559 | 0.0603 | FAIL | 0.09 | 153 |
| clause_classification | 0.06 | 0.0877 | 0.0928 | FAIL | 0.025 | 12 |
| amount_extraction_fin | 0.0233 | 0.0434 | 0.0474 | FAIL | 0.0167 | 12 |

- 判据说明：① 判据修复：PASS 现在唯一定义为 Clopper–Pearson 单侧上界 ≤ ε(=2%)（δ=5%），取代旧的 Wilson 上界 ≤ 20%。② 旧判据过宽（等价于容忍 20% 错误率），不能作为生产门禁；新判据下 mock capability 全部 FAIL —— 这是正确结论：在 n=300 下若要断言总体误差 ≤2%，最多只允许 1 次错误（见 max_errors_allowed_for_pass）。③ 因此 mock 能力只能用于因果实验（同源误差对 A/B 无偏），不可用于生产部署；生产部署需要更高精度 capability 或更大 n。

**旁路实验（早期）**

- S1_multi_use: {"ecom_reuse10": {"domain": "ecom", "reuse": 10, "survivors": 531, "build_once_cost": 0.137234, "amortized_cost_once_reuse": 0.0151513, "amortized_cost_repeated_operator": 0.1386088, "amortized_reduction": 0.89069, "amortized_cost_once_reuse_cacheOFF": 0.1509574, "amortized_reduction_cacheOFF": -0.08909}, "ecom_reuse50": {"domain": "ecom", "reuse": 50, "survivors": 531, "build_once_cost": 0.137234, "amortized_cost_once_reuse": 0.00417258, "amortized_cost_repeated_operator": 0.1386088, "amortized_reduction": 0.9699, "amortized_cost_once_reuse_cacheOFF": 0.13997868, "amortized_reduction_cacheOFF
- S2_tada_matched: {"T1_native_tada_tagging_only": {"n": 300, "cost_A": 2.25923869, "cost_B": 0.8334277, "cost_reduction": 0.63159, "work_reduction": 0.63216, "quality_delta": 0.0}, "T2_matched_representation_all": {"n": 600, "cost_A": 2.42334967, "cost_B": 0.89277046, "cost_reduction": 0.63181, "work_reduction": 0.63216, "quality_delta": 0.0}, "note": "T2 使用与 T1 完全相同的 model/prompt/schema/row payload，仅改 Build Position；若 T2 仍显示收益，则收益来自 Build Position 而非 representation design。"}

---

## 6. 统一指标口径（本次三实验使用的全部字段）

**Cost**：`total_cost`、`cost_per_query`，分解为 `build_cost` / `retrieval_cost` /
`validation_cost` / `synthesis_cost`。
**Semantic Work**：`semantic_tokens`（= build tokens in+out）、`semantic_calls`、
`semantic_rows_built`、`unique_rows_built`。
**Materialization**：`materialized_rows`、`materialization_coverage`、`cache_hit_rate`、
`rebuild_rate`、`evictions`。
**Latency**：模拟 service time（tokens × ms/token）+ 实测 harness 开销 → `p50_ms`/`p95_ms`/`p99_ms`
（**绝对值不具外部可比性**，只有比值有意义）。
**Quality**：策略间恒定（同一 survivor → 同一 artifact → 同一答案），mock 下实测
macro-F1 / field-F1；真实模型下未做 quality 对照（探针只测准确率与成本）。
**Regret**：`(C_strategy - C_oracle) / C_oracle`，oracle = 离线 clairvoyant、逐能力可取
{EAGER 全表, survivor 并集一次, 每查询重建} 的最小值。

---

## 7. Prior-Art 边界矩阵（用于 novelty 判定）

| System | Eager | Late | Persistent | Incremental | Cost-based | Workload-aware | Semantic-specific |
|---|---|---|---|---|---|---|---|
| QuWARTS (VLDB 2026) | Y(offline) | N | Y | N | N(accuracy-latency trade-off) | Y(historical workload) | N |
| ReDD (VLDB 2026) | N | Y(query-specific schema) | Y | N | N | Y(per-query schema) | Y(error-aware) |
| PLOP (arXiv 2604.09944) | Y | Y | Y(function cache) | N | Y(PLOP-Cost) | Y(plan-level) | N |
| Palimpzest (arXiv 2405.14696) | Y | Y | N | N | Y | N | N |
| Abacus (v1.4.0) | Y | Y | N | N | Y(physical plan) | N | N |
| LOTUS (arXiv 2407.11418) | Y | Y | Y(cache/index) | N | Y | N | Y(accuracy guarantees) |
| ThalamusDB | N | Y | N | N | Y(AQP) | N | Y(multimodal) |
| FlockMTL (v0.7.0) | Y | Y | N | N | N | N | N |
| Semantic Caching（Redis / Azure Cosmos DB / Upstash / GPTCache） | N | Y(hit path) | Y | Y(TTL/invalidate) | N | N | Y(content-equivalence key) |
| Cardinality Estimation for Semantic Queries (SIGMOD 2026) | N | N | N | N | Y | N | Y(estimation) |
| IVM（incremental view maintenance，经典） | Y | N | Y | Y | Y | N | N |
| 本研究（Ours） | Y | Y | Y | Y | Y | Y(online estimates) | N |

关键结论（**未运行任何外部系统，故不做任何性能比较**）：

1. **PLOP**（cost-based placement of semantic operators in hybrid query plans）已做语义算子的
   代价模型 + 位置选择，并用 pull-up + 函数缓存解释收益 → 覆盖本研究 build position 实验。
2. **QuWARTS**（VLDB 2026）已用历史查询负载指导离线结构化抽取，显式权衡精度/延迟 → 覆盖「Adaptive」。
3. **ReDD / SCAPE**（VLDB 2026）提供统计校准的误差检测与覆盖保证 → 覆盖 Capability Certificate。
4. **Semantic caching**（Redis / Azure Cosmos DB / Upstash / GPTCache）→ 覆盖语义等价键与失效。
5. **经典 IVM** → 覆盖 source drift 增量重建。
6. **LOTUS / Palimpzest / Abacus / FlockMTL / ThalamusDB** → 覆盖声明式语义算子、批处理、
   模型级联、代价化物理计划、AQP 精度-成本权衡。

详细说明与来源链接见 `research/experiment3_external_baseline/literature_matrix.md`。

---

## 8. 已排除的替代解释 与 不可外推项

**已排除（附隔离证据）**

| 替代解释 | 排除方式 | 证据 |
|---|---|---|
| 收益来自 representation/批处理 | matched UDF 对照（同成本结构） | delta_cost = 0（80 cell）|
| 收益来自输入更干净（survivor 更短） | 同一 unit 表，成本按行实际 payload 计 | 策略间对同一行的单位成本相同 |
| D 的差异来自视界估计误差 | 诊断组 D+ 注入真实 R | regret 仅从 0.8507 降到 0.7186 |
| C/A>1 是语义性质 | 物化作用域/容量消融 | 0.6056（无限）vs 11.98（cell 级）vs 11.96（1% LRU）|
| 语义等价需要新的缓存理论 | 真实探针 P3 | 答案稳定率 1.0 但句法键稳定率 0.0 → semantic caching 已覆盖 |
| 认证成本会吞掉收益 | 认证开销 / oracle 占比 | 5.90% |

**不可外推 / 未决**

1. 实验1/3 的语义执行是 **deterministic-mock**（脚本化词表+规则），其「语义能力」不含真实 LLM 的
   不确定性；质量非劣是构造性成立。
2. Latency 为**模拟 service time**，绝对数值不可与任何真实系统比较。
3. `PRED_*` 谓词族为实验控制手段（确定性 hash 桶 + 长度谓词），非生产日志分布。
4. 本语料 payload 长度几乎均一（偏斜比 1.021），因此「成本—长度耦合」的**决策影响**
   在本数据上不可检验（机制本身已由真实探针验证：0.6451 tokens/char）。
5. 真实模型只在 ecom 域的 40 行/24 行样本上做了 4 类探针，**未做真实模型下的策略对照**。
6. 未运行任何外部系统（QuWARTS / ReDD / PLOP / LOTUS / Palimpzest / ThalamusDB 等）。
7. capability 认证在 ε=2% 口径下未全部通过（见 §5），不得宣称生产级可靠性。

---

## 9. 原始文件索引（含 sha256 前 16 位）

| 文件 | 字节 | sha256_16 |
|---|---:|---|
| `research/common.py` | 31,003 | d8f02ca4706b8ac8 |
| `research/exp1_adaptive.py` | 16,973 | f499a56b32b9d7ee |
| `research/exp2_bundle_scaling.py` | 14,363 | 6351ad53c4fa054d |
| `research/exp2_real_probe.py` | 18,003 | aedf9803e4044ab1 |
| `research/exp2_specificity.py` | 20,123 | 9000933de75970f1 |
| `research/exp3_external.py` | 13,960 | b75b224f8966a784 |
| `research/make_analysis_bundle.py` | 31,058 | b9986c75c8e5cdf8 |
| `research/make_final.py` | 46,114 | d811192a8623f62d |
| `research/FINAL_VERDICT.md` | 12,361 | 4a8c67c6e7ab95d5 |
| `research/README.md` | 2,860 | fdd566a5bf295b31 |
| `research/RESULTS_BUNDLE_FOR_ANALYSIS.md` | 25,664 | 6e9527026924af92 |
| `research/experiment1_adaptive/analysis.md` | 2,233 | 766f920c845dc01c |
| `research/experiment1_adaptive/config.json` | 2,190 | f34d39e0fbec43a7 |
| `research/experiment1_adaptive/cost_curve.csv` | 2,812 | ef9588e418ccce07 |
| `research/experiment1_adaptive/results.json` | 4,850,445 | 7c9ee4d13810cbf0 |
| `research/experiment1_adaptive/scope_ablation.csv` | 18,673 | e73952cc6972270a |
| `research/experiment1_adaptive/traces.jsonl` | 7,030,839 | f99dc633c2cd68f6 |
| `research/experiment1_adaptive/workload.csv` | 272,341 | 117fe02ed16c0d9c |
| `research/experiment2_semantic_specificity/analysis.md` | 2,281 | 18a03693bc5f344d |
| `research/experiment2_semantic_specificity/bundle_scaling.json` | 63,027 | 499b292efdf03159 |
| `research/experiment2_semantic_specificity/capability_dependency.csv` | 1,021 | bee297cf3dc1909e |
| `research/experiment2_semantic_specificity/config.json` | 1,290 | ec85af47b9f0071a |
| `research/experiment2_semantic_specificity/cross_operator_reuse.csv` | 1,044 | 34fe870a458a9fa7 |
| `research/experiment2_semantic_specificity/key_usage_probe.json` | 1,333 | 66440cbcec3576ce |
| `research/experiment2_semantic_specificity/key_usage_probe2.json` | 1,333 | 2f674d32265f9b73 |
| `research/experiment2_semantic_specificity/length_skew_cost_model.csv` | 632 | 9985d0944f72f6e7 |
| `research/experiment2_semantic_specificity/real_probe.json` | 41,338 | 4a3b34b7debd2272 |
| `research/experiment2_semantic_specificity/real_probe_trace.csv` | 2,210 | 269b4ac040ae6c33 |
| `research/experiment2_semantic_specificity/results.json` | 14,635 | 9831f56a04f6e151 |
| `research/experiment2_semantic_specificity/semantic_vs_udf.csv` | 8,846 | 4d0d6c208bc235f7 |
| `research/experiment3_external_baseline/analysis.md` | 3,487 | 943664c79775c181 |
| `research/experiment3_external_baseline/baseline_results.json` | 1,494 | 6b765dc54fbcb70a |
| `research/experiment3_external_baseline/config.json` | 1,243 | 6ce58fbcbc07caef |
| `research/experiment3_external_baseline/literature_matrix.md` | 5,607 | 3289c32dac445623 |
| `research/experiment3_external_baseline/results.json` | 20,963 | a7365f0e9267d16a |
| `research/experiment3_external_baseline/source_drift.csv` | 1,909 | a1f359ef50ad6c9c |
| `research/experiment3_external_baseline/workload_results.csv` | 3,566 | 724026d6fc21a235 |
| `research/artifacts/certificates/capability_certificates.json` | 7,476 | 0e1194c1ee0c7b14 |
| `research/artifacts/certificates/certificate_verdict.json` | 1,061 | 830d29431455ed51 |
| `research/artifacts/hashes/code_and_fixed_items_hashes.json` | 1,195 | 04bd0ca4b6c96bbc |
| `research/artifacts/model_calls/glm_calls_probe.jsonl` | 117,305 | 6b74a14b3afc9e0e |
| `research/artifacts/model_calls/glm_calls_probe2.jsonl` | 202,284 | 02d240122f9761b0 |
| `research/artifacts/model_calls/key_switch_log_probe.jsonl` | 872 | 64ef59be066f128a |
| `research/artifacts/model_calls/key_switch_log_probe2.jsonl` | 2,180 | c2923921ac9ea304 |
| `research/artifacts/raw_traces/exp1_traces.jsonl` | 7,030,839 | f99dc633c2cd68f6 |
| `research/artifacts/raw_traces/exp2_real_probe_trace.csv` | 2,210 | 269b4ac040ae6c33 |
| `research/artifacts/raw_traces/exp3_workload_results.csv` | 3,566 | 724026d6fc21a235 |
| `research/reproducibility/dataset_hash.txt` | 36 | 5e75c57098864438 |
| `research/reproducibility/environment.json` | 377 | f44d58705ac618dd |
| `research/reproducibility/git_commit.txt` | 13 | 27d3c8bc266308d6 |
| `research/reproducibility/run_command.txt` | 461 | b1eb79df1a81fddb |

---

## 10. 给下游分析方的建议问题（可直接动手复核）

1. **D 与 CBO 在 231/840 个 cell 上分歧**（更优 72 / 更差 159）：请独立判断
   「把 EAGER 纳入计划空间」是否构成方法学贡献，还是纯 CBO 计划空间扩张。
2. **在无限物化作用域下，最优计划是否存在任何在线决策空间？**
   C 的 regret = 0.0014，且 60% 的 cell 与 oracle 逐值相等——请检验是否存在
   本实验未覆盖的 workload 形状使 C 显著次优（例如能力间共享成本、非可分解成本）。
3. **D+ 只把 regret 从 0.851 降到 0.719**：请判断这是否意味着『未知视界』不是主要误差源，
   并指出还有什么会造成该残余。
4. **捆绑成本比 0.2785 且精度变化为 0**：请判断「最大化捆绑」是否真的无副作用，
   若要构造成本-精度张力需要什么样的字段组合（本实验的 8 字段均为短抽取任务）。
5. **作用域消融（0.606 vs 11.98）**：请评估这是否足以推翻任何形式的「Late 优于 Eager」主张，
   以及在生产系统中「物化作用域」通常落在哪个区间。
6. **真实探针只有 108k tokens**：请指出在小样本下最可能被推翻的三个数字，并给出最小复核实验设计。

---

_本文件由 `research/make_analysis_bundle.py` 于 2026-09-19 16:20:23 生成；共 427 行。修改任何原始 JSON 后重跑该脚本即可保持同步。_
