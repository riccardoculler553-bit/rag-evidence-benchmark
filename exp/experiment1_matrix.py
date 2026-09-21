# -*- coding: utf-8 -*-
"""实验 1（Mock，0 真实 token）：A Eager-Persistent vs B Late-Per-Query vs C Late-Persistent。

完整矩阵：Selectivity ∈ {1,5,10,25,50,75,100}% × Reuse ∈ {1,10,50,100}
两个工作负载模式：
  - PRED_SHARED  ：同一 cell 内所有 query 共享同一谓词（survivor 集相同）→ 测持久化复用的上限
  - PRED_DISTINCT：每个 query 使用独立的 hash 谓词（survivor 集互不嵌套）→ 测"谓词并集覆盖"边界

输出：完整矩阵结果、s×reuse 热力图数据、最终裁决。
固定项与 v1.2 一致（同一 Source Snapshot / Logical Plan / Capability 版本 / payload hash）。
"""
import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capability as CAP
from capability import CapabilityBuild, capability_version
from config import EXP_OUT, PRICING, SEED
from llm import count_tokens
from operators import op_filter, op_sem_count, op_sem_filter, op_sem_topk
from source_plane import materialize
import workload as WL

S_MATRIX = [1, 5, 10, 25, 50, 75, 100]
REUSE_MATRIX = [1, 10, 50, 100]
DOMAINS = ["ecom", "finproc"]
MODES = ["PRED_SHARED", "PRED_DISTINCT"]
CONSUMERS_BY_KIND = {"classification": [("SEM_COUNT", None), ("SEM_FILTER", None)],
                     "extraction": [("SEM_TOPK", 3)]}


def _consumer_for(cap_key, j):
    kind = "classification" if cap_key in WL.LABELS else "extraction"
    opts = CONSUMERS_BY_KIND[kind]
    return opts[j % len(opts)]


def salt_pred(salt, k):
    return {"op": "hash_lt_salted", "col": "row_id", "value": k, "salt": salt}


def survival(rows, pred):
    return [r for r in rows if _match(rows, pred, r)]


def _match(rows, pred, row):
    from operators import _pred_eval
    return _pred_eval(pred, row)


def oracle_answer(rows, consumer, cap_key):
    cap = CAP.CAPABILITIES[cap_key]
    gf, gv = cap["oracle_path"]
    if consumer[0] == "SEM_COUNT":
        label = _pick_label(rows, cap_key)
        return sum(1 for r in rows if r["oracle"][gf][gv] == label), label
    if consumer[0] == "SEM_FILTER":
        label = _pick_label(rows, cap_key)
        return sorted(r["row_id"] for r in rows if r["oracle"][gf][gv] == label), label
    k = consumer[1]
    srt = sorted(rows, key=lambda r: (r["oracle"][gf][gv] is None, -(r["oracle"][gf][gv] or 0)))
    return [r["row_id"] for r in srt[:k]], None


def _pick_label(rows, cap_key):
    gf, gv = CAP.CAPABILITIES[cap_key]["oracle_path"]
    counts = {}
    for r in rows:
        lb = r["oracle"][gf][gv]
        counts[lb] = counts.get(lb, 0) + 1
    if not counts:
        return CAP.CAPABILITIES[cap_key]["capability_id"]
    order = list(CAP.CAPABILITIES[cap_key]["oracle_path"])
    return max(counts, key=lambda l: counts[l])


def build_tokens(rows, cap_key, model_outputs_cache):
    """返回 (tokens_in, tokens_out, llm_calls) 的逻辑计数（不重复调用模型）。"""
    task = CAP.CAPABILITIES[cap_key]["task"]
    tmpl = CAP.PROMPT_TEMPLATE[task]
    tin = tout = 0
    for r in rows:
        key = (cap_key, r["payload_hash"])
        v = model_outputs_cache.get(key)
        if v is None:
            prompt = tmpl.format(payload=r["payload"])
            v = (count_tokens(prompt), 12)      # 单行 tokens（输出为 JSON ~12 tokens）
            model_outputs_cache[key] = v
        tin += v[0]
        tout += v[1]
    return tin, tout, len(rows)


def mock_cost(tin, tout, calls):
    return (tin / 1000) * PRICING["input_per_1k"] + (tout / 1000) * PRICING["output_per_1k"] \
        + calls * PRICING["per_call_overhead"]


