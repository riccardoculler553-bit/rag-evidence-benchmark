# Execution-Native RAG v1.2 —— Build Position 因果隔离实验报告

**协议**：`Execution_Native_RAG_Foundation_v1.2_实验执行与因果隔离强化版.md`  
**阶段**：Phase 0–2（MVP）+ P1 旁路实验  
**数据集快照**：`7da34d5f450ee09f0f1cba46c5bd4661`　**query 快照**：`bf648f4b90df77bb28ea2983528bea21`  
**模型**：`deterministic-mock-semantic` / `mock-det-v1`（hash `e96217acdf756b13`），temperature=0，greedy，batch_size=1  
**成本模型**：`mock-2026.09`；**种子**：20260919；**并发**：1；**运行时长**：163.43s  
**代码 hash**：`96b5b8938708ca059c06cff00a986a43`（git: `no-git-repo`）

## 0. 一句话结论

> **在当前知识库（星环科技集团 / 电商 + 财务采购两域，N=10,000/域、600 条 paired queries）与确定性 mock 语义模型设定下，Capability-Late Materialization 的独立因果价值成立（判定：支持）**：固定 Source Snapshot / Logical Plan / Capability Implementation / Model / Prompt / Output Schema，仅改变 CapabilityBuild 位置，质量零退化（ΔQuality = 0.000000），但语义工作量下降 63.22%、总成本下降 63.18%、Cost/CorrectQuery 下降 63.16%；成立的边界条件是 **survivor 基数 n ≪ N（高/中选择性）**：W1（s≈5%）语义工作 ↓94.93%、Cost/CorrectQuery ↓94.88%；W2（s≈36%）↓63.84% / 63.95%；W3（s≈87%）收益衰减至 12.51% 且无实质退化（cost ratio 0.8749 ≤ 1.10）。该结论**不外推**到真实 LLM 后端与更高 reuse 的 workload（见 §9 边界条件）。

## 1. 实验设置与因果隔离检查

### 1.1 唯一 treatment

```text
POSITION = EAGER → A (D → B(D) → F → Y)
POSITION = LATE  → B (D → F(D) → B(F(D)) → Y)
```
### 1.2 固定项（§3.1）与自动校验结果（§28）

| 固定项 | 取值 | 校验 |
|---|---|---|
| source_snapshot | `7da34d5f450ee09f0f1cba46c5bd4661` | ✅ A/B 同快照 |
| logical_plan | plan_hash 由 QueryIR 生成 | ✅ 每对 query A/B 相等 |
| capability_implementation | `cap-impl-v1.2`（见 §6 版本历史） | ✅ 同版本 hash |
| model / revision | `deterministic-mock-semantic` / `mock-det-v1` | ✅ 同 model_hash |
| prompt_hash | `{"issue_classification": "d86497291a2ae783", "amount_extraction_ecom": "1d353b9345ea0e2e", "clause_classification": "2b5f4f299dac7217", "amount_extraction_fin": "1d353b9345ea0e2e"}` | ✅ 逐 capability 相等 |
| output_schema_hash | `{"issue_classification": "bfc919f20f0101a4", "amount_extraction_ecom": "bcad0a9f16eed0ec", "clause_classification": "bfc919f20f0101a4", "amount_extraction_fin": "bcad0a9f16eed0ec"}` | ✅ 相等 |
| tokenizer / decoding | `char4-bpe-proxy` / greedy, T=0 | ✅ 相等 |
| reader (synthesis) | hash `0ddafaf59743b6bc` | ✅ 相等 |
| batch_size | 1（§5 强制） | ✅ 全 run = 1 |

- survivor payload hash 一致性：✅ **逐 query 比对通过**（A/B 的 survivor payload digest 完全相同；Eager 未使用全文档、Late 未使用清洗摘要）
- Replay equality（冻结 artifact 下 Quality_A ≈ Quality_B）：✅ True（replay_quality_A=0.9529，replay_quality_B=0.9529）
- **EXPERIMENT_INVALID run 数：0 / 600**（判定进入统计的 run 全部有效）
- CompilerError：**0**（§19：主实验直接使用预定义 Typed QueryIR，未引入 Query Compiler）

### 1.3 数据集与切分

