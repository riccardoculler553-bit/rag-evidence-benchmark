# 实验 2 分析：Semantic Capability Specificity & Cost Structure

## 1. Tier 1：GenericExpensiveUDF matched control

- 对照 cell 数：15；total_cost 最大绝对差：**0**
- 认证成本 / oracle：**1.92%**（0 失败所需 n = 149）
- mock capability 质量：{"issue_classification": 0.9704, "amount_extraction_ecom": 0.9833}
- 结论：成本结构严格匹配时，semantic capability 与 generic expensive UDF 的 total_cost 完全相同（delta = 0）→ 收益机制不含语义成分；语义只带来**额外**的认证成本。

## 2. Tier 0：真实 GLM-4.5-Air

- 消耗：**237,580 tokens / ¥0.106683**；all_primary_model_only = **True**；切换 0 次，429 0 次，fallback 触发 False
- 双 key 均衡：{"glm_key0": 119782, "glm_key1": 117798}

### 2a Bundle scaling（V1/V2/V4/V8 vs SEP8）

| 域 | 变体 | prompt tok | completion tok | 字段准确率 | 相对 SEP8 成本 |
|---|---|---:|---:|---:|---:|
| ecom | V1 | 93.203 | 12 | 1 | 0.1295 |
| ecom | V2 | 107.2 | 19.125 | 1 | 0.1556 |
| ecom | V4 | 136.2 | 31.219 | 1 | 0.2062 |
| ecom | V8 | 200.2 | 102.08 | 0.9129 | 0.3722 |
| ecom | SEP8 | 691.62 | 120.48 | 0.8973 | 1 |
| finproc | V1 | 89.688 | 10.641 | 1 | 0.1244 |
| finproc | V2 | 109.69 | 21.234 | 0.9141 | 0.1623 |
| finproc | V4 | 155.69 | 42.25 | 0.8594 | 0.2454 |
| finproc | V8 | 211.69 | 78.766 | 0.8848 | 0.3601 |
| finproc | SEP8 | 706.5 | 100.17 | 0.8496 | 1 |

- 边际 prompt token/字段：{"f2_minus_f1": 14.0, "f4_minus_f2_over2": 14.5, "f8_minus_f4_over4": 16.0, "separate_per_field": 86.45}（ecom） / {"f2_minus_f1": 20.0, "f4_minus_f2_over2": 23.0, "f8_minus_f4_over4": 14.0, "separate_per_field": 88.31}（finproc）
- 各域逐字段准确率：ecom {"label": {"V1": 1, "V2": 1, "V4": 1, "V8": 1}, "amount": {"V1": null, "V2": 1, "V4": 1, "V8": 1}, "currency": {"V1": null, "V2": null, "V4": 1, "V8": 1}, "has_discount": {"V1": null, "V2": null, "V4": 1, "V8": 1}, "has_defect": {"V1": null, "V2": null, "V4": null, "V8": 1}, "product": {"V1": null, "V2": null, "V4": null, "V8": 0.3906}, "order_id": {"V1": null, "V2": null, "V4": null, "V8": 1}, "summary": {"V1": null, "V2": null, "V4": null, "V8": null}}
  finproc {"clause_kind": {"V1": 1, "V2": 0.8438, "V4": 1, "V8": 1}, "governing_value": {"V1": null, "V2": 0.9844, "V4": 0.8438, "V8": 0.875}, "has_exception_pointer": {"V1": null, "V2": null, "V4": 0.5938, "V8": 0.7812}, "unit_is_wan": {"V1": null, "V2": null, "V4": 1, "V8": 1}, "policy_id": {"V1": null, "V2": null, "V4": null, "V8": 1}, "city": {"V1": null, "V2": null, "V4": null, "V8": 1}, "role": {"V1": null, "V2": null, "V4": null, "V8": 0.4219}, "mentions_2026": {"V1": null, "V2": null, "V4": null, "V8": 1}}
- 难度分级：{"TypeA_independent_short_classification": {"finproc_clause_kind_bundled": 1}, "TypeB_numeric_extraction": {"ecom_amount_bundled": 1}, "TypeC_context_dependent": {"finproc_effective_limit_single_call": 0.9844}, "TypeD_inter_field_dependency": {"finproc_governing_value_bundled": 0.9844, "finproc_governing_value_separate": 0.9844}, "interpretation": "TypeC/TypeD 需要先判定条款类型才能解释金额；若其边际 token 成本显著高于 TypeA/B 而准确率不同，则提示 prompt bundling 存在成本-质量权衡。"}

### 2b Payload length sweep（P10–P99）

- 原生长度范围：[43, 79]；受控加长范围：[129, 1111]
- 斜率：**0.65079 tokens/char**，R² = **1.0**

| 分组 | n | 平均字符 | 平均 input tok | 平均 output tok | 准确率 |
|---|---:|---:|---:|---:|---:|
| augmented_P10 | 12 | 136.4 | 142.33 | 8.83 | 1 |
| augmented_P25 | 12 | 225 | 199.08 | 9.42 | 1 |
| augmented_P50 | 12 | 354.2 | 283 | 10.58 | 1 |
| augmented_P75 | 12 | 489.4 | 370.67 | 11.75 | 1 |
| augmented_P90 | 12 | 709.9 | 515.17 | 12.25 | 1 |
| augmented_P99 | 12 | 1102.8 | 770.33 | 13 | 1 |
| native_P10 | 12 | 50.4 | 86.33 | 8.5 | 1 |
| native_P25 | 12 | 53 | 87.08 | 9.42 | 1 |
| native_P50 | 12 | 56.8 | 89.33 | 9.58 | 1 |
| native_P75 | 12 | 59.4 | 90.67 | 9.75 | 1 |
| native_P90 | 12 | 64.9 | 95.17 | 10.58 | 1 |
| native_P99 | 12 | 70.8 | 98.33 | 11.67 | 1 |

### 2c Multi-use（cache ON/OFF）

- 计价口径：cache ON = 一次性构建 + 每次命中付 artifact lookup+storage；cache OFF = 每次重复调用语义算子；两者均含 validation。**cache hit 不计零成本**（§31）。
- 最高摊销节省（cache ON）：**98.91%**；cache OFF 时节省 = 0.0
- **归因**：优势来源是 artifact reuse（cache ON），不是 Late Materialization 的独立算法收益。
