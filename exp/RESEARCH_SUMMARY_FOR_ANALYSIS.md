# Capability-Late Materialization：研究结果汇总（供外部 AI 分析）

生成时间：2026-09-19　|　数据集快照：`7da34d5f450ee09f0f1cba46c5bd4661`　|　v1.2 query 快照：`bf648f4b90df77bb28ea2983528bea21`

> 本文档自包含：所有结论、数字、表格与原始文件路径均已内联，无需仓库即可审阅。机读版见文末 §12 与 `exp/runs/analysis_bundle.json`。

## 1. 研究问题（可证伪命题）

固定 Source Snapshot / Logical Plan / Capability Implementation / Model / Prompt / Output Schema / batch_size=1 / temperature=0，仅改变 `CapabilityBuild` 的**位置与持久化方式**：

```text
A  Eager-Persistent    : 对整表一次性 CapabilityBuild 并持久化，后续全部复用
B  Late-Per-Query      : 每个 query 先做确定性 Filter，再对 survivor 单独 Build（不持久化）= 纯谓词下推
C  Late-Persistent     : 对 survivor Build 后持久化，支持增量补齐（缺失行才构建）
D  Late + exact payload: 逐行回读并校验 payload_hash，排除「Late 输入更干净」混淆
E  Per-query semantic op: 不物化 capability，逐 query 调用（强 baseline）
```
核心问题：`Capability-Late Materialization` 是否具备**超出传统 Predicate Pushdown 的独立价值**？

## 2. 数据与工作负载（Phase 0/1）

| 项 | 值 |
|---|---|
| 域 | `ecom`（电商客服工单文本，源 orders_2026.csv / orders_2025.json / sku_registry.csv）；`finproc`（制度/采购/财务条款文本，源 TRV-001-v3 / PROC-001-v3 / RMA-001 / 财务口径文件） |
| 行规模 | mock 实验 N=10,000 行/域；真实模型实验 M=300 行/域（确定性子关系，遵守 token 预算） |
| Capability 类型 | ① semantic classification（issue_classification / clause_classification）② attribute extraction（amount_extraction_ecom / amount_extraction_fin） |
| 下游算子 | SEM_COUNT / SEM_FILTER / SEM_TOPK（Filter→P/R，Extract→Field-F1，TopK→Recall@K/NDCG，Classification→Macro-F1） |
| Oracle | 由生成规则直接给出（标签/金额与文本同源），与模型输出无关（deterministic oracle） |
| 切分 | 按 source entity 整组切分（ecom→platform，finproc→policy），Build 60% / Dev 20% / Blind 20% |
| payload 校验 | 每行携带 `raw_payload_hash`，进入 CapabilityBuild 前强制校验 |

## 3. 实验 0（v1.2 主实验，mock）：A/B/D/E 五组 × 选择性 sweep

- 规模：N=10,000/域，**600 paired queries**（300/域，40/选择率点 × 7 点 + 20 自然谓词/域），batch_size=1，treatment 顺序逐 query 随机化
- **因果隔离**：EXPERIMENT_INVALID = 0/600；Replay equality = True；survivor payload digest A=B 逐 query 一致；CompilerError=0
- 质量：quality_score A=0.952900 / B=0.952900（Δ=0.000000），answer_correct A=B=0.400000
- 语义工作：10,000 → 3,677 行；tokens 925,971 → 340,614（**↓63.2%**）
- 成本：总成本 ↓63.2%；**Cost/CorrectQuery ↓63.2%**；validation 占 B 总成本 0.326%（预算 ≤10%），占语义节省 0.192%（预算 ≤25%）
- 延迟 P95 比（B/A）= 0.991900；错误归因 = {'COMPILER': 0, 'CAPABILITY': 360, 'EXECUTION': 0, 'SYNTHESIS': 0, 'SOURCE': 0, 'NONE': 240}（**EXECUTION / SYNTHESIS / SOURCE / COMPILER 均为 0，失败全部来自 capability**）

