# -*- coding: utf-8 -*-
"""最终实验 3：External Baseline + Prior-Art Boundary（zero-token）。

  A. Baseline-0..4（Naive / Eager / Late-Persistent / Simple CBO / Adaptive）+ Oracle
  B. 三种匹配工作负载：A_QueryDriven / B_BatchAnalytics / C_Mixed
  C. Source Drift 0/1/5/10/25%：Eager 全量重建 vs Late-Persistent 受影响行重建 vs Adaptive
     并额外量化"句法缓存键过度失效"（语义等价改写 → answer 不变但 payload_hash 变）
"""
import argparse
import itertools
import json
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402

OUT = os.path.join(HERE, "experiment3_external_baseline")
E1 = os.path.join(HERE, "experiment1_adaptive")
E2 = os.path.join(HERE, "experiment2_semantic_specificity")

BASELINES = dict(B0_naive_per_query="B", B1_eager_persistent="A", B2_late_persistent="C",
                 B3_simple_cbo="CBO", B4_adaptive="D")


# ================================================================ A
def baselines_from_exp1():
    p = os.path.join(E1, "workload.csv")
    if not os.path.exists(p):
        return {}
    import csv
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    for r in rows:
        for k in ["A", "B", "C", "CBO", "D", "O", "D_plus", "regret_D", "regret_CBO",
                  "regret_C", "regret_A", "regret_B", "realized_selectivity", "s", "reuse",
                  "breadth", "union_rows"]:
            if k in r and r[k] not in (None, ""):
                try:
                    r[k] = float(r[k])
                except ValueError:
                    pass
    def agg(sel, key):
        v = [r[key] for r in sel if isinstance(r.get(key), float)]
        return dict(mean=round(st.mean(v), 5), min=round(min(v), 5), max=round(max(v), 5)) if v else {}
    out = {}
    for name, strat in BASELINES.items():
        out[name] = dict(strategy=strat, cost=agg(rows, strat),
                         regret=agg(rows, f"regret_{strat}"))
        # 该 baseline 成为最优（含 oracle）的 cell 占比
        best = 0
        for r in rows:
            costs = {k: r[k] for k in ["A", "B", "C", "CBO", "D", "O"] if isinstance(r.get(k), float)}
            if costs and min(costs, key=lambda k: costs[k]) == strat:
                best += 1
        out[name]["win_rate_over_cells"] = round(best / max(1, len(rows)), 4)
    oracle_wins = 0
    for r in rows:
        costs = {k: r[k] for k in ["A", "B", "C", "CBO", "D", "O"] if isinstance(r.get(k), float)}
        if costs and min(costs, key=lambda k: costs[k]) == "O":
            oracle_wins += 1
    out["O_oracle"] = dict(strategy="O", win_rate_over_cells=round(oracle_wins / max(1, len(rows)), 4))
    # C 与 O 的差距（无限存储下 clairvoyant-late 的理论等价性检验）
    eq = [abs(r["C"] - r["O"]) <= max(1e-9, 1e-6 * r["O"]) for r in rows if isinstance(r.get("C"), float)]
    out["C_equals_oracle_share"] = round(sum(eq) / max(1, len(eq)), 4)
    out["n_cells"] = len(rows)
    return out


# ================================================================ B
def build_workloads(rows_by_domain):
    """三种工作负载（同一 fixed items，只改 workload 形状）。"""
    ecom, fin = rows_by_domain["ecom"], rows_by_domain["finproc"]
    caps_e, caps_f = C.NATIVE_CAPS["ecom"], C.NATIVE_CAPS["finproc"]

    def qs_by_predicate(rows, pattern, s, reuse, caps, salt, domain, start=0):
        qq = C.make_workload(rows, s, reuse, pattern, caps, domain, salt)
        for i, q in enumerate(qq):
            q["qid"] = start + i
        return qq

    # A) Query-driven：低选择率、少量热点谓词、初始覆盖低
    wa = qs_by_predicate(ecom, "PRED_SHARED", 2, 40, caps_e, 101, "ecom", 0)
    wa += qs_by_predicate(fin, "PRED_SHARED", 2, 40, caps_f, 102, "finproc", len(wa))

    # B) Batch analytics：高复用、高覆盖、大量不同 query
    wb = qs_by_predicate(ecom, "PRED_NESTED", 40, 100, caps_e, 201, "ecom", 0)
    wb += qs_by_predicate(fin, "PRED_NESTED", 40, 100, caps_f, 202, "finproc", len(wb))

    # C) Mixed：冷查询 + 热查询 + 新能力 + 旧能力 + 谓词重叠
    wc = qs_by_predicate(ecom, "PRED_SHARED", 3, 20, ["issue_classification"], 301, "ecom", 0)
    wc += qs_by_predicate(ecom, "PRED_SHARED", 3, 20, ["issue_classification",
                                                       "amount_extraction_ecom"], 301, "ecom", len(wc))
    wc += qs_by_predicate(ecom, "PRED_OVERLAP", 8, 15, caps_e, 302, "ecom", len(wc))
    wc += qs_by_predicate(ecom, "PRED_DISTINCT", 2, 8, caps_e, 303, "ecom", len(wc))
    wc += qs_by_predicate(fin, "PRED_SHARED", 5, 25, caps_f, 304, "finproc", len(wc))
    wc += qs_by_predicate(fin, "PRED_DISTINCT", 2, 6, caps_f, 305, "finproc", len(wc))
    return dict(A_query_driven=dict(queries=wa, domain="both"),
                B_batch_analytics=dict(queries=wb, domain="both"),
                C_mixed=dict(queries=wc, domain="both"))


