# NebulaCore Evidence-Native RAG · Research Repository

虚拟企业「星环科技集团 / NebulaCore Holdings」上的 **Evidence-Native RAG 测试知识库**，
以及围绕 **Semantic Capability Materialization** 的三代因果隔离实验。

> 本仓库的立场是**可证伪性优先**：目标不是证明某个架构正确，而是以最小的 token 成本
> 尽可能便宜地证明它是错的。最终档位判定为 **Engineering-only**（见
> [`research/final_three_experiments/FINAL_VERDICT.md`](research/final_three_experiments/FINAL_VERDICT.md)）。

---

## 仓库导航

| 目录 | 内容 | 代际 |
|---|---|---|
| [`gen/`](gen) · [`dataset/`](dataset) | 知识库生成器 + 语料 / 注册表 / 300 题 Gold（确定性可重建） | 阶段 1 |
| [`exp/`](exp) | v1.2 Build Position Ablation（mock + 真实 GLM）、Certificate 修复、旁路实验 | 阶段 2 |
| [`research/`](research) | Adaptive Materialization、语义特异性反证、Prior-Art 边界 | 阶段 3 |
| [`research/final_three_experiments/`](research/final_three_experiments) | v1.3 最终三实验 + 研究生死裁决 | 阶段 4 |

**只读三个文件即可下判断**
1. [`research/final_three_experiments/FINAL_VERDICT.md`](research/final_three_experiments/FINAL_VERDICT.md) —— 逐条回答「什么被证明了 / 什么没有被证明 / 边界在哪」
2. [`research/final_three_experiments/FINAL_REPORT.md`](research/final_three_experiments/FINAL_REPORT.md) —— Tables A–D、Figures 1–3、fail rules、claim 门槛
3. [`research/EXPERIMENT_RUNS_SUMMARY.md`](research/EXPERIMENT_RUNS_SUMMARY.md) —— 跨全部 10 个运行的指标与 API 消耗总账

---

## 科学结论摘要

### 核心问题

> `CapabilityBuild` 是否可以作为一个具有独立经济价值、可持久化、可增量补齐、
> 可由 Operator Demand 驱动的 **Physical Plan Node**？

### 判定：**Engineering-only**（Fail Rule F5 触发）

| 结论 | 状态 | 证据 |
|---|---|---|
| C（Late-Persistent）优于 B（Late-Per-Query） | **Supported** | C/B = 0.388（WORKLOAD，n=504）；log 尺度 95% CI [−0.766, −0.636] |
| C 优于 A（Eager-Persistent） | **Boundary Identified** | 取决于物化作用域：workload 级 C/A = 0.637（≤1 恒成立），cell 级 13.76 |
| `k·s < c` 是否足以刻画边界 | **不足** | 该式准确率 0.632；加入作用域/容量后 0.883（OLS R²=0.86） |
| 收益是否语义特异 | **否** | 成本严格匹配的 generic expensive UDF 对照 `delta_cost = 0`（80 cells） |
| 自适应策略是否有独立价值 | **否** | Adaptive ≡ Simple CBO（609/840 相同），且更差 159 个 cell（均贵 39.6%） |
| 是否可被既有机制解释 | **是** | PLOP（语义算子放置）/ QuWARTS（workload-aware 离线抽取）/ ReDD·SCAPE / semantic caching / IVM |

**一句话**：值得主张的是「CapabilityBuild 是**可持久化、可增量补齐**的物理状态」这一**工程**结论；
「Capability-Late Materialization 是新 RAG 原理」在现有证据下**不成立**。

### 结论演进（重要更正）

v1.2 曾得出 `C/A = 4.73`（真实 GLM）与 `7.7~15.1`（mock），看似 "Late 普遍劣于 Eager"。
v1.3 认定这是**摊销口径伪影**——原口径把 A 的 eager 构建只计一次、C 却按 cell 摊销。
改为统一 workload 级口径后 `C/A = 0.637`（Late 恒不劣于 Eager）；cell 级作用域下仍为 13.76。
**决定性一阶变量是物化作用域/缓存容量，而不是纯粹的语义性质。**

---

## 复现

### 1. 知识库（阶段 1，0 成本）

