# 实验运行结果总汇（全代际）

- 生成时间：2026-09-21 10:22:38（由 `research/make_runs_summary.py` 自动生成）
- 覆盖：v1.2 mock 主实验 → v1.2 真实 GLM 精简矩阵 → Certificate 修复 → research/ 三实验 → v1.3 最终三实验
- 机读版：`research/experiment_runs_bundle.json`；所有数字由脚本从原始 JSON 抽取。

---

## 0. 运行总览

| # | 运行 | 代际 | Tier | 规模 | 真实 token | 结论 |
|---|---|---|---|---|---|---|
| 1 | Build Position Ablation | v1.2 | Tier 1 | 600 paired queries / N=10,000×2 域 | 0 | 语义工作 ↓63.22%，质量 Δ=0，INVALID=0，replay=True |
| 2 | 真实 GLM 精简矩阵（A/B/C） | v1.2-GLM | Tier 0 | 24 cells / 312 queries | 2,834,705 | C/B=0.3178，C/A=4.731；引擎 v2 修复 429 误判后重跑 |
| 3 | Capability Certificate 修复 | v1.2 | Tier 1 | 4 capabilities × 2 校准集 | 0 | PASS 判据改为 CP 单侧上界 ≤2%；legacy 0/4 PASS（旧 Wilson≤20% 下 4/4） |
| 4 | 旁路实验（multi-use / TADA / validation / 低选择率） | v1.2 | Tier 1 | 4 组 | 0 | TADA-matched 收益未消失；cache OFF 时摊销优势归零 |
| 5 | Adaptive Semantic Materialization | research/ | Tier 1 | 840 cells × 6 策略 | 0 | D 与 Simple CBO 相同 609/840，更差 159 → 自适应无增量价值 |
| 6 | 语义特异性（含真实微探针） | research/ | Tier 0+Tier 1 | 80 matched-UDF cells | 108,361 tok | matched UDF delta_cost=0；捆绑 V8/SEP8=0.2785 |
| 7 | 外部基线 + drift | research/ | Tier 1/2 | 3 workloads + 5 drift 档 | 0 | Late-Persistent 在三负载上 regret=0；drift(5%) 增量=0.00313×全量 |
| 8 | Materialization Boundary | v1.3 | Tier 1 | 1512 cells | 0 | 边界 R²=0.86；WORKLOAD C/A=0.6365，CELL C/A=13.76 |
| 9 | 语义特异性三件套（真实 GLM） | v1.3 | Tier 0 | 2 域 × 64 行 × 13 变体 | 237,580 | 捆绑 V8/SEP8=0.3722（ecom）/ 0.3601（finproc）；准确率不低于分次调用 |
| 10 | Prior-Art Boundary + Lifecycle | v1.3 | Tier 2+Tier 1 | 4 workloads + 5 drift 档 | 0 | PLOP-like ≡ Late-Persistent；drift = IVM（未运行任何外部系统） |

---

## 1. API 消耗总账（真实模型）

| 运行 | key | 请求数 | tokens | 费用(¥) | 是否进入 confirmatory 统计 |
|---|---|---:|---:|---:|---|
| v1.2-GLM 真实精简矩阵（24 cells） | glm_key0 | 24,775 | 2,834,705 | 1.31201 | 是 |
| research/ 实验2 微探针 P1–P4 | glm_key0 | 280 | 29,825 | 0.020245 | 是 |
| research/ 实验2 捆绑规模+长度探针 | glm_key0 | 528 | 78,536 | 0.0573309 | 是 |
| v1.3 实验2 捆绑/长度（Tier 0） | glm_key0 | 882 | 119,782 | 按 GLM 计价表折算 | 是 |
| v1.3 实验2 捆绑/长度（Tier 0） | glm_key1 | 862 | 117,798 | 按 GLM 计价表折算 | 是 |