def run_workloads(rows_by_domain, unit):
    wl = build_workloads(rows_by_domain)
    rows_out = []
    for name, spec in wl.items():
        allrows = rows_by_domain["ecom"] + rows_by_domain["finproc"]
        qs = spec["queries"]
        caps = sorted({c for q in qs for c in q["caps"]})
        o = C.oracle(qs, allrows, unit, caps)
        s_mean = st.mean([len(q["survivors"]) for q in qs]) / len(allrows)
        for bname, strat in BASELINES.items():
            r = C.simulate(strat, qs, allrows, unit)
            m = r["metrics"]
            rows_out.append(dict(
                workload=name, baseline=bname, strategy=strat, n_queries=len(qs),
                n_rows=len(allrows), n_caps=len(caps), mean_selectivity=round(s_mean, 5),
                total_cost=round(m["total_cost"], 6), cost_per_query=round(m["cost_per_query"], 8),
                semantic_tokens=m["semantic_tokens"], semantic_rows_built=m["semantic_rows_built"],
                materialized_rows=m["materialized_rows"],
                materialization_coverage=m["materialization_coverage"],
                cache_hit_rate=m["cache_hit_rate"],
                regret=round(C.regret(m["total_cost"], o["total_cost"]), 5),
                oracle_cost=round(o["total_cost"], 6),
                p50_ms=m["p50_ms"], p95_ms=m["p95_ms"], p99_ms=m["p99_ms"],
                quality_note="策略间质量恒定（同一 survivor → 同一 artifact → 同一答案）"))
    return rows_out