```bash
python gen/main.py       # 生成全部数据集（确定性，seed=20260919）
python gen/validate.py   # 6000+ 项校验（实体/FK/时间区间/Gold 存在性/计算复算）
```

### 2. 凭据（仅真实模型实验需要）

仓库内**不含任何明文密钥**。二选一：

```bash
# A. 环境变量
export GLM_KEY_0=<主模型 key #1>
export GLM_KEY_1=<主模型 key #2>
export FREE_FALLBACK_API_KEY=<兜底模型 key，可留空>

# B. 本地文件（已 gitignore）
cp exp/_local_credentials.py.example exp/_local_credentials.py   # 然后填入真实值
```

提交前请运行守卫脚本：

```bash
python check_no_secrets.py            # 扫描全仓
python check_no_secrets.py --staged   # 仅扫描暂存区（可接 pre-commit）
```

> 兜底模型默认**关闭**：只有显式提供 key 才启用，避免非主模型静默混入因果统计。

### 3. 实验

```bash
# v1.2 主实验与旁路（mock 部分 0 token）
python exp/run_experiment.py --stage main     # 输出 exp/runs/main_results.json
python exp/run_experiment.py --stage side
python exp/side_experiments.py
python exp/report.py                          # → exp/EXPERIMENT_REPORT.md

# v1.3 最终三实验（实验 1/3 为 0 token；实验 2 使用真实 GLM）
python research/v13_exp1_boundary.py --workers 6    # ~26 min，1512 cells
python research/v13_exp2_specificity.py             # 真实 GLM（Tier 0）
python research/v13_exp3_external.py
python research/v13_report.py                       # → final_three_experiments/

# 汇总（改数据后重跑即同步）
python research/make_runs_summary.py
```

---

## 实验设计要点（因果隔离）

固定项在**所有**策略间严格一致，唯一变化是 strategy：

```text
source snapshot / revision        logical plan / QueryIR
survivor row IDs                  survivor payload hashes   ← 禁止 Eager 用原文、Late 用摘要
model + model revision            prompt / output schema
parser / normalizer / tokenizer   temperature=0 / greedy / batch_size=1
final reader                      cost model / pricing version
```

- **失效门禁**：任一条件不一致 → `EXPERIMENT_INVALID`，该 cell 不进入统计（v1.2 主实验 0/600 失效）
- **429 语义**：HTTP 429 = 速率限制 → **同 key 指数退避重试**，绝不切 key、绝不切 fallback
  （v1.1 曾误判 429 为额度耗尽并静默降级到免费模型，整轮作废；证据留档
  `exp/runs/key_switch_log_v1_429incident.jsonl`）
- **证据分层**：Tier 0 真实 GLM confirmatory / Tier 1 deterministic mock mechanism /
  Tier 2 structural prior-art proxy —— 三者不混为同一种证据

---

## API 消耗总账

| 项目 | 数值 |
|---|---|
| confirmatory 请求数 | 27,327 |
| confirmatory tokens | **3,180,646** |
| 费用 | **¥1.3896** |
| 配额使用率 | 4.97% |
| fallback 请求 | **0** |
| v1.3 双 key 均衡 | 119,782 / 117,798 tokens（0 次 429、0 次切换） |
| v1.3 内部硬预算使用率 | 0.40% |

实验 1/3（mock 与结构代理）**0 token** —— 先用最便宜的手段尝试推翻假设。

---

## 知识库侧（阶段 1）详情

数据集不是为了测普通 QA 准确率，而是为了系统性攻击
`Source → EvidenceRef → EvidenceState → Warrant → Claim → Answer` 全链路。

```text
dataset/
├── knowledge/            # 107 个文件：policies / historical / finance / procurement / hr /
│                         #   sales / ecommerce / legal / technology / projects / audit /
│                         #   faq / conflicts / structured / attachments
├── registry/             # entities / relationships / documents / revisions / permissions / tables (.jsonl)
├── questions/questions.jsonl
├── gold/gold.jsonl       # 每题完整 Gold（见下）
├── logs/gold_generation_trace.jsonl   # 真值生成日志：选了哪些 Source、为什么、谁是 distractor
├── validation/           # validation_report.json + fixtures.json
└── REPORT.md             # 类型/难度/动作/能力签名/攻击目标 分布统计
```

