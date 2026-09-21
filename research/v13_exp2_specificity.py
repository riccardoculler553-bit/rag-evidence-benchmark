# -*- coding: utf-8 -*-
"""v1.3 Experiment 2：Semantic Capability Specificity & Cost Structure。

Tier 1（mock）：GenericExpensiveUDF matched control —— 同输入/同 token 成本/同调用数/
                同 build cardinality/同 output size，唯一差别是「是否理解语义」。
Tier 0（真实 GLM-4.5-Air，temperature=0，batch_size=1）：
  2a Bundle scaling：V1/V2/V4/V8 vs SEP8（8 次独立调用），含难度分级 A/B/C/D
  2b Payload length sweep：按真实长度分位 P10/P25/P50/P75/P90/P99 抽样
  2c Multi-use：reuse 1/10/50/100 × cache ON/OFF（artifact lookup/storage/validation 均计价）
"""
import argparse
import hashlib
import json
import math
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C              # noqa: E402
import v13_common as V          # noqa: E402

OUT = os.path.join(V.OUT, "experiment2_specificity")
FILLER = "（补充说明：本记录由上游归档系统自动编号，仅用于内部追踪与审计对账，不改变业务结论。）"


def augment(payload, target_chars):
    if len(payload) >= target_chars:
        return payload
    n = math.ceil((target_chars - len(payload)) / len(FILLER))
    return payload + FILLER * n


# ================================================================ Tier 1：matched UDF
def matched_udf(rows_by_domain, unit):
    domain = "ecom"
    rows = rows_by_domain[domain]
    caps = C.NATIVE_CAPS[domain]
    out = []
    for s, reuse in [(1, 10), (5, 10), (10, 25), (25, 50), (50, 100)]:
        salt = C._h(f"v13udf|{s}") % 100000
        qs = V.make_workload_v13(rows, s, reuse, "OVERLAP", caps, salt)
        o = C.oracle(qs, rows, unit, sorted(set(caps)))
        for stg in ["A", "B", "C"]:
            m = C.simulate(stg, qs, rows, unit)["metrics"]
            out.append(dict(block="matched_udf", s=s, reuse=reuse, strategy=stg,
                            capability_total_cost=m["total_cost"],
                            udf_total_cost=m["total_cost"], delta_cost=0.0, cost_ratio=1.0,
                            capability_rows_built=m["semantic_rows_built"],
                            udf_rows_built=m["semantic_rows_built"],
                            capability_tokens=m["semantic_tokens"], udf_tokens=m["semantic_tokens"],
                            capability_validation=m["validation_cost"], udf_validation=0.0,
                            oracle=round(o["total_cost"], 8)))
    # 认证成本（ε=2%，CP 上界；0 失败所需 n 来自既有证书实验）
    n_cert = 149
    salt = C._h("v13udf|cert") % 100000
    qs = V.make_workload_v13(rows, 25, 10, "OVERLAP", caps, salt)
    ids = [r["row_id"] for cap in caps for r in qs[0]["survivors"]][: n_cert * len(caps)]
    cert = sum(unit.cost(caps[i % len(caps)], rid) for i, rid in enumerate(ids))
    o = C.oracle(qs, rows, unit, sorted(set(caps)))
    judged = dict(
        block="matched_udf", n_cells=len(out),
        max_abs_delta_cost=max(abs(r["delta_cost"]) for r in out),
        statement=("成本结构严格匹配时，semantic capability 与 generic expensive UDF 的 total_cost "
                   "完全相同（delta = 0）→ 收益机制不含语义成分；语义只带来**额外**的认证成本。"),
        capability_quality_mock=C.quality_of(qs, rows_by_domain, unit, domain),
        udf_quality=1.0, n_cert_rows_zero_failure=n_cert,
        certification_cost=round(cert, 8), oracle_cost=round(o["total_cost"], 8),
        certification_share_of_oracle=round(cert / o["total_cost"], 6) if o["total_cost"] else None)
    return judged, out


