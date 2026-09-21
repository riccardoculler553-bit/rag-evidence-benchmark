# FINAL REPORT — v1.3 最终三实验

- experiment_version: `v1.3-final-three-experiments`
- 生成时间：2026-09-19 17:34:28
- 最终判定档位：**Engineering-only**

## 0. 三层证据分离（§34）

| Tier | 内容 | 本轮规模 | 说明 |
|---|---|---|---|
| Tier 0 | 真实 GLM-4.5-Air confirmatory | **237,580 tokens / ¥0.106683** | 捆绑规模 2 域 × 64 行 × 13 变体 + 长度分位 6×12×2 |
| Tier 1 | deterministic mock 机制实验 | 1,512 boundary cells（0 token）| 实验 1 全矩阵 + 实验 2 matched UDF |
| Tier 2 | 结构性 prior-art proxy | 4 workloads（0 token）| QuWARTS/ReDD/PLOP/DASE-like，**未运行原系统** |

> 三层证据不得混为同一种证据；下文每张表均标注 tier。

---

## 1. 实验设置与因果隔离

| 固定项 | 值 |
|---|---|
| source snapshot | `"7da34d5f450ee09f0f1cba46c5bd4661"` |
| prompt_hash | `{"issue_classification": "d86497291a2ae783", "clause_classification": "2b5f4f299dac7217", "amount_extraction": "1d353b9345ea0e2e"}` |
| schema_hash | `{"issue_classification": "bfc919f20f0101a4", "clause_classification": "bfc919f20f0101a4", "amount_extraction": "bcad0a9f16eed0ec"}` |
| model / revision | glm-4.5-air（Tier 0）/ deterministic-mock-semantic（Tier 1） / glm-4.5-air@2026 + mock-det-v1 |
| temperature / decoding / batch_size | 0.0 / greedy / 1 |
| tokenizer | char4-bpe-proxy |
| random_seed | 20260919 |
| pricing_version | mock-2026.09 |
| key budget | {"total": 64000000, "internal": 60000000, "reserve": 4000000} |
| key0 / key1 tokens | 119,782 / 117,798 |
| fallback enabled / used | True / False |
| all_primary_model_only | **True** |

**唯一变化量 = strategy**。同一 `(capability, row)` 在所有策略下单位成本相同（共用同一 unit 表）；
Tier 0 逐请求记录 payload_hash / prompt_hash / key_id / retry / cost。

---

## 2. Table A：Materialization Boundary（Tier 1）

| Strategy | Cost (mean) | Tokens (mean) | Build Rows (mean) | Amortized Cost/query | Quality | Regret vs Oracle |
|---|---:|---:|---:|---:|---:|---:|
| A Eager | 5.5811 | 2.15092e+06 | 23333.3 | 1.57583 | 策略间恒定¹ | 7.29 |
| B Late-Per-Query | 76.635 | 2.96508e+07 | 321607 | 1.92646 | 策略间恒定¹ | 16.08 |
| C Late-Persistent | 51.86 | 1.99972e+07 | 216904 | 1.48442 | 策略间恒定¹ | 10.01 |
| O Oracle | 3.5508 | 0（前瞻构建，无额外 token 记账） | 14846.8 | 0.616928 | 1.0（构造性上界） | 0 |

¹ 质量在策略间恒定：所有策略对同一 survivor 行构建同一 artifact、返回同一答案，
  故 non-inferiority 由构造保证；实测 mock 能力 macro-F1 0.97 / field-F1 0.9857（见实验 2 §matched UDF）。

配对统计（log 尺度，n=1512）：log(C/B) mean = **-0.7001**，median 0.00309，P50 0.00309，P95 0.00418，P99 0.00419，95% CI [-0.7660312489013482, -0.6356708500888228]；log(C/A) mean = **0.2082**，95% CI [0.09629423712205702, 0.3216830192246608]。

