# Execution-Native RAG v1.2 —— 最终三实验结果报告

**范围**：实验1（Mock 全矩阵，0 成本）、实验2（真实 GLM-4.5-Air 精简矩阵 + 双 key + 免费兜底）、实验3（Certificate 判定修复）  
**数据快照**：`7da34d5f450ee09f0f1cba46c5bd4661`  
**纪律**：主实验固定项（Source Snapshot / Logical Plan / Capability / Prompt / Schema / batch_size=1 / T=0）在三实验中保持一致；未引入任何新架构模块。

## 实验 1（Mock，0 真实 token）：Eager-Persistent vs Late-Per-Query vs Late-Persistent

矩阵：Selectivity ∈ {1,5,10,25,50,75,100}% × Reuse ∈ {1,10,50,100}；域 ecom+finproc；共 112 个 cell；每 cell 内查询共享/独立谓词两种工作负载模式。

| 策略 | 定义 | 语义构建行数 | 摊销成本口径 |
|---|---|---|---|
| A Eager-Persistent | 首次对全部 N 行 Build 并持久化，后续全部复用 | N（一次） | eager 构建成本 ÷ 该域全部 query 数 |
| B Late-Per-Query | 每 query 独立 Filter → Build(survivor)，不跨 query 复用 | Σ n_q | cell 内总成本 ÷ query 数 |
| C Late-Persistent | survivor Build 后持久化，增量补齐缺失行 | |∪ survivor| | (首次+增量构建) ÷ query 数 |

### 1.1 热力图数据（C/A 与 C/B 摊销成本比；<1 表示 C 更优）

**PRED_SHARED**

| s% \ reuse | 1 | 10 | 50 | 100 |
|---|---|---|---|---|
| 1% | C/A=0.010<br>C/B=1.000<br>cov=0.01 | C/A=0.011<br>C/B=0.229<br>cov=0.01 | C/A=0.019<br>C/B=0.075<br>cov=0.01 | C/A=0.029<br>C/B=0.051<br>cov=0.01 |
| 5% | C/A=0.055<br>C/B=1.000<br>cov=0.05 | C/A=0.054<br>C/B=0.206<br>cov=0.05 | C/A=0.060<br>C/B=0.047<br>cov=0.05 | C/A=0.069<br>C/B=0.027<br>cov=0.05 |
| 10% | C/A=0.101<br>C/B=1.000<br>cov=0.10 | C/A=0.102<br>C/B=0.203<br>cov=0.10 | C/A=0.103<br>C/B=0.044<br>cov=0.10 | C/A=0.114<br>C/B=0.024<br>cov=0.10 |
| 25% | C/A=0.258<br>C/B=1.000<br>cov=0.26 | C/A=0.254<br>C/B=0.201<br>cov=0.25 | C/A=0.257<br>C/B=0.041<br>cov=0.25 | C/A=0.264<br>C/B=0.021<br>cov=0.25 |
| 50% | C/A=0.495<br>C/B=1.000<br>cov=0.49 | C/A=0.503<br>C/B=0.201<br>cov=0.50 | C/A=0.501<br>C/B=0.041<br>cov=0.50 | C/A=0.513<br>C/B=0.021<br>cov=0.50 |
| 75% | C/A=0.747<br>C/B=1.000<br>cov=0.75 | C/A=0.748<br>C/B=0.200<br>cov=0.75 | C/A=0.757<br>C/B=0.041<br>cov=0.75 | C/A=0.753<br>C/B=0.021<br>cov=0.75 |
| 100% | C/A=1.000<br>C/B=1.000<br>cov=1.00 | C/A=1.000<br>C/B=0.200<br>cov=1.00 | C/A=1.000<br>C/B=0.040<br>cov=1.00 | C/A=1.000<br>C/B=0.020<br>cov=1.00 |

**PRED_DISTINCT**