def run_cell(rows, domain, s_pct, reuse, mode, cell_idx):
    """返回该 cell 的 A/B/C 三策略指标。"""
    k = max(1, int(round(s_pct / 100.0 * 1000)))          # hash 桶阈值
    build = CapabilityBuild(memo={})
    tok_cache = {}

    # 预生成查询（谓词 + consumer + oracle）
    queries = []
    for j in range(reuse):
        cap_key = "issue_classification" if (j % 2 == 0) else "amount_extraction_ecom"
        if domain == "finproc":
            cap_key = "clause_classification" if (j % 2 == 0) else "amount_extraction_fin"
        salt = cell_idx if mode == "PRED_SHARED" else cell_idx * 1000 + j
        pred = salt_pred(salt, k)
        surv = op_filter(rows, pred)
        consumer = _consumer_for(cap_key, j)
        oracle, label = oracle_answer(surv, consumer, cap_key)
        queries.append(dict(cap_key=cap_key, pred=pred, surv=surv, consumer=consumer,
                            oracle=oracle, label=label, salt=salt))

    res = {}

    # ---------- A: Eager-Persistent（全表构建一次并持久化，按所有 query 摊销）----------
    eager_rows = {ck: rows for ck in
                  {"issue_classification", "amount_extraction_ecom",
                   "clause_classification", "amount_extraction_fin"}}
    a_build_rows = a_tin = a_tout = a_calls = 0
    eager_caps = {}
    for q in queries:
        eager_caps.setdefault(q["cap_key"], rows)
    for ck in eager_caps:
        tin, tout, calls = build_tokens(rows, ck, tok_cache)
        a_build_rows += len(rows)
        a_tin += tin
        a_tout += tout
        a_calls += calls
    a_build_cost = mock_cost(a_tin, a_tout, a_calls)
    a_exec_cost = 0.0
    correct = 0
    for q in queries:
        outputs, _ = build.build(q["cap_key"], q["surv"])
        typed = _consume(q, outputs)
        ok = int(typed == q["oracle"])
        correct += ok
        a_exec_cost += 0.0001 + 0.0009      # 消费算子 + synthesis + 校验（每 query 固定）
    res["A"] = dict(build_rows=a_build_rows, tokens_in=a_tin, tokens_out=a_tout, llm_calls=a_calls,
                    build_cost=a_build_cost,
                    amortized_cost=(a_build_cost + a_exec_cost) / reuse,
                    total_cost=a_build_cost + a_exec_cost,
                    quality=correct / reuse)

    # ---------- B: Late-Per-Query（每 query 独立构建 survivor，无复用）----------
    b_rows = b_tin = b_tout = b_calls = 0
    b_cost = 0.0
    correct = 0
    for q in queries:
        tin, tout, calls = build_tokens(q["surv"], q["cap_key"], tok_cache)
        b_rows += len(q["surv"])
        b_tin += tin
        b_tout += tout
        b_calls += calls
        b_cost += mock_cost(tin, tout, calls) + 0.0001 + 0.0009
        outputs, _ = build.build(q["cap_key"], q["surv"])
        correct += int(_consume(q, outputs) == q["oracle"])
    res["B"] = dict(build_rows=b_rows, tokens_in=b_tin, tokens_out=b_tout, llm_calls=b_calls,
                    build_cost=b_cost - reuse * 0.001,
                    amortized_cost=b_cost / reuse, total_cost=b_cost, quality=correct / reuse)

    # ---------- C: Late-Persistent（survivor 构建后持久化，增量补齐缺失行）----------
    cache = {}                      # (cap_key, row_id) -> output
    c_rows = c_tin = c_tout = c_calls = 0
    c_build_cost = 0.0
    c_exec = 0.0
    correct = 0
    seen_union = set()
    for q in queries:
        missing = [r for r in q["surv"] if (q["cap_key"], r["row_id"]) not in cache]
        if missing:
            tin, tout, calls = build_tokens(missing, q["cap_key"], tok_cache)
            c_rows += len(missing)
            c_tin += tin
            c_tout += tout
            c_calls += calls
            c_build_cost += mock_cost(tin, tout, calls)
            outs, _ = build.build(q["cap_key"], missing)
            for r in missing:
                cache[(q["cap_key"], r["row_id"])] = outs[r["row_id"]]
        seen_union |= {r["row_id"] for r in q["surv"]}
        c_exec += 0.0001 + 0.0009
        outputs = {r["row_id"]: cache[(q["cap_key"], r["row_id"])] for r in q["surv"]}
        correct += int(_consume(q, outputs) == q["oracle"])
    res["C"] = dict(build_rows=c_rows, tokens_in=c_tin, tokens_out=c_tout, llm_calls=c_calls,
                    build_cost=c_build_cost, amortized_cost=(c_build_cost + c_exec) / reuse,
                    total_cost=c_build_cost + c_exec, quality=correct / reuse,
                    union_rows=len(seen_union))
    res["_cell"] = dict(domain=domain, s_pct=s_pct, reuse=reuse, mode=mode,
                        n=len(rows), survivors=len(queries[0]["surv"]),
                        union_rows=len(seen_union),
                        coverage=round(len(seen_union) / len(rows), 4),
                        capability_version=capability_version(queries[0]["cap_key"]))
    return res