### 2.1 三组对比必须分开报告

| 对比 | 结论 | 证据 |
|---|---|---|
| C vs B | **Supported**：Capability Persistence 有独立成本价值 | C/B = 0.3882（WORKLOAD，n=504）|
| C vs A | **Boundary Identified**：仅在物化作用域/容量充足时 C ≤ A | WORKLOAD C/A=0.6365；CELL C/A=13.76；CAP_10PCT C/A=13.45 |
| C vs O | **Partially Supported**：C 距 oracle 仍有可测 regret | 10.01 |

### 2.2 边界拟合

| 特征 | 系数 | SE | t |
|---|---:|---:|---:|
| const | 1.535653 | 83.078527 | 0.018 |
| log10_s | 2.3117 | 0.035609 | 64.919 |
| log10_reuse | 1.97843 | 0.043468 | 45.515 |
| overlap_ratio | -0.023479 | 0.002593 | -9.055 |
| log2_width | -0.000332 | 0.026578 | -0.012 |
| log10_payload_len | -1.544012 | 47.345459 | -0.033 |
| is_CELL_scope | 1.824177 | 0.053157 | 34.317 |
| is_CAP_scope | 1.537813 | 0.053157 | 28.93 |

R² = **0.86**（adj 0.8593，n=1512）

- 结构式判据（可用容量份额 ≥ 需要并集份额）准确率：**0.8829**
- 经典形式 `k·s<c` 判据准确率：**0.6323** → 该形式**不足以**刻画边界；
  必须加入**物化作用域/容量**（一阶）、reuse 分布、谓词重叠度。

---

## 3. Table B：Semantic Specificity（Tier 0 真实 GLM + Tier 1 matched UDF）

| Capability 域 | Strategy(variant) | Fields | Input Tokens | Output Tokens | Cost(vs SEP8) | Quality(mean field acc) |
|---|---|---:|---:|---:|---:|---:|
| ecom | V1 bundled | 1 | 93.203 | 12 | 0.1295 | 1 |
| ecom | V2 bundled | 2 | 107.2 | 19.125 | 0.1556 | 1 |
| ecom | V4 bundled | 4 | 136.2 | 31.219 | 0.2062 | 1 |
| ecom | V8 bundled | 8 | 200.2 | 102.08 | 0.3722 | 0.9129 |
| ecom | SEP8 separate | 8 | 691.62 | 120.48 | 1.000 | 0.8973 |
| finproc | V1 bundled | 1 | 89.688 | 10.641 | 0.1244 | 1 |
| finproc | V2 bundled | 2 | 109.69 | 21.234 | 0.1623 | 0.9141 |
| finproc | V4 bundled | 4 | 155.69 | 42.25 | 0.2454 | 0.8594 |
| finproc | V8 bundled | 8 | 211.69 | 78.766 | 0.3601 | 0.8848 |
| finproc | SEP8 separate | 8 | 706.5 | 100.17 | 1.000 | 0.8496 |

- 难度分级实测：{"TypeA_independent_short_classification": {"finproc_clause_kind_bundled": 1}, "TypeB_numeric_extraction": {"ecom_amount_bundled": 1}, "TypeC_context_dependent": {"finproc_effective_limit_single_call": 0.9844}, "TypeD_inter_field_dependency": {"finproc_governing_value_bundled": 0.9844, "finproc_governing_value_separate": 0.9844}, "interpretation": "TypeC/TypeD 需要先判定条款类型才能解释金额；若其边际 token 成本显著高于 TypeA/B 而准确率不同，则提示 prompt bundling 存在成本-质量权衡。"}

- Tier 1 matched UDF：delta_cost = **0** → 收益机制与 generic expensive UDF **完全同构**
- Tier 0 结论：捆绑显著更省成本（V8/SEP8 = 0.3722（ecom）/ 0.3601（finproc）），且**准确率不低于**分次调用；
  但逐字段存在退化（ecom product 0.3906，finproc role 0.4219）→ 存在**弱**的「选择性捆绑」动机，但不足以构成语义特异机制。