- **confirmatory 合计：27,327 次请求 / 3,180,646 tokens / ¥1.3896**
- fallback 请求：**0** 次（`fallback_trace.jsonl`；未进入任何 confirmatory 统计）
- 总配额 64,000,000；配额使用率 **4.9698%**；v1.3 内部硬预算 60,000,000 使用率 **0.40%**

> 说明：v1.2-GLM 第一次尝试（引擎 v1）曾把 HTTP 429 误判为额度耗尽并切到免费兜底模型，该轮数据作废、证据留档 `exp/runs/key_switch_log_v1_429incident.jsonl`；修复后的 v2 引擎（keep-alive + 令牌桶 + 429 退避不换 key）重跑得上述 confirmatory 数据。
> v1.3 全程 **0 次 429、0 次 key 切换、fallback 未触发**，双 key 用量均衡 （119,782 / 117,798）。

---

## 2. v1.2 Build Position Ablation（Tier 1，mock，0 token）

固定项：source snapshot / logical plan / capability implementation / model / prompt / schema /
tokenizer / reader / batch_size=1 / temperature=0；唯一变量 = CapabilityBuild 位置。

| 指标 | A=Eager | B=Late-Per-Query | Δ / 比值 |
|---|---|---|---|
| quality_score | 0.9529 | 0.9529 | Δ=0 |
| answer_correct | 0.4 | 0.4 | Δ=0 |
| 语义工作量下降 | - | - | **63.22%** |
| 总成本下降 | - | - | **63.18%** |
| Cost/CorrectQuery 下降 | - | - | **63.16%** |
| validation 占 B 总成本 | - | - | 0.33% |
| EXPERIMENT_INVALID | - | - | 0 |
| Replay equality | - | - | True |

| family | n | work↓ | cost↓ | cost/correct↓ | P95 比值 |
|---|---:|---:|---:|---:|---:|
| W1_high | 252 | 94.93% | 94.90% | 94.88% | 0.0999 |
| W2_medium | 188 | 63.84% | 63.79% | 63.95% | 0.5002 |
| W3_low | 160 | 12.53% | 12.51% | 12.51% | 1 |

- 预注册判定：**SUPPORTED**；未通过的检查项：[]

---

## 3. v1.2 真实 GLM 精简矩阵（Tier 0）

| 策略 | tokens | 成本(¥) | build rows | cost/query(¥) |
|---|---:|---:|---:|---:|
| A Eager-Persistent | 137165 | 0.221048 | 1200 | 0.00070849 |
| B Late-Per-Query | 2.04643e+06 | 3.29075 | 17880 | 0.01054726 |
| C Late-Persistent | 651091 | 1.04588 | 5694 | 0.00335217 |

- query 总数 312；**C/B = 0.3178**，**C/A = 4.731**（token 口径 C/B=0.3182，C/A=4.747）
- 口径：统一口径：执行整个矩阵（24 cells / 全部 query）时的总成本。A=每域一次性 eager 构建 + 全量复用；B=逐 query 重建；C=每 cell 首次构建+增量复用。
- 引擎：{'version': 'v2', 'transport': 'keep-alive(thread-local)', 'workers': 16, 'max_qps': 25.0, 'rate_limit_events': 1985, 'switches': 0, 'fallback_used': False}；all_cells_glm_only = True；wall clock 1559.3 s

> 该轮 A/B/C 的摊销口径为「每 cell」而非「每工作负载」，是后续 v1.3 边界实验要纠正的对象。

---

## 4. Capability Certificate 修复（Tier 1）

- 规则：UpperCI_(1-δ) ≤ ε，Clopper–Pearson 精确单侧上界
- ε=0.02，δ=0.05，0 失败所需 n ≥ **149**
- legacy 校准集：新判据 **0/4 PASS**（旧判据 4/4）；group-stratified：1/4

