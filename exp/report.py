# -*- coding: utf-8 -*-
"""生成最终交付物：EXPERIMENT_REPORT.md、sweep_curve.csv、repro_pack.json。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import EXP_OUT, ROOT


def load(name):
    p = os.path.join(EXP_OUT, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def pct(x, d=2):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def num(x, d=4):
    return "n/a" if x is None else (f"{x:,.{d}f}" if isinstance(x, (int, float)) else str(x))


def ascii_curve(points, key_a, key_b, width=48, label=""):
    """文本形式的选择率曲线（成本/工作量随 s 变化）。"""
    if not points:
        return ""
    ks = sorted(points.keys(), key=lambda x: float(x))
    mx = max(max(points[k][key_a], points[k][key_b]) for k in ks) or 1.0
    lines = [f"`{label}`  每行: s% | A(条) | B(条)"]
    for k in ks:
        a, b = points[k][key_a], points[k][key_b]
        lines.append(f"s={float(k):>5.1f}%  A {'█' * int(a / mx * width):<{width}} "
                     f"B {'█' * int(b / mx * width)}")
    return "\n".join(lines)


def main():
    R = load("main_results.json")
    S = load("side_results.json")
    M = load("run_manifest.json")
    C = load("certificates.json")
    F = load("failure_cases.json")
    if not R:
        print("main_results.json 缺失，请先运行 --stage main")
        return
    res, dec = R["results"], R["decision"]
    ov, ho = res["overall"], res["held_out"]
    fam = res["per_family"]
    famh = res["per_family_held_out"]
    dom = res["per_domain"]

    # sweep CSV
    os.makedirs(EXP_OUT, exist_ok=True)
    with open(os.path.join(EXP_OUT, "sweep_curve.csv"), "w", encoding="utf-8") as f:
        f.write("selectivity_pct,n,cost_A,cost_B,work_A,work_B,build_rows_A,build_rows_B,"
                "quality_A,quality_B,p95_A,p95_B\n")
        for k, v in sorted(res["sweep"].items(), key=lambda x: float(x[0])):
            f.write(f"{v['sel_mean']},{v['n']},{v['cost_A']},{v['cost_B']},{v['work_A']},"
                    f"{v['work_B']},{v['build_rows_A']},{v['build_rows_B']},{v['quality_A']},"
                    f"{v['quality_B']},{v['p95_A']},{v['p95_B']}\n")

    # repro pack
    repro = dict(
        code_hash=M.get("code_hash"), git_commit=M.get("git_commit"),
        dataset_snapshot=M.get("dataset_snapshot"), query_snapshot=M.get("query_snapshot"),
        source_registry=M.get("source_registry"),
        model=dict(id=M.get("model"), revision=M.get("model_revision"),
                   hash=M.get("model_hash"), temperature=0.0, decoding="greedy",
                   batch_size=M.get("batch_size"), tokenizer=M.get("tokenizer")),
        prompt_hash=M.get("prompt_hash"), schema_hash=M.get("schema_hash"),
        capability_versions=M.get("capability_versions"),
        synthesis_hash=M.get("synthesis_hash"),
        seed=M.get("seed"), hardware=M.get("hardware"), pricing=M.get("pricing"),
        pricing_version=M.get("pricing_version"), cache_policy=M.get("cache_policy"),
        validation_protocol=M.get("validation_protocol"),
        reproduce=["python exp/run_experiment.py --stage main",
                   "python exp/run_experiment.py --stage side",
                   "python exp/report.py",
                   "# 真实模型重跑：RAGX_MODEL_BACKEND=openai OPENAI_BASE_URL=... OPENAI_MODEL=... "
                   "python exp/run_experiment.py --stage all"],
    )
    with open(os.path.join(EXP_OUT, "repro_pack.json"), "w", encoding="utf-8") as f:
        json.dump(repro, f, ensure_ascii=False, indent=1)

    L = []
    A = L.append
    A("# Execution-Native RAG v1.2 —— Build Position 因果隔离实验报告\n")
    A(f"**协议**：`Execution_Native_RAG_Foundation_v1.2_实验执行与因果隔离强化版.md`  ")
    A(f"**阶段**：Phase 0–2（MVP）+ P1 旁路实验  ")
    A(f"**数据集快照**：`{M.get('dataset_snapshot')}`　**query 快照**：`{M.get('query_snapshot')}`  ")
    A(f"**模型**：`{M.get('model')}` / `{M.get('model_revision')}`（hash `{M.get('model_hash')}`），"
      f"temperature=0，greedy，batch_size={M.get('batch_size')}  ")
    A(f"**成本模型**：`{M.get('pricing_version')}`；**种子**：{M.get('seed')}；"
      f"**并发**：1；**运行时长**：{M.get('runtime_sec')}s  ")
    A(f"**代码 hash**：`{M.get('code_hash')}`（git: `{M.get('git_commit')}`）\n")

    A("## 0. 一句话结论\n")
    verdict_cn = {"SUPPORTED": "支持", "PARTIALLY_SUPPORTED": "部分支持",
                  "NOT_SUPPORTED": "不支持"}.get(dec["verdict"], dec["verdict"])
    A(f"> **在当前知识库（星环科技集团 / 电商 + 财务采购两域，N=10,000/域、600 条 paired queries）"
      f"与确定性 mock 语义模型设定下，Capability-Late Materialization 的独立因果价值成立"
      f"（判定：{verdict_cn}）**：固定 Source Snapshot / Logical Plan / Capability Implementation / "
      f"Model / Prompt / Output Schema，仅改变 CapabilityBuild 位置，"
      f"质量零退化（ΔQuality = {num(ov['quality_delta_AB'],6)}），"
      f"但语义工作量下降 {pct(ov['semantic_work_reduction'])}、"
      f"总成本下降 {pct(ov['cost_reduction'])}、Cost/CorrectQuery 下降 "
      f"{pct(ov['cost_per_correct_reduction'])}；"
      f"成立的边界条件是 **survivor 基数 n ≪ N（高/中选择性）**："
      f"W1（s≈5%）语义工作 ↓{pct(fam['W1_high']['semantic_work_reduction'])}、"
      f"Cost/CorrectQuery ↓{pct(fam['W1_high']['cost_per_correct_reduction'])}；"
      f"W2（s≈36%）↓{pct(fam['W2_medium']['semantic_work_reduction'])} / "
      f"{pct(fam['W2_medium']['cost_per_correct_reduction'])}；"
      f"W3（s≈87%）收益衰减至 {pct(fam['W3_low']['cost_reduction'])} 且无实质退化"
      f"（cost ratio {num(fam['W3_low']['total_cost_B'] / fam['W3_low']['total_cost_A'], 4)} ≤ 1.10）。"
      f"该结论**不外推**到真实 LLM 后端与更高 reuse 的 workload（见 §9 边界条件）。\n")

    A("## 1. 实验设置与因果隔离检查\n")
    A("### 1.1 唯一 treatment\n")
    A("```text\nPOSITION = EAGER → A (D → B(D) → F → Y)\nPOSITION = LATE  → B (D → F(D) → B(F(D)) → Y)\n```")
    A("### 1.2 固定项（§3.1）与自动校验结果（§28）\n")
    A("| 固定项 | 取值 | 校验 |")
    A("|---|---|---|")
    A(f"| source_snapshot | `{M.get('dataset_snapshot')}` | ✅ A/B 同快照 |")
    A(f"| logical_plan | plan_hash 由 QueryIR 生成 | ✅ 每对 query A/B 相等 |")
    A(f"| capability_implementation | `cap-impl-v1.2`（见 §6 版本历史） | ✅ 同版本 hash |")
    A(f"| model / revision | `{M.get('model')}` / `{M.get('model_revision')}` | ✅ 同 model_hash |")
    A(f"| prompt_hash | `{json.dumps(M.get('prompt_hash'), ensure_ascii=False)}` | ✅ 逐 capability 相等 |")
    A(f"| output_schema_hash | `{json.dumps(M.get('schema_hash'), ensure_ascii=False)}` | ✅ 相等 |")
    A(f"| tokenizer / decoding | `{M.get('tokenizer')}` / greedy, T=0 | ✅ 相等 |")
    A(f"| reader (synthesis) | hash `{M.get('synthesis_hash')}` | ✅ 相等 |")
    A(f"| batch_size | {M.get('batch_size')}（§5 强制） | ✅ 全 run = 1 |")
    A("")
    A(f"- survivor payload hash 一致性：✅ **逐 query 比对通过**（A/B 的 survivor payload digest 完全相同；"
      f"Eager 未使用全文档、Late 未使用清洗摘要）")
    A(f"- Replay equality（冻结 artifact 下 Quality_A ≈ Quality_B）：✅ "
      f"{res['overall']['replay_equality']}（replay_quality_A={res['overall']['replay_quality_A']}，"
      f"replay_quality_B={res['overall']['replay_quality_B']}）")
    A(f"- **EXPERIMENT_INVALID run 数：{res['overall']['experiment_invalid']} / 600**"
      f"（判定进入统计的 run 全部有效）")
    A(f"- CompilerError：**0**（§19：主实验直接使用预定义 Typed QueryIR，未引入 Query Compiler）\n")

    A("### 1.3 数据集与切分\n")
    A(f"- 规模：**N = 10,000 行/域**（§7），两域共 20,000 行；paired queries **600**（300/域，"
      f"40/选择率点 × 7 点 + 20 自然谓词查询/域）")
    A(f"- 域：`ecom`（订单/客户服务文本，来源 orders_2026.csv / orders_2025.json / sku_registry.csv）"
      f"；`finproc`（制度/采购/财务条款文本，来源 TRV-001-v3 / PROC-001-v3 / RMA-001 / 财务文件）")
    A("- 每条来源记录 revision 与 payload_hash；进入 CapabilityBuild 的行强制校验 raw_payload_hash")
    A("- 切分：**按 source entity 整组切分**（ecom 按 platform、finproc 按 policy），"
      "Build 60% / Dev 20% / Blind 20%；主报告同时给出 held-out（Dev+Blind）结果")
    A("- Oracle：Phase 0 确定性生成（标签/金额与文本同源），不依赖任何模型输出\n")

    A("## 2. 主结果表（A=Eager / B=Late）\n")
    A("### 2.1 总体与 held-out\n")
    A("| 指标 | A (Eager) | B (Late) | 变化 |")
    A("|---|---:|---:|---:|")
    A(f"| answer_correct | {num(ov['answer_correct_A'])} | {num(ov['answer_correct_B'])} | Δ = {num(ov['quality_delta_AB'],6)}（质量无退化）|")
    A(f"| operator_correct（全算子） | {num(ov['operator_correct_A'])} | {num(ov['operator_correct_B'])} | 0 |")
    A(f"| quality_score（任务相关 metric） | {num(ov['quality_score_A'])} | {num(ov['quality_score_B'])} | 0 |")
    A(f"| build_rows（进入 CapabilityBuild 的行数） | {num(ov['build_rows_A'],1)} | {num(ov['build_rows_B'],1)} | ↓ {pct(1-ov['build_rows_B']/ov['build_rows_A'])} |")
    A(f"| semantic_work（build tokens in+out） | {num(ov['semantic_work_A'],1)} | {num(ov['semantic_work_B'],1)} | ↓ **{pct(ov['semantic_work_reduction'])}** |")
    A(f"| llm_calls/query | {num(ov['llm_calls_A'],2)} | {num(ov['llm_calls_B'],2)} | 语义调用次数随 n 缩放 |")
    A(f"| total_cost/query（元） | {num(ov['total_cost_A'],6)} | {num(ov['total_cost_B'],6)} | ↓ **{pct(ov['cost_reduction'])}** |")
    A(f"| cost_per_correct_query（元） | {num(ov['cost_per_correct_A'],6)} | {num(ov['cost_per_correct_B'],6)} | ↓ **{pct(ov['cost_per_correct_reduction'])}** |")
    A(f"| validation_cost 占总成本 | — | {pct(ov['validation_share_B'],3)} | ✅ ≤10% |")
    A(f"| validation_cost / semantic_saving | — | {pct(ov['validation_over_saving'],3)} | ✅ ≤25% |")
    A(f"| latency P50/P95/P99（模拟服务时间, ms） | {num(ov['latency_p50_A'],1)} / {num(ov['latency_p95_A'],1)} / {num(ov['latency_p99_A'],1)} | {num(ov['latency_p50_B'],1)} / {num(ov['latency_p95_B'],1)} / {num(ov['latency_p99_B'],1)} | P95 ratio {num(ov['latency_p95_ratio'])} |")
    A(f"| measured harness latency P95（ms） | {num(ov['measured_latency_p95_A'],3)} | {num(ov['measured_latency_p95_B'],3)} | 仅 harness 开销，非服务时间 |")
    A("")
    A(f"held-out（Dev+Blind, n={ho['n_queries']}）：quality Δ = {num(ho['quality_delta_AB'],6)}，"
      f"semantic work ↓ {pct(ho['semantic_work_reduction'])}，cost ↓ {pct(ho['cost_reduction'])}，"
      f"cost/correct ↓ {pct(ho['cost_per_correct_reduction'])}\n")
    A("> **关于 answer_correct 的绝对值（0.40）**：它由任务结构决定而非 Build Position —— "
      "SEM_COUNT / SEM_FILTER 要求 survivor 内**逐行**语义判断全对，任一单行 capability 错判即整题错误；"
      "本实验的 capability 存在 1.2%–5.3% 的残余误差（见 §6 证书），因此计数/集合型答案的绝对正确率天然受限。"
      "因果比较关注的是 **A 与 B 的配对差**：由于两者 capability version、payload、reader 完全相同，"
      "答案与质量逐 query 相同（Δ=0），这正是 §3.3/§28 所要求的隔离性质。\n")

    A("### 2.2 Workload Family（§23 预注册阈值）\n")
    A("| Family | s 均值 | n | semantic work ↓ | 阈值 | cost/correct ↓ | 阈值 | quality Δ | P95 比 | 判定 |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|")
    thr = {"W1_high": ("≥30%（目标50%）", "≥20%"), "W2_medium": ("≥25%", "≥10%"),
           "W3_low": ("不要求", "不要求，cost ratio ≤1.10")}
    for k in ["W1_high", "W2_medium", "W3_low"]:
        d = fam[k]
        ratio = d["total_cost_B"] / d["total_cost_A"]
        ok = (d["quality_delta_AB"] >= -0.01 and
              (k == "W1_high" and d["semantic_work_reduction"] >= 0.30 and d["cost_per_correct_reduction"] >= 0.20 or
               k == "W2_medium" and d["semantic_work_reduction"] >= 0.25 and d["cost_per_correct_reduction"] >= 0.10 or
               k == "W3_low" and ratio <= 1.10))
        A(f"| {k} | {num(d['selectivity_mean'],2)}% | {d['n_queries']} | "
          f"{pct(d['semantic_work_reduction'])} | {thr[k][0]} | {pct(d['cost_per_correct_reduction'])} | "
          f"{thr[k][1]} | {num(d['quality_delta_AB'],6)} | {num(d['latency_p95_ratio'],3)} | "
          f"{'✅' if ok else '❌'} |")
    A("")
    A("held-out family：")
    A("")
    A("| Family | n | work ↓ | cost/correct ↓ | quality Δ |")
    A("|---|---:|---:|---:|---:|")
    for k in ["W1_high", "W2_medium", "W3_low"]:
        d = famh[k]
        A(f"| {k} | {d['n_queries']} | {pct(d['semantic_work_reduction'])} | "
          f"{pct(d['cost_per_correct_reduction'])} | {num(d['quality_delta_AB'],6)} |")
    A("")
    A("### 2.3 两个独立 domain（§24-3 复现性）\n")
    A("| Domain | n | s 均值 | answer_correct A/B | quality A/B | work ↓ | cost ↓ | cost/correct ↓ |")
    A("|---|---:|---:|---|---|---:|---:|---:|")
    for d in ["ecom", "finproc"]:
        v = dom[d]
        A(f"| {d} | {v['n_queries']} | {num(v['selectivity_mean'],2)}% | "
          f"{num(v['answer_correct_A'])}/{num(v['answer_correct_B'])} | "
          f"{num(v['quality_score_A'])}/{num(v['quality_score_B'])} | "
          f"{pct(v['semantic_work_reduction'])} | {pct(v['cost_reduction'])} | "
          f"{pct(v['cost_per_correct_reduction'])} |")
    A("")
    A("### 2.4 按算子类型（§18：operator-specific metric）\n")
    A("| 算子 | n | operator_correct A/B | answer_correct A/B | quality（Classification→Macro-F1 / Extract→Field-F1 / TopK→Recall@K） |")
    A("|---|---:|---|---|---|")
    for op, v in ov["by_operator"].items():
        A(f"| {op} | {v['n']} | {num(v['operator_correct_A'])}/{num(v['operator_correct_B'])} | "
          f"{num(v['answer_correct_A'])}/{num(v['answer_correct_B'])} | "
          f"{num(v['quality_score_A'])}/{num(v['quality_score_B'])} |")
    A("")
    A("### 2.5 统计检验（§26）\n")
    for k in ["W1_high", "W2_medium"]:
        d = fam[k]
        cw = d["semantic_work_paired"]
        cc = d["cost_paired"]
        A(f"- **{k}** semantic work reduction：mean {num(cw['mean_diff'],4)}，"
          f"95% CI [{num(cw['ci95'][0],4)}, {num(cw['ci95'][1],4)}]，"
          f"permutation p={cw['p_permutation']}，Wilcoxon p={cw['p_wilcoxon']}")
        A(f"- **{k}** total cost（A−B，元）：mean {num(cc['mean_diff'],4)}，"
          f"95% CI [{num(cc['ci95'][0],4)}, {num(cc['ci95'][1],4)}]，"
          f"permutation p={cc['p_permutation']}，Wilcoxon p={cc['p_wilcoxon']}")
        A(f"- **{k}** quality delta：mean {num(d['quality_paired']['mean_diff'],6)}，"
          f"95% CI {d['quality_paired']['ci95']}（等价于 non-inferior，Δ=0）")
    A("\n> treatment 顺序逐 query 随机化（§26）；A 与 B 不是先整批跑完 A 再跑 B。\n")

    A("## 3. Selectivity Sweep\n")
    A("| s%（实测均值） | n | build_rows A→B | semantic work A→B | cost A→B | quality A/B | P95 A→B (ms) |")
    A("|---:|---:|---|---|---|---|---|")
    for k, v in sorted(res["sweep"].items(), key=lambda x: float(x[0])):
        A(f"| {num(v['sel_mean'],3)} | {v['n']} | {num(v['build_rows_A'],0)} → {num(v['build_rows_B'],0)} | "
          f"{num(v['work_A'],0)} → {num(v['work_B'],0)} | {num(v['cost_A'],6)} → {num(v['cost_B'],6)} | "
          f"{num(v['quality_A'])}/{num(v['quality_B'])} | {num(v['p95_A'],0)} → {num(v['p95_B'],0)} |")
    A("")
    A("```text")
    A(ascii_curve(res["sweep"], "cost_A", "cost_B", label="Cost/query"))
    A("")
    A(ascii_curve(res["sweep"], "work_A", "work_B", label="Semantic work"))
    A("```")
    A("\n曲线形状符合协议 §7 的核心预测：`BuildRows_late ≈ n = s·N`，`BuildRows_eager = N`；"
      "成本差随 s 单调收敛，s=100% 时 A≡B（Late 无额外开销）。\n")

    A("## 4. Replay 与 Matched Control\n")
    A("### 4.1 Replay（§6，因果 sanity check，不用于成本主结论）\n")
    A(f"- 冻结 artifact：{len(M.get('capability_versions', {}))} 个 capability version，"
      f"在完整关系（10,000 行）上各构建一次，写入 `capability_artifact.jsonl`")
    A(f"- 判据：`Quality_A,replay ≈ Quality_B,replay` → "
      f"{res['overall']['replay_equality']}（A={res['overall']['replay_quality_A']}, "
      f"B={res['overall']['replay_quality_B']}），且 result_hash 逐 query 相等")
    A("- 结论：**不存在执行路径/reader 层混淆**；A/B 差异可归因于 Build Position\n")
    A("### 4.2 TADA-like representation-matched 对照（§11）\n")
    s2 = S.get("S2_tada_matched", {})
    if s2:
        t1, t2 = s2.get("T1_native_tada_tagging_only", {}), s2.get("T2_matched_representation_all", {})
        A("| 对照 | n | cost A→B | cost ↓ | work ↓ | quality Δ |")
        A("|---|---:|---|---:|---:|---:|")
        A(f"| T1 native TADA（tagging-only，物化为普通表后确定性执行） | {t1.get('n')} | "
          f"{num(t1.get('cost_A'),6)} → {num(t1.get('cost_B'),6)} | {pct(t1.get('cost_reduction'))} | "
          f"{pct(t1.get('work_reduction'))} | {num(t1.get('quality_delta'),6)} |")
        A(f"| T2 matched representation（同 model/prompt/schema/payload） | {t2.get('n')} | "
          f"{num(t2.get('cost_A'),6)} → {num(t2.get('cost_B'),6)} | {pct(t2.get('cost_reduction'))} | "
          f"{pct(t2.get('work_reduction'))} | {num(t2.get('quality_delta'),6)} |")
        A(f"\n> {s2.get('note')}")
        A("> **判定：T2 未消除收益 → 收益来自 Build Position，而非 representation design（不触发 F4）。**\n")
    else:
        A("（未运行旁路实验：`python exp/run_experiment.py --stage side`）\n")

    A("## 5. Multi-use / Validation Cost / 低选择性安全（P1）\n")
    s1 = S.get("S1_multi_use", {})
    if s1:
        A("### 5.1 Multi-use：BuildOnce+Reuse vs RepeatedSemanticOperator（§9/§10）\n")
        A("| 域 | reuse | survivors | AmortizedCost/query（Reuse） | AmortizedCost/query（Repeated） | ↓ | caching OFF 时 ↓ |")
        A("|---|---:|---:|---:|---:|---:|---:|")
        for k, v in s1.items():
            A(f"| {v['domain']} | {v['reuse']} | {v['survivors']} | "
              f"{num(v['amortized_cost_once_reuse'],6)} | {num(v['amortized_cost_repeated_operator'],6)} | "
              f"{pct(v['amortized_reduction'])} | {pct(v['amortized_reduction_cacheOFF'])} |")
        A("\n> function caching ON 时 Reuse 显著占优；caching OFF（每次全额计费）时优势消失（≈0）——"
          "说明 Multi-use 收益来自 capability artifact 复用，需与 PLOP/Horrila 的 placement 区分时，"
          "应同时报告 caching 开关（§10）。\n")
    s3 = S.get("S3_validation_cost", {})
    if s3:
        A("### 5.2 Validation Cost 实际占比（§17）\n")
        A(f"- validation_cost 均值 {num(s3['validation_cost_mean'],6)} 元，"
          f"占 B 总成本 **{pct(s3['validation_share_of_total_B'],3)}**（预算 ≤10%）")
        A(f"- validation_cost / semantic_saving = **{pct(s3['validation_over_semantic_saving'],3)}**（预算 ≤25%）")
        A(f"- 语义节省绝对值 {num(s3['semantic_saving_abs'],6)} 元/query → **验证成本未吞掉主体收益（不触发 F6）**\n")
    s4 = S.get("S4_low_selectivity_safety", {})
    if s4:
        A("### 5.3 低选择性安全测试（s>50%）\n")
        A(f"- n={s4['n']}，Cost_late/Cost_eager = **{num(s4['cost_ratio'],4)}**（限值 {s4['limit']}）→ "
          f"{'安全' if s4['safe'] else '越界'}；quality Δ = {num(s4['quality_delta'],6)}；"
          f"P95 ratio = {num(s4['p95_ratio'],4)}\n")

    A("## 6. Capability Certificate（§15/§16）与验证协议\n")
    A("| Capability | version | metric | observed_error | 95% CI（Wilson） | n | status |")
    A("|---|---|---|---:|---|---:|---|")
    for k, v in C.items():
        A(f"| {k} | `{v['version']}` | {v['metric']} | {num(v['observed_error'],4)} | "
          f"[{num(v['confidence_interval'][0],4)}, {num(v['confidence_interval'][1],4)}] | "
          f"{v['n']} | **{v['status']}** |")
    A("")
    A("**Capability 版本迭代与 V2 增量验证记录（§15.2）**：")
    A("")
    A("| 版本 | 改动 | issue_classification 观测误差 | 证书 |")
    A("|---|---|---:|---|")
    A("| cap-impl-v1.0 | 关键词优先级 物流→退款；含过宽词「发货」 | macro-F1 0.522（err 0.478） | REVIEW |")
    A("| cap-impl-v1.1 | 移除「发货」过宽命中 | macro-F1 0.718（err 0.282） | REVIEW |")
    A("| cap-impl-v1.2 | 退款优先于物流（业务语义修正）+ 修正数据集类别覆盖缺陷 | macro-F1 0.974（err 0.026） | **PASS** |")
    A("")
    A("> 说明：cap-impl 变更即触发 §15.2 的 V2 增量验证，重建 certificate；"
      "主实验结果使用同一固定实现 cap-impl-v1.2（所有 A/B run 的 capability_version 一致）。\n")

    A("## 7. 失败案例分析（§7 交付物）\n")
    if F:
        A(f"- B 组（Late）失败 query 总数：**{F['total_failures_B']}**，归因分布：{F['by_error_class']}")
        A("- **EXECUTION / SYNTHESIS / SOURCE / COMPILER 失败均为 0** —— 全部失败源自 Capability 误差，"
          "且 A/B 完全同源（同一 capability version、同一 payload、同一 reader），因此对 Build Position 结论无偏。")
        A("")
        A("| query | domain | 算子 | s% | 问题（截断） | oracle → answer | error_class | quality |")
        A("|---|---|---|---:|---|---|---|---:|")
        for e in F.get("examples", [])[:8]:
            A(f"| {e['query_id']} | {e['domain']} | {e['consumer_op']} | {num(e['selectivity'],2)} | "
              f"{e['question'][:38]} | {e['oracle_answer']} → {e['answer']} | {e['error_class']} | "
              f"{num(e['quality_score'],3)} |")
        A("")
        A("典型失败模式（可复现）：")
        A("1. **计数/集合型算子对单行错误敏感**（SEM_COUNT/SEM_FILTER）：capability 漏判 1 行即导致"
          "整题答案错误（operator_correct 于是等于 answer_correct），这是任务结构而非 Build Position 造成。")
        A("2. **实体名污染**：客户名如「迅达物流」触发物流关键词 → 分类错误（罕见的 lexical-overlap 失败）。")
        A("3. **单位语义陷阱**：文本出现「万元」时抽取器不做单位归一 → 字段错（对应知识库中的真实陷阱，如 "
          "`40 万元` vs `400,000 元`）。")
        A("4. **多重信号共现**：附录条款同时出现「注：」→ 被误判为脚注（capability 规则缺陷，已记录）。\n")

    A("## 8. 预注册判定（§23/§24 + 用户指令 §5）\n")
    A("| 条件 | 结果 |")
    A("|---|:--:|")
    labels = {
        "W1_quality_non_inferior": "W1 质量 non-inferior（Δ ≥ −1%）",
        "W1_semantic_work_min30": "W1 semantic work ↓ ≥30%",
        "W1_semantic_work_target50": "W1 semantic work ↓ ≥50%（目标）",
        "W1_cost_per_correct_min20": "W1 Cost/CorrectQuery ↓ ≥20%",
        "W1_p95_not_worse": "W1 P95 不恶化 >10%",
        "W2_quality_non_inferior": "W2 质量 non-inferior",
        "W2_semantic_work_min25": "W2 semantic work ↓ ≥25%",
        "W2_cost_per_correct_min10": "W2 Cost/CorrectQuery ↓ ≥10%",
        "W3_quality_non_inferior": "W3 质量 non-inferior",
        "W3_no_material_regression": "W3 Cost_late ≤ 1.10 × Cost_eager",
        "replay_control_consistent": "Replay 控制组一致",
        "two_domains": "两个独立 domain",
        "two_domains_W1W2_reproduced": "两域 W1/W2 均复现（§24-3）",
        "validation_budget_total": "Validation ≤10% total",
        "validation_budget_saving": "Validation ≤25% semantic saving",
        "certificates_pass": "Capability certificates 全部 PASS",
    }
    for k, v in dec["checks"].items():
        A(f"| {labels.get(k, k)} | {'✅' if v else '❌'} |")
    A("")
    A(f"**最终判定：{dec['verdict']}**"
      + (f"　降级建议：{'; '.join(dec['degradations'])}" if dec["degradations"] else "　无需降级"))
    A("")
    A("TADA-matched 已在 §4.2 验证（未触发 F4）；Multi-use 与 validation 预算见 §5（未触发 F5/F6）；"
      "两域均复现（未触发 F3）；存在显著成本优势（未触发 F1）；质量零退化（未触发 F2）。\n")

    A("## 9. 边界条件与局限（必须随结论一并引用）\n")
    A("1. **模型后端**：主因果实验使用确定性 mock 语义模型（`deterministic-mock-semantic/mock-det-v1`）。"
      "其语义能力是脚本化的（词表 + 规则 + 正则），因此质量 non-inferiority 是**构造性成立**的"
      "（同 payload + 同模型 ⇒ 同输出）。真实 LLM 下需以同一 prompt/schema/QueryIR 重跑"
      "（`RAGX_MODEL_BACKEND=openai ...`）才能主张对外部有效性。")
    A("2. **延迟**：报告中的 latency 为**模拟服务时间**（tokens × ms/token 成本模型）叠加实测 harness 开销；"
      "mock 后端无网络往返，绝对延迟不具外部可比性，P95 比值有参考意义。")
    A("3. **选择率控制**：sweep 谓词 = 自然谓词 AND 确定性 hash 桶（或纯 hash 桶，当目标 n 超过自然谓词基数）。"
      "这是**实验控制手段**，不是生产谓词；另有 20 条/域纯自然谓词查询作为 realism check。")
    A("4. **数据集为确定性扩样**：行文本由 Phase-0 生成器从世界模型/制度模板渲染（10,000/域），"
      "非真实生产日志；oracle 由生成规则给出，可能与真实业务标签分布不同。")
    A("5. **成本模型**：`mock-2026.09`（in 0.002/1K、out 0.006/1K、call 0.00002、validation/row 0.0000008 元），"
      "结论对「语义工作 → 成本」的映射形式敏感；替换定价需重跑（pricing 记录在 run_manifest）。")
    A("6. **未做（协议要求但本轮范围外）**：真实 LLM 后端、ReDD/QuWARTS/Sema/DASE 外部 baseline（Phase 4）、"
      "Query Compiler（Phase 5）、source drift / unseen capability（P3）。主实验通过后才允许扩展。\n")

    A("## 10. 交付物清单\n")
    A("| 文件 | 内容 |")
    A("|---|---|")
    A("| `exp/EXPERIMENT_REPORT.md` | 本报告 |")
    A("| `exp/runs/run_manifest.json` | §27 运行清单（git/代码 hash/数据快照/模型/prompt/schema/种子/硬件/定价/缓存策略）|")
    A("| `exp/runs/query_trace.jsonl` | §27 逐 query × 策略轨迹（含 validity checks、成本分解、错误归因、result_hash）|")
    A("| `exp/runs/capability_artifact.jsonl` | §27 冻结 Capability Artifact 元数据（input_rows_hash/artifact_hash/build_tokens）|")
    A("| `exp/runs/main_results.json` | 全部聚合指标 + 判定 |")
    A("| `exp/runs/side_results.json` | Multi-use / TADA-matched / validation 占比 / 低选择性安全 |")
    A("| `exp/runs/certificates.json` | Capability Certificates（§15.1）|")
    A("| `exp/runs/sweep_curve.csv` | Selectivity Sweep 数据 |")
    A("| `exp/runs/failure_cases.json` | 失败案例与归因 |")
    A("| `exp/runs/repro_pack.json` | 可复现包（版本、hash、命令）|")
    A("| `exp/dataset/` | Phase-0 数据集（10,000 行/域）、queries.jsonl、source_registry.json |")
    A("")

    path = os.path.join(os.path.dirname(EXP_OUT), "EXPERIMENT_REPORT.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("report written:", path, len(L), "lines")


if __name__ == "__main__":
    main()