- 规模：**N = 10,000 行/域**（§7），两域共 20,000 行；paired queries **600**（300/域，40/选择率点 × 7 点 + 20 自然谓词查询/域）
- 域：`ecom`（订单/客户服务文本，来源 orders_2026.csv / orders_2025.json / sku_registry.csv）；`finproc`（制度/采购/财务条款文本，来源 TRV-001-v3 / PROC-001-v3 / RMA-001 / 财务文件）
- 每条来源记录 revision 与 payload_hash；进入 CapabilityBuild 的行强制校验 raw_payload_hash
- 切分：**按 source entity 整组切分**（ecom 按 platform、finproc 按 policy），Build 60% / Dev 20% / Blind 20%；主报告同时给出 held-out（Dev+Blind）结果
- Oracle：Phase 0 确定性生成（标签/金额与文本同源），不依赖任何模型输出

## 2. 主结果表（A=Eager / B=Late）

### 2.1 总体与 held-out

| 指标 | A (Eager) | B (Late) | 变化 |
|---|---:|---:|---:|
| answer_correct | 0.4000 | 0.4000 | Δ = 0.000000（质量无退化）|
| operator_correct（全算子） | 0.4000 | 0.4000 | 0 |
| quality_score（任务相关 metric） | 0.9529 | 0.9529 | 0 |
| build_rows（进入 CapabilityBuild 的行数） | 10,000.0 | 3,677.8 | ↓ 63.22% |
| semantic_work（build tokens in+out） | 925,971.0 | 340,614.4 | ↓ **63.22%** |
| llm_calls/query | 10,001.00 | 3,678.76 | 语义调用次数随 n 缩放 |
| total_cost/query（元） | 2.423350 | 0.892770 | ↓ **63.18%** |
| cost_per_correct_query（元） | 6.058374 | 2.231926 | ↓ **63.16%** |
| validation_cost 占总成本 | — | 0.326% | ✅ ≤10% |
| validation_cost / semantic_saving | — | 0.192% | ✅ ≤25% |
| latency P50/P95/P99（模拟服务时间, ms） | 212,513.0 / 216,932.2 / 216,932.2 | 52,104.5 / 215,179.2 / 216,932.2 | P95 ratio 0.9919 |
| measured harness latency P95（ms） | 38.084 | 38.101 | 仅 harness 开销，非服务时间 |

held-out（Dev+Blind, n=240）：quality Δ = 0.000000，semantic work ↓ 63.05%，cost ↓ 63.02%，cost/correct ↓ 63.01%

> **关于 answer_correct 的绝对值（0.40）**：它由任务结构决定而非 Build Position —— SEM_COUNT / SEM_FILTER 要求 survivor 内**逐行**语义判断全对，任一单行 capability 错判即整题错误；本实验的 capability 存在 1.2%–5.3% 的残余误差（见 §6 证书），因此计数/集合型答案的绝对正确率天然受限。因果比较关注的是 **A 与 B 的配对差**：由于两者 capability version、payload、reader 完全相同，答案与质量逐 query 相同（Δ=0），这正是 §3.3/§28 所要求的隔离性质。

### 2.2 Workload Family（§23 预注册阈值）

| Family | s 均值 | n | semantic work ↓ | 阈值 | cost/correct ↓ | 阈值 | quality Δ | P95 比 | 判定 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|
| W1_high | 5.07% | 252 | 94.93% | ≥30%（目标50%） | 94.88% | ≥20% | 0.000000 | 0.100 | ✅ |
| W2_medium | 36.15% | 188 | 63.84% | ≥25% | 63.95% | ≥10% | 0.000000 | 0.500 | ✅ |
| W3_low | 87.46% | 160 | 12.53% | 不要求 | 12.51% | 不要求，cost ratio ≤1.10 | 0.000000 | 1.000 | ✅ |

held-out family：

| Family | n | work ↓ | cost/correct ↓ | quality Δ |
|---|---:|---:|---:|---:|
| W1_high | 100 | 94.89% | 94.85% | 0.000000 |
| W2_medium | 76 | 63.70% | 63.83% | 0.000000 |
| W3_low | 64 | 12.53% | 12.51% | 0.000000 |

### 2.3 两个独立 domain（§24-3 复现性）

