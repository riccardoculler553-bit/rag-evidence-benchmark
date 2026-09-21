# research/ — Semantic Capability Materialization 最终研究包

> 目的：**尽可能便宜地证明当前方向是错的**。三个决定性实验 + prior-art 边界。
> 生成时间：2026-09-19 16:18:18

## 目录

```text
research/
├── README.md                     ← 本文件
├── FINAL_VERDICT.md              ← 最终四档裁决（NO / POTENTIAL / YES / STRONG）
├── common.py                     ← 共享内核（mock 成本模型 / 策略 / oracle / 存储）
├── exp1_adaptive.py              → experiment1_adaptive/
├── exp2_specificity.py           → experiment2_semantic_specificity/
├── exp2_real_probe.py            ← 真实 GLM 微探针（P1–P4）
├── exp2_bundle_scaling.py        ← 真实 GLM 捆绑规模-精度曲线
├── exp3_external.py              → experiment3_external_baseline/
├── make_final.py                 ← 本包生成器（数字全部程序化抽取）
├── experiment1_adaptive/         config.json results.json workload.csv traces.jsonl
│                                 cost_curve.csv scope_ablation.csv analysis.md
├── experiment2_semantic_specificity/ config.json results.json semantic_vs_udf.csv
│                                 capability_dependency.csv cross_operator_reuse.csv
│                                 real_probe.json bundle_scaling.json analysis.md
├── experiment3_external_baseline/ config.json results.json literature_matrix.md
│                                 baseline_results.json workload_results.csv
│                                 source_drift.csv analysis.md
├── artifacts/{raw_traces,model_calls,certificates,hashes}
└── reproducibility/{environment.json,git_commit.txt,dataset_hash.txt,run_command.txt}
```

## 复现

```bash
python research/exp1_adaptive.py --tag full        # 0 token（deterministic mock）
python research/exp2_specificity.py                # 0 token
python research/exp3_external.py                   # 0 token
python research/exp2_real_probe.py --rows 24       # GLM-4.5-Air，约 30k tokens
python research/exp2_bundle_scaling.py --rows 40   # GLM-4.5-Air，约 79k tokens
python research/make_final.py                      # 重新生成本包
```

## 预算与实际消耗

- 真实模型总消耗：**108,361 tokens**（计划上限 800k，总配额 64M）
- 实验 1/2(mock)/3 全部 **0 token**（deterministic mock，符合『先做最便宜的反证』的纪律）
- 全程 `all_primary_model_only = True`（无 fallback 混入），429 一律退避重试、不换 key

## 一句话结论

见 `FINAL_VERDICT.md` §0：**NO（Tier 0）** —— 现有证据下该方向不构成独立研究贡献；
其可交付价值是受控负结果 + 可复用评测夹具 + 成本标定数据。
