# -*- coding: utf-8 -*-
"""v1.3 Experiment 1：Materialization Boundary（A / B / C / O）。

回答三件分开的事：
  C vs B → Capability Persistence 是否有独立价值
  C vs A → Late-Persistent 是否优于 Offline Eager（**不预设成立**）
  C vs O → 距理论最优的 regret
并拟合可解释边界模型：CostRatio ~ s + reuse + overlap + width + payload_len + scope。
"""
import argparse
import concurrent.futures as cf
import itertools
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

OUT = os.path.join(V.OUT, "experiment1_boundary")
S_LIST = [1, 5, 10, 25, 50, 75, 100]
R_LIST = [1, 10, 50, 100]
WIDTHS = [1, 2, 4]
SCOPES = ["WORKLOAD", "CAP_10PCT", "CELL"]
STRATS = ["A", "B", "C", "CBO", "D"]
FOCAL_S, FOCAL_R = [1, 10, 50, 100], [1, 10, 50, 100]
_W = {}


def _init():
    rows, snap = C.materialize()
    _W["rows"] = rows
    _W["snap"] = snap
    _W["unit"] = C.UnitCost().build(rows)


def scope_kw(scope, N, width):
    if scope == "WORKLOAD":
        return dict(), "workload-inf"
    if scope == "CELL":
        return dict(reset_per_query=True), "cell"
    if scope == "CAP_10PCT":
        return dict(scope_capacity=max(1, N * width // 10)), "cap-10pct"
    raise ValueError(scope)


def run_cell(domain, s, reuse, pattern, width, scope, want_trace=False):
    rows = _W["rows"][domain]
    unit = _W["unit"]
    caps = C.caps_for_breadth(domain, width)
    salt = C._h(f"v13|{domain}|{pattern}|{s}|{width}") % 100000
    qs = V.make_workload_v13(rows, s, reuse, pattern, caps, salt)
    kw, scope_label = scope_kw(scope, len(rows), len(caps))
    o = C.oracle(qs, rows, unit, sorted(set(caps)))
    res = {}
    for stg in STRATS:
        r = C.simulate(stg, qs, rows, unit, **kw)
        res[stg] = r["metrics"]
        if want_trace:
            res[stg + "_trace"] = r["per_query"]
    u_ids = [set(r["row_id"] for r in q["survivors"]) for q in qs]
    union = set().union(*u_ids) if u_ids else set()
    same = 0
    for i in range(len(u_ids)):
        for j in range(i + 1, len(u_ids)):
            same += len(u_ids[i] & u_ids[j])
    tot_pairs = max(1, sum(len(u) for u in u_ids))
    overlap = same / tot_pairs
    surv_len = st.mean([len(r["payload"]) for r in qs[0]["survivors"]]) if qs[0]["survivors"] else 0
    all_len = st.mean([len(r["payload"]) for r in rows])
    return dict(domain=domain, s=s, reuse=reuse, pattern=pattern, width=width, scope=scope,
                scope_label=scope_label, n_rows=len(rows), n_caps=len(caps),
                n_queries=len(qs), realized_s=st.mean([len(u) for u in u_ids]) / len(rows),
                union_rows=len(union), union_share=len(union) / len(rows),
                overlap_ratio=overlap,
                mean_survivor_payload_len=surv_len, mean_row_payload_len=all_len,
                oracle=o, strategies=res)


def row_of(c):
    od = c["oracle"]
    o = od["total_cost"]
    g = c["strategies"]
    cost = {k: g[k]["total_cost"] for k in STRATS}
    cost["O"] = o
    return dict(
        cell=f"{c['domain']}|s{c['s']}|r{c['reuse']}|{c['pattern']}|w{c['width']}|{c['scope']}",
        domain=c["domain"], s=c["s"], reuse=c["reuse"], pattern=c["pattern"], width=c["width"],
        scope=c["scope"], n_rows=c["n_rows"], n_caps=c["n_caps"],
        realized_s=round(c["realized_s"], 5), union_rows=c["union_rows"],
        union_share=round(c["union_share"], 6), overlap_ratio=round(c["overlap_ratio"], 6),
        mean_payload_len=round(c["mean_row_payload_len"], 2),
        survivor_payload_len=round(c["mean_survivor_payload_len"], 2),
        A=round(cost["A"], 6), B=round(cost["B"], 6), C=round(cost["C"], 6),
        CBO=round(cost["CBO"], 6), D=round(cost["D"], 6), O=round(o, 6),
        C_over_B=round(cost["C"] / cost["B"], 5), C_over_A=round(cost["C"] / cost["A"], 5),
        C_over_O=round(cost["C"] / o, 5), B_over_O=round(cost["B"] / o, 5),
        A_over_O=round(cost["A"] / o, 5),
        regret_C=round(C.regret(cost["C"], o), 5), regret_A=round(C.regret(cost["A"], o), 5),
        regret_B=round(C.regret(cost["B"], o), 5),
        logr_C_A=round(math.log(max(1e-12, cost["C"] / cost["A"])), 6),
        logr_C_B=round(math.log(max(1e-12, cost["C"] / cost["B"])), 6),
        tokens_A=g["A"]["semantic_tokens"], tokens_B=g["B"]["semantic_tokens"],
        tokens_C=g["C"]["semantic_tokens"], tokens_O=g["C"]["synthesis_cost"],
        rows_A=g["A"]["semantic_rows_built"], rows_B=g["B"]["semantic_rows_built"],
        rows_C=g["C"]["semantic_rows_built"],
        amort_A=round(g["A"]["cost_per_query"], 8), amort_B=round(g["B"]["cost_per_query"], 8),
        amort_C=round(g["C"]["cost_per_query"], 8), amort_O=round(od["cost_per_query"], 8),
        evictions_C=g["C"]["evictions"], cov_C=g["C"]["materialization_coverage"],
        quality_note="策略间质量恒定（同一 survivor → 同一 artifact → 同一答案）",
    )


def _task(job):
    c = run_cell(*job[:6], want_trace=(job[3] in V.PATTERNS_V13 and job[2] in FOCAL_R
                                       and job[1] in FOCAL_S and job[4] == 2
                                       and job[5] == "WORKLOAD"))
    key = f"{job[0]}|s{job[1]}|r{job[2]}|{job[3]}|w{job[4]}|{job[5]}"
    traces = []
    for stg in ("A", "B", "C"):
        for pq in c["strategies"].get(stg + "_trace", []):
            traces.append(dict(cell=key, strategy=stg, **pq))
    compact = dict(domain=c["domain"], s=c["s"], reuse=c["reuse"], pattern=c["pattern"],
                   width=c["width"], scope=c["scope"], caps=c["n_caps"],
                   realized_s=round(c["realized_s"], 5), union_share=round(c["union_share"], 6),
                   overlap_ratio=round(c["overlap_ratio"], 6),
                   mean_payload_len=round(c["mean_row_payload_len"], 2),
                   oracle={k: v for k, v in c["oracle"].items() if k != "per_capability"},
                   strategies={k: v for k, v in c["strategies"].items()
                               if not k.endswith("_trace")})
    return key, compact, row_of(c), traces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    S = S_LIST[:3] if args.quick else S_LIST
    R = R_LIST[:2] if args.quick else R_LIST
    Wd = [1, 2] if args.quick else WIDTHS
    Sc = ["WORKLOAD", "CELL"] if args.quick else SCOPES
    jobs = [(d, s, r, p, w, sc) for d in ["ecom", "finproc"]
            for s, r, p, w, sc in itertools.product(S, R, V.PATTERNS_V13, Wd, Sc)]
    t0 = time.time()
    _init()
    cells, rows, traces = {}, [], []
    with cf.ProcessPoolExecutor(max_workers=args.workers, initializer=_init) as ex:
        n = 0
        for key, comp, rw, tr in ex.map(_task, jobs, chunksize=4):
            cells[key] = comp
            rows.append(rw)
            traces.extend(tr)
            n += 1
            if n % 100 == 0 or n == len(jobs):
                print(f"[e1] {n}/{len(jobs)} cells {time.time()-t0:.0f}s", flush=True)
    # ---- 分组汇总
    def agg(sel, k):
        v = [r[k] for r in sel if r.get(k) is not None]
        return (round(st.mean(v), 5), round(min(v), 5), round(max(v), 5)) if v else (None,) * 3
    by_scope = {sc: dict(n=len([r for r in rows if r["scope"] == sc]),
                         C_over_B=agg([r for r in rows if r["scope"] == sc], "C_over_B"),
                         C_over_A=agg([r for r in rows if r["scope"] == sc], "C_over_A"),
                         C_over_O=agg([r for r in rows if r["scope"] == sc], "C_over_O"),
                         regret_C=agg([r for r in rows if r["scope"] == sc], "regret_C"))
                for sc in Sc}
    by_pattern = {p: dict(n=len([r for r in rows if r["pattern"] == p]),
                          C_over_B=agg([r for r in rows if r["pattern"] == p], "C_over_B"),
                          C_over_A=agg([r for r in rows if r["pattern"] == p], "C_over_A"),
                          overlap=agg([r for r in rows if r["pattern"] == p], "overlap_ratio"))
                  for p in V.PATTERNS_V13}
    by_s = {s: dict(n=len([r for r in rows if r["s"] == s]),
                    C_over_B=agg([r for r in rows if r["s"] == s], "C_over_B"),
                    C_over_A=agg([r for r in rows if r["s"] == s], "C_over_A"),
                    A_over_O=agg([r for r in rows if r["s"] == s], "A_over_O"))
            for s in S}
    by_width = {w: dict(n=len([r for r in rows if r["width"] == w]),
                        C_over_B=agg([r for r in rows if r["width"] == w], "C_over_B"),
                        C_over_A=agg([r for r in rows if r["width"] == w], "C_over_A"))
                for w in Wd}
    by_reuse = {r0: dict(n=len([r for r in rows if r["reuse"] == r0]),
                         C_over_B=agg([r for r in rows if r["reuse"] == r0], "C_over_B"),
                         C_over_A=agg([r for r in rows if r["reuse"] == r0], "C_over_A"))
                for r0 in R}
    # ---- 边界拟合（OLS，target = log(C_C / C_A)）
    fit_rows = [r for r in rows if r["C"] > 0 and r["A"] > 0]
    names = ["const", "log10_s", "log10_reuse", "overlap_ratio", "log2_width",
             "log10_payload_len", "is_CELL_scope", "is_CAP_scope"]
    X, y = [], []
    for r in fit_rows:
        scope_cap = 1.0 if r["scope"] == "CAP_10PCT" else 0.0
        X.append([1.0, math.log10(max(1e-9, r["realized_s"])), math.log10(max(1, r["reuse"])),
                  r["overlap_ratio"], math.log(max(1e-9, r["width"]), 2),
                  math.log10(max(1, r["mean_payload_len"])),
                  1.0 if r["scope"] == "CELL" else 0.0, scope_cap])
        y.append(r["logr_C_A"])
    model = V.ols(X, y, names)
    # 简化结构式预测器：C 优于 A  iff  可用容量份额 >= 需要并集份额
    pred_rows = []
    for r in fit_rows:
        cap_share = {"WORKLOAD": 1.0, "CAP_10PCT": 0.1, "CELL": 1.0 / max(1, r["reuse"])}[r["scope"]]
        pred_C = 1 if cap_share >= r["union_share"] else 0
        actual_C = 1 if r["C_over_A"] <= 1.0 else 0
        pred_rows.append(dict(cell=r["cell"], scope=r["scope"], reuse=r["reuse"],
                              union_share=r["union_share"], cap_share=cap_share,
                              pred_C_beats_A=pred_C, actual_C_beats_A=actual_C,
                              correct=int(pred_C == actual_C)))
    acc = sum(p["correct"] for p in pred_rows) / max(1, len(pred_rows))
    # 经典 k*s<c 形式：k=互斥谓词数（DISJOINT→reuse，否则 1），c=width
    ks_rows = []
    for r in fit_rows:
        k = r["reuse"] if r["pattern"] == "DISJOINT" else 1
        lhs = k * r["realized_s"]
        rhs = min(1.0, r["width"] * 0.5)   # eager 的成本尺度（相对全表覆盖的启发式上限）
        pred = 1 if lhs < rhs else 0
        ks_rows.append(dict(cell=r["cell"], k=k, s=r["realized_s"], c=r["width"], k_times_s=lhs,
                            rhs=rhs, pred_C_beats_A=pred,
                            actual_C_beats_A=1 if r["C_over_A"] <= 1.0 else 0,
                            correct=int(pred == (1 if r["C_over_A"] <= 1.0 else 0))))
    acc_ks = sum(x["correct"] for x in ks_rows) / max(1, len(ks_rows))
    results = dict(
        experiment="E1_materialization_boundary", experiment_id=V.new_experiment_id("e1"),
        tier="Tier 1 (deterministic mock mechanism result)",
        fixed_items=C.fixed_items_manifest(), snapshot=_W["snap"],
        matrix=dict(selectivity=S, reuse=R, patterns=V.PATTERNS_V13, widths=Wd, scopes=Sc,
                    strategies=STRATS + ["O"], n_cells=len(rows)),
        cells=cells, aggregates=dict(by_scope=by_scope, by_pattern=by_pattern, by_selectivity=by_s,
                                     by_width=by_width, by_reuse=by_reuse),
        boundary_model=model,
        structural_predictor=dict(name="capacity_share >= union_share", accuracy=round(acc, 4),
                                  n=len(pred_rows)),
        classical_form_predictor=dict(name="k*s < c（启发式 c=width*0.5）",
                                      accuracy=round(acc_ks, 4), n=len(ks_rows)),
        runtime_sec=round(time.time() - t0, 1))
    V.C.write_json(os.path.join(OUT, "results.json"), results)
    V.C.write_json(os.path.join(OUT, "config.json"), dict(
        experiment_id=results["experiment_id"], matrix=results["matrix"],
        fixed_items=results["fixed_items"],
        scope_defs=dict(WORKLOAD="跨查询无限持久（capability artifact store 无容量限制）",
                        CAP_10PCT="跨查询持久但容量 = N×width×10%（LRU 淘汰）",
                        CELL="每个 query 重置（等价于旧实验口径，模拟极短生命周期缓存）"),
        strategy_defs=dict(A="Eager Persistent：t=0 全表×全部能力构建并持久化",
                           B="Late Per Query：过滤后构建 survivor，不持久化",
                           C="Late Persistent：过滤后只构建缺失行并持久化",
                           CBO="PLOP-like 简单代价规划器（计划空间 {PerQuery, LatePersistent}）",
                           D="类 CBO + 覆盖度感知 Eager 分支（用于实验 3 对照）",
                           O="Clairvoyant oracle：逐能力可取 {Eager全表, 并集一次, 每查询重建} 的 min")))
    V.C.write_csv(os.path.join(OUT, "cost_curve.csv"), rows)
    V.C.write_csv(os.path.join(OUT, "boundary_fit.csv"), pred_rows + ks_rows)
    V.C.write_jsonl(os.path.join(OUT, "query_trace.jsonl"), traces)
    print(json.dumps(dict(n_cells=len(rows), by_scope={k: v["C_over_A"] for k, v in by_scope.items()},
                          model_r2=model["r2"] if model else None,
                          structural_acc=round(acc, 4), ks_acc=round(acc_ks, 4),
                          traces=len(traces), runtime=results["runtime_sec"]),
                     ensure_ascii=False, indent=1))
    return results


if __name__ == "__main__":
    main()