| Domain | n | s 均值 | answer_correct A/B | quality A/B | work ↓ | cost ↓ | cost/correct ↓ |
|---|---:|---:|---|---|---:|---:|---:|
| ecom | 300 | 36.79% | 0.2800/0.2800 | 0.9770/0.9770 | 63.21% | 63.18% | 63.16% |
| finproc | 300 | 36.77% | 0.5200/0.5200 | 0.9289/0.9289 | 63.22% | 63.18% | 63.16% |

### 2.4 按算子类型（§18：operator-specific metric）

| 算子 | n | operator_correct A/B | answer_correct A/B | quality（Classification→Macro-F1 / Extract→Field-F1 / TopK→Recall@K） |
|---|---:|---|---|---|
| SEM_COUNT | 160 | 0.2375/0.2375 | 0.2375/0.2375 | 0.9228/0.9228 |
| SEM_FILTER | 140 | 0.1714/0.1714 | 0.1714/0.1714 | 0.9580/0.9580 |
| SEM_TOPK | 300 | 0.5933/0.5933 | 0.5933/0.5933 | 0.9666/0.9666 |

### 2.5 统计检验（§26）

- **W1_high** semantic work reduction：mean 0.9493，95% CI [0.9447, 0.9539]，permutation p=0.0001，Wilcoxon p=0.0
- **W1_high** total cost（A−B，元）：mean 2.2901，95% CI [2.2535, 2.3261]，permutation p=0.0001，Wilcoxon p=0.0
- **W1_high** quality delta：mean 0.000000，95% CI [0.0, 0.0]（等价于 non-inferior，Δ=0）
- **W2_medium** semantic work reduction：mean 0.6384，95% CI [0.6195, 0.6570]，permutation p=0.0001，Wilcoxon p=0.0
- **W2_medium** total cost（A−B，元）：mean 1.5569，95% CI [1.5018, 1.6120]，permutation p=0.0001，Wilcoxon p=0.0
- **W2_medium** quality delta：mean 0.000000，95% CI [0.0, 0.0]（等价于 non-inferior，Δ=0）

> treatment 顺序逐 query 随机化（§26）；A 与 B 不是先整批跑完 A 再跑 B。

## 3. Selectivity Sweep

| s%（实测均值） | n | build_rows A→B | semantic work A→B | cost A→B | quality A/B | P95 A→B (ms) |
|---:|---:|---|---|---|---|---|
| 0.852 | 92 | 10,000 → 85 | 915,550 → 7,915 | 2.398825 → 0.021325 | 0.8464/0.8464 | 216,932 → 2,183 |
| 0.852 | 92 | 10,000 → 85 | 915,550 → 7,915 | 2.398825 → 0.021325 | 0.8464/0.8464 | 216,932 → 2,183 |
| 4.984 | 80 | 10,000 → 498 | 925,971 → 46,206 | 2.421953 → 0.121591 | 0.9719/0.9719 | 216,932 → 10,858 |
| 9.990 | 80 | 10,000 → 999 | 925,971 → 92,532 | 2.422179 → 0.242967 | 0.9714/0.9714 | 216,932 → 21,719 |
| 20.000 | 20 | 10,000 → 2,000 | 1,005,862 → 201,172 | 2.597714 → 0.520028 | 0.9779/0.9779 | 216,932 → 43,971 |
| 24.963 | 80 | 10,000 → 2,496 | 925,971 → 231,226 | 2.422839 → 0.606196 | 0.9716/0.9716 | 216,932 → 54,207 |
| 49.991 | 88 | 10,000 → 4,999 | 918,708 → 459,454 | 2.407727 → 1.205307 | 0.9712/0.9712 | 216,932 → 108,500 |
| 74.925 | 80 | 10,000 → 7,492 | 925,971 → 693,879 | 2.425047 → 1.818128 | 0.9726/0.9726 | 216,932 → 162,634 |
| 100.000 | 80 | 10,000 → 10,000 | 925,971 → 925,971 | 2.426528 → 2.426528 | 0.9732/0.9732 | 216,932 → 216,932 |