- 依赖型字段（TypeD）在 bundled 与 separate 下准确率相同（均为 0.9844）→ 字段间依赖未产生新的成本-质量张力。

---

## 4. Table C：Prior-Art Boundary（Tier 2 proxy）

| Workload | Eager | Late-Persistent | QuWARTS-like | ReDD-like | PLOP-like | DASE-like | Oracle |
|---|---:|---:|---:|---:|---:|---:|---:|
| W1_cold_query_driven | 5.1842 | 1.723 | 1.723ᴾ | 4.1045ᴾ | 1.723 (Late-Persistent) | 2.1313ᴾ | 1.7193 |
| W2_warm_high_reuse | 5.1842 | 4.6724 | 4.6725ᴾ | 206.66ᴾ | 4.6724 (Late-Persistent) | 4.8864ᴾ | 4.0924 |
| W3_mixed | 5.1842 | 3.7695 | 3.7697ᴾ | 70.885ᴾ | 3.7695 (Late-Persistent) | 4.0553ᴾ | 3.5812 |
| W4_unseen_capability | 5.1842 | 1.9711 | 2.0277ᴾ | 5.948ᴾ | 1.9711 (Late-Persistent) | 2.364ᴾ | 1.9608 |

ᴾ = structural proxy（**未运行原系统**）；其余为本次实现的 native baseline。

---

## 5. Table D：Lifecycle / Source Drift（Tier 1）

| Drift | Full Rebuild | Affected-row Rebuild | Rebuild Ratio | Stale Rows (if no rebuild) | Freshness |
|---|---:|---:|---:|---:|---:|
| 0% | 5.1682 | 0 | 0 | 0 | 1.0 |
| 1% | 5.1682 | 0.031196 | 0.00604 | 158 | 1.0 |
| 5% | 5.1682 | 0.16433 | 0.0318 | 786 | 1.0 |
| 10% | 5.1682 | 0.32424 | 0.06274 | 1572 | 1.0 |
| 25% | 5.1682 | 0.80852 | 0.15644 | 3932 | 1.0 |

---

## 6. Figure 1–3

| 图 | 文件 | 说明 |
|---|---|---|
| Figure 1 | `figures/figure1_selectivity_reuse_costratio.svg` | selectivity × reuse → C/A 与 C/B（scope=WORKLOAD） |
| Figure 2a/b | `figures/figure2_width_token_cost.svg` / `figure2b_width_quality.svg` | 能力宽度 → token 成本 / 质量（真实 GLM） |
| Figure 3 | `figures/figure3_workload_baseline_cost.svg` | workload → baseline → amortized cost/query（ᴾ 标注 proxy） |

---

## 7. Fail Rules（§43）

| 规则 | 触发 | 证据 |
|---|---|---|
| F1_C_vs_B_no_cost_benefit | **NO** | C/B（WORKLOAD scope, 504 cells）= 0.3882；paired log(C/B) mean=-0.7001, 95% CI=[-0.7660312489013482, -0.6356708500888228] |
| F2_quality_non_inferior | **NO** | 策略间质量由构造保证恒定（同一 survivor → 同一 artifact → 同一答案）；Tier 0 实测能力准确率：TypeA 1.000 / TypeB 1.000 / TypeC 0.984 / TypeD 0.984 |
| F3_late_only_helps_at_low_selectivity | **NO** | 高选择性区间 C/B = {"25": 0.78295, "50": 0.77401, "75": 0.76846, "100": 0.76563}；全部 < 1 ⇒ 收益不限于低选择性（F3 不触发）；但 C/A 随 s 上升趋近 1（见 Table A / Figure 1） |
| F4_TADA_matched_removes_benefit | **NO** | TADA-matched 为 v1.2 已完成的实验（prior evidence）；本轮未重复，故标注 Not Tested（不引用旧数字作为新结果） |
| F5_prior_art_explains_all | **YES** | QuWARTS-like ≈ Late-Persistent；PLOP-like ≡ argmin{Late,Eager,PerQuery}；DASE-like 优势来自 prefilter；IVM 解释 drift —— 全部收益可由既有机制解释 |
| F6_validation_eats_benefit | **NO** | 认证成本 / oracle = 1.92% |