| Family | s 均值 | n | semantic work ↓ | Cost/CorrectQuery ↓ | quality Δ | P95 比 |
|---|---:|---:|---:|---:|---:|---:|
| W1_high | 5.07% | 252 | 94.9% | 94.9% | 0.000000 | 0.099900 |
| W2_medium | 36.15% | 188 | 63.8% | 64.0% | 0.000000 | 0.500200 |
| W3_low | 87.46% | 160 | 12.5% | 12.5% | 0.000000 | 1.000 |

- held-out（Dev+Blind, n=240）：work ↓63.1%，cost ↓63.0%，cost/correct ↓63.0%，quality Δ=0.000000
- 统计：W1 work reduction 均值 0.949317，95% CI [0.944658, 0.953931]，paired permutation p=0.0001，Wilcoxon p=0.0

## 4. 实验 0b（旁路，mock）：TADA-matched / Multi-use / Validation

| 对照 | n | cost ↓ | work ↓ | quality Δ |
|---|---:|---:|---:|---:|
| T1 native TADA（tagging-only） | 300 | 63.2% | 63.2% | 0.000000 |
| T2 matched representation（同 model/prompt/schema/payload） | 600 | 63.2% | 63.2% | 0.000000 |

| 域 | reuse | survivors | BuildOnce+Reuse 摊销/query | RepeatedOperator 摊销/query | ↓（cache ON） | ↓（cache OFF） |
|---|---:|---:|---:|---:|---:|---:|
| ecom | 10 | 531 | 0.015151 | 0.138609 | 89.1% | -8.9% |
| ecom | 50 | 531 | 0.004173 | 0.138609 | 97.0% | -1.0% |
| ecom | 100 | 531 | 0.002800 | 0.138609 | 98.0% | 0.0% |
| finproc | 10 | 533 | 0.011589 | 0.102968 | 88.7% | -8.5% |
| finproc | 50 | 533 | 0.003462 | 0.102968 | 96.6% | -0.6% |
| finproc | 100 | 533 | 0.002446 | 0.102968 | 97.6% | 0.4% |

> Multi-use 收益来自 capability artifact 复用；**关闭 function caching 后优势归零**（0% 左右），说明必须显式声明缓存策略（§10）。

## 5. 实验 1（mock，0 真实 token）：A vs B vs C 全矩阵

- 矩阵：s ∈ [1, 5, 10, 25, 50, 75, 100]%；reuse ∈ [1, 10, 50, 100]%；两种工作负载模式：`PRED_SHARED`（同 cell 共享谓词）/ `PRED_DISTINCT`（各 query 独立谓词）
- cell 总数：112；N=10,000/域

### 5.1 per-cell 摊销（注意：分母不同，仅供看形态）

| 模式 | C/B 最小~最大 | C/A 最小~最大 | C 支配 B | C 支配 A |
|---|---|---|---|:--:|:--:|
| PRED_SHARED | 0.0204 ~ 1.0 | 0.0097 ~ 1.0 | ✅ | ✅ |
| PRED_DISTINCT | 0.0204 ~ 1.0 | 0.0093 ~ 1.0 | ✅ | ✅ |

### 5.2 工作负载级公平口径（**裁决用**；A 的 eager 构建只计一次）

| 工作负载 | cells | A 总成本 | B 总成本 | C 总成本 | **C/B** | **C/A** | 构建行数 A/B/C | 单 cell 平均覆盖 |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| ecom|PRED_SHARED | 28 | 6.618 | 1,178.5 | 52.7 | **0.0447** | **7.9667** | 20,000 / 4,286,263 / 186,367 | 0.3804 |
| ecom|PRED_DISTINCT | 28 | 6.618 | 1,177.6 | 100.0 | **0.0849** | **15.1029** | 20,000 / 4,283,656 / 358,414 | 0.7387 |
| finproc|PRED_SHARED | 28 | 6.011 | 1,046.7 | 46.3 | **0.0443** | **7.7055** | 20,000 / 4,282,110 / 186,356 | 0.3804 |
| finproc|PRED_DISTINCT | 28 | 6.011 | 1,046.3 | 88.4 | **0.0845** | **14.7137** | 20,000 / 4,281,014 / 358,862 | 0.7399 |