```text
`Cost/query`  每行: s% | A(条) | B(条)
s=  0.0%  A ████████████████████████████████████████████     B 
s=  1.0%  A ████████████████████████████████████████████     B 
s=  5.0%  A ████████████████████████████████████████████     B ██
s= 10.0%  A ████████████████████████████████████████████     B ████
s= 20.0%  A ████████████████████████████████████████████████ B █████████
s= 25.0%  A ████████████████████████████████████████████     B ███████████
s= 50.0%  A ████████████████████████████████████████████     B ██████████████████████
s= 75.0%  A ████████████████████████████████████████████     B █████████████████████████████████
s=100.0%  A ████████████████████████████████████████████     B ████████████████████████████████████████████

`Semantic work`  每行: s% | A(条) | B(条)
s=  0.0%  A ███████████████████████████████████████████      B 
s=  1.0%  A ███████████████████████████████████████████      B 
s=  5.0%  A ████████████████████████████████████████████     B ██
s= 10.0%  A ████████████████████████████████████████████     B ████
s= 20.0%  A ████████████████████████████████████████████████ B █████████
s= 25.0%  A ████████████████████████████████████████████     B ███████████
s= 50.0%  A ███████████████████████████████████████████      B █████████████████████
s= 75.0%  A ████████████████████████████████████████████     B █████████████████████████████████
s=100.0%  A ████████████████████████████████████████████     B ████████████████████████████████████████████
```

曲线形状符合协议 §7 的核心预测：`BuildRows_late ≈ n = s·N`，`BuildRows_eager = N`；成本差随 s 单调收敛，s=100% 时 A≡B（Late 无额外开销）。

## 4. Replay 与 Matched Control

### 4.1 Replay（§6，因果 sanity check，不用于成本主结论）

- 冻结 artifact：4 个 capability version，在完整关系（10,000 行）上各构建一次，写入 `capability_artifact.jsonl`
- 判据：`Quality_A,replay ≈ Quality_B,replay` → True（A=0.9529, B=0.9529），且 result_hash 逐 query 相等
- 结论：**不存在执行路径/reader 层混淆**；A/B 差异可归因于 Build Position

### 4.2 TADA-like representation-matched 对照（§11）

| 对照 | n | cost A→B | cost ↓ | work ↓ | quality Δ |
|---|---:|---|---:|---:|---:|
| T1 native TADA（tagging-only，物化为普通表后确定性执行） | 300 | 2.259239 → 0.833428 | 63.16% | 63.22% | 0.000000 |
| T2 matched representation（同 model/prompt/schema/payload） | 600 | 2.423350 → 0.892770 | 63.18% | 63.22% | 0.000000 |

> T2 使用与 T1 完全相同的 model/prompt/schema/row payload，仅改 Build Position；若 T2 仍显示收益，则收益来自 Build Position 而非 representation design。
> **判定：T2 未消除收益 → 收益来自 Build Position，而非 representation design（不触发 F4）。**

## 5. Multi-use / Validation Cost / 低选择性安全（P1）

### 5.1 Multi-use：BuildOnce+Reuse vs RepeatedSemanticOperator（§9/§10）

| 域 | reuse | survivors | AmortizedCost/query（Reuse） | AmortizedCost/query（Repeated） | ↓ | caching OFF 时 ↓ |
|---|---:|---:|---:|---:|---:|---:|
| ecom | 10 | 531 | 0.015151 | 0.138609 | 89.07% | -8.91% |
| ecom | 50 | 531 | 0.004173 | 0.138609 | 96.99% | -0.99% |
| ecom | 100 | 531 | 0.002800 | 0.138609 | 97.98% | 0.00% |
| finproc | 10 | 533 | 0.011589 | 0.102968 | 88.74% | -8.53% |
| finproc | 50 | 533 | 0.003462 | 0.102968 | 96.64% | -0.64% |
| finproc | 100 | 533 | 0.002446 | 0.102968 | 97.62% | 0.35% |

> function caching ON 时 Reuse 显著占优；caching OFF（每次全额计费）时优势消失（≈0）——说明 Multi-use 收益来自 capability artifact 复用，需与 PLOP/Horrila 的 placement 区分时，应同时报告 caching 开关（§10）。

### 5.2 Validation Cost 实际占比（§17）

- validation_cost 均值 0.002942 元，占 B 总成本 **0.326%**（预算 ≤10%）
- validation_cost / semantic_saving = **0.192%**（预算 ≤25%）
- 语义节省绝对值 1.530579 元/query → **验证成本未吞掉主体收益（不触发 F6）**