---

## 8. 论文级 Claim 门槛（§44）

| # | 条件 | 满足 | 证据 |
|---:|---|---|---|
| 1 | C_over_B_two_domains | ✅ | C/B=0.3882（两域合并；分域见 by_domain） |
| 2 | quality_non_inferior | ✅ | 构造性恒定 + Tier 0 实测 0.984–1.000 |
| 3 | payload_hash_control | ✅ | 所有策略共用同一 unit 表（同一 payload_hash → 同一单位成本）；Tier 0 记录每请求 payload_hash |
| 4 | replay_equality | ✅ | deterministic mock 下重跑逐值一致；Tier 0 未做 replay（Not Tested） |
| 5 | tada_matched | ❓ Not Tested | Not Tested（本轮未重复 v1.2 的 TADA-matched） |
| 6 | generic_udf_cannot_explain | ❌ | matched UDF 的 total_cost 与 semantic capability 完全相同（delta=0） |
| 7 | multi_use_real_artifact_reuse | ✅ | cache ON 摊销节省最高 98.91%；但 cache OFF 时优势为 0 → 来源是 artifact reuse |
| 8 | validation_not_eating_benefit | ✅ | 认证成本占 oracle < 2% |
| 9 | prior_art_cannot_explain | ❌ | 见 F5 |
| 10 | drift_unseen_boundary | ✅ | drift 与 unseen capability 均给出明确量化边界（Table D + unseen_capability.csv） |

**结论档位：Engineering-only**（存在 ❌ 项 ⇒ 不得声称独立研究机制）

---

## 9. 预算与执行

| 实验 | Tier | 估算 tokens | 实际 tokens | 说明 |
|---|---|---:|---:|---|
| E1_boundary（mock） | Tier 1 | 0 | 0 | 零 token（确定性 mock 仿真） |
| E2_specificity（mock matched UDF） | Tier 1 | 0 | 0 | 零 token |
| E2_specificity（真实 GLM） | Tier 0 | 482,560 | 237,580 | 预算估算（§21）与实际消耗 |
| E3_external（proxy + lifecycle） | Tier 2 + Tier 1 | 0 | 0 | 零 token |

- 实际总消耗 **237,580 / 60,000,000**（内部硬预算）= **0.40%**；剩余 59,762,420 tokens 未使用。
- 429 处理：全程 **0 次 429**；所有调用同一 key 内重试，**未发生任何 key 切换**；fallback 触发 = **False**。

---

## 10. 最终裁决文本（克制版）

```text
C vs B（Capability Persistence 的独立成本价值）      : Supported（Tier 1，边界见 §2.1）
C vs A（Late-Persistent 优于 Offline Eager）         : Boundary Identified（非普遍成立）
C vs O（逼近理论最优）                              : Partially Supported
Semantic Specificity（语义特异机制）                 : Unsupported（Tier 1 matched UDF delta=0）
Bundle Scaling（捆绑的成本-质量结构）                : Supported（Tier 0，弱选择性捆绑动机）
Prior-Art 边界（是否只是已知机制重组）               : Fully Explained by Prior Art（Tier 2 proxy）
Source Drift / Unseen Capability                    : Boundary Identified（等价 IVM）
TADA-matched                                        : Not Tested（本轮未重复）
```

不得使用以下表述：我们证明了一个全新的 RAG 范式 / 我们击败了现有方法 / Late Materialization 是未来。