> 关键：per-cell 口径下 C/A < 1（看似 C 更优）是**摊销分母不一致**造成的假象；按工作负载级口径，A（一次性构建 2×N 行）远优于 C（为每个 cell 的 survivor 并集付费）。

## 6. 实验 2（真实 GLM-4.5-Air，精简矩阵，双 key + 免费兜底）

- 模型：`glm-4.5-air`，temperature=0，greedy，`thinking=disabled`，batch_size=1；关系规模 M=300 行/域（确定性子关系）
- 矩阵：s ∈ {1,10,50,100}%，reuse ∈ {1,10,50}%，每 cell ≤20 queries，域 ecom+finproc，策略 A/B/C；cell 数 = 24
- **真实消耗 2,834,705 tokens = ¥1.3120**；wall-clock 1,559.3s
- 后端分布：**全部 cell 仅用 GLM-4.5-Air = True**；切换次数 0；限流退避事件 1985；免费兜底 False
- 引擎：v2 / keep-alive(thread-local) / workers=16 / max_qps=25.0
- 质量：GLM A=B=C = 1.0000，mock 同 cell = 0.750000 → **真实模型质量 non-inferior（实际更优）**

| 后端 | 掩码 | calls | prompt_tokens | completion_tokens | 缓存命中 | 费用(元) | 限流次数 |
|---|---|---:|---:|---:|---:|---:|---:|
| glm_key0 | `glm_key0` | 24775 | 2394015 | 440690 | 2319654 | 1.312013 | 1985 |
| glm_key1 | `glm_key1` | 0 | 0 | 0 | 0 | 0.000000 | 0 |
| free_fallback | `free_fallback` | 0 | 0 | 0 | 0 | 0.000000 | 0 |

### 6.1 工作负载级公平口径（真实 token / 人民币）

| 域 | queries | 策略 | 构建行数 | tokens | 成本(元) | 元/query |
|---|---:|---|---:|---:|---:|---:|
| ecom | 156 | A | 600 | 71,244 | 0.113436 | 0.000727 |
| ecom | 156 | B | 9,192 | 1,093,064 | 1.739544 | 0.011151 |
| ecom | 156 | C | 2,856 | 339,487 | 0.539224 | 0.003457 |
| ecom | 156 | **C/B / C/A** | 0.3107 / 4.76 | | | **0.31 / 4.7535** |
| finproc | 156 | A | 600 | 65,921 | 0.107612 | 0.000690 |
| finproc | 156 | B | 8,688 | 953,368 | 1.551202 | 0.009944 |
| finproc | 156 | C | 2,838 | 311,604 | 0.506654 | 0.003248 |
| finproc | 156 | **C/B / C/A** | 0.3267 / 4.73 | | | **0.3266 / 4.7081** |

**合计（312 queries）：A ¥0.221048／B ¥3.290746／C ¥1.045878；C/B = 0.3178，C/A = 4.7315**

- per-cell C/B：均值 0.228342，范围 [0.062200, 0.500200]

## 7. 执行引擎诊断与修复记录（影响可信度，必须随结论阅读）

实测延迟/吞吐（keep-alive，单 key）：