| capability | legacy err | CP 上界95 | 旧 Wilson | 独立 source group 数 |
|---|---:|---:|---:|---:|
| issue_classification | 0.0267 | 0.0476 | 0.0517 | 153 |
| amount_extraction_ecom | 0.0333 | 0.0559 | 0.0603 | 153 |
| clause_classification | 0.06 | 0.0877 | 0.0928 | 12 |
| amount_extraction_fin | 0.0233 | 0.0434 | 0.0474 | 12 |

> 结论：mock capability 只能用于因果机制实验（同源误差对 A/B 无偏），**不得**宣称生产级可靠性。

---

## 5. 旁路实验（v1.2，Tier 1）

- **Multi-use**：reuse=10 时摊销节省 89.07%；**cache OFF 时 -8.91%** → 优势来源是 artifact reuse
- **TADA-matched**：T1 cost↓63.16% / T2 cost↓63.18%，两者 quality Δ 均为 0 → 收益来自 Build Position 而非 representation 设计
- **Validation cost**：{"validation_cost_mean": 0.00294221, "validation_share_of_total_B": 0.00326, "validation_over_semantic_saving": 0.00192, "total_A": 2.42334967, "total_B": 0.89277046, "semantic_saving_abs": 1.53057921, "budget_total_limit": 0.1, "protocol": {"mode": "V1_CACHED_CERTIFICATE", "sequential_sampling": [3
- **低选择率安全性**：{"n": 160, "cost_ratio": 0.8749, "quality_delta": 0.0, "p95_ratio": 1.0, "limit": 1.1, "safe": true}

---

## 6. research/ 三实验（第一轮最终实验）

### 6.1 Adaptive Semantic Materialization（840 cells）

| 策略 | regret mean | min | max |
|---|---:|---:|---:|
| A Eager | 9.038 | 0 | 120.8 |
| B Late-Per-Query | 17.26 | 0 | 98.59 |
| C Late-Persistent | 0.00137 | 0 | 0.0042 |
| Simple CBO | 0.2615 | 0 | 0.9968 |
| D Adaptive | 0.8507 | 0 | 18.67 |
| D+（诊断，知悉视界） | 0.7186 | 0 | 17.68 |

- **D vs CBO**：相同 609/840，更优 72，更差 159，成本比均值 1.3961
- 最优标签分布：{"B": 336, "C": 342, "A": 162}
- 作用域消融（C/A）：workload 级 n/a，cell 级 n/a

### 6.2 语义特异性（真实微探针 + matched UDF）

- 真实探针：108,361 tokens / ¥0.077576；all_primary=True
- P1 成本-长度 pearson=0.9533；P2 四字段捆绑/四次单字段=0.4752
- P2b 八字段捆绑/八次单字段=0.2785；广度 1→8 准确率变化=0
- P3 答案稳定率=1 / 句法键稳定率=0；P4 依赖上下文 +27.83%
- matched UDF：80 cells，delta_cost 最大绝对差 = **0**；认证开销/oracle=5.90%

### 6.3 外部基线 + drift（3 workloads）

| Baseline | 策略 | 成为最优的 cell 占比 | regret mean |
|---|---|---:|---:|
| B0_naive_per_query | B | 0.4 | 17.26 |
| B1_eager_persistent | A | 0.1929 | 9.038 |
| B2_late_persistent | C | 0.4071 | 0.00137 |
| B3_simple_cbo | CBO | 0 | 0.2615 |
| B4_adaptive | D | 0 | 0.8507 |

- C（Late-Persistent）与 oracle 完全相等的 cell 占比：**0.6**
| workload | Late regret | Adaptive regret | CBO regret |
|---|---:|---:|---:|
| A_query_driven | 0 | 0.9662 | 0.9662 |
| B_batch_analytics | 0 | 0.8136 | 0.00956 |
| C_mixed | 0 | 2.683 | 0.1003 |

---

## 7. v1.3 最终三实验

### 7.1 Materialization Boundary（1512 cells / 1537.3 s / 0 token）

- 矩阵：selectivity [1, 5, 10, 25, 50, 75, 100]，reuse [1, 10, 50, 100]，patterns ['DISJOINT', 'OVERLAP', 'NESTED']，widths [1, 2, 4]，scopes ['WORKLOAD', 'CAP_10PCT', 'CELL']

| scope | n | C/A mean | C/A min | C/A max | C/B mean |
|---|---:|---:|---:|---:|---:|
| WORKLOAD | 504 | 0.6365 | 0.00795 | 1 | 0.3882 |
| CAP_10PCT | 504 | 13.45 | 0.00795 | 99.92 | 0.8756 |
| CELL | 504 | 13.76 | 0.00795 | 99.92 | 1.003 |

- 边界模型（target=log C_C/C_A）：**R²=0.86**（adj 0.8593，n=1512）

| 特征 | 系数 | t |
|---|---:|---:|
| const | 1.536 | 0.018 |
| log10_s | 2.312 | 64.92 |
| log10_reuse | 1.978 | 45.52 |
| overlap_ratio | -0.02348 | -9.055 |
| log2_width | -0.000332 | -0.012 |
| log10_payload_len | -1.544 | -0.033 |
| is_CELL_scope | 1.824 | 34.32 |
| is_CAP_scope | 1.538 | 28.93 |

- 结构式判据（容量份额 ≥ 并集份额）准确率 **0.8829**；经典 `k·s<c` 准确率 **0.6323**

### 7.2 语义特异性三件套（Tier 0 真实 GLM）

- 消耗 **237,580 tokens / ¥0.106683**；all_primary=True；切换 0 次；429 0 次；fallback=False
- 双 key：{"glm_key0": 119782, "glm_key1": 117798}

| 域 | V1 pt | V2 pt | V4 pt | V8 pt | SEP8 pt | V8/SEP8 成本比 | V1 acc | V8 acc | SEP8 acc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ecom | 93.2 | 107.2 | 136.2 | 200.2 | 691.6 | 0.3722 | 1 | 0.9129 | 0.8973 |
| finproc | 89.69 | 109.7 | 155.7 | 211.7 | 706.5 | 0.3601 | 1 | 0.8848 | 0.8496 |

- 难度分级：{"TypeA_independent_short_classification": {"finproc_clause_kind_bundled": 1}, "TypeB_numeric_extraction": {"ecom_amount_bundled": 1}, "TypeC_context_dependent": {"finproc_effective_limit_single_call": 0.9844}, "TypeD_inter_field_dependency": {"finproc_governing_value_bundled": 0.9844, "finproc_governing_value_separate": 0.9844}}
- 长度扫描：斜率 **0.6508 tokens/char**，R²=1；原生范围 [43, 79]，受控加长范围 [129, 1111]
- Multi-use：cache ON 最高摊销节省 **98.91%**；cache OFF 节省 = 0.0（= artifact reuse 贡献）
- Tier 1 matched UDF：delta_cost = **0**（15 cells）

### 7.3 Prior-Art Boundary + Lifecycle

- experiment_id：`v1.3-final-three-experiments:e3:98fa60d8`；tier：Tier 2（结构性 proxy）+ Tier 1（Lifecycle 机制）
- ****未运行任何外部系统**。QuWARTS-like / ReDD-like / PLOP-like / DASE-like 均为结构性 proxy baseline，严禁表述为原论文系统实验。**

| workload | Eager | Late-Persistent | QuWARTS-like | ReDD-like | PLOP-like | DASE-like | Oracle |
|---|---:|---:|---:|---:|---:|---:|---:|
| W1_cold_query_driven | 5.184 | 1.723 | 1.723ᴾ | 4.105ᴾ | 1.723ᴾ | 2.131ᴾ | 1.719 |
| W2_warm_high_reuse | 5.184 | 4.672 | 4.673ᴾ | 206.7ᴾ | 4.672ᴾ | 4.886ᴾ | 4.092 |
| W3_mixed | 5.184 | 3.769 | 3.77ᴾ | 70.88ᴾ | 3.769ᴾ | 4.055ᴾ | 3.581 |
| W4_unseen_capability | 5.184 | 1.971 | 2.028ᴾ | 5.948ᴾ | 1.971ᴾ | 2.364ᴾ | 1.961 |

ᴾ = structural proxy（未运行原系统）。

| drift | full rebuild | affected-row rebuild | ratio | stale rows |
|---|---:|---:|---:|---:|
| 0% | 5.168 | 0 | 0 | 0 |
| 1% | 5.168 | 0.0312 | 0.00604 | 158 |
| 5% | 5.168 | 0.1643 | 0.0318 | 786 |
| 10% | 5.168 | 0.3242 | 0.06274 | 1572 |
| 25% | 5.168 | 0.8085 | 0.1564 | 3932 |

| unseen capability | total | amortized/query | first-query | build rows | native/proxy |
|---|---:|---:|---:|---:|---|
| Eager | 5.184 | 0.0864 | n/a | 20000 | native |
| Late-Persistent | 1.971 | 0.03285 | 0.07716 | 7534 | native |
| QuWARTS-like | 2.028 | 0.03379 | 0.03556 | 7752 | proxy |
| ReDD-like | 5.948 | 0.09913 | 0.03839 | 27660 | proxy |

---

## 8. 结论演进时间线

| 阶段 | 当时的结论 | 后续被什么修正 |
|---|---|---|
| v1.2 mock | Late 相对 Per-Query 省 63% 语义工作与成本，质量 Δ=0 | 未修正（v1.3 复现并细化：C/B=0.388@WORKLOAD） |
| v1.2-GLM | C/A = 4.73，读作「Late 不普遍优于 Eager」 | **被 v1.3 修正为口径伪影**：摊销按 cell 而非 workload |
| research/ 实验1 | D(Adaptive) 无增量价值，C ≈ oracle | 未修正（v1.3 用 1512 cells 与边界回归进一步确认） |
| research/ 实验2 | 捆绑 sub-additive 且精度不降 → 无成本-质量张力 | 部分修正：v1.3 逐字段发现退化（product/role）→ 弱选择性捆绑动机 |
| research/ 实验3 + v1.3 | 收益全部可由 PLOP/QuWARTS/ReDD/semantic caching/IVM 解释 | 未修正（v1.3 以 proxy baseline 与文献边界再次确认） |

**当前最终档位（v1.3）：Engineering-only**；Fail Rules 中 F5（prior art 解释全部收益）触发。

---

## 9. 已知缺陷与修正记录（会伪造结论的那些）

| # | 缺陷 | 影响面 | 状态 |
|---|---|---|---|
| 1 | v1 引擎把 HTTP 429 误判为额度耗尽并切 fallback 模型 | v1.2-GLM 第一次尝试整轮作废 | 已修复（v2 引擎），证据留档 |
| 2 | Adaptive/CBO 的历史观测集从未写入（`per_query` 缺 `_set`） | research/ 实验1 的 D 退化为「永不持久化」 | 已修复并重跑 |
| 3 | oracle 定义多计 validation → regret 可为负 | research/ 实验1 regret 指标 | 已修复（true lower bound） |
| 4 | LRU `Store.touch` 对已淘汰键抛 KeyError | v1.3 实验1 容量受限 scope | 已修复（仅在容量受限维度暴露） |
| 5 | ecom 8 字段中 4 字段无 oracle → 伪造「捆绑损失 15.4 点准确率」 | v1.3 实验2 | 已修复（改为全部可验证字段） |
| 6 | TypeC 键名映射错 + `pred` 在评分前弹出 → 伪造「TypeC 准确率 0」 | v1.3 实验2 | 已修复 |
| 7 | F3 判据方向写反（`all(<1)` 应为 `any(≥1)`） | v1.3 报告 fail rule | 已修复 |

---

## 10. 原始文件索引（sha256 前 12 位）

| 文件 | 字节 | sha256_12 |
|---|---:|---|
| `exp/runs/analysis_bundle.json` | 43,404 | 9998ef63b7e3 |
| `exp/runs/capability_artifact.jsonl` | 1,824 | c86cf2077306 |
| `exp/runs/certificates.json` | 2,981 | 4ab8baa75853 |
| `exp/runs/certificates_v3_clopper_pearson.json` | 7,476 | 0e1194c1ee0c |
| `exp/runs/demo_capability_outputs.json` | 1,445 | 7fcbcb48e9d1 |
| `exp/runs/exp1_heatmap.csv` | 12,153 | feea292ac77e |
| `exp/runs/exp1_matrix.json` | 41,877 | cb7dc3e6c4b0 |
| `exp/runs/exp2_query_trace.jsonl` | 28,117 | d5c683412672 |
| `exp/runs/exp2_results.json` | 42,544 | ea6a0d8b5fed |
| `exp/runs/exp2_workload_totals.json` | 1,835 | 9fa36983dae3 |
| `exp/runs/failure_cases.json` | 1,613 | f4281a0c8af4 |
| `exp/runs/key_switch_log.jsonl` | 1,061,510 | 72d5598d085a |
| `exp/runs/key_switch_log.jsonl.bak` | 2,315 | 5ef4f92a5c22 |
| `exp/runs/key_switch_log_v1_429incident.jsonl` | 2,315 | 5ef4f92a5c22 |
| `exp/runs/key_usage.json` | 1,350 | 17c4b81b060f |
| `exp/runs/main_results.json` | 92,983 | 3dd6bbc5ec9c |
| `exp/runs/query_trace.jsonl` | 31,091,907 | 5b8a5b1dd064 |
| `exp/runs/rate_probe.json` | 1,263 | 03f554386fa0 |
| `exp/runs/repro_pack.json` | 4,643 | 415cf7fb98d2 |
| `exp/runs/repro_pack_v2.json` | 1,743 | a9e3179894e3 |
| `exp/runs/run_manifest.json` | 4,643 | 913ec268fa12 |
| `exp/runs/side_results.json` | 3,463 | 1a6f85dc29bb |
| `exp/runs/sweep_curve.csv` | 972 | d3d3924275a9 |
| `research/EXPERIMENT_RUNS_SUMMARY.md` | 17,527 | dd9a1bd3a0ed |
| `research/FINAL_VERDICT.md` | 12,361 | 4a8c67c6e7ab |
| `research/README.md` | 2,860 | fdd566a5bf29 |
| `research/RESULTS_BUNDLE_FOR_ANALYSIS.md` | 26,442 | 3398f20409de |
| `research/final_three_experiments/FINAL_REPORT.md` | 12,065 | bc0113cbea88 |
| `research/final_three_experiments/FINAL_VERDICT.md` | 3,733 | 976a79309ac9 |
| `research/final_three_experiments/results_summary.json` | 8,630 | 90063146857d |
| `research/final_three_experiments/run_manifest.json` | 1,537 | 206723ca3e76 |
| `research/final_three_experiments/artifacts/certificate_results.json` | 7,314 | 2d5f4e4d4a58 |
| `research/final_three_experiments/artifacts/key_usage.json` | 1,114 | 828f357cb5ab |
| `research/final_three_experiments/experiment1_boundary/config.json` | 2,204 | 40a51c497a89 |
| `research/final_three_experiments/experiment1_boundary/results.json` | 7,399,156 | 4fa3c342d7fe |
| `research/final_three_experiments/experiment2_specificity/config.json` | 954 | 783969088f58 |
| `research/final_three_experiments/experiment2_specificity/results.json` | 16,467 | a994aa9a279e |
| `research/final_three_experiments/experiment3_external/config.json` | 616 | 886641d6e913 |
| `research/final_three_experiments/experiment3_external/results.json` | 24,265 | 4a3cba2d2291 |

_本文件由 `research/make_runs_summary.py` 于 2026-09-21 10:22:39 生成；301 行；共索引 39 个文件。_
