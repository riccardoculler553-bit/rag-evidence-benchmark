# -*- coding: utf-8 -*-
"""主实验入口：Phase 0–2（Eager / Late / Replay / Sweep / 五组对照）+ 全指标与判定。

用法：
    python exp/run_experiment.py --stage main      # 主因果实验（必须先跑）
    python exp/run_experiment.py --stage side      # 旁路实验（multi-use / TADA-matched / 低选择性安全）
    python exp/run_experiment.py --stage all
"""
import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capability as CAP
from capability import CapabilityBuild, build_artifact, build_certificate, capability_version
from config import (EXP_OUT, SEED, THRESHOLDS, VALIDATION, PRICING, BATCH_SIZE, N_ROWS_PER_DOMAIN)
import harness as H
import llm
from operators import synthesis_hash
from source_plane import SourcePlane, materialize, dataset_snapshot_hash, build_source_registry
import stats as ST
import workload as WL

FAMILY = lambda s: "W1_high" if s <= 10 else ("W2_medium" if s <= 50 else "W3_low")


def git_commit():
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "no-git-repo"


def code_hash():
    h = hashlib.sha256()
    d = os.path.dirname(os.path.abspath(__file__))
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".py"):
            with open(os.path.join(d, fn), "rb") as f:
                h.update(fn.encode()); h.update(f.read())
    return h.hexdigest()[:32]


def prepare(force=False):
    rows, snap = materialize(force=force)
    rows_by_domain = {"ecom": rows["ecom"], "finproc": rows["finproc"]}
    sp = SourcePlane(rows["ecom"] + rows["finproc"])
    return rows_by_domain, sp, snap


def build_artifacts(rows_by_domain):
    """Replay 用：对每个 capability 在完整关系上构建一次冻结 Capability Artifact。"""
    build = CapabilityBuild(memo={})
    arts = {}
    for domain, rows in rows_by_domain.items():
        for kind in ["classification", "extraction"]:
            cap_key = WL.CAP_SPEC[(domain, kind)][0]
            arts[cap_key] = build_artifact(cap_key, rows, build)
    return arts


def build_certificates(rows_by_domain):
    """V1 Cached Certificate：以确定性顺序抽样的校准集认证 capability version（§15/§16）。"""
    certs = {}
    build = CapabilityBuild(memo={})
    for domain, rows in rows_by_domain.items():
        calib = rows[:300]          # 顺序抽样 30→60→…→300 的最终样本量
        for kind in ["classification", "extraction"]:
            cap_key = WL.CAP_SPEC[(domain, kind)][0]
            outputs, _ = build.build(cap_key, calib)
            certs[cap_key] = build_certificate(cap_key, calib, outputs)
    return certs