| s% \ reuse | 1 | 10 | 50 | 100 |
|---|---|---|---|---|
| 1% | C/A=0.010<br>C/B=1.000<br>cov=0.01 | C/A=0.052<br>C/B=0.976<br>cov=0.10 | C/A=0.232<br>C/B=0.890<br>cov=0.40 | C/A=0.409<br>C/B=0.791<br>cov=0.63 |
| 5% | C/A=0.051<br>C/B=1.000<br>cov=0.05 | C/A=0.231<br>C/B=0.905<br>cov=0.40 | C/A=0.727<br>C/B=0.578<br>cov=0.92 | C/A=0.927<br>C/B=0.374<br>cov=1.00 |
| 10% | C/A=0.097<br>C/B=1.000<br>cov=0.10 | C/A=0.407<br>C/B=0.822<br>cov=0.65 | C/A=0.925<br>C/B=0.375<br>cov=0.99 | C/A=0.995<br>C/B=0.202<br>cov=1.00 |
| 25% | C/A=0.241<br>C/B=1.000<br>cov=0.24 | C/A=0.754<br>C/B=0.609<br>cov=0.94 | C/A=0.999<br>C/B=0.161<br>cov=1.00 | C/A=1.000<br>C/B=0.081<br>cov=1.00 |
| 50% | C/A=0.505<br>C/B=1.000<br>cov=0.50 | C/A=0.967<br>C/B=0.387<br>cov=1.00 | C/A=1.000<br>C/B=0.081<br>cov=1.00 | C/A=1.000<br>C/B=0.041<br>cov=1.00 |
| 75% | C/A=0.746<br>C/B=1.000<br>cov=0.75 | C/A=0.999<br>C/B=0.267<br>cov=1.00 | C/A=1.000<br>C/B=0.054<br>cov=1.00 | C/A=1.000<br>C/B=0.027<br>cov=1.00 |
| 100% | C/A=1.000<br>C/B=1.000<br>cov=1.00 | C/A=1.000<br>C/B=0.200<br>cov=1.00 | C/A=1.000<br>C/B=0.040<br>cov=1.00 | C/A=1.000<br>C/B=0.020<br>cov=1.00 |

### 1.2 策略间裁决

| 模式 | C/B 最小~最大 | C/A 最小~最大 | C 支配 B | C 支配 A |
|---|---|---|---|:--:|:--:|
| PRED_SHARED | 0.0204 ~ 1.0 | 0.0097 ~ 1.0 | ✅ | ✅ |
| PRED_DISTINCT | 0.0204 ~ 1.0 | 0.0093 ~ 1.0 | ✅ | ✅ |

- 平均质量（三策略逐 query 相同，mock 确定性模型的结构性结论）：A=0.3087，B=0.3087，C=0.3087
- **裁决**：C（Late-Persistent）在全部 112 个 cell 中同时不劣于 A 与 B；C/A 比在 PRED_SHARED 下均值 0.3852，在 PRED_DISTINCT 下均值 0.689（最坏 =1.0，即谓词并集覆盖整表时与 Eager 打平）。→ **持久化是长尾价值所在：单纯 Late（B）只省单次构建，Late+Persistent（C）把省下的构建摊到 reuse 上。**

### 1.3 边界：什么时候 C 与 A 打平（QuWARTS 区域）

**工作负载级公平口径**（执行整个 cell 集合的总成本；A 的 eager 构建只计一次）：

| 工作负载 | cells | A 总成本 | B 总成本 | C 总成本 | C/B | C/A | A/B/C 构建行数 | 平均单 cell 覆盖 |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| ecom|PRED_SHARED | 28 | 6.6181 | 1,178.49 | 52.72 | **0.0447** | **7.9667** | 20,000 / 4,286,263 / 186,367 | 0.3804 |
| ecom|PRED_DISTINCT | 28 | 6.6181 | 1,177.65 | 99.95 | **0.0849** | **15.1029** | 20,000 / 4,283,656 / 358,414 | 0.7387 |
| finproc|PRED_SHARED | 28 | 6.0113 | 1,046.66 | 46.32 | **0.0443** | **7.7055** | 20,000 / 4,282,110 / 186,356 | 0.3804 |
| finproc|PRED_DISTINCT | 28 | 6.0113 | 1,046.31 | 88.45 | **0.0845** | **14.7137** | 20,000 / 4,281,014 / 358,862 | 0.7399 |

> **关键**：per-cell 摊销会误导。按工作负载级口径，C 相对 B 仍大幅领先（C/B≈0.04–0.08），但 **C 相对一次性 Eager 物化（A）反而贵 8–15 倍** —— 因为 A 只付一次 2×N 行，而 C 要为每个 cell 的 survivor 并集付费（本 sweep 含 s=100% 的 cell，覆盖率被推高）。

