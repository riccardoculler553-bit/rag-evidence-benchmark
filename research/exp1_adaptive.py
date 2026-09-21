# -*- coding: utf-8 -*-
"""最终实验 1：Adaptive Semantic Materialization（Zero-token / deterministic-mock）。

问题：是否存在一个**不使用 oracle、不访问未来** 的 workload-aware 策略，
能在 selectivity × reuse × predicate-pattern × capability-breadth 下自动选择
Eager / Late-Persistent / Per-Query，并逼近离线 oracle 最优成本？

同时回答 F1–F4：
  F1/F2  Adaptive 是否只是"简单 cost model + 传统物化选择"（CBO）？
  F3     结果是否只由 selectivity × reuse 解释？
  F4     oracle 与普通启发式的差距是否很小？

实现：单元级多进程并行（每个 worker 各持一份只读 unit 表，数值语义完全一致）。
"""
import argparse
import concurrent.futures as cf
import itertools
import json
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402

OUT = os.path.join(HERE, "experiment1_adaptive")

S_LIST = [1, 5, 10, 25, 50, 75, 100]
REUSE_LIST = [1, 10, 50, 100]
BREADTH = [1, 2, 4]
DOMAINS = ["ecom", "finproc"]
STRATEGIES = ["A", "B", "C", "CBO", "D"]
SCOPE_SLICE = dict(s=[1, 10, 50, 100], reuse=[1, 10, 50, 100], breadth=[2])
FOCAL_S = [1, 10, 50, 100]
FOCAL_R = [1, 10, 50, 100]

_W = {}


def _init_worker():
    rows, snap = C.materialize()
    _W["rows"] = rows
    _W["snap"] = snap
    _W["unit"] = C.UnitCost().build(rows)


def run_cell(rows, unit, domain, s, reuse, pattern, c, salt, want_trace=False):
    caps = C.caps_for_breadth(domain, c)
    queries = C.make_workload(rows, s, reuse, pattern, caps, domain, salt)
    realized = st.mean([len(q["survivors"]) for q in queries]) / len(rows)
    o = C.oracle(queries, rows, unit, sorted(set(caps)))
    res = {}
    for strat in STRATEGIES:
        r = C.simulate(strat, queries, rows, unit)
        res[strat] = r["metrics"]
        if want_trace:
            res[strat + "_trace"] = r["per_query"]
            res[strat + "_decisions"] = r["decisions"]
    r_dp = C.simulate("D", queries, rows, unit, adaptive_opts=dict(privileged_horizon=reuse))
    res["D_plus"] = r_dp["metrics"]
    return dict(caps=caps, realized_s=realized, oracle=o,
                union_share=o["unique_rows_built"] / max(1, len(rows) * len(caps)),
                n_rows=len(rows), strategies=res, n_queries=len(queries))


def cell_row(key, domain, s, reuse, pattern, c, cell):
    o = cell["oracle"]["total_cost"]
    stg = cell["strategies"]
    costs = {k: stg[k]["total_cost"] for k in STRATEGIES}
    costs["O"] = o
    best = min(costs, key=lambda k: costs[k])
    dec = stg.get("D_decisions", [])
    return dict(cell=key, domain=domain, s=s, reuse=reuse, pattern=pattern, breadth=c,
                realized_selectivity=round(cell["realized_s"], 5),
                union_share=round(cell["union_share"], 6),
                n_queries=cell["n_queries"],
                A=round(costs["A"], 6), B=round(costs["B"], 6), C=round(costs["C"], 6),
                CBO=round(costs["CBO"], 6), D=round(costs["D"], 6), O=round(o, 6),
                D_plus=round(stg["D_plus"]["total_cost"], 6), optimal=best,
                regret_D=round(C.regret(costs["D"], o), 5),
                regret_CBO=round(C.regret(costs["CBO"], o), 5),
                regret_D_plus=round(C.regret(stg["D_plus"]["total_cost"], o), 5),
                regret_C=round(C.regret(costs["C"], o), 5),
                regret_A=round(C.regret(costs["A"], o), 5),
                regret_B=round(C.regret(costs["B"], o), 5),
                C_over_A=round(costs["C"] / costs["A"], 4),
                C_over_B=round(costs["C"] / costs["B"], 4),
                D_over_CBO=round(costs["D"] / costs["CBO"], 4),
                D_over_O=round(costs["D"] / o, 4),
                A_over_O=round(costs["A"] / o, 4), B_over_O=round(costs["B"] / o, 4),
                union_rows=cell["oracle"]["unique_rows_built"],
                semantic_rows_A=stg["A"]["semantic_rows_built"],
                semantic_rows_B=stg["B"]["semantic_rows_built"],
                semantic_rows_C=stg["C"]["semantic_rows_built"],
                semantic_rows_D=stg["D"]["semantic_rows_built"],
                tokens_A=stg["A"]["semantic_tokens"], tokens_D=stg["D"]["semantic_tokens"],
                switches_D=sum(1 for a, b in zip(dec, dec[1:]) if a["plan"] != b["plan"]) if dec else None,
                plan_hist_D={k: sum(1 for d in dec if d.get("plan") == k)
                             for k in ("EAGER", "LATE_PERSIST", "PER_QUERY")},
                p95_A=stg["A"]["p95_ms"], p95_D=stg["D"]["p95_ms"])


