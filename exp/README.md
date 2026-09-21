# exp/ —— v1.2 Build Position 因果隔离实验（MVP, Phase 0–2 + P1）

严格按 `Execution_Native_RAG_Foundation_v1.2_实验执行与因果隔离强化版.md` 实现的最小可验证原型。
只验证一个可证伪命题：**在 Source / Logical Plan / Capability Implementation / Model / Prompt /
Output Schema 全部固定的前提下，仅改变 `CapabilityBuild` 的位置（EAGER vs LATE），
当 n ≪ N 时能否在质量 non-inferior 的同时显著降低语义工作与 Cost/CorrectQuery。**

## 一键复现

```bash
python exp/run_experiment.py --stage main   # 主因果实验（A–E 五组 × Sweep × Replay）
python exp/run_experiment.py --stage side   # 旁路：Multi-use / TADA-matched / validation / W3 安全
python exp/report.py                        # 生成 EXPERIMENT_REPORT.md 与 repro_pack.json

# 用真实模型重跑（prompt/schema/QueryIR 完全不变）
RAGX_MODEL_BACKEND=openai OPENAI_BASE_URL=... OPENAI_API_KEY=... OPENAI_MODEL=... \
  python exp/run_experiment.py --stage main
```

## 模块

| 文件 | 职责 |
|---|---|
| `config.py` | 固定项、成本/延迟模型、预注册阈值、种子、规模（N=10,000/域、600 paired queries） |
| `source_plane.py` | Phase 0 确定性 Oracle 数据集 + Source Plane（list/metadata/read/revision/payload_hash） |
| `operators.py` | FILTER/PROJECT/JOIN/GROUP/AGG/ORDER/TOPK + Logical Plan hash + Synthesis |
| `llm.py` | 模型适配（`deterministic-mock-semantic` 默认；OpenAI 兼容后端可选），tokenizer 代理 |
| `capability.py` | 2 类 Capability（semantic classification / attribute extraction）、Artifact、Certificate、operator-specific metric |
| `workload.py` | Typed QueryIR 生成（含 deterministic oracle、按实体整组切分 60/20/20） |
| `harness.py` | A–E 五组策略、§28 有效性检查、全指标 trace |
| `stats.py` | paired bootstrap 95% CI、permutation、Wilcoxon |
| `run_experiment.py` | 主实验编排 + 聚合 + 预注册判定 |
| `side_experiments.py` | Multi-use（reuse 10/50/100，caching ON/OFF）、TADA-matched T1/T2、validation 占比、低选择性安全 |
| `report.py` | 实验报告与可复现包 |

## 五个控制组（§4）

| 组 | 实现 |
|---|---|
| A Eager | 先对全部 N 行 `CapabilityBuild`，再执行上游 FILTER |
| B Late | 先执行上游 FILTER（n 行），再对 survivor 做 `CapabilityBuild` |
| C Replay | A/B 均只读同一冻结 Capability Artifact（因果 sanity check） |
| D Late + exact survivor payload | 逐行回读并按 payload_hash 校验，排除"输入更干净"混淆 |
| E Per-query semantic operator | 不物化 Capability，逐查询调用，无跨查询复用（强 baseline） |

## 输出

`exp/runs/`：`run_manifest.json`、`query_trace.jsonl`、`capability_artifact.jsonl`、
`main_results.json`、`side_results.json`、`certificates.json`、`sweep_curve.csv`、
`failure_cases.json`、`repro_pack.json`；报告：`exp/EXPERIMENT_REPORT.md`。

## 纪律（§30）

未引入 Graph / Neural Memory / RL / Agent Planner / 自动 View / 多模型 ensemble / 复杂 Claim Validator；
主实验使用预定义 Typed QueryIR（CompilerError ≡ 0）；batch_size 固定为 1；不做事后阈值调整或删除失败 query。