| 并发 | 调用 | 成功 | 429 | 吞吐(QPS) | P50(ms) | P95(ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 5 | 0 | 2.48 | 382.0 | 420.3 |
| 2 | 8 | 8 | 0 | 5.16 | 381.1 | 443.1 |
| 4 | 16 | 16 | 0 | 9.92 | 402.4 | 439.5 |
| 6 | 24 | 24 | 0 | 13.96 | 414.1 | 457.2 |
| 8 | 32 | 32 | 0 | 16.28 | 467.7 | 611.1 |
| 12 | 48 | 48 | 0 | 28.03 | 409.1 | 463.1 |

**v1 引擎缺陷（已定位并修复，证据文件 `key_switch_log_v1_429incident.jsonl`）**：
1. urllib 每请求新建 TLS 连接 → 有效单次延迟 ~1.7s（keep-alive 实测 0.38–0.47s）；
2. **HTTP 429（code 1302「已达到速率限制」）被误判为「额度耗尽」**，客户端因此永久弃用两个 key 并切换到免费兜底 Qwen2.5-7B —— 13:40:09 `KEY_SWITCH 429 glm_key0→glm_key1`、13:40:11 `FALLBACK_ENABLED 429 glm_key1→free_fallback`。这会让后半程数据来自不同 model revision，**破坏固定项，该轮数据被整体作废**；
3. 修复（v2）：线程本地 keep-alive + 令牌桶限流（25 QPS）+ 429 指数退避重试（不切 key）；仅 401/403/余额不足才切 key；每次调用记录实际后端，并输出 `all_cells_glm_only` 标记。修复后单元耗时 70s → 5–36s（约 7×），本轮 0 切换 0 兜底。

## 8. 实验 3（Certificate 判定修复，0 成本）

- 新判据：**PASS ⇔ UpperCI_(1−δ) ≤ ε**，ε=0.02，δ=0.05（Clopper–Pearson 精确单侧上界）；旧判据 = Wilson 上界 ≤ 0.20（等价于容忍 20% 错误率）
- 0 失败情形所需样本量：**n ≥ 149**；n=300 下最多允许 **1 次**错误才能断言总体误差 ≤2%

| Capability | 校准集 | n | errors | 观测误差 | CP 单侧上界95% | 旧 Wilson | groups | 旧→新 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `issue_classification` | legacy | 300 | 8 | 0.026700 | 0.047600 | 0.051700 | 153 | PASS → **FAIL** |
| `issue_classification` | group_stratified | 300 | 0 | 0.000000 | 0.009900 | 0.012600 | 18 | PASS → **PASS** |
| `amount_extraction_ecom` | legacy | 300 | 10 | 0.033300 | 0.055900 | 0.060300 | 153 | PASS → **FAIL** |
| `amount_extraction_ecom` | group_stratified | 300 | 27 | 0.090000 | 0.122000 | 0.127800 | 18 | PASS → **FAIL** |
| `clause_classification` | legacy | 300 | 18 | 0.060000 | 0.087700 | 0.092800 | 12 | PASS → **FAIL** |
| `clause_classification` | group_stratified | 240 | 6 | 0.025000 | 0.048700 | 0.053500 | 12 | PASS → **FAIL** |
| `amount_extraction_fin` | legacy | 300 | 7 | 0.023300 | 0.043400 | 0.047400 | 12 | PASS → **FAIL** |
| `amount_extraction_fin` | group_stratified | 240 | 4 | 0.016700 | 0.037700 | 0.042100 | 12 | PASS → **FAIL** |

- legacy 校准集（与 v1.2 同口径）：新判据 PASS 0/4，旧判据 PASS 4/4
- 分层校准集：新判据 PASS 1/4，旧判据 PASS 4/4
- 结论：① 判据修复：PASS 现在唯一定义为 Clopper–Pearson 单侧上界 ≤ ε(=2%)（δ=5%），取代旧的 Wilson 上界 ≤ 20%。② 旧判据过宽（等价于容忍 20% 错误率），不能作为生产门禁；新判据下 mock capability 全部 FAIL —— 这是正确结论：在 n=300 下若要断言总体误差 ≤2%，最多只允许 1 次错误（见 max_errors_allowed_for_pass）。③ 因此 mock 能力只能用于因果实验（同源误差对 A/B 无偏），不可用于生产部署；生产部署需要更高精度 capability 或更大 n。

## 9. 总裁决与边界判据

必须区分两个基线：

| 基线 | 定义 | C 相对表现 | 判定 |
|---|---|---|---|
| **B = Predicate Pushdown（不持久化）** | 下推过滤，仅对 survivor Build，每 query 重建 | mock C/B = 0.0443–0.0849；真实 GLM C/B = 0.3178 | ✅ **成立** |
| **A = Offline Eager Materialization（QuWARTS 式）** | 整表一次性 Build 并持久化 | mock C/A = 7.7055–15.1029；真实 GLM C/A = 4.7315 | ❌ **不成立（本负载）** |

边界公式（设 k = 互不共享的谓词数，s = 平均选择率，c = eager 构建的 capability 列数，c_row = 单行构建成本）：

```text
C_total ≈ k · s · N · c_row        # 每个谓词组各自构建 survivor 并集
A_total ≈ c · N · c_row            # 整表只构建一次
=> C 优于 A  ⟺  k · s < c
```
- 本轮：k=28/12（cell 数），s 含 100% → `k·s ≫ c` → **A 胜出**；
- 反例（C 胜出）：2 个互斥谓词各 1% 选择率 + 高 reuse → k·s = 0.02 < c=2；
- 与 v1.2 §13 的 QuWARTS 边界一致。

**一句话结论**：
> 相对「谓词下推但不持久化」（B），Capability-Late Materialization 的独立价值成立且显著（真实 GLM 下成本降至 31.8%，mock 降至 4–9%）；但相对「一次性离线 Eager 物化」（A）**并不普遍成立**，边界为 `k·s < c`。可主张的独立点是「**CapabilityBuild 是可持久化、可增量补齐的物理算子**」，而非「Late 普遍优于 Eager」。

## 10. 已排除的替代解释（因果隔离证据）

| 潜在混淆 | 检验 | 结果 |
|---|---|---|
| A 与 B 的 survivor 输入不同（全文档 vs 清洗摘要） | §28 逐 query 比对 survivor payload digest | 完全一致 ✅（D 组进一步逐行回读校验 payload_hash） |
| 执行路径 / reader 造成差异 | Replay 组：A/B 均读同一冻结 capability artifact | quality 与 result_hash 逐 query 相同 ✅ |
| batch composition 影响语义输出 | 强制 batch_size=1 | 全 run 校验通过 ✅ |
| 质量差异来自 capability 误差分布 | 三策略使用同一 capability version / prompt / schema / normalizer | A=B=C 质量逐 query 相同（Δ=0）✅ |
| 成本优势来自缓存假象 | Multi-use 分别报告 caching ON/OFF | caching OFF 时优势归零 → 优势确为 artifact 复用 ✅ |
| 失败被选择性删除 | 失败 query 全部保留，错误归因 100% 为 CAPABILITY | EXECUTION/SYNTHESIS/SOURCE/COMPILER = 0 ✅ |
| 真实模型实验混入其他模型 | 逐调用后端标记 + `all_cells_glm_only` | True（0 切换 0 兜底）✅ |

## 11. 局限与不可外推项

1. **模型后端**：实验 0/1 使用确定性 mock 语义模型（词表+规则），质量非劣具有构造性；实验 2 使用 GLM-4.5-Air（真实），但仅覆盖 M=300/域的精简矩阵，绝对成本不可外推（比例结论由工作负载结构决定）；
2. **延迟**：mock 阶段的延迟为模拟服务时间（tokens × ms/token）+ harness 实测开销；真实阶段的延迟受 429 退避影响（1,985 次退避事件）；
3. **规模**：真实矩阵 s 只取 4 点、reuse 3 点、每 cell ≤20 query（预算约束），统计功效低于 mock 全矩阵；
4. **成本模型**：GLM 价目 输入 0.8 元/M、缓存命中 0.16 元/M、输出 2 元/M（≤200 tokens 档），替换定价会等比缩放结论，不改变 C/B、C/A 的排序结构；
5. **未做（协议 P3/P4）**：ReDD / QuWARTS / Sema / DASE 外部基线、source drift、unseen capability、Natural Language → QueryIR 编译器；
6. **能力可用性**：生产级证书（ε=2%）下 mock capability 3/4 FAIL → 该 capability 不可部署，结论仅针对 Build Position 的因果效应。

## 12. 原始文件索引与校验值

| 文件 | 内容 |
|---|---|
| `exp/runs/main_results.json` | v1.2 主实验全部聚合指标 + 判定 |
| `exp/runs/query_trace.jsonl` | v1.2 逐 query × 策略轨迹（3,600 行，含 validity checks） |
| `exp/runs/side_results.json` | TADA-matched / Multi-use / validation 占比 / W3 安全 |
| `exp/runs/exp1_matrix.json` | 实验1 全矩阵 + 热力图 + 工作负载级口径 |
| `exp/runs/exp1_heatmap.csv` | 实验1 热力图明细（CSV） |
| `exp/runs/exp2_results.json` | 实验2 逐 cell 真实结果（含后端分布） |
| `exp/runs/exp2_workload_totals.json` | 实验2 公平口径总计 |
| `exp/runs/key_usage.json` | 每 key tokens/费用/限流次数 |
| `exp/runs/key_switch_log.jsonl` | 本轮切换/限流事件日志（含 drill） |
| `exp/runs/key_switch_log_v1_429incident.jsonl` | v1 引擎 429 误判事件证据 |
| `exp/runs/rate_probe.json` | 并发/吞吐/延迟实测 |
| `exp/runs/certificates_v3_clopper_pearson.json` | 实验3 证书（新旧判据对比） |
| `exp/runs/repro_pack_v2.json` | 可复现包（版本/快照/定价/命令） |

- 代码 hash：`dd17add6cbf01c92ccca13fceb777fb1`；数据集快照 `7da34d5f450ee09f0f1cba46c5bd4661`；query 快照 `bf648f4b90df77bb28ea2983528bea21`
- 固定项 hash：model `mock-det-v1`/`e96217acdf756b13`；prompt `{"issue_classification": "d86497291a2ae783", "amount_extraction_ecom": "1d353b9345ea0e2e", "clause_classification": "2b5f4f299dac7217", "amount_extraction_fin": "1d353b9345ea0e2e"}`；schema `{"issue_classification": "bfc919f20f0101a4", "amount_extraction_ecom": "bcad0a9f16eed0ec", "clause_classification": "bfc919f20f0101a4", "amount_extraction_fin": "bcad0a9f16eed0ec"}`
- 运行环境：{"platform": "Windows-10-10.0.19045-SP0", "processor": "Intel64 Family 6 Model 151 Stepping 5, GenuineIntel", "python": "3.13.14"}；seed=20260919；定价版本 `mock-2026.09`（mock）/ `bigmodel-2026.09`（GLM）

## 13. 建议下游 AI 分析的问题

1. 在本工作负载结构下，`k·s < c` 的判定是否充分？是否需要加入「谓词并集是否嵌套」「payload 长度分布」等修正项？
2. C/B 的真实模型收益（0.318）与 mock（0.044–0.085）差异巨大，差异来源是 payload/单行成本结构还是工作负载差异？可否用同一口径重算 mock 以获得可比数字？
3. 若要主张「Late-Persistent 独立价值」，需要哪些补充实验才能排除 QuWARTS 式离线物化的支配（k·s < c 的低覆盖工作负载）？
4. 生产级 certificate（ε=2%）下 capability 全部 FAIL，是否应改为「离线认证 + 线上只读」的部署形态？需要多少样本/多少误差才能达到 PASS？
5. 429 退避（1,985 次）对延迟结论的影响有多大？是否需要在低 QPS（≤10）下重跑一遍以给出干净延迟？
