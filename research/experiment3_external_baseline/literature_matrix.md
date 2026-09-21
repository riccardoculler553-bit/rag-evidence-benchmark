# Prior-Art Boundary Matrix（语义能力物化的文献边界）

> 检索时间：2026-09-19。**未运行**上述任何外部系统（沙箱内无可用实现），
> 因此本文**不声明**任何 outperform 结论；本矩阵只做行为维度划分，用于判定 novelty 边界。

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

## 逐系统说明与来源

### QuWARTS (VLDB 2026)
- Query Workload Aware Relational Table Synthesis from Unstructured Text：用历史查询负载指导**离线**结构化抽取，对齐 schema / 保证 joinability / 归一实体，显式权衡结果精度与查询延迟。
- Source: https://www.vldb.org/pvldb/volumes/19/paper/QuWARTS%3A%20Query%20Workload%20Aware%20Relational%20Table%20Synthesis%20from%20Unstructured%20Text

### ReDD (VLDB 2026)
- Relational Deep Dive：动态发现查询专属 schema、填充关系表；SCAPE 提供**统计校准的错误检测与覆盖保证**（错误率 30%→<1%），SCAPE-Hyb 优化精度-人工修正成本。
- Source: https://dl.acm.org/doi/abs/10.14778/3811243.3811256

### PLOP (arXiv 2604.09944)
- Cost-Based Placement of Semantic Operators in Hybrid Query Plans：语义算子的**代价模型 + 位置选择**，并用 pull-up 把语义过滤穿过关系算子、借助函数缓存减少重复 LLM 调用（4.18–4.29× 成本下降，F1≈0.85）。**与本研究最接近的已有工作。**
- Source: https://arxiv.org/html/2604.09944

### Palimpzest (arXiv 2405.14696)
- 声明式 AI 分析 + 代价优化框架，在运行时/费用/质量之间搜索 plan（模型、prompt、推理方式）。
- Source: https://arxiv.org/abs/2405.14696

### Abacus (v1.4.0)
- 在 Palimpzest 之上增加基于代价的物理计划选择。
- Source: https://arxiv.org/html/2604.09944

### LOTUS (arXiv 2407.11418)
- Semantic Operators：声明式语义算子（sem_filter/extract/topk/join/agg），批处理 LLM 操作、模型级联、带统计精度保证的优化（最高 400× 加速）。
- Source: https://github.com/Bastion-AI-Project/lotus/blob/main/README.md

### ThalamusDB
- 面向多模态数据的近似查询处理（AQP）；在 SemBench 上成本下降最高但 F1 仅 ~0.5。
- Source: https://arxiv.org/html/2604.09944

### FlockMTL (v0.7.0)
- 在 DuckDB 中集成 LLM 算子，含 prompt 与 batching 优化。
- Source: https://arxiv.org/html/2604.09944

### Semantic Caching（Redis / Azure Cosmos DB / Upstash / GPTCache）
- 以**语义等价**（embedding 相似度 + 阈值）为缓存键，而非句法精确匹配；含失效与新鲜度策略。**完全覆盖本研究的 P3（句法键过度失效）发现。**
- Source: https://redis.io/blog/what-is-semantic-caching/

### Cardinality Estimation for Semantic Queries (SIGMOD 2026)
- 面向非结构化数据语义查询的基数/代价估计——覆盖「成本模型需条件化」这一改进方向。
- Source: https://dbgroup.cs.tsinghua.edu.cn/ligl/publications.html

### IVM（incremental view maintenance，经典）
- 增量视图维护：只重算受影响部分。**完全覆盖本研究的 source-drift 增量重建结论。**
- Source: https://en.wikipedia.org/wiki/Materialized_view

### 本研究（Ours）
- 本研究的每一项行为都落在一项或多项已有工作之内；唯一新增的是**在单一 fixed-items 因果隔离下对 build position 的受控实测**（含 GLM-4.5-Air 真实计价），以及一项**纠正性负结果**（C/A>1 是物化作用域/缓存容量伪影）。
- Source: 本工作（无外部来源）

## 结论性边界划分

1. **Build position（Eager/Late）× persistence × caching** → PLOP 已用代价模型与 pull-up 完整覆盖，并明确把收益归因于『把语义过滤穿过关系算子 + 函数缓存减少重复 LLM 调用』。
2. **Workload-aware 的离线/在线物化抉择** → QuWARTS 已明确提出并用历史负载指导离线抽取，显式处理 accuracy–latency 权衡；本研究的『Adaptive』是其特例。
3. **能力产物的统计认证** → ReDD 的 SCAPE 提供统计校准的误差检测与覆盖保证；本研究的 Capability Certificate 与其同构。
4. **语义等价缓存键 / 失效** → semantic caching 已是成熟工业+研究方向。
5. **增量重建（source drift）** → 经典 IVM。
6. **成本模型需条件化到过滤后总体** → 语义查询基数/代价估计（SIGMOD 2026）已在处理。