| 指标 | 数量 |
|---|---|
| 注册文档 | 79（知识库文件 107） |
| 结构化表 | 10（CSV/JSON/SQL/YAML） |
| 实体 / 关系 | 587 / 1,666 |
| 问题 = Gold 记录 | 300（多标签） |
| 校验断言 | 6,122（全部通过） |

### 覆盖的攻击面

- **Temporal**：v1/v2/v3 版本演化、published ≠ effective、As-of 快照、事件时间 ≠ 记录时间
- **Scope / Role / Region 外推**：VP、海外、实习生不适用 → UNKNOWN
- **例外与脚注**：展会 +20%、客户指定酒店、供应商陪同 80%、紧急当天申请、NDA 豁免
- **冲突**：真冲突、假冲突（版本更替）、权威冲突（FAQ < 正式制度）、区域越权通知无效
- **否定 / 穷举**：ABSENT vs UNKNOWN、免审批 4 项（1 项只在附录 C，almost-complete）
- **数值陷阱**：万元表头 800、EUR/USD、含税/不含税、Top3 平手
- **多跳**：S001 四源 Join、五跳员工→项目→区域→预算、API→服务→库→字段、订单→VIP→数字商品例外
- **证据增量**：staged 收窄（LCE(E3) ⊂ LCE(E2)）、超旁消解、新冲突、权威裁决
- **Claim Force / 引用攻击**：scope overreach、temporal leak、numeric force violation
- **权限**：Evidence 层 ACL、ACCESS_DENIED、权限撤销与缓存失效
- **解析器诚实性**：OCR PARTIAL 文档 → 不得编造
- **红鲱鱼 / 实体解析**：外派补贴 vs 差旅标准、近似 SKU、近邻供应商主体

### Gold 记录 Schema（每题）

```jsonc
{
  "question_id": "Q-0038",
  "question": "...",
  "question_type": ["exception", "table", "derivation"],
  "difficulty": "L4",
  "required_sources": ["TRV-001-v3"],
  "gold_evidence_refs": ["TRV-001-v3#tbl-a", "TRV-001-v3#fn-2"],  // doc_id#anchor
  "required_dependencies": ["table_header", "footnote", "arithmetic"],
  "gold_claims": [{"claim": "...", "status": "SUPPORTED", "scope": "CN",
                   "effective_at": "...", "claim_force": "exact|approx|upper_bound|usually"}],
  "warrant_requirements": {"support","coverage","scope","temporal","authority","conflict"},
  "expected_action": "ANSWER|PARTIAL|UNKNOWN|ABSTAIN|CLARIFY|CONFLICT|ACCESS_DENIED|OUT_OF_SCOPE|ABSENT",
  "acceptable_answer": "...",
  "must_not_claim": ["..."],
  "acceptable_evidence_sets": [],
  "evidence_stages": [],
  "evidence_order_variants": [],
  "reasoning_signature": [],
  "failure_target": []
}
```

---

## 工程注意事项（踩过的坑）

1. **Windows 后台长任务 CPU 占用异常**：单进程跑 840/1512 cells 时出现「20 分钟仅 88 秒 CPU」，
   改用 `ProcessPoolExecutor` 单元级并行后 1512 cells 约 26 分钟。
2. **跨进程确定性**：禁用内置 `hash()`（受 `PYTHONHASHSEED` 影响），一律用 sha256 派生 salt。
3. **LRU 存储的 `touch` 必须容错**：键可能已被淘汰；此缺陷仅在容量受限时暴露。
4. **先验证度量再跑正式实验**：曾出现「ecom 8 字段中 4 个字段缺 oracle」与「TypeC 键名映射错」
   导致的伪结论（假的「捆绑损失 15.4 点准确率」、假的「准确率 0」）。
5. **oracle 定义必须严格是下界**：早期多计 validation 成本，导致 regret 可为负。
6. **不要用掩码泄露密钥**：`k[:6]…k[-4:]` 会把前缀/后缀写进日志，已改为不可逆标签。

---

## 许可与使用

研究与评测用途。虚拟企业、人员、订单、合同、财务数据**全部为合成数据**，
与现实组织无关。未运行任何外部系统（QuWARTS / ReDD / LOTUS / TADA / PLOP 等），
仓库中所有 `*-like` 基线均为**结构代理**，因此**不构成任何 outperform 声明**。