def aggregate(pairs, split_filter=None, family=None, domain=None):
    sel = []
    for p in pairs:
        if split_filter and p["split"] not in split_filter:
            continue
        if domain and p["domain"] != domain:
            continue
        if family and FAMILY(p["B"]["actual_selectivity_pct"]) != family:
            continue
        sel.append(p)
    if not sel:
        return {}
    A = [p["A"] for p in sel]
    B = [p["B"] for p in sel]
    D = [p["D"] for p in sel]
    E = [p["E"] for p in sel]
    Ce = [p["C_eager"] for p in sel]
    Cl = [p["C_late"] for p in sel]

    def red_work(a, b):
        return 1 - (b["semantic_work"] / a["semantic_work"]) if a["semantic_work"] else 0.0

    nA = sum(r["correct"] for r in A)
    nB = sum(r["correct"] for r in B)
    cost_per_correct_A = (sum(r["total_cost"] for r in A) / nA) if nA else None
    cost_per_correct_B = (sum(r["total_cost"] for r in B) / nB) if nB else None
    correct_cost_red = (1 - cost_per_correct_B / cost_per_correct_A
                        if (cost_per_correct_A and cost_per_correct_B) else None)

    res = dict(
        n_queries=len(sel),
        selectivity_mean=round(ST.mean([p["B"]["actual_selectivity_pct"] for p in sel]), 3),
        selectivity_range=[round(min(p["B"]["actual_selectivity_pct"] for p in sel), 3),
                           round(max(p["B"]["actual_selectivity_pct"] for p in sel), 3)],
        # ---- quality ----
        answer_correct_A=round(ST.mean([r["correct"] for r in A]), 4),
        answer_correct_B=round(ST.mean([r["correct"] for r in B]), 4),
        answer_correct_D=round(ST.mean([r["correct"] for r in D]), 4),
        answer_correct_E=round(ST.mean([r["correct"] for r in E]), 4),
        operator_correct_A=round(ST.mean([r["operator_correct"] for r in A]), 4),
        operator_correct_B=round(ST.mean([r["operator_correct"] for r in B]), 4),
        quality_score_A=round(ST.mean([r["quality_score"] for r in A]), 4),
        quality_score_B=round(ST.mean([r["quality_score"] for r in B]), 4),
        quality_delta_AB=round(ST.mean([a["quality_score"] - b["quality_score"]
                                        for a, b in zip(A, B)]), 6),
        quality_paired=ST.summarize_paired([a["quality_score"] for a in A],
                                           [b["quality_score"] for b in B]),
        # ---- semantic work ----
        build_rows_A=ST.mean([r["build_cardinality"] for r in A]),
        build_rows_B=ST.mean([r["build_cardinality"] for r in B]),
        semantic_work_A=round(ST.mean([r["semantic_work"] for r in A]), 3),
        semantic_work_B=round(ST.mean([r["semantic_work"] for r in B]), 3),
        semantic_work_reduction=round(ST.mean([red_work(a, b) for a, b in zip(A, B)]), 5),
        semantic_work_paired=ST.summarize_paired(A, B, transform=red_work),
        llm_calls_A=round(ST.mean([r["llm_calls"] for r in A]), 2),
        llm_calls_B=round(ST.mean([r["llm_calls"] for r in B]), 2),
        # ---- cost ----
        total_cost_A=round(ST.mean([r["total_cost"] for r in A]), 8),
        total_cost_B=round(ST.mean([r["total_cost"] for r in B]), 8),
        total_cost_D=round(ST.mean([r["total_cost"] for r in D]), 8),
        total_cost_E=round(ST.mean([r["total_cost"] for r in E]), 8),
        cost_reduction=round(ST.mean([1 - (b["total_cost"] / a["total_cost"])
                                      for a, b in zip(A, B) if a["total_cost"]]), 5),
        cost_per_correct_A=round(cost_per_correct_A, 8) if cost_per_correct_A else None,
        cost_per_correct_B=round(cost_per_correct_B, 8) if cost_per_correct_B else None,
        cost_per_correct_D=round((sum(r["total_cost"] for r in D) / max(1, sum(r["correct"] for r in D))), 8),
        cost_per_correct_E=round((sum(r["total_cost"] for r in E) / max(1, sum(r["correct"] for r in E))), 8),
        cost_per_correct_reduction=round(correct_cost_red, 5) if correct_cost_red is not None else None,
        cost_paired=ST.summarize_paired([a["total_cost"] for a in A],
                                        [b["total_cost"] for b in B]),
        validation_cost_B=round(ST.mean([r["validation_cost"] for r in B]), 8),
        validation_share_B=round(ST.mean([r["validation_cost"] / r["total_cost"]
                                          for r in B if r["total_cost"]]), 5),
        validation_over_saving=round(
            (ST.mean([r["validation_cost"] for r in B]) /
             max(1e-12, ST.mean([a["total_cost"] - b["total_cost"] for a, b in zip(A, B)]))), 5),
        # ---- latency ----
        latency_p50_A=round(ST.percentile([r["execution_latency_ms"] for r in A], 50), 3),
        latency_p95_A=round(ST.percentile([r["execution_latency_ms"] for r in A], 95), 3),
        latency_p99_A=round(ST.percentile([r["execution_latency_ms"] for r in A], 99), 3),
        latency_p50_B=round(ST.percentile([r["execution_latency_ms"] for r in B], 50), 3),
        latency_p95_B=round(ST.percentile([r["execution_latency_ms"] for r in B], 95), 3),
        latency_p99_B=round(ST.percentile([r["execution_latency_ms"] for r in B], 99), 3),
        latency_p95_ratio=round(ST.percentile([r["execution_latency_ms"] for r in B], 95) /
                                max(1e-9, ST.percentile([r["execution_latency_ms"] for r in A], 95)), 4),
        build_time_ms_B=round(ST.mean([r["build_time_ms"] for r in B]), 3),
        execution_time_ms_B=round(ST.mean([r["measured_latency_ms"] for r in B]), 4),
        synthesis_time_ms_B=round(ST.mean([r["synthesis_tokens"] for r in B]) * 0.6, 3),
        # ---- controls ----
        replay_quality_A=round(ST.mean([r["quality_score"] for r in Ce]), 4),
        replay_quality_B=round(ST.mean([r["quality_score"] for r in Cl]), 4),
        replay_equality=all(p["checks"].get("replay_equality") for p in sel),
        experiment_invalid=sum(1 for p in sel if p["status"] != "VALID"),
        # ---- error attribution ----
        error_attribution={k: sum(1 for r in B if r["error_class"] == k)
                           for k in ["COMPILER", "CAPABILITY", "EXECUTION", "SYNTHESIS", "SOURCE", "NONE"]},
        # ---- operator-type breakdown（§4：按 operator 类型分别报告）----
        by_operator={
            op: dict(
                n=len([1 for p in sel if p["B"]["consumer_op"] == op]),
                operator_correct_A=round(ST.mean([p["A"]["operator_correct"] for p in sel
                                                  if p["B"]["consumer_op"] == op] or [0]), 4),
                operator_correct_B=round(ST.mean([p["B"]["operator_correct"] for p in sel
                                                  if p["B"]["consumer_op"] == op] or [0]), 4),
                answer_correct_A=round(ST.mean([p["A"]["correct"] for p in sel
                                                if p["B"]["consumer_op"] == op] or [0]), 4),
                answer_correct_B=round(ST.mean([p["B"]["correct"] for p in sel
                                                if p["B"]["consumer_op"] == op] or [0]), 4),
                quality_score_A=round(ST.mean([p["A"]["quality_score"] for p in sel
                                               if p["B"]["consumer_op"] == op] or [0]), 4),
                quality_score_B=round(ST.mean([p["B"]["quality_score"] for p in sel
                                               if p["B"]["consumer_op"] == op] or [0]), 4),
            )
            for op in ["SEM_COUNT", "SEM_FILTER", "SEM_TOPK"]
        },
        measured_latency_p95_A=round(ST.percentile([r["measured_latency_ms"] for r in A], 95), 4),
        measured_latency_p95_B=round(ST.percentile([r["measured_latency_ms"] for r in B], 95), 4),
    )
    return res