def _task(job):
    domain, s, reuse, pattern, c = job
    rows = _W["rows"][domain]
    unit = _W["unit"]
    salt = C._h(f"{domain}|{pattern}|{s}") % 100000
    focal = (c == 2 and s in FOCAL_S and reuse in FOCAL_R)
    cell = run_cell(rows, unit, domain, s, reuse, pattern, c, salt, want_trace=focal)
    key = f"{domain}|s{s}|r{reuse}|{pattern}|c{c}"
    row = cell_row(key, domain, s, reuse, pattern, c, cell)
    traces = []
    if focal:
        for strat in ("A", "B", "C", "D", "CBO"):
            for pq in cell["strategies"].get(strat + "_trace", []):
                traces.append(dict(cell=key, strategy=strat, **pq))
        for d in cell["strategies"].get("D_decisions", []):
            traces.append(dict(cell=key, strategy="D_DECISION", **d))
    compact = dict(domain=domain, s=s, reuse=reuse, pattern=pattern, breadth=c,
                   caps=cell["caps"], realized_selectivity=round(cell["realized_s"], 5),
                   oracle={k: v for k, v in cell["oracle"].items() if k != "per_capability"},
                   strategies={k: v for k, v in cell["strategies"].items()
                               if not k.endswith("_trace") and not k.endswith("_decisions")})
    return key, compact, row, traces


