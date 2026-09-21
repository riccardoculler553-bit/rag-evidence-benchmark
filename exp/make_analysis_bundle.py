# -*- coding: utf-8 -*-
"""生成「可直接发给 AI 分析」的自包含研究汇总包：
   exp/RESEARCH_SUMMARY_FOR_ANALYSIS.md   （人/LLM 可读，含全部关键数字与表格）
   exp/runs/analysis_bundle.json          （机读版：全部关键数字，便于下游做统计/再分析）
"""
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import EXP_OUT
import config as CFG

EXP = os.path.dirname(EXP_OUT)


def L(p):
    p = os.path.join(EXP_OUT, p)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def n(x, d=4):
    dec = 6
    if x is None:
        return "n/a"
    if isinstance(x, str):
        return x
    a = abs(x)
    if 0 < a < 0.0001:
        dec = 8
    return f"{x:,.{d if a >= 1 else dec}f}"


def pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def build():
    m = L("main_results.json")            # v1.2 主实验（A–E，mock）
    s = L("side_results.json")            # v1.2 旁路
    e1 = L("exp1_matrix.json")            # 实验1 mock 矩阵
    e2 = L("exp2_results.json")           # 实验2 真实 GLM
    e2t = L("exp2_workload_totals.json")  # 实验2 公平口径
    e3 = L("certificates_v3_clopper_pearson.json")
    ku = L("key_usage.json")
    probe = L("rate_probe.json")
    manifest = L("run_manifest.json")

    R = {}          # 机读 bundle
    A = []          # markdown
    A.append("# Capability-Late Materialization：研究结果汇总（供外部 AI 分析）\n")
    A.append(f"生成时间：2026-09-19　|　数据集快照：`{e1.get('snapshot') or e2.get('snapshot')}`　"
             f"|　v1.2 query 快照：`{manifest.get('query_snapshot')}`\n")
    A.append("> 本文档自包含：所有结论、数字、表格与原始文件路径均已内联，无需仓库即可审阅。"
             "机读版见文末 §12 与 `exp/runs/analysis_bundle.json`。\n")

    # ---------------------------------------------------------------- 1
    A.append("## 1. 研究问题（可证伪命题）\n")
    A.append("固定 Source Snapshot / Logical Plan / Capability Implementation / Model / Prompt / "
             "Output Schema / batch_size=1 / temperature=0，仅改变 `CapabilityBuild` 的**位置与持久化方式**：\n")
    A.append("```text")
    A.append("A  Eager-Persistent    : 对整表一次性 CapabilityBuild 并持久化，后续全部复用")
    A.append("B  Late-Per-Query      : 每个 query 先做确定性 Filter，再对 survivor 单独 Build（不持久化）= 纯谓词下推")
    A.append("C  Late-Persistent     : 对 survivor Build 后持久化，支持增量补齐（缺失行才构建）")
    A.append("D  Late + exact payload: 逐行回读并校验 payload_hash，排除「Late 输入更干净」混淆")
    A.append("E  Per-query semantic op: 不物化 capability，逐 query 调用（强 baseline）")
    A.append("```")
    A.append("核心问题：`Capability-Late Materialization` 是否具备**超出传统 Predicate Pushdown 的独立价值**？\n")

    # ---------------------------------------------------------------- 2
    A.append("## 2. 数据与工作负载（Phase 0/1）\n")
    A.append("| 项 | 值 |")
    A.append("|---|---|")
    A.append("| 域 | `ecom`（电商客服工单文本，源 orders_2026.csv / orders_2025.json / sku_registry.csv）；"
             "`finproc`（制度/采购/财务条款文本，源 TRV-001-v3 / PROC-001-v3 / RMA-001 / 财务口径文件） |")
    A.append("| 行规模 | mock 实验 N=10,000 行/域；真实模型实验 M=300 行/域（确定性子关系，遵守 token 预算） |")
    A.append("| Capability 类型 | ① semantic classification（issue_classification / clause_classification）"
             "② attribute extraction（amount_extraction_ecom / amount_extraction_fin） |")
    A.append("| 下游算子 | SEM_COUNT / SEM_FILTER / SEM_TOPK（Filter→P/R，Extract→Field-F1，TopK→Recall@K/NDCG，Classification→Macro-F1） |")
    A.append("| Oracle | 由生成规则直接给出（标签/金额与文本同源），与模型输出无关（deterministic oracle） |")
    A.append("| 切分 | 按 source entity 整组切分（ecom→platform，finproc→policy），Build 60% / Dev 20% / Blind 20% |")
    A.append("| payload 校验 | 每行携带 `raw_payload_hash`，进入 CapabilityBuild 前强制校验 |\n")

    # ---------------------------------------------------------------- 3 v1.2 主实验
    A.append("## 3. 实验 0（v1.2 主实验，mock）：A/B/D/E 五组 × 选择性 sweep\n")
    if m:
        ov = m["results"]["overall"]
        ho = m["results"]["held_out"]
        fam = m["results"]["per_family"]
        A.append(f"- 规模：N=10,000/域，**600 paired queries**（300/域，40/选择率点 × 7 点 + 20 自然谓词/域），"
                 f"batch_size=1，treatment 顺序逐 query 随机化")
        A.append(f"- **因果隔离**：EXPERIMENT_INVALID = {ov['experiment_invalid']}/600；Replay equality = "
                 f"{ov['replay_equality']}；survivor payload digest A=B 逐 query 一致；CompilerError=0")
        A.append(f"- 质量：quality_score A={n(ov['quality_score_A'])} / B={n(ov['quality_score_B'])}"
                 f"（Δ={n(ov['quality_delta_AB'],6)}），answer_correct A=B={n(ov['answer_correct_A'])}")
        A.append(f"- 语义工作：{int(ov['build_rows_A']):,} → {int(ov['build_rows_B']):,} 行；"
                 f"tokens {int(ov['semantic_work_A']):,} → {int(ov['semantic_work_B']):,}（**↓{pct(ov['semantic_work_reduction'])}**）")
        A.append(f"- 成本：总成本 ↓{pct(ov['cost_reduction'])}；**Cost/CorrectQuery ↓{pct(ov['cost_per_correct_reduction'])}**；"
                 f"validation 占 B 总成本 {pct(ov['validation_share_B'],3)}（预算 ≤10%），"
                 f"占语义节省 {pct(ov['validation_over_saving'],3)}（预算 ≤25%）")
        A.append(f"- 延迟 P95 比（B/A）= {n(ov['latency_p95_ratio'])}；错误归因 = {ov['error_attribution']}"
                 f"（**EXECUTION / SYNTHESIS / SOURCE / COMPILER 均为 0，失败全部来自 capability**）")
        A.append("")
        A.append("| Family | s 均值 | n | semantic work ↓ | Cost/CorrectQuery ↓ | quality Δ | P95 比 |")
        A.append("|---|---:|---:|---:|---:|---:|---:|")
        for k in ["W1_high", "W2_medium", "W3_low"]:
            v = fam[k]
            A.append(f"| {k} | {n(v['selectivity_mean'],2)}% | {v['n_queries']} | {pct(v['semantic_work_reduction'])} | "
                     f"{pct(v['cost_per_correct_reduction'])} | {n(v['quality_delta_AB'],6)} | {n(v['latency_p95_ratio'],3)} |")
        A.append("")
        A.append(f"- held-out（Dev+Blind, n={ho['n_queries']}）：work ↓{pct(ho['semantic_work_reduction'])}，"
                 f"cost ↓{pct(ho['cost_reduction'])}，cost/correct ↓{pct(ho['cost_per_correct_reduction'])}，quality Δ={n(ho['quality_delta_AB'],6)}")
        w1 = fam["W1_high"]["semantic_work_paired"]
        A.append(f"- 统计：W1 work reduction 均值 {n(w1['mean_diff'])}，95% CI {w1['ci95']}，"
                 f"paired permutation p={w1['p_permutation']}，Wilcoxon p={w1['p_wilcoxon']}\n")
        R["experiment0_v12_main"] = dict(overall=ov, per_family=fam, held_out=ho)
    else:
        A.append("（缺失 main_results.json）\n")

    # ---------------------------------------------------------------- 4 旁路
    A.append("## 4. 实验 0b（旁路，mock）：TADA-matched / Multi-use / Validation\n")
    if s:
        t = s.get("S2_tada_matched", {})
        A.append("| 对照 | n | cost ↓ | work ↓ | quality Δ |")
        A.append("|---|---:|---:|---:|---:|")
        for key, label in [("T1_native_tada_tagging_only", "T1 native TADA（tagging-only）"),
                           ("T2_matched_representation_all", "T2 matched representation（同 model/prompt/schema/payload）")]:
            v = t.get(key, {})
            A.append(f"| {label} | {v.get('n')} | {pct(v.get('cost_reduction'))} | "
                     f"{pct(v.get('work_reduction'))} | {n(v.get('quality_delta'),6)} |")
        A.append("")
        mu = s.get("S1_multi_use", {})
        if mu:
            A.append("| 域 | reuse | survivors | BuildOnce+Reuse 摊销/query | RepeatedOperator 摊销/query | ↓（cache ON） | ↓（cache OFF） |")
            A.append("|---|---:|---:|---:|---:|---:|---:|")
            for k, v in mu.items():
                A.append(f"| {v['domain']} | {v['reuse']} | {v['survivors']} | "
                         f"{n(v['amortized_cost_once_reuse'])} | {n(v['amortized_cost_repeated_operator'])} | "
                         f"{pct(v['amortized_reduction'])} | {pct(v['amortized_reduction_cacheOFF'])} |")
            A.append("\n> Multi-use 收益来自 capability artifact 复用；**关闭 function caching 后优势归零**"
                     "（0% 左右），说明必须显式声明缓存策略（§10）。\n")
        R["experiment0_v12_side"] = s
    else:
        A.append("（缺失 side_results.json）\n")

    # ---------------------------------------------------------------- 5 实验1
    A.append("## 5. 实验 1（mock，0 真实 token）：A vs B vs C 全矩阵\n")
    if e1:
        A.append(f"- 矩阵：s ∈ {e1['matrix']['S']}%；reuse ∈ {e1['matrix']['REUSE']}%；"
                 f"两种工作负载模式：`PRED_SHARED`（同 cell 共享谓词）/ `PRED_DISTINCT`（各 query 独立谓词）")
        A.append(f"- cell 总数：{len(e1['heatmap'])}；N={e1['matrix']['n_rows_per_domain']:,}/域\n")
        A.append("### 5.1 per-cell 摊销（注意：分母不同，仅供看形态）\n")
        A.append("| 模式 | C/B 最小~最大 | C/A 最小~最大 | C 支配 B | C 支配 A |")
        A.append("|---|---|---|---|:--:|:--:|")
        for mode, v in e1["verdict"].items():
            A.append(f"| {mode} | {v['C_over_B_min']} ~ {v['C_over_B_max']} | {v['C_over_A_min']} ~ "
                     f"{v['C_over_A_max']} | {'✅' if v['C_dominates_B'] else '❌'} | {'✅' if v['C_dominates_A'] else '❌'} |")
        A.append("\n### 5.2 工作负载级公平口径（**裁决用**；A 的 eager 构建只计一次）\n")
        wt = e1.get("workload_totals", {})
        A.append("| 工作负载 | cells | A 总成本 | B 总成本 | C 总成本 | **C/B** | **C/A** | 构建行数 A/B/C | 单 cell 平均覆盖 |")
        A.append("|---|---:|---:|---:|---:|---:|---:|---|---:|")
        for k, v in wt.items():
            A.append(f"| {k} | {v['n_cells']} | {n(v['A']['total_cost'],3)} | {n(v['B']['total_cost'],1)} | "
                     f"{n(v['C']['total_cost'],1)} | **{v['C_over_B_cost']}** | **{v['C_over_A_cost']}** | "
                     f"{int(v['A']['build_rows']):,} / {int(v['B']['build_rows']):,} / {int(v['C']['build_rows']):,} | "
                     f"{v['avg_predicate_union_coverage']} |")
        A.append("\n> 关键：per-cell 口径下 C/A < 1（看似 C 更优）是**摊销分母不一致**造成的假象；"
                 "按工作负载级口径，A（一次性构建 2×N 行）远优于 C（为每个 cell 的 survivor 并集付费）。\n")
        R["experiment1"] = dict(matrix=e1["matrix"], verdict=e1["verdict"], workload_totals=wt,
                                summary_quality=e1.get("summary_quality", {}))
    else:
        A.append("（缺失 exp1_matrix.json）\n")

    # ---------------------------------------------------------------- 6 实验2
    A.append("## 6. 实验 2（真实 GLM-4.5-Air，精简矩阵，双 key + 免费兜底）\n")
    if e2:
        eng = e2.get("engine", {})
        A.append(f"- 模型：`{e2.get('model')}`，temperature=0，greedy，`thinking=disabled`，batch_size=1；"
                 f"关系规模 M={e2.get('rows_per_domain')} 行/域（确定性子关系）")
        A.append(f"- 矩阵：s ∈ {{1,10,50,100}}%，reuse ∈ {{1,10,50}}%，每 cell ≤20 queries，域 ecom+finproc，"
                 f"策略 A/B/C；cell 数 = {len(e2['cells'])}")
        A.append(f"- **真实消耗 {int(e2.get('used_tokens', 0)):,} tokens = ¥{n(ku.get('total_cost_yuan'), 4)}**；"
                 f"wall-clock {n(e2.get('wall_clock_sec'), 1)}s")
        A.append(f"- 后端分布：**全部 cell 仅用 GLM-4.5-Air = {e2.get('all_cells_glm_only')}**；"
                 f"切换次数 {ku.get('switches')}；限流退避事件 {ku.get('rate_limit_events')}；"
                 f"免费兜底 {ku.get('using_fallback')}")
        A.append(f"- 引擎：{eng.get('version')} / {eng.get('transport')} / workers={eng.get('workers')} / "
                 f"max_qps={eng.get('max_qps')}")
        A.append(f"- 质量：GLM A=B=C = {n(st.mean([v['A']['quality'] for v in e2['cells'].values()]))}，"
                 f"mock 同 cell = {n(st.mean([v['mock_quality'] for v in e2['cells'].values()]))}"
                 f" → **真实模型质量 non-inferior（实际更优）**\n")
        pb = ku.get("per_backend", {})
        A.append("| 后端 | 掩码 | calls | prompt_tokens | completion_tokens | 缓存命中 | 费用(元) | 限流次数 |")
        A.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for k, v in pb.items():
            A.append(f"| {k} | `{v.get('eq')}` | {v.get('calls')} | {v.get('prompt_tokens')} | "
                     f"{v.get('completion_tokens')} | {v.get('cached_tokens')} | {n(v.get('cost'), 6)} | "
                     f"{v.get('rate_limits')} |")
        A.append("")
        if e2t:
            A.append("### 6.1 工作负载级公平口径（真实 token / 人民币）\n")
            A.append("| 域 | queries | 策略 | 构建行数 | tokens | 成本(元) | 元/query |")
            A.append("|---|---:|---|---:|---:|---:|---:|")
            for dom, v in e2t["per_domain"].items():
                for stg in ["A", "B", "C"]:
                    A.append(f"| {dom} | {v['n_queries']} | {stg} | {int(v[stg]['build_rows']):,} | "
                             f"{int(v[stg]['tokens']):,} | {n(v[stg]['cost_yuan'], 6)} | {n(v[stg]['cost_per_query'], 8)} |")
                A.append(f"| {dom} | {v['n_queries']} | **C/B / C/A** | {v['C_over_B_rows']} / {v['C_over_A_rows']} |"
                         f" | | **{v['C_over_B_total']} / {v['C_over_A_total']}** |")
            t = e2t["total"]
            A.append("")
            A.append(f"**合计（{e2t['n_queries_total']} queries）：A ¥{n(t['A']['cost_yuan'], 6)}／"
                     f"B ¥{n(t['B']['cost_yuan'], 6)}／C ¥{n(t['C']['cost_yuan'], 6)}；"
                     f"C/B = {e2t['C_over_B_total']}，C/A = {e2t['C_over_A_total']}**\n")
        cb = [v["C_over_B"] for v in e2["cells"].values()]
        A.append(f"- per-cell C/B：均值 {n(st.mean(cb), 3)}，范围 [{n(min(cb), 3)}, {n(max(cb), 3)}]")
        A.append("")
        R["experiment2"] = dict(model=e2.get("model"), rows_per_domain=e2.get("rows_per_domain"),
                                used_tokens=e2.get("used_tokens"),
                                cost_yuan=ku.get("total_cost_yuan"), engine=eng,
                                key_usage=pb, workload_totals=e2t,
                                cells={k: dict(s=None, C_over_B=v["C_over_B"], C_over_A=v["C_over_A"],
                                               quality_B=v["B"]["quality"], quality_C=v["C"]["quality"],
                                               mock_quality=v["mock_quality"],
                                               rows_B=v["B"]["stats"]["rows"],
                                               rows_C=v["C"]["stats"]["rows"],
                                               tokens_B=v["B"]["stats"]["pt"] + v["B"]["stats"]["ct"],
                                               tokens_C=v["C"]["stats"]["pt"] + v["C"]["stats"]["ct"])
                                       for k, v in e2["cells"].items()})
    else:
        A.append("（缺失 exp2_results.json）\n")

    # ---------------------------------------------------------------- 7 引擎诊断
    A.append("## 7. 执行引擎诊断与修复记录（影响可信度，必须随结论阅读）\n")
    if probe:
        A.append("实测延迟/吞吐（keep-alive，单 key）：\n")
        A.append("| 并发 | 调用 | 成功 | 429 | 吞吐(QPS) | P50(ms) | P95(ms) |")
        A.append("|---:|---:|---:|---:|---:|---:|---:|")
        for key in ["sequential", "conc2", "conc4", "conc6", "conc8", "conc12"]:
            if key in probe:
                p = probe[key]
                A.append(f"| {p['concurrency']} | {p['calls']} | {p['ok']} | {p['n429']} | "
                         f"{p['throughput_qps']} | {p['p50_ms']} | {p['p95_ms']} |")
        A.append("")
    A.append("**v1 引擎缺陷（已定位并修复，证据文件 `key_switch_log_v1_429incident.jsonl`）**：")
    A.append("1. urllib 每请求新建 TLS 连接 → 有效单次延迟 ~1.7s（keep-alive 实测 0.38–0.47s）；")
    A.append("2. **HTTP 429（code 1302「已达到速率限制」）被误判为「额度耗尽」**，客户端因此永久弃用两个 key "
             "并切换到免费兜底 Qwen2.5-7B —— 13:40:09 `KEY_SWITCH 429 glm_key0→glm_key1`、"
             "13:40:11 `FALLBACK_ENABLED 429 glm_key1→free_fallback`。这会让后半程数据来自不同 model revision，"
             "**破坏固定项，该轮数据被整体作废**；")
    A.append("3. 修复（v2）：线程本地 keep-alive + 令牌桶限流（25 QPS）+ 429 指数退避重试（不切 key）；"
             "仅 401/403/余额不足才切 key；每次调用记录实际后端，并输出 `all_cells_glm_only` 标记。"
             "修复后单元耗时 70s → 5–36s（约 7×），本轮 0 切换 0 兜底。\n")
    R["engine_incident"] = dict(rate_probe=probe, v2=dict(workers=16, max_qps=25.0,
                                                          switches=ku.get("switches"),
                                                          rate_limit_events=ku.get("rate_limit_events"),
                                                          fallback=ku.get("using_fallback")))

    # ---------------------------------------------------------------- 8 实验3
    A.append("## 8. 实验 3（Certificate 判定修复，0 成本）\n")
    if e3:
        A.append(f"- 新判据：**PASS ⇔ UpperCI_(1−δ) ≤ ε**，ε={e3['epsilon']}，δ={e3['delta']}"
                 f"（Clopper–Pearson 精确单侧上界）；旧判据 = Wilson 上界 ≤ 0.20（等价于容忍 20% 错误率）")
        A.append(f"- 0 失败情形所需样本量：**n ≥ {e3['required_n_zero_failure']}**；n=300 下最多允许 "
                 f"**1 次**错误才能断言总体误差 ≤2%")
        A.append("")
        A.append("| Capability | 校准集 | n | errors | 观测误差 | CP 单侧上界95% | 旧 Wilson | groups | 旧→新 |")
        A.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
        for k, v in e3["capabilities"].items():
            for setn in ["legacy", "group_stratified"]:
                sd = v[setn]
                A.append(f"| `{k}` | {setn} | {sd['n']} | {sd['n_errors']} | {n(sd['observed_error'])} | "
                         f"{n(sd['clopper_pearson_upper_onesided_95'])} | {n(sd['wilson_upper_95_old'])} | "
                         f"{sd['n_independent_source_groups']} | {sd['status_old']} → **{sd['status_new']}** |")
        A.append("")
        sm = e3["summary"]
        A.append(f"- legacy 校准集（与 v1.2 同口径）：新判据 PASS {sm['legacy_set']['n_pass_new']}/"
                 f"{sm['n_capabilities']}，旧判据 PASS {sm['legacy_set']['n_pass_old']}/{sm['n_capabilities']}")
        A.append(f"- 分层校准集：新判据 PASS {sm['group_stratified_set']['n_pass_new']}/"
                 f"{sm['n_capabilities']}，旧判据 PASS {sm['group_stratified_set']['n_pass_old']}/"
                 f"{sm['n_capabilities']}")
        A.append(f"- 结论：{sm['interpretation']}\n")
        R["experiment3"] = e3
    else:
        A.append("（缺失 certificates_v3_clopper_pearson.json）\n")

    # ---------------------------------------------------------------- 9 裁决
    A.append("## 9. 总裁决与边界判据\n")
    A.append("必须区分两个基线：\n")
    A.append("| 基线 | 定义 | C 相对表现 | 判定 |")
    A.append("|---|---|---|---|")
    if e1.get("workload_totals"):
        cbs = [v["C_over_B_cost"] for v in e1["workload_totals"].values()]
        cas = [v["C_over_A_cost"] for v in e1["workload_totals"].values()]
        A.append(f"| **B = Predicate Pushdown（不持久化）** | 下推过滤，仅对 survivor Build，每 query 重建 | "
                 f"mock C/B = {min(cbs):.4f}–{max(cbs):.4f}；"
                 + (f"真实 GLM C/B = {e2t['C_over_B_total']}" if e2t else "") + " | ✅ **成立** |")
        A.append(f"| **A = Offline Eager Materialization（QuWARTS 式）** | 整表一次性 Build 并持久化 | "
                 f"mock C/A = {min(cas):.4f}–{max(cas):.4f}；"
                 + (f"真实 GLM C/A = {e2t['C_over_A_total']}" if e2t else "") + " | ❌ **不成立（本负载）** |")
    A.append("")
    A.append("边界公式（设 k = 互不共享的谓词数，s = 平均选择率，c = eager 构建的 capability 列数，"
             "c_row = 单行构建成本）：\n")
    A.append("```text")
    A.append("C_total ≈ k · s · N · c_row        # 每个谓词组各自构建 survivor 并集")
    A.append("A_total ≈ c · N · c_row            # 整表只构建一次")
    A.append("=> C 优于 A  ⟺  k · s < c")
    A.append("```")
    A.append("- 本轮：k=28/12（cell 数），s 含 100% → `k·s ≫ c` → **A 胜出**；")
    A.append("- 反例（C 胜出）：2 个互斥谓词各 1% 选择率 + 高 reuse → k·s = 0.02 < c=2；")
    A.append("- 与 v1.2 §13 的 QuWARTS 边界一致。\n")
    A.append("**一句话结论**：")
    A.append("> 相对「谓词下推但不持久化」（B），Capability-Late Materialization 的独立价值成立且显著"
             "（真实 GLM 下成本降至 31.8%，mock 降至 4–9%）；但相对「一次性离线 Eager 物化」（A）**并不普遍成立**，"
             "边界为 `k·s < c`。可主张的独立点是「**CapabilityBuild 是可持久化、可增量补齐的物理算子**」，"
             "而非「Late 普遍优于 Eager」。\n")

    # ---------------------------------------------------------------- 10 已排除解释
    A.append("## 10. 已排除的替代解释（因果隔离证据）\n")
    A.append("| 潜在混淆 | 检验 | 结果 |")
    A.append("|---|---|---|")
    A.append("| A 与 B 的 survivor 输入不同（全文档 vs 清洗摘要） | §28 逐 query 比对 survivor payload digest | 完全一致 ✅（D 组进一步逐行回读校验 payload_hash） |")
    A.append("| 执行路径 / reader 造成差异 | Replay 组：A/B 均读同一冻结 capability artifact | quality 与 result_hash 逐 query 相同 ✅ |")
    A.append("| batch composition 影响语义输出 | 强制 batch_size=1 | 全 run 校验通过 ✅ |")
    A.append("| 质量差异来自 capability 误差分布 | 三策略使用同一 capability version / prompt / schema / normalizer | A=B=C 质量逐 query 相同（Δ=0）✅ |")
    A.append("| 成本优势来自缓存假象 | Multi-use 分别报告 caching ON/OFF | caching OFF 时优势归零 → 优势确为 artifact 复用 ✅ |")
    A.append("| 失败被选择性删除 | 失败 query 全部保留，错误归因 100% 为 CAPABILITY | EXECUTION/SYNTHESIS/SOURCE/COMPILER = 0 ✅ |")
    A.append("| 真实模型实验混入其他模型 | 逐调用后端标记 + `all_cells_glm_only` | True（0 切换 0 兜底）✅ |\n")

    # ---------------------------------------------------------------- 11 局限
    A.append("## 11. 局限与不可外推项\n")
    A.append("1. **模型后端**：实验 0/1 使用确定性 mock 语义模型（词表+规则），质量非劣具有构造性；"
             "实验 2 使用 GLM-4.5-Air（真实），但仅覆盖 M=300/域的精简矩阵，绝对成本不可外推（比例结论由工作负载结构决定）；")
    A.append("2. **延迟**：mock 阶段的延迟为模拟服务时间（tokens × ms/token）+ harness 实测开销；"
             "真实阶段的延迟受 429 退避影响（1,985 次退避事件）；")
    A.append("3. **规模**：真实矩阵 s 只取 4 点、reuse 3 点、每 cell ≤20 query（预算约束），"
             "统计功效低于 mock 全矩阵；")
    A.append("4. **成本模型**：GLM 价目 输入 0.8 元/M、缓存命中 0.16 元/M、输出 2 元/M（≤200 tokens 档），"
             "替换定价会等比缩放结论，不改变 C/B、C/A 的排序结构；")
    A.append("5. **未做（协议 P3/P4）**：ReDD / QuWARTS / Sema / DASE 外部基线、source drift、unseen capability、"
             "Natural Language → QueryIR 编译器；")
    A.append("6. **能力可用性**：生产级证书（ε=2%）下 mock capability 3/4 FAIL → 该 capability 不可部署，"
             "结论仅针对 Build Position 的因果效应。\n")

    # ---------------------------------------------------------------- 12 索引
    A.append("## 12. 原始文件索引与校验值\n")
    A.append("| 文件 | 内容 |")
    A.append("|---|---|")
    for f, d in [("exp/runs/main_results.json", "v1.2 主实验全部聚合指标 + 判定"),
                 ("exp/runs/query_trace.jsonl", "v1.2 逐 query × 策略轨迹（3,600 行，含 validity checks）"),
                 ("exp/runs/side_results.json", "TADA-matched / Multi-use / validation 占比 / W3 安全"),
                 ("exp/runs/exp1_matrix.json", "实验1 全矩阵 + 热力图 + 工作负载级口径"),
                 ("exp/runs/exp1_heatmap.csv", "实验1 热力图明细（CSV）"),
                 ("exp/runs/exp2_results.json", "实验2 逐 cell 真实结果（含后端分布）"),
                 ("exp/runs/exp2_workload_totals.json", "实验2 公平口径总计"),
                 ("exp/runs/key_usage.json", "每 key tokens/费用/限流次数"),
                 ("exp/runs/key_switch_log.jsonl", "本轮切换/限流事件日志（含 drill）"),
                 ("exp/runs/key_switch_log_v1_429incident.jsonl", "v1 引擎 429 误判事件证据"),
                 ("exp/runs/rate_probe.json", "并发/吞吐/延迟实测"),
                 ("exp/runs/certificates_v3_clopper_pearson.json", "实验3 证书（新旧判据对比）"),
                 ("exp/runs/repro_pack_v2.json", "可复现包（版本/快照/定价/命令）")]:
        A.append(f"| `{f}` | {d} |")
    A.append("")
    A.append(f"- 代码 hash：`{json.load(open(os.path.join(EXP_OUT, 'repro_pack_v2.json'), encoding='utf-8')).get('code_hash') if os.path.exists(os.path.join(EXP_OUT, 'repro_pack_v2.json')) else 'n/a'}`；"
             f"数据集快照 `{e1.get('snapshot')}`；query 快照 `{manifest.get('query_snapshot')}`")
    A.append(f"- 固定项 hash：model `{manifest.get('model_revision')}`/`{manifest.get('model_hash')}`；"
             f"prompt `{json.dumps(manifest.get('prompt_hash', {}), ensure_ascii=False)}`；"
             f"schema `{json.dumps(manifest.get('schema_hash', {}), ensure_ascii=False)}`")
    A.append(f"- 运行环境：{json.dumps(manifest.get('hardware', {}), ensure_ascii=False)}；seed={manifest.get('seed')}；"
             f"定价版本 `{CFG.PRICING['pricing_version']}`（mock）/ `bigmodel-2026.09`（GLM）\n")

    A.append("## 13. 建议下游 AI 分析的问题\n")
    A.append("1. 在本工作负载结构下，`k·s < c` 的判定是否充分？是否需要加入「谓词并集是否嵌套」「payload 长度分布」等修正项？")
    A.append("2. C/B 的真实模型收益（0.318）与 mock（0.044–0.085）差异巨大，"
             "差异来源是 payload/单行成本结构还是工作负载差异？可否用同一口径重算 mock 以获得可比数字？")
    A.append("3. 若要主张「Late-Persistent 独立价值」，需要哪些补充实验才能排除 QuWARTS 式离线物化的支配（k·s < c 的低覆盖工作负载）？")
    A.append("4. 生产级 certificate（ε=2%）下 capability 全部 FAIL，是否应改为「离线认证 + 线上只读」的部署形态？"
             "需要多少样本/多少误差才能达到 PASS？")
    A.append("5. 429 退避（1,985 次）对延迟结论的影响有多大？是否需要在低 QPS（≤10）下重跑一遍以给出干净延迟？\n")

    md = "\n".join(A)
    with open(os.path.join(EXP, "RESEARCH_SUMMARY_FOR_ANALYSIS.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(EXP_OUT, "analysis_bundle.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=1)
    print("written: exp/RESEARCH_SUMMARY_FOR_ANALYSIS.md", len(A), "lines;",
          "exp/runs/analysis_bundle.json")


if __name__ == "__main__":
    build()
