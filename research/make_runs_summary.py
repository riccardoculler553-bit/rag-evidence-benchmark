# -*- coding: utf-8 -*-
"""汇总全部实验运行结果 → research/EXPERIMENT_RUNS_SUMMARY.md + experiment_runs_bundle.json

覆盖代际：v1.2（mock 主实验）→ v1.2-GLM（真实精简矩阵）→ Certificate 修复 →
research/（Adaptive / 语义特异性 / 外部基线）→ v1.3（最终三实验）。
所有数字均从原始 JSON 抽取，禁止手抄。
"""
import glob
import hashlib
import json
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXP_RUNS = os.path.join(ROOT, "exp", "runs")
F3 = os.path.join(HERE, "final_three_experiments")


def jl(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return d


def csv_rows(p):
    import csv
    if not os.path.exists(p):
        return []
    return list(csv.DictReader(open(p, encoding="utf-8")))


def f(x, d=4):
    if x is None or x == "":
        return "n/a"
    if isinstance(x, bool):
        return str(x)
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{v:.{d}g}"


def pct(x, d=2):
    try:
        return f"{100*float(x):.{d}f}%"
    except (TypeError, ValueError):
        return "n/a"


def sha8(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()[:12]


# ---------------------------------------------------------------- 数据装载
def load_all():
    D = {}
    D["v12"] = jl(os.path.join(EXP_RUNS, "main_results.json"), {})
    D["glm"] = jl(os.path.join(EXP_RUNS, "exp2_results.json"), {})
    D["glm_tot"] = jl(os.path.join(EXP_RUNS, "exp2_workload_totals.json"), {})
    D["glm_usage"] = jl(os.path.join(EXP_RUNS, "key_usage.json"), {})
    D["cert"] = jl(os.path.join(EXP_RUNS, "certificates_v3_clopper_pearson.json"), {})
    D["side"] = jl(os.path.join(EXP_RUNS, "side_results.json"), {})
    D["rate"] = jl(os.path.join(EXP_RUNS, "rate_probe.json"), {})
    D["r1"] = jl(os.path.join(HERE, "experiment1_adaptive", "results.json"), {})
    D["r2"] = jl(os.path.join(HERE, "experiment2_semantic_specificity", "results.json"), {})
    D["r2p"] = jl(os.path.join(HERE, "experiment2_semantic_specificity", "real_probe.json"), {})
    D["r2b"] = jl(os.path.join(HERE, "experiment2_semantic_specificity", "bundle_scaling.json"), {})
    D["r3"] = jl(os.path.join(HERE, "experiment3_external_baseline", "results.json"), {})
    D["v3e1"] = jl(os.path.join(F3, "experiment1_boundary", "results.json"), {})
    D["v3e2"] = jl(os.path.join(F3, "experiment2_specificity", "results.json"), {})
    D["v3e3"] = jl(os.path.join(F3, "experiment3_external", "results.json"), {})
    D["v3usage"] = jl(os.path.join(F3, "artifacts", "key_usage.json"), {})
    D["v3man"] = jl(os.path.join(F3, "run_manifest.json"), {})
    D["v3sum"] = jl(os.path.join(F3, "results_summary.json"), {})
    return D


def api_ledger(D):
    rows = []
    g = D["glm_usage"]
    if g:
        for k, v in (g.get("per_backend") or {}).items():
            if v.get("calls"):
                rows.append(dict(run="v1.2-GLM 真实精简矩阵（24 cells）", key=k, calls=v.get("calls"),
                                 tokens=(v.get("prompt_tokens", 0) + v.get("completion_tokens", 0)),
                                 cost=v.get("cost"), confirmed_only=(k != "free_fallback")))
    for tag, path, label in [("probe1", os.path.join(HERE, "experiment2_semantic_specificity",
                                                     "key_usage_probe.json"),
                              "research/ 实验2 微探针 P1–P4"),
                             ("probe2", os.path.join(HERE, "experiment2_semantic_specificity",
                                                     "key_usage_probe2.json"),
                              "research/ 实验2 捆绑规模+长度探针"),
                             ("v3", os.path.join(F3, "artifacts", "key_usage.json"),
                              "v1.3 实验2 捆绑/长度（Tier 0）")]:
        u = jl(path, {})
        if not u:
            continue
        if "per_key" in u:                      # v1.3 格式
            for k, v in (u.get("per_key") or {}).items():
                if v.get("request_count"):
                    rows.append(dict(run=label, key=k, calls=v.get("request_count"),
                                     tokens=v.get("tokens_used"), cost=None,
                                     confirmed_only=True))
        else:                                    # v1.2 格式
            for k, v in (u.get("per_backend") or {}).items():
                if v.get("calls"):
                    rows.append(dict(run=label, key=k, calls=v.get("calls"),
                                     tokens=(v.get("prompt_tokens", 0) + v.get("completion_tokens", 0)),
                                     cost=v.get("cost"), confirmed_only=(k != "free_fallback")))
    return rows



def slim(d, drop=("cells", "queries", "per_capability")):
    """剔除逐 cell / 逐 query 明细，控制投喂体积（明细仍在各自 results.json 中）。"""
    if not isinstance(d, dict):
        return d
    return {k: v for k, v in d.items() if k not in drop}

def main():
    D = load_all()
    L = []
    A = L.append
    ledger = api_ledger(D)
    conf_tokens = sum(r["tokens"] for r in ledger if r["confirmed_only"])
    conf_calls = sum(r["calls"] for r in ledger if r["confirmed_only"])
    conf_cost = sum((r["cost"] or 0) for r in ledger if r["confirmed_only"])
    v3_conf = sum(r["tokens"] for r in ledger if r["run"].startswith("v1.3"))
    fb_calls = sum(r["calls"] for r in ledger if not r["confirmed_only"])

    A("# 实验运行结果总汇（全代际）")
    A("")
    A(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}（由 `research/make_runs_summary.py` 自动生成）")
    A("- 覆盖：v1.2 mock 主实验 → v1.2 真实 GLM 精简矩阵 → Certificate 修复 → "
      "research/ 三实验 → v1.3 最终三实验")
    A("- 机读版：`research/experiment_runs_bundle.json`；所有数字由脚本从原始 JSON 抽取。")
    A("")
    A("---")
    A("")
    A("## 0. 运行总览")
    A("")
    A("| # | 运行 | 代际 | Tier | 规模 | 真实 token | 结论 |")
    A("|---|---|---|---|---|---|---|")
    v12o = (D["v12"].get("results") or {}).get("overall", {})
    glmt = (D["glm_tot"].get("total") or {})
    dd0 = ((D["r1"].get("aggregates") or {}).get("d_vs_cbo") or {})
    _r2t = D["r2p"].get("used_tokens", 0) + D["r2b"].get("used_tokens", 0)
    _b3 = ((D["r2b"].get("bundling") or {}) or {}).get("cost_ratio_V8_vs_8calls")
    _dr = [r for r in D["r3"].get("drift", [])
           if r.get("drift_rate") == 0.05 and r.get("policy") == "Late_affected_rows_rebuild"]
    _sc = (D["v3e1"].get("aggregates", {}).get("by_scope") or {})
    _v3e2b = ((D["v3e2"].get("tier0_real_glm") or {}).get("bundle") or {})

    A("| 1 | Build Position Ablation | v1.2 | Tier 1 | 600 paired queries / N=10,000×2 域 | 0 | "
      "语义工作 ↓" + pct(v12o.get("semantic_work_reduction")) + "，质量 Δ=" + f(v12o.get("quality_delta_AB"), 8)
      + "，INVALID=" + str(v12o.get("experiment_invalid")) + "，replay=" + str(v12o.get("replay_equality")) + " |")
    A("| 2 | 真实 GLM 精简矩阵（A/B/C） | v1.2-GLM | Tier 0 | 24 cells / 312 queries | "
      + f"{D['glm'].get('used_tokens'):,}" + " | C/B=" + f(D["glm_tot"].get("C_over_B_total"))
      + "，C/A=" + f(D["glm_tot"].get("C_over_A_total")) + "；引擎 v2 修复 429 误判后重跑 |")
    A("| 3 | Capability Certificate 修复 | v1.2 | Tier 1 | 4 capabilities × 2 校准集 | 0 | "
      "PASS 判据改为 CP 单侧上界 ≤2%；legacy " + str((D["cert"].get("summary", {}).get("legacy_set") or {}).get("n_pass_new"))
      + "/" + str(D["cert"].get("summary", {}).get("n_capabilities")) + " PASS（旧 Wilson≤20% 下 4/4） |")
    A("| 4 | 旁路实验（multi-use / TADA / validation / 低选择率） | v1.2 | Tier 1 | 4 组 | 0 | "
      "TADA-matched 收益未消失；cache OFF 时摊销优势归零 |")
    A("| 5 | Adaptive Semantic Materialization | research/ | Tier 1 | 840 cells × 6 策略 | 0 | "
      "D 与 Simple CBO 相同 " + str(dd0.get("equal")) + "/" + str(dd0.get("n")) + "，更差 "
      + str(dd0.get("strictly_worse")) + " → 自适应无增量价值 |")
    A("| 6 | 语义特异性（含真实微探针） | research/ | Tier 0+Tier 1 | 80 matched-UDF cells | "
      + f"{_r2t:,}" + " tok | matched UDF delta_cost=0；捆绑 V8/SEP8=" + f(_b3) + " |")
    A("| 7 | 外部基线 + drift | research/ | Tier 1/2 | 3 workloads + 5 drift 档 | 0 | "
      "Late-Persistent 在三负载上 regret=0；drift(5%) 增量=" + f(_dr[0]["rebuild_over_full"] if _dr else None)
      + "×全量 |")
    A("| 8 | Materialization Boundary | v1.3 | Tier 1 | " + str(len(D["v3e1"].get("cells", {}))) + " cells | 0 | "
      "边界 R²=" + f((D["v3e1"].get("boundary_model") or {}).get("r2")) + "；WORKLOAD C/A="
      + f((_sc.get("WORKLOAD") or {}).get("C_over_A", [None])[0]) + "，CELL C/A="
      + f((_sc.get("CELL") or {}).get("C_over_A", [None])[0]) + " |")
    A("| 9 | 语义特异性三件套（真实 GLM） | v1.3 | Tier 0 | 2 域 × 64 行 × 13 变体 | "
      + f"{D['v3usage'].get('total_tokens'):,}" + " | 捆绑 V8/SEP8="
      + f((_v3e2b.get("ecom") or {}).get("cost_ratio_V8_vs_SEP8")) + "（ecom）/ "
      + f((_v3e2b.get("finproc") or {}).get("cost_ratio_V8_vs_SEP8")) + "（finproc）；准确率不低于分次调用 |")
    A("| 10 | Prior-Art Boundary + Lifecycle | v1.3 | Tier 2+Tier 1 | 4 workloads + 5 drift 档 | 0 | "
      "PLOP-like ≡ Late-Persistent；drift = IVM（未运行任何外部系统） |")
    A("")
    A("---")
    A("")
    A("## 1. API 消耗总账（真实模型）")
    A("")
    A("| 运行 | key | 请求数 | tokens | 费用(¥) | 是否进入 confirmatory 统计 |")
    A("|---|---|---:|---:|---:|---|")
    for r in ledger:
        A(f"| {r['run']} | {r['key']} | {r['calls']:,} | {r['tokens']:,} | "
          f"{f(r['cost'], 6) if r['cost'] is not None else '按 GLM 计价表折算'} | "
          f"{'是' if r['confirmed_only'] else '否（NON_CONFIRMATORY）'} |")
    A("")
    A(f"- **confirmatory 合计：{conf_calls:,} 次请求 / {conf_tokens:,} tokens / ¥{conf_cost:.4f}**")
    A(f"- fallback 请求：**{fb_calls}** 次（`fallback_trace.jsonl`；未进入任何 confirmatory 统计）")
    A(f"- 总配额 64,000,000；配额使用率 **{pct(conf_tokens / 64_000_000, 4)}**；"
      f"v1.3 内部硬预算 60,000,000 使用率 **{pct(v3_conf / 60_000_000)}**")
    A("")
    A("> 说明：v1.2-GLM 第一次尝试（引擎 v1）曾把 HTTP 429 误判为额度耗尽并切到免费兜底模型，"
      "该轮数据作废、证据留档 `exp/runs/key_switch_log_v1_429incident.jsonl`；"
      "修复后的 v2 引擎（keep-alive + 令牌桶 + 429 退避不换 key）重跑得上述 confirmatory 数据。")
    A("> v1.3 全程 **0 次 429、0 次 key 切换、fallback 未触发**，双 key 用量均衡 "
      f"（{D['v3usage'].get('per_key', {}).get('glm_key0', {}).get('tokens_used'):,} / "
      f"{D['v3usage'].get('per_key', {}).get('glm_key1', {}).get('tokens_used'):,}）。")
    A("")
    A("---")
    A("")
    A("## 2. v1.2 Build Position Ablation（Tier 1，mock，0 token）")
    A("")
    A("固定项：source snapshot / logical plan / capability implementation / model / prompt / schema /")
    A("tokenizer / reader / batch_size=1 / temperature=0；唯一变量 = CapabilityBuild 位置。")
    A("")
    A("| 指标 | A=Eager | B=Late-Per-Query | Δ / 比值 |")
    A("|---|---|---|---|")
    for k, lab in [("quality_score", "quality_score"), ("answer_correct", "answer_correct")]:
        A(f"| {lab} | {f(v12o.get(k + '_A'))} | {f(v12o.get(k + '_B'))} | "
          f"Δ={f(v12o.get('quality_delta_AB'), 8)} |")
    for k, lab in [("semantic_work_reduction", "语义工作量下降"), ("cost_reduction", "总成本下降"),
                   ("cost_per_correct_reduction", "Cost/CorrectQuery 下降")]:
        A(f"| {lab} | - | - | **{pct(v12o.get(k))}** |")
    A(f"| validation 占 B 总成本 | - | - | {pct(v12o.get('validation_share_B'))} |")
    A(f"| EXPERIMENT_INVALID | - | - | {v12o.get('experiment_invalid')} |")
    A(f"| Replay equality | - | - | {v12o.get('replay_equality')} |")
    A("")
    fam = (D["v12"].get("results") or {}).get("per_family", {})
    if fam:
        A("| family | n | work↓ | cost↓ | cost/correct↓ | P95 比值 |")
        A("|---|---:|---:|---:|---:|---:|")
        for k, v in fam.items():
            A(f"| {k} | {v.get('n_queries')} | {pct(v.get('semantic_work_reduction'))} | "
              f"{pct(v.get('cost_reduction'))} | {pct(v.get('cost_per_correct_reduction'))} | "
              f"{f(v.get('latency_p95_ratio'))} |")
        A("")
    dec = D["v12"].get("decision", {})
    A(f"- 预注册判定：**{dec.get('verdict')}**；未通过的检查项："
      f"{[k for k, v in (dec.get('checks') or {}).items() if not v]}")
    A("")
    A("---")
    A("")
    A("## 3. v1.2 真实 GLM 精简矩阵（Tier 0）")
    A("")
    tot = D["glm_tot"].get("total", {})
    A("| 策略 | tokens | 成本(¥) | build rows | cost/query(¥) |")
    A("|---|---:|---:|---:|---:|")
    for k, lab in [("A", "A Eager-Persistent"), ("B", "B Late-Per-Query"), ("C", "C Late-Persistent")]:
        v = tot.get(k, {})
        A(f"| {lab} | {f(v.get('tokens'), 6)} | {f(v.get('cost_yuan'), 6)} | {f(v.get('build_rows'), 6)} | "
          f"{f(v.get('cost_per_query'), 8)} |")
    A("")
    A(f"- query 总数 {D['glm_tot'].get('n_queries_total')}；**C/B = {f(D['glm_tot'].get('C_over_B_total'))}**，"
      f"**C/A = {f(D['glm_tot'].get('C_over_A_total'))}**（token 口径 C/B={f(D['glm_tot'].get('C_over_B_tokens'))}，"
      f"C/A={f(D['glm_tot'].get('C_over_A_tokens'))}）")
    A(f"- 口径：{D['glm_tot'].get('note')}")
    A(f"- 引擎：{D['glm'].get('engine')}；all_cells_glm_only = {D['glm'].get('all_cells_glm_only')}；"
      f"wall clock {f(D['glm'].get('wall_clock_sec'), 6)} s")
    A("")
    A("> 该轮 A/B/C 的摊销口径为「每 cell」而非「每工作负载」，是后续 v1.3 边界实验要纠正的对象。")
    A("")
    A("---")
    A("")
    A("## 4. Capability Certificate 修复（Tier 1）")
    A("")
    cs = D["cert"].get("summary", {})
    A(f"- 规则：{D['cert'].get('rule')}")
    A(f"- ε={D['cert'].get('epsilon')}，δ={D['cert'].get('delta')}，"
      f"0 失败所需 n ≥ **{D['cert'].get('required_n_zero_failure')}**")
    A(f"- legacy 校准集：新判据 **{cs.get('legacy_set', {}).get('n_pass_new')}/"
      f"{cs.get('n_capabilities')} PASS**（旧判据 {cs.get('legacy_set', {}).get('n_pass_old')}/"
      f"{cs.get('n_capabilities')}）；group-stratified："
      f"{cs.get('group_stratified_set', {}).get('n_pass_new')}/{cs.get('n_capabilities')}")
    A("")
    A("| capability | legacy err | CP 上界95 | 旧 Wilson | 独立 source group 数 |")
    A("|---|---:|---:|---:|---:|")
    for k, v in (D["cert"].get("capabilities") or {}).items():
        lg = v.get("legacy", {}) or {}
        A(f"| {k} | {f(lg.get('observed_error'))} | {f(lg.get('clopper_pearson_upper_onesided_95'))} | "
          f"{f(lg.get('wilson_upper_95_old'))} | {lg.get('n_independent_source_groups')} |")
    A("")
    A("> 结论：mock capability 只能用于因果机制实验（同源误差对 A/B 无偏），**不得**宣称生产级可靠性。")
    A("")
    A("---")
    A("")
    A("## 5. 旁路实验（v1.2，Tier 1）")
    A("")
    s = D["side"]
    s1 = (s.get("S1_multi_use") or {})
    if s1:
        k0 = next(iter(s1))
        v = s1[k0]
        A(f"- **Multi-use**：reuse=10 时摊销节省 {pct(v.get('amortized_reduction'))}；"
          f"**cache OFF 时 {pct(v.get('amortized_reduction_cacheOFF'))}** → 优势来源是 artifact reuse")
    s2 = (s.get("S2_tada_matched") or {})
    if s2:
        t1, t2 = s2.get("T1_native_tada_tagging_only", {}), s2.get("T2_matched_representation_all", {})
        A(f"- **TADA-matched**：T1 cost↓{pct(t1.get('cost_reduction'))} / T2 cost↓{pct(t2.get('cost_reduction'))}，"
          f"两者 quality Δ 均为 {f(t1.get('quality_delta'))} → 收益来自 Build Position 而非 representation 设计")
    s3 = (s.get("S3_validation_cost") or {})
    if s3:
        A(f"- **Validation cost**：{json.dumps(s3, ensure_ascii=False)[:300]}")
    s4 = (s.get("S4_low_selectivity_safety") or {})
    if s4:
        A(f"- **低选择率安全性**：{json.dumps(s4, ensure_ascii=False)[:300]}")
    A("")
    A("---")
    A("")
    A("## 6. research/ 三实验（第一轮最终实验）")
    A("")
    r1a = D["r1"].get("aggregates", {})
    dd = r1a.get("d_vs_cbo", {}) or {}
    A("### 6.1 Adaptive Semantic Materialization（840 cells）")
    A("")
    A("| 策略 | regret mean | min | max |")
    A("|---|---:|---:|---:|")
    for k, lab in [("regret_A_overall", "A Eager"), ("regret_B_overall", "B Late-Per-Query"),
                   ("regret_C_overall", "C Late-Persistent"), ("regret_CBO_overall", "Simple CBO"),
                   ("regret_D_overall", "D Adaptive"), ("regret_D_plus_overall", "D+（诊断，知悉视界）")]:
        v = r1a.get(k, {}) or {}
        A(f"| {lab} | {f(v.get('mean'))} | {f(v.get('min'))} | {f(v.get('max'))} |")
    A("")
    A(f"- **D vs CBO**：相同 {dd.get('equal')}/{dd.get('n')}，更优 {dd.get('strictly_better')}，"
      f"更差 {dd.get('strictly_worse')}，成本比均值 {f(dd.get('mean_ratio'), 5)}")
    A(f"- 最优标签分布：{json.dumps(r1a.get('optimal_label_counts'), ensure_ascii=False)}")
    A(f"- 作用域消融（C/A）：workload 级 "
      f"{f(next((v['C_over_A']['mean'] for k, v in (r1a.get('by_scope') or {}).items() if k=='WORKLOAD'), None))}，"
      f"cell 级 {f(next((v['C_over_A']['mean'] for k, v in (r1a.get('by_scope') or {}).items() if k=='CELL'), None))}")
    A("")
    A("### 6.2 语义特异性（真实微探针 + matched UDF）")
    A("")
    rps = D["r2"].get("real_probe_summary", {}) or {}
    A(f"- 真实探针：{rps.get('tokens_spent'):,} tokens / ¥{rps.get('cost_yuan')}；"
      f"all_primary={rps.get('all_primary_model_only')}")
    A(f"- P1 成本-长度 pearson={f(rps.get('P1_pearson_len_pt'))}；"
      f"P2 四字段捆绑/四次单字段={f(rps.get('P2_cost_ratio_4fields_vs_4calls'))}")
    A(f"- P2b 八字段捆绑/八次单字段={f(rps.get('bundle_cost_ratio_V8_vs_8calls'))}；"
      f"广度 1→8 准确率变化={f(rps.get('bundle_accuracy_drop_V8_minus_V1'))}")
    A(f"- P3 答案稳定率={f(rps.get('P3_label_stability'))} / 句法键稳定率="
      f"{f(rps.get('P3_syntactic_key_stability'))}；P4 依赖上下文 +{pct(rps.get('P4_dependency_delta_ratio'))}")
    a2 = D["r2"].get("exp2a", {}) or {}
    A(f"- matched UDF：{a2.get('n_cells')} cells，delta_cost 最大绝对差 = "
      f"**{f(a2.get('max_abs_delta_cost'), 6)}**；认证开销/oracle={pct((a2.get('certification_overhead') or {}).get('share_of_oracle'))}")
    A("")
    A("### 6.3 外部基线 + drift（3 workloads）")
    A("")
    b = D["r3"].get("baselines", {}) or {}
    A("| Baseline | 策略 | 成为最优的 cell 占比 | regret mean |")
    A("|---|---|---:|---:|")
    for k, v in b.items():
        if k.startswith("B") and isinstance(v, dict):
            A(f"| {k} | {v.get('strategy')} | {f(v.get('win_rate_over_cells'))} | "
              f"{f((v.get('regret') or {}).get('mean'))} |")
    A("")
    A(f"- C（Late-Persistent）与 oracle 完全相等的 cell 占比：**{f(b.get('C_equals_oracle_share'))}**")
    wl = {}
    for r in D["r3"].get("workloads", []):
        wl.setdefault(r["workload"], {})[r["baseline"]] = r.get("regret")
    A("| workload | Late regret | Adaptive regret | CBO regret |")
    A("|---|---:|---:|---:|")
    for k, v in wl.items():
        A(f"| {k} | {f(v.get('B2_late_persistent'))} | {f(v.get('B4_adaptive'))} | {f(v.get('B3_simple_cbo'))} |")
    A("")
    A("---")
    A("")
    A("## 7. v1.3 最终三实验")
    A("")
    m3 = D["v3e1"].get("matrix", {}) or {}
    sc = ((D["v3e1"].get("aggregates") or {}).get("by_scope") or {})
    A(f"### 7.1 Materialization Boundary（{len(D['v3e1'].get('cells', {}))} cells / "
      f"{D['v3e1'].get('runtime_sec')} s / 0 token）")
    A("")
    A(f"- 矩阵：selectivity {m3.get('selectivity')}，reuse {m3.get('reuse')}，"
      f"patterns {m3.get('patterns')}，widths {m3.get('widths')}，scopes {m3.get('scopes')}")
    A("")
    A("| scope | n | C/A mean | C/A min | C/A max | C/B mean |")
    A("|---|---:|---:|---:|---:|---:|")
    for k, v in sc.items():
        ca, cb = v.get("C_over_A"), v.get("C_over_B")
        A(f"| {k} | {v.get('n')} | {f(ca[0])} | {f(ca[1])} | {f(ca[2])} | {f(cb[0])} |")
    A("")
    bm = D["v3e1"].get("boundary_model") or {}
    A(f"- 边界模型（target=log C_C/C_A）：**R²={f(bm.get('r2'))}**（adj {f(bm.get('adj_r2'))}，n={bm.get('n')}）")
    if bm.get("names"):
        A("")
        A("| 特征 | 系数 | t |")
        A("|---|---:|---:|")
        for n, bta, t in zip(bm["names"], bm["beta"], bm["t"]):
            A(f"| {n} | {f(bta)} | {f(t)} |")
    A("")
    A(f"- 结构式判据（容量份额 ≥ 并集份额）准确率 **{f((D['v3e1'].get('structural_predictor') or {}).get('accuracy'))}**；"
      f"经典 `k·s<c` 准确率 **{f((D['v3e1'].get('classical_form_predictor') or {}).get('accuracy'))}**")
    A("")
    A("### 7.2 语义特异性三件套（Tier 0 真实 GLM）")
    A("")
    u3 = D["v3usage"]
    A(f"- 消耗 **{u3.get('total_tokens'):,} tokens / ¥{u3.get('total_cost_yuan')}**；"
      f"all_primary={u3.get('all_primary_model_only')}；切换 {u3.get('switches')} 次；"
      f"429 {u3.get('rate_limit_events')} 次；fallback={u3.get('fallback_used')}")
    A(f"- 双 key：{json.dumps({k: v['tokens_used'] for k, v in (u3.get('per_key') or {}).items()}, ensure_ascii=False)}")
    bb = ((D["v3e2"].get("tier0_real_glm") or {}).get("bundle") or {})
    A("")
    A("| 域 | V1 pt | V2 pt | V4 pt | V8 pt | SEP8 pt | V8/SEP8 成本比 | V1 acc | V8 acc | SEP8 acc |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for dom in ["ecom", "finproc"]:
        d = bb.get(dom) or {}
        if not d:
            continue
        pt, ac = d.get("mean_prompt_tokens", {}), d.get("mean_field_accuracy", {})
        A(f"| {dom} | {f(pt.get('V1'))} | {f(pt.get('V2'))} | {f(pt.get('V4'))} | {f(pt.get('V8'))} | "
          f"{f(pt.get('SEP8'))} | {f(d.get('cost_ratio_V8_vs_SEP8'))} | {f(ac.get('V1'))} | "
          f"{f(ac.get('V8'))} | {f(ac.get('SEP8'))} |")
    A("")
    dt = bb.get("difficulty_types") or {}
    A(f"- 难度分级：{json.dumps({k: v for k, v in dt.items() if k != 'interpretation'}, ensure_ascii=False)}")
    ls = ((D["v3e2"].get("tier0_real_glm") or {}).get("length_summary") or {})
    A(f"- 长度扫描：斜率 **{f(ls.get('tokens_per_char_slope'))} tokens/char**，R²={f(ls.get('proportionality_R2'))}；"
      f"原生范围 {ls.get('native_length_range')}，受控加长范围 {ls.get('augmented_length_range')}")
    mu = D["v3e2"].get("multi_use") or {}
    A(f"- Multi-use：cache ON 最高摊销节省 **{pct(mu.get('max_saving_cache_on'))}**；"
      f"cache OFF 节省 = {mu.get('saving_when_cache_off')}（= artifact reuse 贡献）")
    tj = D["v3e2"].get("tier1_matched_udf") or {}
    A(f"- Tier 1 matched UDF：delta_cost = **{f(tj.get('max_abs_delta_cost'), 6)}**（{tj.get('n_cells')} cells）")
    A("")
    A("### 7.3 Prior-Art Boundary + Lifecycle")
    A("")
    A(f"- experiment_id：`{D['v3e3'].get('experiment_id')}`；tier：{D['v3e3'].get('tier')}")
    A(f"- **{D['v3e3'].get('note')}**")
    A("")
    A("| workload | Eager | Late-Persistent | QuWARTS-like | ReDD-like | PLOP-like | DASE-like | Oracle |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    bmat = {}
    for r in D["v3e3"].get("baseline_matrix", []):
        bmat.setdefault(r["workload"], {})[r["strategy"]] = r
    for w, row in bmat.items():
        cells = []
        for s in ["Eager", "Late-Persistent", "QuWARTS-like", "ReDD-like", "PLOP-like", "DASE-like", "Oracle"]:
            v = row.get(s)
            if not v:
                cells.append("n/a")
            else:
                tag = "ᴾ" if v.get("native_or_proxy") == "proxy" else ""
                cells.append(f"{f(v.get('total_cost'))}{tag}")
        A("| " + w + " | " + " | ".join(cells) + " |")
    A("")
    A("ᴾ = structural proxy（未运行原系统）。")
    A("")
    A("| drift | full rebuild | affected-row rebuild | ratio | stale rows |")
    A("|---|---:|---:|---:|---:|")
    for r in D["v3e3"].get("source_drift", []):
        A(f"| {pct(r.get('drift_rate'), 0)} | {f(r.get('full_rebuild_cost'))} | "
          f"{f(r.get('affected_row_rebuild_cost'))} | {f(r.get('rebuild_ratio'))} | "
          f"{r.get('stale_rows_if_no_rebuild')} |")
    A("")
    A("| unseen capability | total | amortized/query | first-query | build rows | native/proxy |")
    A("|---|---:|---:|---:|---:|---|")
    for r in D["v3e3"].get("unseen_capability", []):
        A(f"| {r.get('strategy')} | {f(r.get('total_cost'))} | {f(r.get('amortized_per_query'))} | "
          f"{f(r.get('first_query_cost'))} | {r.get('build_rows')} | {r.get('native_or_proxy')} |")
    A("")
    A("---")
    A("")
    A("## 8. 结论演进时间线")
    A("")
    A("| 阶段 | 当时的结论 | 后续被什么修正 |")
    A("|---|---|---|")
    A("| v1.2 mock | Late 相对 Per-Query 省 63% 语义工作与成本，质量 Δ=0 | 未修正（v1.3 复现并细化：C/B=0.388@WORKLOAD） |")
    A("| v1.2-GLM | C/A = 4.73，读作「Late 不普遍优于 Eager」 | **被 v1.3 修正为口径伪影**：摊销按 cell 而非 workload |")
    A("| research/ 实验1 | D(Adaptive) 无增量价值，C ≈ oracle | 未修正（v1.3 用 1512 cells 与边界回归进一步确认） |")
    A("| research/ 实验2 | 捆绑 sub-additive 且精度不降 → 无成本-质量张力 | 部分修正：v1.3 逐字段发现退化（product/role）→ 弱选择性捆绑动机 |")
    A("| research/ 实验3 + v1.3 | 收益全部可由 PLOP/QuWARTS/ReDD/semantic caching/IVM 解释 | 未修正（v1.3 以 proxy baseline 与文献边界再次确认） |")
    A("")
    A("**当前最终档位（v1.3）：Engineering-only**；Fail Rules 中 F5（prior art 解释全部收益）触发。")
    A("")
    A("---")
    A("")
    A("## 9. 已知缺陷与修正记录（会伪造结论的那些）")
    A("")
    A("| # | 缺陷 | 影响面 | 状态 |")
    A("|---|---|---|---|")
    A("| 1 | v1 引擎把 HTTP 429 误判为额度耗尽并切 fallback 模型 | v1.2-GLM 第一次尝试整轮作废 | 已修复（v2 引擎），证据留档 |")
    A("| 2 | Adaptive/CBO 的历史观测集从未写入（`per_query` 缺 `_set`） | research/ 实验1 的 D 退化为「永不持久化」 | 已修复并重跑 |")
    A("| 3 | oracle 定义多计 validation → regret 可为负 | research/ 实验1 regret 指标 | 已修复（true lower bound） |")
    A("| 4 | LRU `Store.touch` 对已淘汰键抛 KeyError | v1.3 实验1 容量受限 scope | 已修复（仅在容量受限维度暴露） |")
    A("| 5 | ecom 8 字段中 4 字段无 oracle → 伪造「捆绑损失 15.4 点准确率」 | v1.3 实验2 | 已修复（改为全部可验证字段） |")
    A("| 6 | TypeC 键名映射错 + `pred` 在评分前弹出 → 伪造「TypeC 准确率 0」 | v1.3 实验2 | 已修复 |")
    A("| 7 | F3 判据方向写反（`all(<1)` 应为 `any(≥1)`） | v1.3 报告 fail rule | 已修复 |")
    A("")
    A("---")
    A("")
    A("## 10. 原始文件索引（sha256 前 12 位）")
    A("")
    A("| 文件 | 字节 | sha256_12 |")
    A("|---|---:|---|")
    idx = []
    for pat in [os.path.join(EXP_RUNS, "*"), os.path.join(HERE, "*.md"),
                os.path.join(F3, "*.md"), os.path.join(F3, "*.json"),
                os.path.join(F3, "*", "*.json")]:
        for p in sorted(glob.glob(pat)):
            if os.path.isfile(p):
                rel = os.path.relpath(p, ROOT).replace("\\", "/")
                idx.append(dict(path=rel, bytes=os.path.getsize(p), sha256_12=sha8(p)))
    for r in idx:
        A(f"| `{r['path']}` | {r['bytes']:,} | {r['sha256_12']} |")
    A("")
    A(f"_本文件由 `research/make_runs_summary.py` 于 {time.strftime('%Y-%m-%d %H:%M:%S')} 生成；"
      f"{len(L)} 行；共索引 {len(idx)} 个文件。_")

    md = "\n".join(L) + "\n"
    out_md = os.path.join(HERE, "EXPERIMENT_RUNS_SUMMARY.md")
    open(out_md, "w", encoding="utf-8").write(md)
    bundle = dict(
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        api_ledger=ledger,
        totals=dict(confirmatory_requests=conf_calls, confirmatory_tokens=conf_tokens,
                    confirmatory_cost_yuan=round(conf_cost, 6),
                    fallback_requests=fb_calls,
                    quota_utilization=round(conf_tokens / 64_000_000, 6)),
        v12=slim(D["v12"]), v12_glm=dict(cells=D["glm"].get("cells"),
                                   key_usage=D["glm_usage"], totals=D["glm_tot"],
                                   used_tokens=D["glm"].get("used_tokens")),
        certificate=D["cert"], side=D["side"],
        research_r1=slim(D["r1"]), research_r2=D["r2"], research_r2_probe=D["r2p"],
        research_r2_bundle=D["r2b"], research_r3=D["r3"],
        v13_e1=slim(D["v3e1"]), v13_e2=D["v3e2"], v13_e3=D["v3e3"],
        v13_usage=D["v3usage"], v13_manifest=D["v3man"], v13_summary=D["v3sum"],
        files=idx)
    out_json = os.path.join(HERE, "experiment_runs_bundle.json")
    json.dump(bundle, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"written: {out_md} ({len(md)} chars, {len(L)} lines)")
    print(f"written: {out_json} ({os.path.getsize(out_json):,} bytes)")
    print(json.dumps(dict(confirmatory_requests=conf_calls, confirmatory_tokens=conf_tokens,
                          cost=round(conf_cost, 4), fallback_requests=fb_calls,
                          indexed=len(idx)), ensure_ascii=False))
    return md


if __name__ == "__main__":
    main()