def _consume(q, outputs):
    if q["consumer"][0] == "SEM_COUNT":
        return op_sem_count(q["surv"], outputs, q["label"])
    if q["consumer"][0] == "SEM_FILTER":
        return sorted(r["row_id"] for r in op_sem_filter(q["surv"], outputs, q["label"]))
    return [r["row_id"] for r in op_sem_topk(q["surv"], outputs, q["consumer"][1])]


def main():
    rows, snap = materialize()
    rows_by_domain = {"ecom": rows["ecom"], "finproc": rows["finproc"]}
    cells = []
    cell_idx = 0
    for domain in DOMAINS:
        for mode in MODES:
            for s in S_MATRIX:
                for reuse in REUSE_MATRIX:
                    cell_idx += 1
                    r = run_cell(rows_by_domain[domain], domain, s, reuse, mode, cell_idx)
                    r["_cell"]["cell_id"] = cell_idx
                    cells.append(r)
                    print(f"cell {cell_idx} {domain} {mode} s={s}% reuse={reuse} "
                          f"A={r['A']['amortized_cost']:.6f} B={r['B']['amortized_cost']:.6f} "
                          f"C={r['C']['amortized_cost']:.6f}")

    # ---- 汇总：热力图数据 + 裁决 ----
    heat = {}
    for r in cells:
        c = r["_cell"]
        heat[f"{c['domain']}|{c['mode']}|s{c['s_pct']}|r{c['reuse']}"] = dict(
            s=c["s_pct"], reuse=c["reuse"], coverage=c["coverage"],
            A=r["A"]["amortized_cost"], B=r["B"]["amortized_cost"], C=r["C"]["amortized_cost"],
            A_rows=r["A"]["build_rows"], B_rows=r["B"]["build_rows"], C_rows=r["C"]["build_rows"],
            C_over_A=round(r["C"]["amortized_cost"] / r["A"]["amortized_cost"], 4),
            C_over_B=round(r["C"]["amortized_cost"] / r["B"]["amortized_cost"], 4),
            quality_A=r["A"]["quality"], quality_B=r["B"]["quality"], quality_C=r["C"]["quality"],
        )
    # CSV（每个 domain×mode 一个矩阵）
    os.makedirs(EXP_OUT, exist_ok=True)
    csv_path = os.path.join(EXP_OUT, "exp1_heatmap.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("domain,mode,s_pct,reuse,coverage,A_amortized,B_amortized,C_amortized,"
                "C_over_A,C_over_B,A_rows,B_rows,C_rows,quality_A,quality_B,quality_C\n")
        for k, v in heat.items():
            dom, mode = k.split("|")[0], k.split("|")[1]
            f.write(f"{dom},{mode},{v['s']},{v['reuse']},{v['coverage']},{v['A']:.8f},"
                    f"{v['B']:.8f},{v['C']:.8f},{v['C_over_A']},{v['C_over_B']},{v['A_rows']},"
                    f"{v['B_rows']},{v['C_rows']},{v['quality_A']},{v['quality_B']},{v['quality_C']}\n")

    def agg(mode, key):
        vals = [v[key] for v in heat.values()
                if f"|{mode}|" in "" or True]
        return vals

    def stat(mode, field, dom=None):
        vals = [v[field] for k, v in heat.items()
                if f"|{mode}|" in k and (dom is None or k.startswith(dom))]
        return (min(vals), sum(vals) / len(vals), max(vals)) if vals else (None, None, None)

    verdict = {}
    for mode in MODES:
        ca = [v["C_over_A"] for k, v in heat.items() if f"|{mode}|" in k]
        cb = [v["C_over_B"] for k, v in heat.items() if f"|{mode}|" in k]
        cov = [v["coverage"] for k, v in heat.items() if f"|{mode}|" in k]
        verdict[mode] = dict(
            C_over_A_min=round(min(ca), 4), C_over_A_mean=round(sum(ca) / len(ca), 4),
            C_over_A_max=round(max(ca), 4),
            C_over_B_min=round(min(cb), 4), C_over_B_mean=round(sum(cb) / len(cb), 4),
            C_over_B_max=round(max(cb), 4),
            coverage_min=round(min(cov), 4), coverage_max=round(max(cov), 4),
            C_dominates_B=all(x <= 1.0001 for x in cb),
            C_dominates_A=all(x <= 1.0001 for x in ca),
        )

    # ---- 工作负载级口径（公平对比：执行整个 cell 集合的总成本）----
    workload_totals = {}
    for domain in DOMAINS:
        for mode in MODES:
            subset = [r for r in cells if r["_cell"]["domain"] == domain
                      and r["_cell"]["mode"] == mode]
            if not subset:
                continue
            # A：每域一次 eager 构建（各 cell 重复计入，需去重）；exec 逐 cell 累加
            a_build = max(r["A"]["build_cost"] for r in subset)
            a_exec = sum(r["A"]["total_cost"] - r["A"]["build_cost"] for r in subset)
            b_total = sum(r["B"]["total_cost"] for r in subset)
            c_build = sum(r["C"]["build_cost"] for r in subset)
            c_exec = sum(r["C"]["total_cost"] - r["C"]["build_cost"] for r in subset)
            c_total = c_build + c_exec
            a_total = a_build + a_exec
            workload_totals[f"{domain}|{mode}"] = dict(
                n_cells=len(subset),
                A=dict(build_rows=max(r["A"]["build_rows"] for r in subset),
                       build_cost=round(a_build, 8), total_cost=round(a_total, 8)),
                B=dict(build_rows=sum(r["B"]["build_rows"] for r in subset),
                       total_cost=round(b_total, 8)),
                C=dict(build_rows=sum(r["C"]["build_rows"] for r in subset),
                       build_cost=round(c_build, 8), total_cost=round(c_total, 8)),
                C_over_B_cost=round(c_total / b_total, 4),
                C_over_A_cost=round(c_total / a_total, 4),
                C_over_B_rows=round(sum(r["C"]["build_rows"] for r in subset) /
                                    max(1, sum(r["B"]["build_rows"] for r in subset)), 4),
                C_over_A_rows=round(sum(r["C"]["build_rows"] for r in subset) /
                                    max(1, max(r["A"]["build_rows"] for r in subset)), 4),
                avg_predicate_union_coverage=round(
                    sum(r["_cell"]["union_rows"] for r in subset) /
                    max(1, len(subset) * subset[0]["_cell"]["n"]), 4),
            )
    out = dict(snapshot=snap, matrix=dict(S=S_MATRIX, REUSE=REUSE_MATRIX, modes=MODES,
                                          domains=DOMAINS, n_rows_per_domain=len(rows["ecom"])),
               heatmap=heat, verdict=verdict, workload_totals=workload_totals,
               summary_quality=dict(
                   A=round(sum(r["A"]["quality"] for r in cells) / len(cells), 4),
                   B=round(sum(r["B"]["quality"] for r in cells) / len(cells), 4),
                   C=round(sum(r["C"]["quality"] for r in cells) / len(cells), 4),
                   note="mock 确定性模型下三策略输出逐 query 相同，质量恒等（结构性结论）"))
    with open(os.path.join(EXP_OUT, "exp1_matrix.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out["verdict"], ensure_ascii=False, indent=1))
    print("exp1 done -> exp1_matrix.json / exp1_heatmap.csv")
    return out


if __name__ == "__main__":
    main()