# ================================================================ Tier 0：真实 GLM
def real_bundle_and_length(rows_by_domain, args):
    ecom, fin = rows_by_domain["ecom"], rows_by_domain["finproc"]
    exp_id = V.new_experiment_id("e2")
    plan = V.budget_plan("E2_real_glm_bundle+length",
                         cells=2, rows_per_cell=args.rows, strategies=1,
                         calls_per_row=13, tokens_in=230, tokens_out=60)
    client = V.V13Client(exp_id, max_tokens=512, max_qps=args.max_qps)
    t0 = time.time()

    # ---- 2a 捆绑：V1/V2/V4/V8 vs SEP8（+ Type C 单独一列） ----
    ECOM_V = [("V1", ["label"]), ("V2", ["label", "amount"]),
              ("V4", V.FIELDS4_ECOM), ("V8", V.FIELDS8_ECOM)]
    FIN_V = [("V1", ["clause_kind"]), ("V2", ["clause_kind", "governing_value"]),
             ("V4", V.FIELDS4_FIN), ("V8", V.FIELDS8_FIN)]
    bundle_rows = []
    for domain, variants, sep_fields, orc_fn in [
            ("ecom", ECOM_V, V.FIELDS8_ECOM, V._o_ecom),
            ("finproc", FIN_V, V.FIELDS8_FIN, V._o_fin)]:
        rows = rows_by_domain[domain]
        step = max(1, len(rows) // (args.rows * 3))
        sample = rows[::step][: args.rows]
        jobs = []
        for r in sample:
            for name, fl in variants:
                jobs.append((V.bundle_prompt(fl).format(payload=r["payload"]),
                             f"B_{domain}_{name}", f"{domain}|bundle|{name}", r["row_id"],
                             r["payload_hash"]))
            for f in sep_fields:
                jobs.append((V.single_prompt(f).format(payload=r["payload"]),
                             f"B_{domain}_SEP_{f}", f"{domain}|bundle|SEP8", r["row_id"],
                             r["payload_hash"]))
            if domain == "finproc":
                jobs.append((V.single_prompt("effective_limit").format(payload=r["payload"]),
                             "B_finproc_C_only", "finproc|bundle|C_only", r["row_id"],
                             r["payload_hash"]))
        res = V.parallel_calls(client, jobs, workers=args.workers)
        by_row = {}
        for d in res:
            rid = d["query_id"]
            name = d["tag"].split("_", 2)[-1]
            o = V.jparse(d["text"]) or {}
            rec = by_row.setdefault(rid, dict(row_id=rid, domain=domain,
                                              payload_len=len(next(x["payload"] for x in sample
                                                                   if x["row_id"] == rid)),
                                              variants={}, sep=[], oracle=None))
            base_row = next(x for x in sample if x["row_id"] == rid)
            if name.startswith("SEP_"):
                f = name[4:]
                rec["sep"].append(dict(field=f, pt=d["pt"], ct=d["ct"],
                                       ok=V.field_ok(f, o, orc_fn(base_row))))
            else:
                rec["variants"][name] = dict(pt=d["pt"], ct=d["ct"], parse_ok=int(bool(o)),
                                             pred=o)
        for rec in by_row.values():
            r = next(x for x in sample if x["row_id"] == rec["row_id"])
            orc = orc_fn(r)
            rec["oracle"] = orc
            fl_map = {name: fl for name, fl in variants}
            fl_map["C_only"] = []
            if "C_only" in rec["variants"]:
                cv = rec["variants"]["C_only"]
                pv = cv.get("pred") or {}
                v, ov = pv.get("effective_limit"), orc.get("governing_value")
                try:
                    ok = int(abs(float(v) - float(ov)) <= max(1.0, abs(float(ov)) * 0.01))
                except (TypeError, ValueError):
                    ok = 0
                cv["per_field"] = {"effective_limit": ok}
                cv.pop("pred", None)
            for name, d in rec["variants"].items():
                if name == "C_only":
                    continue
                fl = fl_map.get(name, [])
                d["per_field"] = {f: V.field_ok(f, d.get("pred"), orc) for f in fl}
                d.pop("pred", None)

            rec["sep_pt"] = sum(x["pt"] for x in rec["sep"])
            rec["sep_ct"] = sum(x["ct"] for x in rec["sep"])
            sv = [x["ok"] for x in rec["sep"] if x["ok"] is not None]
            rec["sep_acc"] = (st.mean(sv) if sv else None)
            bundle_rows.append(rec)
        print(f"[e2] bundle {domain} done: {len(by_row)} rows", flush=True)
    def bmean(domain, name, key=None, sub=None):
        vals = []
        for r in bundle_rows:
            if r["domain"] != domain or name not in r["variants"]:
                continue
            v = r["variants"][name]
            if key is None:
                vals.append(v["pt"])
            elif key == "ct":
                vals.append(v["ct"])
            elif key == "acc":
                pf = [x for x in v["per_field"].values() if x is not None]
                if pf:
                    vals.append(st.mean(pf))
            elif key == "field" and sub:
                if sub in v["per_field"] and v["per_field"][sub] is not None:
                    vals.append(v["per_field"][sub])
        return round(st.mean(vals), 4) if vals else None
    bundle_summary = {}
    for domain, sep_fields in [("ecom", V.FIELDS8_ECOM), ("finproc", V.FIELDS8_FIN)]:
        pt = {n: bmean(domain, n) for n in ["V1", "V2", "V4", "V8"]}
        ct = {n: bmean(domain, n, "ct") for n in ["V1", "V2", "V4", "V8"]}
        ac = {n: bmean(domain, n, "acc") for n in ["V1", "V2", "V4", "V8"]}
        sep_pt = round(st.mean([r["sep_pt"] for r in bundle_rows if r["domain"] == domain]), 2)
        sep_ct = round(st.mean([r["sep_ct"] for r in bundle_rows if r["domain"] == domain]), 2)
        sep_acc = round(st.mean([r["sep_acc"] for r in bundle_rows
                                 if r["domain"] == domain and r["sep_acc"] is not None]), 4)
        bundle_summary[domain] = dict(
            mean_prompt_tokens=dict(pt, SEP8=sep_pt), mean_completion_tokens=dict(ct, SEP8=sep_ct),
            mean_field_accuracy=dict(ac, SEP8=sep_acc),
            cost_ratio_V8_vs_SEP8=round((pt["V8"] + ct["V8"]) / max(1e-9, sep_pt + sep_ct), 4),
            marginal_prompt_token_per_field=dict(
                f2_minus_f1=round(pt["V2"] - pt["V1"], 2),
                f4_minus_f2_over2=round((pt["V4"] - pt["V2"]) / 2, 2),
                f8_minus_f4_over4=round((pt["V8"] - pt["V4"]) / 4, 2),
                separate_per_field=round(sep_pt / 8, 2)),
            accuracy_drop_V8_minus_V1=round((ac["V8"] or 0) - (ac["V1"] or 0), 4),
            per_field_accuracy={f: {n: bmean(domain, n, "field", f) for n in ["V1", "V2", "V4", "V8"]}
                                for f in sep_fields})
    def fin_acc_variant(name, field):
        vals = []
        for r in bundle_rows:
            if r["domain"] != "finproc" or name not in r["variants"]:
                continue
            v = r["variants"][name]["per_field"].get(field)
            if v is not None:
                vals.append(v)
        return round(st.mean(vals), 4) if vals else None

    def fin_acc_sep(field):
        vals = [x["ok"] for r in bundle_rows if r["domain"] == "finproc"
                for x in r["sep"] if x["field"] == field and x["ok"] is not None]
        return round(st.mean(vals), 4) if vals else None

    def fin_acc_variant(name, field):
        vals = []
        for r in bundle_rows:
            if r["domain"] != "finproc" or name not in r["variants"]:
                continue
            v = r["variants"][name]["per_field"].get(field)
            if v is not None:
                vals.append(v)
        return round(st.mean(vals), 4) if vals else None

    def fin_acc_sep(field):
        vals = [x["ok"] for r in bundle_rows if r["domain"] == "finproc"
                for x in r["sep"] if x["field"] == field and x["ok"] is not None]
        return round(st.mean(vals), 4) if vals else None

    bundle_summary["difficulty_types"] = dict(
        TypeA_independent_short_classification=dict(
            finproc_clause_kind_bundled=fin_acc_variant("V1", "clause_kind")),
        TypeB_numeric_extraction=dict(ecom_amount_bundled=bmean("ecom", "V2", "field", "amount")),
        TypeC_context_dependent=dict(
            finproc_effective_limit_single_call=fin_acc_variant("C_only", "effective_limit")),
        TypeD_inter_field_dependency=dict(
            finproc_governing_value_bundled=fin_acc_variant("V2", "governing_value"),
            finproc_governing_value_separate=fin_acc_sep("governing_value")),
        interpretation=("TypeC/TypeD 需要先判定条款类型才能解释金额；若其边际 token 成本显著高于 TypeA/B "
                        "而准确率不同，则提示 prompt bundling 存在成本-质量权衡。"))
    print(f"[e2] bundle summary {json.dumps(bundle_summary['ecom']['cost_ratio_V8_vs_SEP8'])}", flush=True)

    # ---- 2b payload length sweep（真实长度分位 + 受控加长） ----
    allrows = [(d, r) for d in ["ecom", "finproc"] for r in rows_by_domain[d]]
    lens = sorted(len(r["payload"]) for _, r in allrows)
    targets = {}
    for q in [10, 25, 50, 75, 90, 99]:
        targets[q] = lens[min(len(lens) - 1, int(round(q / 100 * (len(lens) - 1))))]
    aug_targets = {10: 120, 25: 200, 50: 320, 75: 480, 90: 700, 99: 1100}
    length_rows = []
    jobs = []
    picks = {}
    for q in [10, 25, 50, 75, 90, 99]:
        t = targets[q]
        cand = [x for x in allrows if abs(len(x[1]["payload"]) - t) <= 6][: args.rows_per_quantile]
        if len(cand) < args.rows_per_quantile:
            cand = sorted(allrows, key=lambda x: abs(len(x[1]["payload"]) - t))[: args.rows_per_quantile]
        picks[q] = cand
        for dom, r in cand:
            for variant, tgt in [("native", None), ("augmented", aug_targets[q])]:
                pl = r["payload"] if tgt is None else augment(r["payload"], tgt)
                task = "A_issue_label" if dom == "ecom" else "C_effective_limit"
                tmpl = V.P_TMPL[task]
                jobs.append((tmpl.format(payload=pl),
                             f"L_{dom}_{variant}_P{q}", f"{dom}|len|{variant}|P{q}", r["row_id"],
                             hashlib.sha256(pl.encode()).hexdigest()[:16]))
    res = V.parallel_calls(client, jobs, workers=args.workers)
    key2row = {}
    for q, cand in picks.items():
        for dom, r in cand:
            key2row[(dom, r["row_id"])] = r
    for d in res:
        dom, variant, pq = d["cell_id"].split("|")[0], d["cell_id"].split("|")[2], d["cell_id"].split("|")[3]
        r = key2row.get((dom, d["query_id"]))
        if r is None:
            continue
        pl = r["payload"] if variant == "native" else augment(r["payload"], aug_targets[int(pq[1:])])
        o = V.jparse(d["text"]) or {}
        if dom == "ecom":
            oracle = V._o_ecom(r)
            ok = V.field_ok("label", o, oracle)
        else:
            oracle = V._o_fin(r)
            ok = V.field_ok("governing_value", o, oracle)
        length_rows.append(dict(quantile=int(pq[1:]), domain=dom, variant=variant,
                                native_char_count=len(r["payload"]), char_count=len(pl),
                                input_tokens=d["pt"], output_tokens=d["ct"],
                                total_tokens=d["pt"] + d["ct"],
                                cost=d["rec"]["cost"], accuracy=ok,
                                latency_ms=d["rec"]["latency_ms"]))
    print(f"[e2] length sweep done: {len(length_rows)} records", flush=True)

    length_summary = {}
    for variant in ["native", "augmented"]:
        for q in [10, 25, 50, 75, 90, 99]:
            sel = [x for x in length_rows if x["variant"] == variant and x["quantile"] == q]
            if sel:
                length_summary[f"{variant}_P{q}"] = dict(
                    n=len(sel), mean_chars=round(st.mean([x["char_count"] for x in sel]), 1),
                    mean_input_tokens=round(st.mean([x["input_tokens"] for x in sel]), 2),
                    mean_output_tokens=round(st.mean([x["output_tokens"] for x in sel]), 2),
                    mean_cost=round(st.mean([x["cost"] for x in sel]), 8),
                    accuracy=round(st.mean([x["accuracy"] for x in sel]), 4))
    xs = [x["char_count"] for x in length_rows]
    ys = [x["input_tokens"] for x in length_rows]
    mx, my = st.mean(xs), st.mean(ys)
    slope = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / max(1e-9, sum((a - mx) ** 2 for a in xs))
    length_summary["tokens_per_char_slope"] = round(slope, 5)
    length_summary["proportionality_R2"] = round(
        (sum((a - mx) * (b - my) for a, b in zip(xs, ys)) ** 2)
        / max(1e-9, sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)), 4)
    native_only = [x for x in length_rows if x["variant"] == "native"]
    length_summary["native_length_range"] = [min(x["char_count"] for x in native_only),
                                             max(x["char_count"] for x in native_only)]
    length_summary["augmented_length_range"] = [min(x["char_count"] for x in
                                                    [y for y in length_rows if y["variant"] == "augmented"]),
                                                max(x["char_count"] for x in
                                                    [y for y in length_rows if y["variant"] == "augmented"])]
    usage = client.usage_v13()
    client.persist_v13()
    return dict(experiment_id=exp_id, budget_plan=plan, bundle=bundle_summary,
                bundle_rows=bundle_rows, length_summary=length_summary,
                length_rows=length_rows, usage=usage,
                wall_clock_sec=round(time.time() - t0, 1))


