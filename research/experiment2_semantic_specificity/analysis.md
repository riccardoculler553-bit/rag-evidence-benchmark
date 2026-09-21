# 实验 2 分析：Semantic-Specificity Isolation

## 0. 真实 GLM-4.5-Air 探针（辅助，非因果对照）

- 总消耗：**108,361 tokens / ¥0.077576**；全部来自主模型：**True**
- P1 成本-长度相关（pearson）：**0.9533**；label 准确率 1
- P2 四字段捆绑 / 四次单字段调用 成本比：**0.4752**；准确率 {'V1_label': 1, 'V2_label': 1, 'V4_label': 1, 'V2_amount': 1, 'V4_amount': 1, 'V4_parse_ok': 1}
- P2b 八字段捆绑 / 八次单字段调用 成本比：**0.2785**；广度 1→8 的总体字段准确率变化：**0**
- P3 语义保持扰动：答案稳定性 **1**，句法 payload_hash 稳定性 **0**
- P4 依赖上下文成本增量：**27.83%** input tokens
- 输入长度斜率（probe2）：**0.6451 tokens/char**

## 1. 2A：成本严格匹配的 generic expensive UDF 对照

- 对照 cell 数：**80**；total_cost 最大绝对差：**0**
- semantic capability 实测质量（mock）：{'issue_classification': 0.97, 'amount_extraction_ecom': 0.9857}；UDF 质量 = 1.0
- 认证成本（CP 上界 ≤2% 所需 149 行 × 2 能力）/ oracle 成本 = **5.90%**
- 长度偏斜工作负载的实测长度比：**1.021**（本语料 payload 长度过于均一 → 该机制在本语料上不可检验；只能给出机制性上界）

> 结论：**收益机制与 generic expensive UDF 完全同构**（delta_cost 严格为 0）；
> 语义能力带来的差异是**额外的成本项**（认证/失效），而不是额外的节省。

## 2. 2B：跨算子复用（fan-out）

- 共享工件 / 独立调用 成本比：**0.3334** （cells=12）
- generic UDF 结构匹配对照：**True（同一算术，比率完全相同）**
- 需求异质性（更细粒度算子）→ 泛化物化因子 1.52 （实测自 V4/V1 prompt tokens）

> 结论：fan-out 收益 = 『materialize once, read many times』，属 CSE / materialized view，不含语义特异成分。

## 3. 2C：能力依赖 / 部分物化

- 依赖上下文成本增量（实测）：**27.83%**
- 最优策略分布：{'FULL': 3, 'PARTIAL': 9}；partial/full 均值：**0.3733**

> 结论：依赖感知部分物化有效，但由『构建次数的集合运算 + 依赖闭包』决定，对应 view dependency graph 与 IVM。
