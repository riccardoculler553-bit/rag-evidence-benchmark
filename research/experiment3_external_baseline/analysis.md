# 实验 3 分析：External Baseline + Prior-Art Boundary

## 1. Baseline-0..4 在实验 1 全矩阵上的表现

| Baseline | 策略 | 成为最优（含 oracle）的 cell 占比 | 成本 mean | regret mean |
|---|---|---|---|---|
| B0_naive_per_query | B | **0.4** | 63.862 | 17.262 |
| B1_eager_persistent | A | **0.1929** | 5.5811 | 9.0377 |
| B2_late_persistent | C | **0.4071** | 3.4223 | 0.00137 |
| B3_simple_cbo | CBO | **0** | 4.3333 | 0.26148 |
| B4_adaptive | D | **0** | 4.4173 | 0.85068 |
| O_oracle | O | **0** | - | 0 |

- **C（Late-Persistent）与 oracle 完全相等的 cell 占比：0.6**
  → 在无限存储 + 无 source drift 下，『总是 Late-Persistent』即已达 oracle 下界，
  **在线决策问题几乎不存在**（残余差异仅来自 validation 开销）。

## 2. 三种工作负载

| workload | baseline | 成本 | regret | 覆盖率 | P95(ms) |
|---|---|---|---|---|---|
| A_query_driven | B0_naive_per_query | 8.097 | 37.68 | 0 | 9043 |
| A_query_driven | B1_eager_persistent | 19.278 | 91.09 | 1 | 21.4 |
| A_query_driven | B2_late_persistent | 0.20933 | 0 | 0.01045 | 21.4 |
| A_query_driven | B3_simple_cbo | 0.4116 | 0.9662 | 0.01045 | 21.4 |
| A_query_driven | B4_adaptive | 0.4116 | 0.9662 | 0.01045 | 21.4 |
| B_batch_analytics | B0_naive_per_query | 385.69 | 49.34 | 0 | 3.027e+05 |
| B_batch_analytics | B1_eager_persistent | 19.288 | 1.518 | 1 | 21.4 |
| B_batch_analytics | B2_late_persistent | 7.6613 | 0 | 0.3948 | 3875 |
| B_batch_analytics | B3_simple_cbo | 7.7346 | 0.00956 | 0.3948 | 3946 |
| B_batch_analytics | B4_adaptive | 13.895 | 0.8136 | 0.6982 | 3736 |
| C_mixed | B0_naive_per_query | 18.517 | 4.776 | 0 | 3.449e+04 |
| C_mixed | B1_eager_persistent | 19.279 | 5.014 | 1 | 21.4 |
| C_mixed | B2_late_persistent | 3.2059 | 0 | 0.1595 | 1.355e+04 |
| C_mixed | B3_simple_cbo | 3.5273 | 0.1003 | 0.1595 | 1.38e+04 |
| C_mixed | B4_adaptive | 11.808 | 2.683 | 0.618 | 1.453e+04 |

## 3. Source Drift

| drift | policy | rebuild 成本 | total 成本 | rebuild/full |
|---|---|---|---|---|
| 0% | Eager_full_rebuild | 5.1682 | 5.4466 | 1 |
| 0% | Late_affected_rows_rebuild | 0 | 0.27839 | 0 |
| 0% | Adaptive_pick_min | 0 | 0.27839 | 0 |
| 1% | Eager_full_rebuild | 5.1682 | 5.4466 | 1 |
| 1% | Late_affected_rows_rebuild | 0.002116 | 0.2805 | 0.00041 |
| 1% | Adaptive_pick_min | 0.002116 | 0.2805 | 0.00041 |
| 5% | Eager_full_rebuild | 5.1682 | 5.4466 | 1 |
| 5% | Late_affected_rows_rebuild | 0.016198 | 0.29458 | 0.00313 |
| 5% | Adaptive_pick_min | 0.016198 | 0.29458 | 0.00313 |
| 10% | Eager_full_rebuild | 5.1682 | 5.4466 | 1 |
| 10% | Late_affected_rows_rebuild | 0.027598 | 0.30599 | 0.00534 |
| 10% | Adaptive_pick_min | 0.027598 | 0.30599 | 0.00534 |
| 25% | Eager_full_rebuild | 5.1682 | 5.4466 | 1 |
| 25% | Late_affected_rows_rebuild | 0.064918 | 0.34331 | 0.01256 |
| 25% | Adaptive_pick_min | 0.064918 | 0.34331 | 0.01256 |

_在无限存储下，受影响行重建（IVM 式增量）恒 ≤ 全量重建；Adaptive 的『选择』退化为 min(full, incremental)=incremental，即经典 incremental view maintenance，无需任何 workload-aware 决策。_


### 句法缓存键的过度失效（语义等价改写）

- 探针实测答案稳定率：None
- 首行 note：句法键失效 = 全量 union 重建；语义等价改写下的真实需要 = 0.000000（探针测得答案不变率 1）；过度失效倍数 = 274606000000.0x