# ================================================================ C
def source_drift(rows_by_domain, unit, real):
    """source drift：Eager 全量重建 / Late-Persistent 受影响行重建 / Adaptive 选择。
    + 句法缓存键的过度失效量化（语义等价改写）。"""
    domain = "ecom"
    rows = rows_by_domain[domain]
    caps = C.NATIVE_CAPS[domain]
    perturb_rate_measured = (real.get("probe1", {}).get("P3_perturbation", {})
                             .get("label_stability"))
    rows_out = []
    for drift in [0.0, 0.01, 0.05, 0.10, 0.25]:
        salt = C._h(f"DRIFT|{drift}") % 100000
        n_aff = int(round(drift * len(rows)))
        affected = set(r["row_id"] for r in sorted(rows, key=lambda x: C._h(x["row_id"]))[:n_aff])
        phase1 = C.make_workload(rows, 5, 30, "PRED_SHARED", caps, domain, salt)
        # phase2 与 phase1 谓词相同（同热点），但 source 发生了 drift
        phase2 = C.make_workload(rows, 5, 30, "PRED_SHARED", caps, domain, salt)
        union1 = {r["row_id"] for q in phase1 for r in q["survivors"]}
        # 冷启动 phase1 的成本（统一用 C：无限存储下的最近最优）
        c1 = C.simulate("C", phase1, rows, unit)["metrics"]["total_cost"]

        full_rebuild = sum(unit.cost(cap, r["row_id"]) for cap in caps for r in rows)
        affected_rebuild = sum(unit.cost(cap, rid) for cap in caps for rid in union1 & affected)
        no_invalidation = 0.0        # 保持陈旧工件（成本 0，但可能返回过时答案）
        phase2_hits = C.simulate("C", phase2, rows, unit)["metrics"]["total_cost"] * 0  # 全命中
        # 句法失效：改写后 payload_hash 全变 → 若按句法键，需重建全部 union 行
        syntactic_invalidation = sum(unit.cost(cap, rid) for cap in caps for rid in union1)
        # 语义失效：真实探针测得「语义保持扰动下答案不变率 = 1.0」→ 无需重建
        semantic_invalidation = (1 - (perturb_rate_measured or 1.0)) * syntactic_invalidation

        for name, cost in [("Eager_full_rebuild", full_rebuild),
                           ("Late_affected_rows_rebuild", affected_rebuild),
                           ("Adaptive_pick_min", min(full_rebuild, affected_rebuild)),
                           ("No_invalidation_stale", no_invalidation)]:
            rows_out.append(dict(drift_rate=drift, n_affected_rows=n_aff,
                                 n_union_rows=len(union1), policy=name,
                                 rebuild_cost=round(cost, 6),
                                 phase1_cost=round(c1, 6),
                                 total_cost=round(c1 + cost, 6),
                                 rebuild_over_full=round(cost / max(1e-12, full_rebuild), 5),
                                 affected_share_of_union=round(len(union1 & affected)
                                                               / max(1, len(union1)), 5)))
        rows_out.append(dict(drift_rate=drift, n_affected_rows=n_aff, n_union_rows=len(union1),
                             policy="KEY_GRANULARITY",
                             rebuild_cost=round(syntactic_invalidation, 6),
                             phase1_cost=round(c1, 6),
                             total_cost=round(c1 + syntactic_invalidation, 6),
                             rebuild_over_full=round(syntactic_invalidation
                                                     / max(1e-12, full_rebuild), 5),
                             affected_share_of_union=None,
                             note=(f"句法键失效 = 全量 union 重建；语义等价改写下的真实需要 = "
                                   f"{semantic_invalidation:.6f}（探针测得答案不变率 "
                                   f"{perturb_rate_measured}）；过度失效倍数 = "
                                   f"{syntactic_invalidation / max(1e-12, semantic_invalidation):.1f}x"),
                             semantic_invalidation_cost=round(semantic_invalidation, 8)))
    summ = dict(
        block="source_drift",
        statement=("在无限存储下，受影响行重建（IVM 式增量）恒 ≤ 全量重建；"
                   "Adaptive 的『选择』退化为 min(full, incremental)=incremental，"
                   "即经典 incremental view maintenance，无需任何 workload-aware 决策。"),
        n_rows=len(rows),
        drift_levels=[0.0, 0.01, 0.05, 0.10, 0.25],
        semantic_preserving_answer_stability_measured=perturb_rate_measured,
    )
    return rows_out, summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    rows_by_domain, snap = C.materialize()
    unit = C.UnitCost().build(rows_by_domain)
    real = {}
    for k, p in [("probe1", os.path.join(E2, "real_probe.json")),
                 ("probe2", os.path.join(E2, "bundle_scaling.json"))]:
        if os.path.exists(p):
            real[k] = json.load(open(p, encoding="utf-8"))

    base = baselines_from_exp1()
    wl = run_workloads(rows_by_domain, unit)
    drift, drift_sum = source_drift(rows_by_domain, unit, real)

    results = dict(experiment="E3_external_baseline_and_prior_art_boundary",
                   fixed_items=C.fixed_items_manifest(), snapshot=snap,
                   baselines=base, workloads=wl, drift=drift, drift_summary=drift_sum,
                   external_systems_runnable=dict(
                       note=("QuWARTS / ReDD / Sema / DASE / LOTUS / TADA / Palimpzest / PLOP / "
                             "ThalamusDB 均未提供可在本沙箱内以同一 fixed items 运行的公开实现；"
                             "因此**不声明**任何「outperforms X」。仅以行为矩阵做 prior-art 边界划分，"
                             "并以 Baseline-0..4 作为可运行对照。")))
    C.write_json(os.path.join(OUT, "results.json"), results)
    C.write_json(os.path.join(OUT, "baseline_results.json"), dict(
        baselines=base, note="Baseline-0..4 与 Oracle 在实验 1 全矩阵（840 cell）上的聚合"))
    C.write_csv(os.path.join(OUT, "workload_results.csv"), wl)
    C.write_csv(os.path.join(OUT, "source_drift.csv"), drift)
    C.write_json(os.path.join(OUT, "config.json"), dict(
        baselines={k: v for k, v in BASELINES.items()},
        workloads=["A_query_driven", "B_batch_analytics", "C_mixed"],
        drift_levels=[0.0, 0.01, 0.05, 0.10, 0.25],
        fixed_items=results["fixed_items"]))
    print(json.dumps(dict(
        baselines={k: v.get("win_rate_over_cells") for k, v in base.items()
                   if isinstance(v, dict)},
        C_equals_oracle=base.get("C_equals_oracle_share"),
        workloads=[dict(w=r["workload"], b=r["baseline"], cost=r["total_cost"], regret=r["regret"])
                   for r in wl],
        drift=[dict(d=r["drift_rate"], p=r["policy"], total=r["total_cost"])
               for r in drift if r["policy"] in ("Eager_full_rebuild",
                                                 "Late_affected_rows_rebuild",
                                                 "Adaptive_pick_min")],
    ), ensure_ascii=False, indent=1)[:3000])
    return results


if __name__ == "__main__":
    main()