### 5.3 低选择性安全测试（s>50%）

- n=160，Cost_late/Cost_eager = **0.8749**（限值 1.1）→ 安全；quality Δ = 0.000000；P95 ratio = 1.0000

## 6. Capability Certificate（§15/§16）与验证协议

| Capability | version | metric | observed_error | 95% CI（Wilson） | n | status |
|---|---|---|---:|---|---:|---|
| issue_classification | `509066539dce0cfc` | macro_f1 | 0.0262 | [0.0132, 0.0511] | 300 | **PASS** |
| amount_extraction_ecom | `c26b3ec40742374e` | field_f1 | 0.0169 | [0.0073, 0.0388] | 300 | **PASS** |
| clause_classification | `198f329f5247f991` | macro_f1 | 0.0529 | [0.0327, 0.0843] | 300 | **PASS** |
| amount_extraction_fin | `32b60069094ce65b` | field_f1 | 0.0118 | [0.0044, 0.0316] | 300 | **PASS** |

**Capability 版本迭代与 V2 增量验证记录（§15.2）**：

| 版本 | 改动 | issue_classification 观测误差 | 证书 |
|---|---|---:|---|
| cap-impl-v1.0 | 关键词优先级 物流→退款；含过宽词「发货」 | macro-F1 0.522（err 0.478） | REVIEW |
| cap-impl-v1.1 | 移除「发货」过宽命中 | macro-F1 0.718（err 0.282） | REVIEW |
| cap-impl-v1.2 | 退款优先于物流（业务语义修正）+ 修正数据集类别覆盖缺陷 | macro-F1 0.974（err 0.026） | **PASS** |

> 说明：cap-impl 变更即触发 §15.2 的 V2 增量验证，重建 certificate；主实验结果使用同一固定实现 cap-impl-v1.2（所有 A/B run 的 capability_version 一致）。

## 7. 失败案例分析（§7 交付物）

- B 组（Late）失败 query 总数：**360**，归因分布：{'CAPABILITY': 360, 'EXECUTION': 0, 'SYNTHESIS': 0, 'SOURCE': 0}
- **EXECUTION / SYNTHESIS / SOURCE / COMPILER 失败均为 0** —— 全部失败源自 Capability 误差，且 A/B 完全同源（同一 capability version、同一 payload、同一 reader），因此对 Build Position 结论无偏。

| query | domain | 算子 | s% | 问题（截断） | oracle → answer | error_class | quality |
|---|---|---|---:|---|---|---|---:|
| ECOM-Q0009 | ecom | SEM_COUNT | 1.00 | 在平台=抖音的记录中，语义类别为「other」的共有多少条？ | 28 → 22 | CAPABILITY | 0.835 |
| ECOM-Q0042 | ecom | SEM_TOPK | 5.00 | 在平台=Shopify的记录中，金额最高的前 3 条是哪些？ | ['ECOM-00607', 'ECOM-02473', 'ECOM-02784'] → ['ECOM-08281', 'ECOM-00607', 'ECOM-02473'] | CAPABILITY | 0.983 |
| FINPROC-Q0001 | finproc | SEM_COUNT | 0.97 | 在制度=TRV-001-v2的记录中，语义类别为「条款」的共有多少条？ | 36 → 30 | CAPABILITY | 0.949 |

典型失败模式（可复现）：
1. **计数/集合型算子对单行错误敏感**（SEM_COUNT/SEM_FILTER）：capability 漏判 1 行即导致整题答案错误（operator_correct 于是等于 answer_correct），这是任务结构而非 Build Position 造成。
2. **实体名污染**：客户名如「迅达物流」触发物流关键词 → 分类错误（罕见的 lexical-overlap 失败）。
3. **单位语义陷阱**：文本出现「万元」时抽取器不做单位归一 → 字段错（对应知识库中的真实陷阱，如 `40 万元` vs `400,000 元`）。
4. **多重信号共现**：附录条款同时出现「注：」→ 被误判为脚注（capability 规则缺陷，已记录）。

## 8. 预注册判定（§23/§24 + 用户指令 §5）