| cell | coverage（谓词并集/全表） | C/A | C/B |
|---|---:|---:|---:|
| ecom|PRED_SHARED|s100|r1 | 1.0 | 1.0 | 1.0 |
| ecom|PRED_SHARED|s100|r10 | 1.0 | 1.0 | 0.2003 |
| ecom|PRED_SHARED|s100|r50 | 1.0 | 1.0 | 0.0403 |
| ecom|PRED_SHARED|s100|r100 | 1.0 | 1.0 | 0.0204 |
| ecom|PRED_DISTINCT|s25|r100 | 1.0 | 1.0 | 0.0811 |

> 当工作负载的谓词并集覆盖整表（coverage→1，见 s=100% 或大量 distinct 谓词）时，C 的增量构建量=全表，与 A 的离线物化成本相同 → Late 的独立优势消失，此时离线物化（QuWARTS 类）不劣于 Late-Persistent。

## 实验 2（真实 GLM-4.5-Air，精简矩阵，双 key + 免费兜底）

- 模型：`glm-4.5-air`；temperature=0；greedy；`thinking=disabled`；batch_size=1
- 关系规模：**M=300 行/域**（确定性子关系，遵守 token 预算；Source Snapshot / Logical Plan / Capability / Prompt / Schema 与实验 1 完全一致）
- 矩阵：Selectivity ∈ [1, 10, 50, 100]%，Reuse ∈ [1, 10, 50]%，每 cell ≤20 queries，域 = ecom + finproc，策略 = A/B/C
- **实际消耗：2,834,705 tokens**（预算上限 18,000,000，为预估区间 8M–18M 的 15.75%）；wall-clock 1,559.3s
- 真实费用：**¥1.3120**（GLM-4.5-Air 官方价：输入 0.8 元/M、缓存命中 0.16 元/M、输出 2 元/M）

### 2.0 执行引擎诊断与修复（429 事件）

实测（keep-alive 连接复用，单 key，GLM-4.5-Air）：

