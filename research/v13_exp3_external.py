# -*- coding: utf-8 -*-
"""v1.3 Experiment 3：Prior-Art Boundary + Lifecycle。

Tier 2（结构性 proxy baseline，**未运行任何原系统**）：
  QuWARTS-like   历史 workload → 离线 eager 物化 → 查询复用
  ReDD-like      查询专属 schema → 只填充所需字段（不跨查询持久化）
  PLOP-like      简单代价模型在 {Eager, Late, PerQuery} 中 argmin
  DASE-like      确定性高召回 prefilter → CapabilityBuild
Lifecycle：source drift 0/1/5/10/25% ×（全量重建 / 受影响行重建）+ unseen capability。
"""
import argparse
import itertools
import json
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C              # noqa: E402
import v13_common as V          # noqa: E402

OUT = os.path.join(V.OUT, "experiment3_external")
DRIFT_LEVELS = [0.0, 0.01, 0.05, 0.10, 0.25]


def build_demands(rows, unit, caps, specs):
    """specs: [(pattern, s_pct, reuse, salt)] → 展开为 demand 列表（每 demand = 一个 query）。"""
    out = []
    for pattern, s, reuse, salt in specs:
        out.extend(V.make_workload_v13(rows, s, reuse, pattern, caps, salt))
    return out


def cost_builds(rows_ids, caps, unit, per_field_frac=1.0):
    tot = 0.0
    n = 0
    for cap in caps:
        for rid in rows_ids:
            tot += unit.cost(cap, rid) * per_field_frac
            n += 1
    return tot, n