| 条件 | 结果 |
|---|:--:|
| W1 质量 non-inferior（Δ ≥ −1%） | ✅ |
| W1 semantic work ↓ ≥30% | ✅ |
| W1 semantic work ↓ ≥50%（目标） | ✅ |
| W1 Cost/CorrectQuery ↓ ≥20% | ✅ |
| W1 P95 不恶化 >10% | ✅ |
| W2 质量 non-inferior | ✅ |
| W2 semantic work ↓ ≥25% | ✅ |
| W2 Cost/CorrectQuery ↓ ≥10% | ✅ |
| W3 质量 non-inferior | ✅ |
| W3 Cost_late ≤ 1.10 × Cost_eager | ✅ |
| Replay 控制组一致 | ✅ |
| 两个独立 domain | ✅ |
| Validation ≤10% total | ✅ |
| Validation ≤25% semantic saving | ✅ |
| Capability certificates 全部 PASS | ✅ |
| 两域 W1/W2 均复现（§24-3） | ✅ |

**最终判定：SUPPORTED**　无需降级

TADA-matched 已在 §4.2 验证（未触发 F4）；Multi-use 与 validation 预算见 §5（未触发 F5/F6）；两域均复现（未触发 F3）；存在显著成本优势（未触发 F1）；质量零退化（未触发 F2）。

## 9. 边界条件与局限（必须随结论一并引用）

1. **模型后端**：主因果实验使用确定性 mock 语义模型（`deterministic-mock-semantic/mock-det-v1`）。其语义能力是脚本化的（词表 + 规则 + 正则），因此质量 non-inferiority 是**构造性成立**的（同 payload + 同模型 ⇒ 同输出）。真实 LLM 下需以同一 prompt/schema/QueryIR 重跑（`RAGX_MODEL_BACKEND=openai ...`）才能主张对外部有效性。
2. **延迟**：报告中的 latency 为**模拟服务时间**（tokens × ms/token 成本模型）叠加实测 harness 开销；mock 后端无网络往返，绝对延迟不具外部可比性，P95 比值有参考意义。
3. **选择率控制**：sweep 谓词 = 自然谓词 AND 确定性 hash 桶（或纯 hash 桶，当目标 n 超过自然谓词基数）。这是**实验控制手段**，不是生产谓词；另有 20 条/域纯自然谓词查询作为 realism check。
4. **数据集为确定性扩样**：行文本由 Phase-0 生成器从世界模型/制度模板渲染（10,000/域），非真实生产日志；oracle 由生成规则给出，可能与真实业务标签分布不同。
5. **成本模型**：`mock-2026.09`（in 0.002/1K、out 0.006/1K、call 0.00002、validation/row 0.0000008 元），结论对「语义工作 → 成本」的映射形式敏感；替换定价需重跑（pricing 记录在 run_manifest）。
6. **未做（协议要求但本轮范围外）**：真实 LLM 后端、ReDD/QuWARTS/Sema/DASE 外部 baseline（Phase 4）、Query Compiler（Phase 5）、source drift / unseen capability（P3）。主实验通过后才允许扩展。

## 10. 交付物清单

| 文件 | 内容 |
|---|---|
| `exp/EXPERIMENT_REPORT.md` | 本报告 |
| `exp/runs/run_manifest.json` | §27 运行清单（git/代码 hash/数据快照/模型/prompt/schema/种子/硬件/定价/缓存策略）|
| `exp/runs/query_trace.jsonl` | §27 逐 query × 策略轨迹（含 validity checks、成本分解、错误归因、result_hash）|
| `exp/runs/capability_artifact.jsonl` | §27 冻结 Capability Artifact 元数据（input_rows_hash/artifact_hash/build_tokens）|
| `exp/runs/main_results.json` | 全部聚合指标 + 判定 |
| `exp/runs/side_results.json` | Multi-use / TADA-matched / validation 占比 / 低选择性安全 |
| `exp/runs/certificates.json` | Capability Certificates（§15.1）|
| `exp/runs/sweep_curve.csv` | Selectivity Sweep 数据 |
| `exp/runs/failure_cases.json` | 失败案例与归因 |
| `exp/runs/repro_pack.json` | 可复现包（版本、hash、命令）|
| `exp/dataset/` | Phase-0 数据集（10,000 行/域）、queries.jsonl、source_registry.json |