def decide(res_by_family, res_all, replay_ok, certs):
    """预注册判定（§23/§24 + 用户指令 §5）。"""
    w1 = res_by_family.get("W1_high", {})
    w2 = res_by_family.get("W2_medium", {})
    w3 = res_by_family.get("W3_low", {})
    checks = {}

    def ge(x, t):
        return x is not None and x >= t

    checks["W1_quality_non_inferior"] = ge(w1.get("quality_delta_AB", -1), -0.01)
    checks["W1_semantic_work_min30"] = ge(w1.get("semantic_work_reduction"), THRESHOLDS["W1_semantic_work_reduction_min"])
    checks["W1_semantic_work_target50"] = ge(w1.get("semantic_work_reduction"), THRESHOLDS["W1_semantic_work_reduction"])
    checks["W1_cost_per_correct_min20"] = ge(w1.get("cost_per_correct_reduction"), THRESHOLDS["W1_cost_per_correct_reduction"])
    checks["W1_p95_not_worse"] = ge(-(w1.get("latency_p95_ratio", 99) - 1),
                                    -THRESHOLDS["W1_p95_degradation"])
    checks["W2_quality_non_inferior"] = ge(w2.get("quality_delta_AB", -1), -0.01)
    checks["W2_semantic_work_min25"] = ge(w2.get("semantic_work_reduction"), THRESHOLDS["W2_semantic_work_reduction"])
    checks["W2_cost_per_correct_min10"] = ge(w2.get("cost_per_correct_reduction"), THRESHOLDS["W2_cost_per_correct_reduction"])
    checks["W3_quality_non_inferior"] = ge(w3.get("quality_delta_AB", -1), -0.01)
    checks["W3_no_material_regression"] = (w3.get("total_cost_B") is not None
                                           and w3["total_cost_B"] <= THRESHOLDS["W3_cost_ratio_limit"] * w3["total_cost_A"])
    checks["replay_control_consistent"] = bool(replay_ok)
    checks["two_domains"] = len(res_all.get("per_domain", {})) == 2
    checks["validation_budget_total"] = ge(-(res_all.get("overall", {}).get("validation_share_B", 1) or 1), -THRESHOLDS["validation_share_total"])
    checks["validation_budget_saving"] = (res_all.get("overall", {}).get("validation_over_saving", 99) or 99) <= THRESHOLDS["validation_share_saving"]
    checks["certificates_pass"] = all(c["status"] == "PASS" for c in certs.values())
    # ---- 两个独立 domain 的 W1/W2 复现（§24-3）----
    dom_ok = True
    dom_detail = {}
    for d in ["ecom", "finproc"]:
        w1d = res_all.get("per_domain_family", {}).get(f"{d}|W1_high", {})
        w2d = res_all.get("per_domain_family", {}).get(f"{d}|W2_medium", {})
        ok = (ge(w1d.get("semantic_work_reduction"), 0.30)
              and ge(w1d.get("cost_per_correct_reduction"), 0.20)
              and ge(w1d.get("quality_delta_AB", -1), -0.01)
              and ge(w2d.get("semantic_work_reduction"), 0.25)
              and ge(w2d.get("cost_per_correct_reduction"), 0.10)
              and ge(w2d.get("quality_delta_AB", -1), -0.01))
        dom_detail[d] = ok
        dom_ok = dom_ok and ok
    checks["two_domains_W1W2_reproduced"] = dom_ok

    supported = all([checks["W1_quality_non_inferior"], checks["W1_semantic_work_min30"],
                     checks["W1_cost_per_correct_min20"], checks["W2_quality_non_inferior"],
                     checks["W2_semantic_work_min25"], checks["W2_cost_per_correct_min10"],
                     checks["W3_no_material_regression"], checks["replay_control_consistent"],
                     checks["two_domains"], checks["two_domains_W1W2_reproduced"],
                     checks["validation_budget_total"],
                     checks["validation_budget_saving"]])
    if supported:
        verdict = "SUPPORTED"
        degradations = []
    else:
        degradations = []
        if not (w1.get("cost_per_correct_reduction") or 0) > 0:
            degradations.append("F1: no cost advantage → stop paper claim")
        if not checks["W1_quality_non_inferior"] or not checks["W2_quality_non_inferior"]:
            degradations.append("F2: quality non-inferiority not met → drop 'equal-quality lower-cost' claim")
        if checks["W1_semantic_work_min30"] and not checks["W2_semantic_work_min25"]:
            degradations.append("F3: only high-selectivity works → reframe as selective-workload optimization")
        if not checks["validation_budget_total"] or not checks["validation_budget_saving"]:
            degradations.append("F6: validation eats the gain → offline certification only")
        if not checks["replay_control_consistent"]:
            degradations.append("EXECUTION CONFOUND: replay inconsistency → investigate execution path")
        verdict = "PARTIALLY_SUPPORTED" if (checks["W1_semantic_work_min30"]
                                            and checks["W1_quality_non_inferior"]) else "NOT_SUPPORTED"
    return dict(checks=checks, verdict=verdict, degradations=degradations)