def run_workload(name, rows, unit, caps, demands, history_preds):
    """返回各策略的成本 / 数值指标。"""
    N = len(rows)
    ids = [r["row_id"] for r in rows]
    VW = C.PRICING["validation_per_row"]
    lookup, storage = C.PRICING["retrieval_per_row"], C.PRICING["retrieval_per_row"] * 0.5
    W = len(caps)
    res = {}

    # ---- Eager：t=0 全表 × 全部能力
    eager_cost, eager_rows = cost_builds(ids, caps, unit)
    eager_cost += eager_rows * VW
    res["Eager"] = dict(total_cost=round(eager_cost, 6), build_rows=eager_rows,
                        first_query_cost=None, amortized_per_query=round(eager_cost / max(1, len(demands)), 6),
                        materialized_share=1.0)

    # ---- Late-Persistent
    store = set()
    cost = 0.0
    built = 0
    first = None
    for d in demands:
        q = 0.0
        for cap in d["caps"]:
            for r in d["survivors"]:
                k = (cap, r["row_id"])
                if k in store:
                    q += lookup + storage
                else:
                    q += unit.cost(cap, r["row_id"]) + VW + lookup
                    store.add(k)
                    built += 1
        cost += q
        if first is None:
            first = q
    res["Late-Persistent"] = dict(total_cost=round(cost, 6), build_rows=built,
                                  first_query_cost=round(first or 0, 6),
                                  amortized_per_query=round(cost / max(1, len(demands)), 6),
                                  materialized_share=round(len(store) / max(1, N * W), 6))

    # ---- Per-Query（不持久化）
    cost, built = 0.0, 0
    first = None
    for d in demands:
        q, _ = cost_builds([r["row_id"] for r in d["survivors"]], d["caps"], unit)
        cost += q
        built += sum(len(d["survivors"]) for _ in d["caps"])
        if first is None:
            first = q
    res["Per-Query"] = dict(total_cost=round(cost, 6), build_rows=built,
                            first_query_cost=round(first or 0, 6),
                            amortized_per_query=round(cost / max(1, len(demands)), 6),
                            materialized_share=0.0)

    # ---- QuWARTS-like：从"历史 workload"离线物化，之后查询复用
    hist_ids, hist_rows = set(), 0
    for pred in history_preds:
        for r in C.op_filter(rows, pred):
            hist_ids.add(r["row_id"])
    off_cost, hist_rows = cost_builds(sorted(hist_ids), caps, unit)
    off_cost += hist_rows * VW
    store = {(cap, rid) for cap in caps for rid in hist_ids}
    cost = off_cost
    built = hist_rows
    first = None
    for d in demands:
        q = 0.0
        for cap in d["caps"]:
            for r in d["survivors"]:
                k = (cap, r["row_id"])
                if k in store:
                    q += lookup + storage
                else:
                    q += unit.cost(cap, r["row_id"]) + VW + lookup
                    store.add(k)
                    built += 1
        cost += q
        if first is None:
            first = q
    res["QuWARTS-like"] = dict(
        total_cost=round(cost, 6), build_rows=built, offline_build_cost=round(off_cost, 6),
        offline_rows=hist_rows, history_share=round(len(hist_ids) / N, 5),
        first_query_cost=round(first or 0, 6),
        amortized_per_query=round(cost / max(1, len(demands)), 6),
        materialized_share=round(len(store) / max(1, N * W), 6),
        is_proxy=True, note="结构性 proxy：历史 predicate 集合由本实验构造，非真实历史日志。")

    # ---- ReDD-like：查询专属 schema，只填充所需字段，不跨查询持久化
    cost, built = 0.0, 0
    first = None
    for d in demands:
        need_fields = max(1, len(d["caps"]))
        frac = need_fields / W           # 只支付所需字段的 token 成本
        q, n = cost_builds([r["row_id"] for r in d["survivors"]], d["caps"], unit,
                           per_field_frac=frac)
        cost += q
        built += n
        if first is None:
            first = q
    res["ReDD-like"] = dict(total_cost=round(cost, 6), build_rows=built,
                            first_query_cost=round(first or 0, 6),
                            amortized_per_query=round(cost / max(1, len(demands)), 6),
                            materialized_share=0.0, is_proxy=True,
                            note="结构性 proxy：query-specific schema + 只填充所需字段；未运行 ReDD 实现。")

    # ---- PLOP-like：代价模型在 {Eager, Late, PerQuery} 中 argmin（点估计，无前瞻）
    best = min(["Eager", "Late-Persistent", "Per-Query"],
               key=lambda k: res[k]["total_cost"])
    res["PLOP-like"] = dict(chosen=best, total_cost=res[best]["total_cost"],
                            amortized_per_query=res[best]["amortized_per_query"],
                            is_proxy=True,
                            note="结构性 proxy：简单代价模型 argmin；未运行 PLOP 实现。")

    # ---- DASE-like：确定性高召回 prefilter（含误召）后构建
    fp_rate = 0.10
    extra = 0
    fp_ids = set()
    for i, r in enumerate(sorted(rows, key=lambda x: C._h(x["row_id"]))):
        if i % int(1 / fp_rate) == 0:
            fp_ids.add(r["row_id"])
    late_cost = 0.0
    store = set()
    for d in demands:
        eff = {r["row_id"] for r in d["survivors"]} | fp_ids
        for cap in d["caps"]:
            for rid in eff:
                k = (cap, rid)
                if k in store:
                    late_cost += lookup + storage
                else:
                    late_cost += unit.cost(cap, rid) + VW + lookup
                    store.add(k)
                    extra += 1
    eager_ids = set()
    for d in demands:
        eager_ids |= {r["row_id"] for r in d["survivors"]}
    eager_ids |= fp_ids
    eager_d, eager_n = cost_builds(sorted(eager_ids), caps, unit)
    eager_d += eager_n * VW
    res["DASE-like"] = dict(prefilter_false_positive_rate=fp_rate,
                            total_cost=round(late_cost, 6),
                            amortized_per_query=round(late_cost / max(1, len(demands)), 6),
                            build_rows=extra,
                            late_after_prefilter=round(late_cost, 6),
                            eager_after_prefilter=round(eager_d, 6),
                            late_minus_eager=round(late_cost - eager_d, 6),
                            extra_rows_from_prefilter=extra, is_proxy=True,
                            note="结构性 proxy：确定性高召回 prefilter + CapabilityBuild。")
    res["Oracle"] = dict(total_cost=round(C.oracle(demands, rows, unit, sorted(set(caps)))["total_cost"], 6),
                         amortized_per_query=round(
                             C.oracle(demands, rows, unit, sorted(set(caps)))["cost_per_query"], 6))
    base = res["Oracle"]["total_cost"]
    for k, v in res.items():
        if isinstance(v, dict) and "total_cost" in v and v["total_cost"]:
            v["regret_vs_oracle"] = round((v["total_cost"] - base) / base, 5)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    rows_by_domain, snap = C.materialize()
    unit = C.UnitCost().build(rows_by_domain)
    ecom = rows_by_domain["ecom"]
    caps = C.NATIVE_CAPS["ecom"]
    t0 = time.time()

    # ---------- 三种工作负载（matched workload for prior-art comparison）
    hist = [{"col": "row_id", "op": "hash_lt", "value": 30}]      # 历史：3% 覆盖
    wl = {}
    wl["W1_cold_query_driven"] = dict(
        rows=ecom, caps=caps,
        demands=build_demands(ecom, unit, caps, [("OVERLAP", 2, 40, 11)]), history_preds=[])
    wl["W2_warm_high_reuse"] = dict(
        rows=ecom, caps=caps,
        demands=build_demands(ecom, unit, caps, [("NESTED", 40, 100, 22)]), history_preds=hist)
    wl["W3_mixed"] = dict(
        rows=ecom, caps=caps,
        demands=build_demands(ecom, unit, caps, [("OVERLAP", 3, 30, 33), ("DISJOINT", 2, 10, 44),
                                                 ("NESTED", 25, 50, 55)]), history_preds=hist)
    # ---------- W4 unseen capability：warm 阶段只用 1 个能力，随后突然引入第 2 个能力
    seen = [caps[0]]
    unseen_demands = (build_demands(ecom, unit, seen, [("OVERLAP", 3, 30, 66)])
                      + build_demands(ecom, unit, caps, [("OVERLAP", 3, 30, 66)]))
    wl["W4_unseen_capability"] = dict(rows=ecom, caps=caps, demands=unseen_demands,
                                      history_preds=hist)

    matrix, wl_results = [], {}
    for name, spec in wl.items():
        r = run_workload(name, spec["rows"], unit, spec["caps"], spec["demands"],
                         spec["history_preds"])
        wl_results[name] = r
        for strat, v in r.items():
            if isinstance(v, dict):
                matrix.append(dict(workload=name, strategy=strat, native_or_proxy=(
                    "proxy" if v.get("is_proxy") else "native"),
                    total_cost=v.get("total_cost"),
                    amortized_per_query=v.get("amortized_per_query"),
                    build_rows=v.get("build_rows"),
                    first_query_cost=v.get("first_query_cost"),
                    materialized_share=v.get("materialized_share"),
                    regret_vs_oracle=v.get("regret_vs_oracle"),
                    chosen=v.get("chosen")))
        print(f"[e3] workload {name} done", flush=True)

    # ---------- Source drift
    drift_rows = []
    N = len(ecom)
    ids_sorted = sorted([r["row_id"] for r in ecom], key=lambda x: C._h(x))
    union_ids = sorted({r["row_id"] for d in wl["W2_warm_high_reuse"]["demands"]
                        for r in d["survivors"]})
    for d_rate in DRIFT_LEVELS:
        n_aff = int(round(d_rate * len(union_ids)))
        affected = set(ids_sorted[:n_aff])
        full_cost, full_n = cost_builds([r["row_id"] for r in ecom], caps, unit)
        aff_hit = sorted(affected & set(union_ids))
        aff_cost, aff_n = cost_builds(aff_hit, caps, unit)
        stale_rows = len(affected) * len(caps)
        drift_rows.append(dict(drift_rate=d_rate, affected_rows=n_aff,
                               affected_in_materialized=n_aff, affected_share_of_union=round(
                                   len(aff_hit) / max(1, len(union_ids)), 5),
                               full_rebuild_cost=round(full_cost, 6),
                               affected_row_rebuild_cost=round(aff_cost, 6),
                               rebuild_ratio=round(aff_cost / full_cost, 5),
                               stale_rows_if_no_rebuild=stale_rows,
                               freshness_full=1.0,
                               freshness_incremental=1.0,
                               note="增量重建 = 只重建『受影响 ∧ 已被物化』的行；等价于 IVM。"))
    print(f"[e3] drift done", flush=True)

    # ---------- Unseen capability 冷启动
    unseen_rows = []
    r4 = wl_results["W4_unseen_capability"]
    for strat in ["Eager", "Late-Persistent", "QuWARTS-like", "ReDD-like"]:
        v = r4.get(strat, {})
        unseen_rows.append(dict(strategy=strat, total_cost=v.get("total_cost"),
                                amortized_per_query=v.get("amortized_per_query"),
                                first_query_cost=v.get("first_query_cost"),
                                build_rows=v.get("build_rows"),
                                native_or_proxy="proxy" if v.get("is_proxy") else "native",
                                note="新能力首次出现时：Eager 需整表重建；Late 只对 survivor 增量补齐。"))
    results = dict(
        experiment="E3_prior_art_boundary_and_lifecycle",
        experiment_id=V.new_experiment_id("e3"),
        tier="Tier 2（结构性 proxy）+ Tier 1（Lifecycle 机制）",
        snapshot=snap, fixed_items=C.fixed_items_manifest(),
        external_systems_run=[],
        note=("**未运行任何外部系统**。QuWARTS-like / ReDD-like / PLOP-like / DASE-like 均为"
              "结构性 proxy baseline，严禁表述为原论文系统实验。"),
        workloads=wl_results, baseline_matrix=matrix,
        source_drift=drift_rows, unseen_capability=unseen_rows,
        runtime_sec=round(time.time() - t0, 1))
    V.C.write_json(os.path.join(OUT, "results.json"), results)
    V.C.write_json(os.path.join(OUT, "config.json"), dict(
        experiment_id=results["experiment_id"], drift_levels=DRIFT_LEVELS,
        prefilter_false_positive_rate=0.10,
        proxy_defs=dict(QuWARTS_like="历史 workload → 离线 eager 物化 → 查询复用",
                        ReDD_like="查询专属 schema → 只填充所需字段（不跨查询持久化）",
                        PLOP_like="简单代价模型在 {Eager, Late, PerQuery} 中 argmin",
                        DASE_like="确定性高召回 prefilter（10% 误召）→ CapabilityBuild"),
        disclaimer="所有 *-like 结果均为结构性 proxy，不代表原系统性能。"))
    V.C.write_csv(os.path.join(OUT, "baseline_matrix.csv"), matrix)
    V.C.write_csv(os.path.join(OUT, "source_drift.csv"), drift_rows)
    V.C.write_csv(os.path.join(OUT, "unseen_capability.csv"), unseen_rows)
    print(json.dumps(dict(
        w1={k: v.get("total_cost") or v.get("chosen") for k, v in wl_results["W1_cold_query_driven"].items()},
        w2={k: v.get("total_cost") or v.get("chosen") for k, v in wl_results["W2_warm_high_reuse"].items()},
        w3={k: v.get("total_cost") or v.get("chosen") for k, v in wl_results["W3_mixed"].items()},
        w4={k: v.get("total_cost") or v.get("chosen") for k, v in wl_results["W4_unseen_capability"].items()},
        drift=[(r["drift_rate"], r["rebuild_ratio"]) for r in drift_rows],
        runtime=results["runtime_sec"]), ensure_ascii=False, indent=1))
    return results


if __name__ == "__main__":
    main()