def _scope_task(job):
    domain, s, reuse, pattern, c = job
    rows = _W["rows"][domain]
    unit = _W["unit"]
    caps = C.caps_for_breadth(domain, c)
    salt = C._h(f"{domain}|{pattern}|{s}") % 100000
    queries = C.make_workload(rows, s, reuse, pattern, caps, domain, salt)
    N = len(rows)
    A = C.simulate("A", queries, rows, unit)["metrics"]["total_cost"]
    work = C.simulate("C", queries, rows, unit)["metrics"]["total_cost"]
    percell = C.simulate("C", queries, rows, unit, reset_per_query=True)["metrics"]["total_cost"]
    # 真正的容量消融：store 跨查询持久，但容量受限 → LRU 抖动
    lru10 = C.simulate("C", queries, rows, unit,
                       scope_capacity=max(1, N * len(caps) // 10))["metrics"]
    lru1 = C.simulate("C", queries, rows, unit,
                      scope_capacity=max(1, N * len(caps) // 100))["metrics"]
    b10, b100 = lru10["total_cost"], lru1["total_cost"]
    return dict(domain=domain, s=s, reuse=reuse, pattern=pattern, breadth=c, A=round(A, 6),
                C_workload_scope=round(work, 6), C_cell_scope=round(percell, 6),
                C_lru_10pct=round(b10, 6), C_lru_1pct=round(b100, 6),
                ratio_workload=round(work / A, 4), ratio_cell=round(percell / A, 4),
                ratio_lru_10pct=round(b10 / A, 4), ratio_lru_1pct=round(b100 / A, 4),
                evictions_lru_10pct=lru10["evictions"], evictions_lru_1pct=lru1["evictions"],
                rows_rebuilt_lru_1pct=lru1["semantic_rows_built"])


def _agg(rows, field):
    v = [r[field] for r in rows if r[field] is not None]
    if not v:
        return {}
    return dict(mean=round(st.mean(v), 5), min=round(min(v), 5), max=round(max(v), 5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", default="full")
    ap.add_argument("--scope-only", action="store_true")
    args = ap.parse_args()

    S, R = (S_LIST[:3], REUSE_LIST[:2]) if args.quick else (S_LIST, REUSE_LIST)
    breadth = [1, 2] if args.quick else BREADTH
    patterns = C.PATTERNS
    slice_s = [1, 10] if args.quick else SCOPE_SLICE["s"]
    slice_r = [1, 2] if args.quick else SCOPE_SLICE["reuse"]
    slice_c = 1 if args.quick else 2

    jobs = [(d, s, r, p, c) for d in DOMAINS for s, r, p, c in
            itertools.product(S, R, patterns, breadth)]
    scope_jobs = [(d, s, r, p, c) for d in DOMAINS for s, r, p, c in
                  itertools.product(slice_s, slice_r, patterns, [slice_c])]

    t0 = time.time()
    _init_worker()          # 主进程也持一份（用于 quick 路径/调试）
    if args.scope_only:
        scope_rows = [_scope_task(j) for j in scope_jobs]
        C.write_csv(os.path.join(OUT, "scope_ablation.csv"), scope_rows)
        rp = os.path.join(OUT, "results.json")
        if os.path.exists(rp):
            res = json.load(open(rp, encoding="utf-8"))
            res["scope_ablation"] = scope_rows
            res["scope_ablation_note"] = ("口径：workload=跨查询无限持久；cell=每 query 重置（旧实验口径）；"
                                          "lru_10pct/1pct=跨查询持久但容量受限（LRU 抖动）")
            C.write_json(rp, res)
        import statistics as _st
        for k in ["ratio_workload", "ratio_cell", "ratio_lru_10pct", "ratio_lru_1pct"]:
            v = [r[k] for r in scope_rows]
            print(f"{k}: mean={_st.mean(v):.4f} min={min(v):.4f} max={max(v):.4f}", flush=True)
        return None
    cells, cell_rows, traces = {}, [], []
    with cf.ProcessPoolExecutor(max_workers=args.workers,
                                initializer=_init_worker) as ex:
        done = 0
        for key, compact, row, tr in ex.map(_task, jobs, chunksize=4):
            cells[key] = compact
            cell_rows.append(row)
            traces.extend(tr)
            done += 1
            if done % 60 == 0 or done == len(jobs):
                print(f"[exp1] {done}/{len(jobs)} cells  {time.time()-t0:.0f}s", flush=True)
    scope_rows = []
    with cf.ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker) as ex:
        for r in ex.map(_scope_task, scope_jobs, chunksize=4):
            scope_rows.append(r)
    print(f"[exp1] all done in {time.time()-t0:.0f}s", flush=True)

    by_pattern = {p: dict(n=len([r for r in cell_rows if r["pattern"] == p]),
                          regret_D=_agg([r for r in cell_rows if r["pattern"] == p], "regret_D"),
                          regret_CBO=_agg([r for r in cell_rows if r["pattern"] == p], "regret_CBO"),
                          C_over_A=_agg([r for r in cell_rows if r["pattern"] == p], "C_over_A"),
                          union_rows=_agg([r for r in cell_rows if r["pattern"] == p], "union_rows"))
                  for p in patterns}
    by_breadth = {c: dict(n=len([r for r in cell_rows if r["breadth"] == c]),
                          regret_D=_agg([r for r in cell_rows if r["breadth"] == c], "regret_D"),
                          regret_CBO=_agg([r for r in cell_rows if r["breadth"] == c], "regret_CBO"),
                          D_over_O=_agg([r for r in cell_rows if r["breadth"] == c], "D_over_O"))
                  for c in breadth}
    by_selectivity = {s: dict(n=len([r for r in cell_rows if r["s"] == s]),
                              C_over_A=_agg([r for r in cell_rows if r["s"] == s], "C_over_A"),
                              regret_D=_agg([r for r in cell_rows if r["s"] == s], "regret_D"),
                              A_over_O=_agg([r for r in cell_rows if r["s"] == s], "A_over_O"))
                      for s in S}
    opt_counts = {}
    for r in cell_rows:
        opt_counts[r["optimal"]] = opt_counts.get(r["optimal"], 0) + 1
    d_over_cbo = [r["D_over_CBO"] for r in cell_rows]
    results = dict(
        experiment="E1_adaptive_semantic_materialization",
        backend="deterministic-mock-semantic (zero-token)",
        fixed_items=C.fixed_items_manifest(), snapshot=_W["snap"],
        matrix=dict(domains=DOMAINS, selectivity=S, reuse=R, patterns=patterns,
                    breadth=breadth, strategies=STRATEGIES + ["O", "D_plus"],
                    n_cells=len(cell_rows), workers=args.workers),
        cells=cells,
        aggregates=dict(
            by_pattern=by_pattern, by_breadth=by_breadth, by_selectivity=by_selectivity,
            optimal_label_counts=opt_counts,
            regret_D_overall=_agg(cell_rows, "regret_D"),
            regret_CBO_overall=_agg(cell_rows, "regret_CBO"),
            regret_D_plus_overall=_agg(cell_rows, "regret_D_plus"),
            regret_C_overall=_agg(cell_rows, "regret_C"),
            regret_A_overall=_agg(cell_rows, "regret_A"),
            regret_B_overall=_agg(cell_rows, "regret_B"),
            C_over_A_overall=_agg(cell_rows, "C_over_A"),
            C_over_B_overall=_agg(cell_rows, "C_over_B"),
            D_over_CBO=_agg(cell_rows, "D_over_CBO"),
            D_over_O=_agg(cell_rows, "D_over_O"),
            A_over_O=_agg(cell_rows, "A_over_O"), B_over_O=_agg(cell_rows, "B_over_O"),
            d_vs_cbo=dict(n=len(d_over_cbo),
                          strictly_better=sum(1 for x in d_over_cbo if x < 1 - 1e-9),
                          equal=sum(1 for x in d_over_cbo if abs(x - 1) <= 1e-9),
                          strictly_worse=sum(1 for x in d_over_cbo if x > 1 + 1e-9),
                          mean_ratio=round(st.mean(d_over_cbo), 5)),
            plan_hist_D_aggregate={k: sum(r["plan_hist_D"][k] for r in cell_rows)
                                   for k in ("EAGER", "LATE_PERSIST", "PER_QUERY")},
        ),
        scope_ablation=scope_rows, runtime_sec=round(time.time() - t0, 1),
    )
    C.write_json(os.path.join(OUT, "results.json"), results)
    C.write_json(os.path.join(OUT, "config.json"), dict(
        matrix=results["matrix"], fixed_items=results["fixed_items"],
        note="策略均为调度决策；prompt/schema/parser/价格/快照/模型全部固定。",
        strategy_defs=dict(
            A="Eager-Persistent：t=0 全表×全部能力构建并持久化",
            B="Late-Per-Query：过滤后构建 survivor，不持久化",
            C="Late-Persistent：过滤后仅构建存储中缺失的行并持久化",
            CBO="Simple CBO：点估计期望成本最小化（规划空间仅 {PER_QUERY, LATE_PERSIST}）",
            D="Adaptive：CBO 估计器 + 覆盖度感知 EAGER 分支 + 滞后",
            D_plus="诊断组：额外知道真实 R（视界），仅用于分离「未知视界」与「估计误差」，不作为方法主张",
            O="离线 clairvoyant oracle：逐能力在 {EAGER, 并集一次, 每查询重建} 中取 min")))
    C.write_csv(os.path.join(OUT, "workload.csv"), cell_rows)
    C.write_jsonl(os.path.join(OUT, "traces.jsonl"), traces)
    C.write_csv(os.path.join(OUT, "scope_ablation.csv"), scope_rows)

    curve = []
    for s, reuse in itertools.product(S, R):
        sel = [r for r in cell_rows if r["s"] == s and r["reuse"] == reuse]
        curve.append(dict(s=s, reuse=reuse, n_cells=len(sel),
                          A=round(st.mean([r["A"] for r in sel]), 6),
                          B=round(st.mean([r["B"] for r in sel]), 6),
                          C=round(st.mean([r["C"] for r in sel]), 6),
                          CBO=round(st.mean([r["CBO"] for r in sel]), 6),
                          D=round(st.mean([r["D"] for r in sel]), 6),
                          O=round(st.mean([r["O"] for r in sel]), 6),
                          regret_D=round(st.mean([r["regret_D"] for r in sel]), 5),
                          regret_CBO=round(st.mean([r["regret_CBO"] for r in sel]), 5),
                          C_over_A=round(st.mean([r["C_over_A"] for r in sel]), 4),
                          C_over_B=round(st.mean([r["C_over_B"] for r in sel]), 4),
                          D_over_CBO=round(st.mean([r["D_over_CBO"] for r in sel]), 4)))
    C.write_csv(os.path.join(OUT, "cost_curve.csv"), curve)

    print(json.dumps(dict(n_cells=len(cell_rows), optimal=opt_counts,
                          regret_D=results["aggregates"]["regret_D_overall"],
                          regret_CBO=results["aggregates"]["regret_CBO_overall"],
                          d_vs_cbo=results["aggregates"]["d_vs_cbo"],
                          C_over_A=results["aggregates"]["C_over_A_overall"],
                          C_over_B=results["aggregates"]["C_over_B_overall"],
                          plan_hist=results["aggregates"]["plan_hist_D_aggregate"],
                          traces=len(traces), runtime_s=results["runtime_sec"]),
                     ensure_ascii=False, indent=1))
    return results


if __name__ == "__main__":
    main()