def run_main(verbose=True):
    t_start = time.time()
    rows_by_domain, sp, snap = prepare(force=True)
    queries = WL.build_queries(rows_by_domain)
    q_snap = WL.persist(queries)
    arts = build_artifacts(rows_by_domain)
    certs = build_certificates(rows_by_domain)
    if verbose:
        print(f"dataset snapshot={snap} queries={len(queries)} artifacts={len(arts)}")
    traces, pairs = H.execute(rows_by_domain, queries, sp, arts, snap, progress=verbose)

    # ---- 汇总 ----
    res_all = dict(
        overall=aggregate(pairs),
        held_out=aggregate(pairs, split_filter={"dev", "blind"}),
        per_domain={d: aggregate(pairs, domain=d) for d in ["ecom", "finproc"]},
        per_domain_held_out={d: aggregate(pairs, split_filter={"dev", "blind"}, domain=d)
                             for d in ["ecom", "finproc"]},
        per_family={f: aggregate(pairs, family=f)
                    for f in ["W1_high", "W2_medium", "W3_low"]},
        per_family_held_out={f: aggregate(pairs, split_filter={"dev", "blind"}, family=f)
                             for f in ["W1_high", "W2_medium", "W3_low"]},
        per_domain_family={f"{d}|{f}": aggregate(pairs, domain=d, family=f)
                           for d in ["ecom", "finproc"]
                           for f in ["W1_high", "W2_medium", "W3_low"]},
        per_domain_family_held_out={f"{d}|{f}": aggregate(pairs, split_filter={"dev", "blind"},
                                                         domain=d, family=f)
                                    for d in ["ecom", "finproc"]
                                    for f in ["W1_high", "W2_medium", "W3_low"]},
        sweep={},
    )
    # selectivity sweep 曲线
    for s in sorted({round(p["B"]["actual_selectivity_pct"]) for p in pairs}):
        sub = [p for p in pairs if abs(round(p["B"]["actual_selectivity_pct"]) - s) <= 1
               and p["B"]["actual_selectivity_pct"] <= s + 1]
        if not sub:
            continue
        A = [p["A"] for p in sub]; B = [p["B"] for p in sub]
        res_all["sweep"][str(s)] = dict(
            n=len(sub),
            sel_mean=round(ST.mean([p["B"]["actual_selectivity_pct"] for p in sub]), 3),
            cost_A=round(ST.mean([r["total_cost"] for r in A]), 8),
            cost_B=round(ST.mean([r["total_cost"] for r in B]), 8),
            work_A=round(ST.mean([r["semantic_work"] for r in A]), 2),
            work_B=round(ST.mean([r["semantic_work"] for r in B]), 2),
            build_rows_A=round(ST.mean([r["build_cardinality"] for r in A]), 1),
            build_rows_B=round(ST.mean([r["build_cardinality"] for r in B]), 1),
            quality_A=round(ST.mean([r["quality_score"] for r in A]), 4),
            quality_B=round(ST.mean([r["quality_score"] for r in B]), 4),
            p95_A=round(ST.percentile([r["execution_latency_ms"] for r in A], 95), 3),
            p95_B=round(ST.percentile([r["execution_latency_ms"] for r in B], 95), 3),
        )
    decision = decide(res_all["per_family"], res_all,
                      res_all["overall"]["replay_equality"], certs)

    # ---- 日志落盘 ----
    os.makedirs(EXP_OUT, exist_ok=True)
    with open(os.path.join(EXP_OUT, "query_trace.jsonl"), "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    with open(os.path.join(EXP_OUT, "capability_artifact.jsonl"), "w", encoding="utf-8") as f:
        for k, a in arts.items():
            meta = {kk: vv for kk, vv in a.items() if kk != "outputs"}
            meta["output_rows"] = len(a["outputs"])
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    with open(os.path.join(EXP_OUT, "demo_capability_outputs.json"), "w", encoding="utf-8") as f:
        json.dump({k: dict(list(a["outputs"].items())[:5]) for k, a in arts.items()},
                  f, ensure_ascii=False, indent=1)
    manifest = dict(
        experiment="v1.2 Build Position Ablation (static plan)",
        stage="main (Phase 0–2)",
        git_commit=git_commit(), code_hash=code_hash(),
        dataset_snapshot=snap, query_snapshot=q_snap,
        source_registry=build_source_registry(),
        model=llm.MockSemanticModel.model_id, model_revision=llm.MockSemanticModel.revision,
        model_hash=llm.model_hash(), prompt_hash={k: CAP.prompt_hash(CAP.CAPABILITIES[k]["task"])
                                                 for k in CAP.CAPABILITIES},
        schema_hash={k: CAP.schema_hash(CAP.CAPABILITIES[k]["task"]) for k in CAP.CAPABILITIES},
        capability_versions={k: capability_version(k) for k in CAP.CAPABILITIES},
        synthesis_hash=synthesis_hash(),
        tokenizer=llm.count_tokens.__doc__.split("：")[0],
        temperature=0.0, decoding="greedy", batch_size=BATCH_SIZE,
        hardware=dict(platform=platform.platform(), processor=platform.processor(),
                      python=platform.python_version()),
        seed=SEED, cache_policy="physical_memoization=True / cost_accounting=logical",
        pricing_version=PRICING["pricing_version"], pricing=PRICING,
        concurrency=1, n_rows_per_domain=N_ROWS_PER_DOMAIN, n_queries=len(queries),
        validation_protocol=VALIDATION,
        model_swappable="RAGX_MODEL_BACKEND=openai 可用同一 prompt/schema 重跑真实模型",
        runtime_sec=round(time.time() - t_start, 2),
    )
    with open(os.path.join(EXP_OUT, "run_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    with open(os.path.join(EXP_OUT, "certificates.json"), "w", encoding="utf-8") as f:
        json.dump(certs, f, ensure_ascii=False, indent=1)
    with open(os.path.join(EXP_OUT, "main_results.json"), "w", encoding="utf-8") as f:
        json.dump(dict(results=res_all, decision=decision, certificates=certs),
                  f, ensure_ascii=False, indent=1)
    # ---- 失败案例分析（§7 交付物：失败案例）----
    fails = []
    for t in traces:
        if t["strategy"] == "B" and t["correct"] == 0 and t["error_class"] != "NONE":
            fails.append(dict(query_id=t["query_id"], domain=t["domain"], split=t["split"],
                              question=t["question"], capability=t["capability"],
                              consumer_op=t["consumer_op"], selectivity=t["actual_selectivity_pct"],
                              survivor_cardinality=t["survivor_cardinality"],
                              oracle_answer=t["oracle_answer"], answer=t["answer"],
                              error_class=t["error_class"],
                              quality_score=t["quality_score"],
                              operator_correct=t["operator_correct"]))
    seen = set()
    uniq = []
    for f_ in fails:
        if f_["error_class"] + f_["capability"] in seen:
            continue
        seen.add(f_["error_class"] + f_["capability"])
        uniq.append(f_)
    with open(os.path.join(EXP_OUT, "failure_cases.json"), "w", encoding="utf-8") as f:
        json.dump(dict(total_failures_B=len(fails), examples=uniq[:15],
                       by_error_class={k: sum(1 for x in fails if x["error_class"] == k)
                                       for k in ["CAPABILITY", "EXECUTION", "SYNTHESIS", "SOURCE"]}),
                  f, ensure_ascii=False, indent=1)
    if verbose:
        print(json.dumps(decision, ensure_ascii=False, indent=1))
    return dict(rows_by_domain=rows_by_domain, queries=queries, pairs=pairs, traces=traces,
                results=res_all, decision=decision, artifacts=arts, certs=certs,
                manifest=manifest, snapshot=snap)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="main", choices=["main", "side", "all"])
    args = ap.parse_args()
    if args.stage in ("main", "all"):
        run_main()
        print("main stage done")
    if args.stage in ("side", "all"):
        import side_experiments
        side_experiments.run()