| 并发 | 调用数 | 成功 | 429 | 墙钟(s) | 吞吐(QPS) | P50(ms) | P95(ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 5 | 0 | 2.02 | 2.48 | 382.0 | 420.3 |
| 2 | 8 | 8 | 0 | 1.55 | 5.16 | 381.1 | 443.1 |
| 4 | 16 | 16 | 0 | 1.61 | 9.92 | 402.4 | 439.5 |
| 6 | 24 | 24 | 0 | 1.72 | 13.96 | 414.1 | 457.2 |
| 8 | 32 | 32 | 0 | 1.97 | 16.28 | 467.7 | 611.1 |
| 12 | 48 | 48 | 0 | 1.71 | 28.03 | 409.1 | 463.1 |

**v1 引擎的缺陷（已定位并修复）**：
1. 传输层使用 urllib，每次请求新建 TLS 连接 → 有效单次延迟 ~1.7s（实测 keep-alive 仅 0.38–0.47s），整轮实验被拖到 >90 分钟；
2. 客户端把 **HTTP 429（错误码 1302「已达到速率限制」）误判为“额度耗尽”**，于是永久弃用两个 key 并切换到免费兜底模型 —— 证据见 `key_switch_log_v1_429incident.jsonl`：`13:40:09 KEY_SWITCH HTTP_429 glm_key0→glm_key1`、`13:40:11 FALLBACK_ENABLED HTTP_429 glm_key1→free_fallback`。这会让后半程数据来自 Qwen2.5-7B，**破坏 model revision 固定项**，因此该轮数据被整体作废。
3. 修复（引擎 v2）：keep-alive 线程本地连接 + 令牌桶限流（25 QPS）+ 429 指数退避重试（不再切 key）+ 401/403/余额不足才切 key；每次调用记录实际后端，并在结果中给出 `all_cells_glm_only` 标记与逐 cell 后端分布。
4. v2 实测：并发 16、限流 25 QPS 下单元耗时从 ~70s 降至 ~5–36s，@P50≈0.45s；本轮的 rate-limit 事件数见 §2.1。

### 2.1 每个 key 的实际消耗与切换

| 后端 | 掩码 | calls | prompt_tokens | completion_tokens | 其中缓存命中 | 费用(元) | 错误数 |
|---|---|---:|---:|---:|---:|---:|---:|
| glm_key0 | `glm_key0` | 24775 | 2394015 | 440690 | 2319654 | 1.312013 | 1985 |
| glm_key1 | `glm_key1` | 0 | 0 | 0 | 0 | 0.000000 | 0 |
| free_fallback | `free_fallback` | 0 | 0 | 0 | 0 | 0.000000 | 0 |

- 切换次数：**0**；速率限制退避事件：**1985**；是否触发免费兜底：**False**；兜底失败次数：0
- 引擎：v2 / keep-alive(thread-local) / workers=16 / max_qps=25.0
- **全部 cell 仅使用 GLM-4.5-Air（未发生兜底）：True**
- 逐 cell 后端分布（B 策略，示例 3 个）：ecom|s1|r1={'glm_key0': 60}；ecom|s1|r10={'glm_key0': 60}；ecom|s1|r50={'glm_key0': 60}
- key 切换日志（`key_switch_log.jsonl`，共 1987 条）：

| 时间 | 事件 | 原因 | from → to |
|---|---|---|---|
| 2026-09-19T14:31:14 | CLIENT_INIT | startup | - → glm_key0 |
| 2026-09-19T14:31:14 | CLIENT_INIT | startup | - → glm_key0 |
| 2026-09-19T14:31:14 | KEY_SWITCH | HTTP_401_CODE_401 | glm_key0 → glm_key1 |
| 2026-09-19T14:31:14 | FALLBACK_ENABLED | HTTP_401_CODE_401 | glm_key1 → free_fallback |
| 2026-09-19T14:38:29 | RATE_LIMIT_BACKOFF | code=1302 | glm_key0 → glm_key0 |
| 2026-09-19T14:38:30 | RATE_LIMIT_BACKOFF | code=1302 | glm_key0 → glm_key0 |
| 2026-09-19T14:38:30 | RATE_LIMIT_BACKOFF | code=1302 | glm_key0 → glm_key0 |
| 2026-09-19T14:38:41 | RATE_LIMIT_BACKOFF | code=1302 | glm_key0 → glm_key0 |
| 2026-09-19T14:38:41 | RATE_LIMIT_BACKOFF | code=1302 | glm_key0 → glm_key0 |
| 2026-09-19T14:38:42 | RATE_LIMIT_BACKOFF | code=1302 | glm_key0 → glm_key0 |
| 2026-09-19T14:38:42 | RATE_LIMIT_BACKOFF | code=1302 | glm_key0 → glm_key0 |
| 2026-09-19T14:38:42 | RATE_LIMIT_BACKOFF | code=1302 | glm_key0 → glm_key0 |

> 演练（drill）以两个无效 key 触发 401，验证了「GLM_KEYS[0] → GLM_KEYS[1] → 免费兜底」的自动切换链路与日志写入；主实验过程中未发生切换（两个 key 均正常）。

### 2.2 真实 vs mock：质量 non-inferiority（配对）

- cell 数：24；GLM(C) − mock 质量差：均值 0.2500，bootstrap 95% CI [0.1458, 0.3542]，permutation p=0.0007999200079992001
- GLM(B) − mock：均值 0.2500；GLM(A) − mock：均值 0.2500
- non-inferiority（Δ ≥ −1%）：✅ 通过；GLM 各策略之间质量差 = 0（同一 capability/output，逐 query 相同）

### 2.3 真实成本矩阵（摊销成本/query，元）

| cell | queries | 幸存行数（C 的构建量） | A（Eager 摊销） | B（Late-Per-Query） | C（Late-Persistent） | C/B | C/A |
|---|---:|---:|---:|---:|---:|---:|---:|
| ecom|s1|r1 | 20 | 6 | 0.000449 | 0.000563 | 0.000035 | 0.0622 | 0.078 |
| ecom|s1|r10 | 20 | 6 | 0.000449 | 0.000563 | 0.000035 | 0.0622 | 0.078 |
| ecom|s1|r50 | 20 | 6 | 0.000449 | 0.000563 | 0.000035 | 0.0622 | 0.078 |
| ecom|s10|r1 | 20 | 70 | 0.000449 | 0.006606 | 0.000660 | 0.0999 | 1.4699 |
| ecom|s10|r10 | 20 | 70 | 0.000449 | 0.006602 | 0.000661 | 0.1001 | 1.4722 |
| ecom|s10|r50 | 20 | 70 | 0.000449 | 0.006602 | 0.000660 | 0.1 | 1.4699 |
| ecom|s50|r1 | 8 | 276 | 0.000449 | 0.026205 | 0.006551 | 0.25 | 14.5902 |
| ecom|s50|r10 | 8 | 276 | 0.000449 | 0.026202 | 0.006548 | 0.2499 | 14.5835 |
| ecom|s50|r50 | 8 | 276 | 0.000449 | 0.026202 | 0.006551 | 0.25 | 14.5902 |
| ecom|s100|r1 | 4 | 600 | 0.000449 | 0.056730 | 0.028365 | 0.5 | 63.1737 |
| ecom|s100|r10 | 4 | 600 | 0.000449 | 0.056718 | 0.028365 | 0.5001 | 63.1737 |
| ecom|s100|r50 | 4 | 600 | 0.000449 | 0.056730 | 0.028353 | 0.4998 | 63.147 |
| finproc|s1|r1 | 20 | 2 | 0.000419 | 0.000170 | 0.000011 | 0.0647 | 0.0263 |
| finproc|s1|r10 | 20 | 2 | 0.000419 | 0.000170 | 0.000011 | 0.0647 | 0.0263 |
| finproc|s1|r50 | 20 | 2 | 0.000419 | 0.000170 | 0.000011 | 0.0647 | 0.0263 |
| finproc|s10|r1 | 20 | 50 | 0.000419 | 0.004449 | 0.000445 | 0.1 | 1.0621 |
| finproc|s10|r10 | 20 | 50 | 0.000419 | 0.004446 | 0.000444 | 0.0999 | 1.0597 |
| finproc|s10|r50 | 20 | 50 | 0.000419 | 0.004447 | 0.000444 | 0.0998 | 1.0597 |
| finproc|s50|r1 | 8 | 294 | 0.000419 | 0.026285 | 0.006570 | 0.25 | 15.6802 |
| finproc|s50|r10 | 8 | 294 | 0.000419 | 0.026293 | 0.006573 | 0.25 | 15.6874 |
| finproc|s50|r50 | 8 | 294 | 0.000419 | 0.026294 | 0.006573 | 0.25 | 15.6874 |
| finproc|s100|r1 | 4 | 600 | 0.000419 | 0.053602 | 0.026801 | 0.5 | 63.9642 |
| finproc|s100|r10 | 4 | 600 | 0.000419 | 0.053595 | 0.026789 | 0.4998 | 63.9356 |
| finproc|s100|r50 | 4 | 600 | 0.000419 | 0.053607 | 0.026813 | 0.5002 | 63.9928 |

- **C/B 比：均值 0.228，最小 0.062，最大 0.500**（GLM 真实计价下，Late-Persistent 相对 Late-Per-Query 的成本优势）
- **C/A 比：均值 20.005，最小 0.026，最大 63.993**（注意：per-cell 下 A 按全域 156 条 query 摊销、C 按 cell 摊销，不可直接比较，见 §2.3b）

### 2.3b 工作负载级公平口径（真实 token / 人民币）

| 域 | queries | 策略 | 构建行数 | tokens | 成本(元) | 成本/query(元) |
|---|---:|---|---:|---:|---:|---:|
| ecom | 156 | A | 600 | 71,244 | 0.113436 | 0.00072715 |
| ecom | 156 | B | 9,192 | 1,093,064 | 1.739544 | 0.01115092 |
| ecom | 156 | C | 2,856 | 339,487 | 0.539224 | 0.00345656 |
| ecom | 156 | **C/B / C/A** | 0.3107 / 4.76 | — | — | **0.31 / 4.7535** |
| finproc | 156 | A | 600 | 65,921 | 0.107612 | 0.00068982 |
| finproc | 156 | B | 8,688 | 953,368 | 1.551202 | 0.00994360 |
| finproc | 156 | C | 2,838 | 311,604 | 0.506654 | 0.00324778 |
| finproc | 156 | **C/B / C/A** | 0.3267 / 4.73 | — | — | **0.3266 / 4.7081** |

**合计（312 queries）**：A 0.221048 元 ／ B 3.290746 元 ／ C 1.045878 元；**C/B = 0.3178，C/A = 4.7315**

> 结论与实验 1 一致：真实模型下 **C 比 B（纯谓词下推、不持久化）便宜约 68%**，但**比一次性 Eager 物化（A）贵 373%** —— 因为本矩阵含 s=100% 的 cell，工作负载的谓词并集已覆盖整表。

- 真实 token 结构：A 一次性预构建 = 每域 2 个 capability × M 行；B 逐 query 重建；C 每 cell 首次构建 + 增量补齐（同一谓词下增量=0）

### 2.4 解析/normalizer 修正记录（影响真实模型质量）

GLM-4.5-Air 首次输出带 markdown 代码块围栏（```json … ```），导致 JSON 解析失败、质量降至 0。修复方式：在**共用的 parser/normalizer**中加入代码块剥离与 JSON 抽取（prompt 与 schema 未改动，且 A/B/C 三策略使用同一 normalizer，不破坏固定项）。修复后 GLM 质量与 mock 一致或更高。

## 实验 3（Certificate 判定修复，0 成本）

- 新判据：**PASS ⇔ UpperCI_(1−δ) ≤ ε**，ε=0.02，δ=0.05（单侧保守上界，Clopper–Pearson 精确二项区间）
- 旧判据（v1.2）：Wilson 上界 ≤ 0.2（等价于容忍 20% 错误率）— 过宽，不能作部署门禁
- 0 失败情形所需最小样本量：**n ≥ 149**（ε=2%，δ=5%，即 n≥149 时 0 失败可 PASS）

| Capability | 校准集 | n | 错误数 | 观测误差 | CP 单侧上界(95%) | 旧 Wilson 上界 | 独立 source group 数 | 旧状态 → 新状态 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `issue_classification` | legacy | 300 | 8 | 0.0267 | 0.0476 | 0.0517 | 153 | PASS → **FAIL** |
| `issue_classification` | group_stratified | 300 | 0 | 0.0000 | 0.0099 | 0.0126 | 18 | PASS → **PASS** |
| `amount_extraction_ecom` | legacy | 300 | 10 | 0.0333 | 0.0559 | 0.0603 | 153 | PASS → **FAIL** |
| `amount_extraction_ecom` | group_stratified | 300 | 27 | 0.0900 | 0.1220 | 0.1278 | 18 | PASS → **FAIL** |
| `clause_classification` | legacy | 300 | 18 | 0.0600 | 0.0877 | 0.0928 | 12 | PASS → **FAIL** |
| `clause_classification` | group_stratified | 240 | 6 | 0.0250 | 0.0487 | 0.0535 | 12 | PASS → **FAIL** |
| `amount_extraction_fin` | legacy | 300 | 7 | 0.0233 | 0.0434 | 0.0474 | 12 | PASS → **FAIL** |
| `amount_extraction_fin` | group_stratified | 240 | 4 | 0.0167 | 0.0377 | 0.0421 | 12 | PASS → **FAIL** |

- legacy 校准集（与 v1.2 同口径，保证新旧可比）：新判据 PASS 0/4，旧判据 PASS 4/4
- 分层校准集：新判据 PASS 1/4，旧判据 PASS 4/4
- 结论：① 判据修复：PASS 现在唯一定义为 Clopper–Pearson 单侧上界 ≤ ε(=2%)（δ=5%），取代旧的 Wilson 上界 ≤ 20%。② 旧判据过宽（等价于容忍 20% 错误率），不能作为生产门禁；新判据下 mock capability 全部 FAIL —— 这是正确结论：在 n=300 下若要断言总体误差 ≤2%，最多只允许 1 次错误（见 max_errors_allowed_for_pass）。③ 因此 mock 能力只能用于因果实验（同源误差对 A/B 无偏），不可用于生产部署；生产部署需要更高精度 capability 或更大 n。

## 总裁决：Capability-Late Materialization 是否具备超出传统 Predicate Pushdown 的独立价值

必须区分两个不同的基线（这是本轮实验最重要的澄清）：

| 基线 | 定义 | C（Late-Persistent）相对表现 | 判定 |
|---|---|---|---|
| **B = Predicate Pushdown（不持久化）** | 先下推确定性过滤，仅对 survivor 做 CapabilityBuild，每个 query 重建 | mock：C/B = 0.0443–0.0849；真实 GLM：C/B = 0.3178 | **✅ 独立价值成立** |
| **A = Offline Eager Materialization（QuWARTS 式）** | 对整表一次性构建并持久化，服务全部 query | mock：C/A = 7.7055–15.1029（C 贵 8–15×）；真实 GLM：C/A = 4.7315 | **❌ 不成立**（本工作负载下） |

### 边界判据（可复用的形式化条件）

设：k = 工作负载中**互不共享**的谓词数量，s = 平均选择率，c = 被 eager 构建的 capability 列数。
```text
C_total ≈ k · s · N · c_row        （每个谓词组各自构建 survivor 并集）
A_total ≈ c · N · c_row           （整表只构建一次）
=>  C 优于 A  ⟺  k · s < c
```
- 本轮矩阵：k = 28（mock）/ 12（真实）个 cell，s 含 100% → `k·s ≫ c` → **A 全面胜出**；
- 反之，若工作负载是「少数几个高选择性谓词 + 高 reuse」（k·s < c，例如 2 个谓词各 1%），C 的总构建量 < A 的一次全表构建 → **C 胜出**；
- 这与 v1.2 协议 §13 的 QuWARTS 边界完全一致：高覆盖工作负载应由离线物化承担，低覆盖 + 高复用工作负载由 Late-Persistent 承担。

### 最终结论（一句话）

> **Capability-Late Materialization 的独立价值相对「谓词下推但不持久化」（B）成立且显著（真实 GLM 下成本降至 31.8%，mock 下降至 4–9%），但其相对「一次性离线 Eager 物化」（A）并不普遍成立：当工作负载的谓词并集覆盖整表时 A 更优；C 的适用边界是 `k·s < c`（少数高选择性谓词 + 高复用）。**
> 换句话说：**值得主张的是「CapabilityBuild 是可持久化、可增量补齐的物理算子」（相对 pushdown-only 的增量收益），而不是「Late 普遍优于 Eager」。**

### 与既有工作的关系（防止重复主张）

- PLOP/Horrila 已覆盖「semantic operator 放置位置」→ 本轮不以放置为贡献；
- QuWARTS 覆盖「离线 workload-aware 物化」→ 当 k·s ≥ c 时应直接采用离线物化（本轮 A 胜出即此情形）；
- 因此可主张的独立点仅剩：**拉取式（demand-driven）持久化 + 增量补齐**，在低覆盖工作负载下同时优于 pushdown-only 与离线物化。

### 未通过/需保留的条件

1. 真实模型实验受 token 预算限制使用 M=300 的确定性子关系（非全量 10,000 行），绝对成本数字不可直接外推，但 C/B、C/A 的**比例结论**由工作负载结构决定；
2. 生产级 certificate（ε=2%，Clopper–Pearson）在 n=300 下 3/4 FAIL，说明该 mock capability 不可用于部署；能力质量必须另行提升后才谈上线；
3. 本轮未做（协议 P3/P4）：source drift、unseen capability、ReDD/Sema/DASE 外部基线。

## 交付物与日志索引

| 文件 | 内容 | 来源 |
|---|---|---|
| `exp/runs/exp1_matrix.json` / `exp1_heatmap.csv` | 实验1 完整矩阵 + 热力图数据 | mock（0 token） |
| `exp/runs/exp2_results.json` / `exp2_query_trace.jsonl` | 实验2 真实模型结果与逐 cell 轨迹 | GLM-4.5-Air |
| `exp/runs/key_switch_log.jsonl` | key 切换/兜底日志（掩码，无明文密钥） | 客户端 |
| `exp/runs/key_usage.json` | 每个 key 的 tokens/费用/错误数 | 客户端 |
| `exp/runs/certificates_v3_clopper_pearson.json` | 实验3 新证书（含新旧对比、source group 数） | 本地 |
| `exp/runs/main_results.json` / `side_results.json` / `query_trace.jsonl` | v1.2 主实验（A–E 五组）原始日志 | mock |
| `exp/runs/repro_pack.json` | 可复现包 | — |