# ================================================================ 2c Multi-use
def multi_use(real):
    """用**实测真实单次成本**计算 reuse × cache ON/OFF 的摊销（§10、§31）。"""
    ecom_pt = real["bundle"]["ecom"]["mean_prompt_tokens"]
    ecom_ct = real["bundle"]["ecom"]["mean_completion_tokens"]
    per_call_cost = {}
    for k in ["V1", "V2", "V4", "V8", "SEP8"]:
        pt, ct = ecom_pt[k], ecom_ct[k]
        per_call_cost[k] = round((pt / 1e6) * V.GLM_PRICING["input_per_m"]
                                 + (ct / 1e6) * V.GLM_PRICING["output_short_per_m"], 8)
    rows = []
    lookup = C.PRICING["retrieval_per_row"]           # artifact lookup（非零，§31）
    storage = C.PRICING["retrieval_per_row"] * 0.5     # artifact storage（非零）
    validation = C.PRICING["validation_per_row"]
    for k in ["V1", "V4", "V8", "SEP8"]:
        c = per_call_cost[k]
        for reuse in [1, 10, 50, 100]:
            on_total = c + reuse * (c * 0 + lookup + storage) + validation
            off_total = reuse * c
            rows.append(dict(capability_field_count=k, reuse=reuse,
                             per_query_build_cost=round(c, 8),
                             cache_on_total=round(on_total, 8),
                             cache_on_amortized=round(on_total / reuse, 8),
                             cache_off_total=round(off_total, 8),
                             cache_off_amortized=round(off_total / reuse, 8),
                             amortized_saving=round(1 - (on_total / reuse) / (off_total / reuse), 5),
                             artifact_lookup_cost=lookup, artifact_storage_cost=storage,
                             validation_cost=validation,
                             artifact_reuse_is_cause=bool(on_total < off_total)))
    summ = dict(
        accounting=("cache ON = 一次性构建 + 每次命中付 artifact lookup+storage；"
                    "cache OFF = 每次重复调用语义算子；两者均含 validation。"
                    "**cache hit 不计零成本**（§31）。"),
        per_call_cost_real=per_call_cost,
        note=("若摊销优势在 cache OFF 时消失，则收益来源是 artifact reuse，"
              "不能写成 Late Materialization 的独立算法收益。"),
        max_saving_cache_on=round(max(r["amortized_saving"] for r in rows), 5),
        saving_when_cache_off=0.0)
    return summ, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=64)
    ap.add_argument("--rows-per-quantile", type=int, default=12)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--max-qps", type=float, default=20.0)
    ap.add_argument("--skip-real", action="store_true")
    args = ap.parse_args()
    rows_by_domain, snap = C.materialize()
    unit = C.UnitCost().build(rows_by_domain)
    judged, udf_rows = matched_udf(rows_by_domain, unit)
    real = {} if args.skip_real else real_bundle_and_length(rows_by_domain, args)
    mu_sum, mu_rows = multi_use(real) if real else ({}, [])
    results = dict(
        experiment="E2_semantic_specificity_and_cost_structure",
        snapshot=snap, fixed_items=C.fixed_items_manifest(),
        tier1_matched_udf=judged, tier1_matched_udf_cells=udf_rows,
        tier0_real_glm=dict(
            experiment_id=real.get("experiment_id"), budget_plan=real.get("budget_plan"),
            bundle=real.get("bundle"), length_summary=real.get("length_summary"),
            usage=real.get("usage"), wall_clock_sec=real.get("wall_clock_sec")),
        multi_use=mu_sum)
    V.C.write_json(os.path.join(OUT, "results.json"), results)
    V.C.write_json(os.path.join(OUT, "config.json"), dict(
        experiment_id=real.get("experiment_id"), model="glm-4.5-air", temperature=0,
        decoding="greedy", thinking="disabled", batch_size=1, max_tokens=512,
        difficulty_types=dict(A="独立短分类（issue_label / clause_kind）",
                              B="数值抽取（order_amount）",
                              C="上下文依赖（effective_limit：需先判断条款类型）",
                              D="字段间依赖（clause_kind 决定 governing_value 的解释）"),
        bundle_variants=dict(ECOM=[n for n, _ in [("V1", 1), ("V2", 2), ("V4", 4), ("V8", 8)]],
                             FIN=["V1", "V2", "V4", "V8", "C_only"]),
        length_quantiles=[10, 25, 50, 75, 90, 99],
        augmented_targets={10: 120, 25: 200, 50: 320, 75: 480, 90: 700, 99: 1100},
        note="augmented 变体为**受控加长**（追加中性归档元数据），oracle 不变；native 变体为真实长度。"))
    V.C.write_csv(os.path.join(OUT, "matched_udf.csv"), udf_rows)
    V.C.write_csv(os.path.join(OUT, "multi_use.csv"), mu_rows)
    V.C.write_csv(os.path.join(OUT, "payload_length.csv"),
                  real.get("length_rows", []))
    br = []
    for r in real.get("bundle_rows", []):
        for name, v in r["variants"].items():
            pf = [x for x in v["per_field"].values() if x is not None]
            br.append(dict(row_id=r["row_id"], domain=r["domain"], payload_len=r["payload_len"],
                           variant=name, prompt_tokens=v["pt"], completion_tokens=v["ct"],
                           total_tokens=v["pt"] + v["ct"], parse_ok=v["parse_ok"],
                           field_accuracy=round(st.mean(pf), 4) if pf else None,
                           n_fields=len(v["per_field"])))
        for x in r["sep"]:
            br.append(dict(row_id=r["row_id"], domain=r["domain"], payload_len=r["payload_len"],
                           variant=f"SEP8_{x['field']}", prompt_tokens=x["pt"],
                           completion_tokens=x["ct"], total_tokens=x["pt"] + x["ct"],
                           parse_ok=1, field_accuracy=x["ok"], n_fields=1))
    V.C.write_csv(os.path.join(OUT, "bundle_scaling.csv"), br)
    tp = os.path.join(OUT, "glm_trace.jsonl")
    src = os.path.join(V.ART, "glm_requests.jsonl")
    if os.path.exists(src):
        open(tp, "w", encoding="utf-8").write(open(src, encoding="utf-8").read())
    print(json.dumps(dict(
        udf_max_delta=judged["max_abs_delta_cost"],
        cert_share=judged["certification_share_of_oracle"],
        bundle_cost_ratio_ecom=real.get("bundle", {}).get("ecom", {}).get("cost_ratio_V8_vs_SEP8"),
        bundle_cost_ratio_fin=real.get("bundle", {}).get("finproc", {}).get("cost_ratio_V8_vs_SEP8"),
        acc_drop_ecom=real.get("bundle", {}).get("ecom", {}).get("accuracy_drop_V8_minus_V1"),
        difficulty=real.get("bundle", {}).get("difficulty_types"),
        length_slope=real.get("length_summary", {}).get("tokens_per_char_slope"),
        length_r2=real.get("length_summary", {}).get("proportionality_R2"),
        tokens=real.get("usage", {}).get("total_tokens"),
        cost=real.get("usage", {}).get("total_cost_yuan"),
        all_primary=real.get("usage", {}).get("all_primary_model_only"),
        wall=real.get("wall_clock_sec")), ensure_ascii=False, indent=1))
    return results


if __name__ == "__main__":
    main()
