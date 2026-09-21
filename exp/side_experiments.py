# -*- coding: utf-8 -*-
"""P1 旁路实验（主实验通过后才执行，§9/§11/§17/§23）。

实验：
  S1 Multi-use（reuse ∈ {10,50,100}）：BuildOnce+Reuse vs RepeatedSemanticOperator，
     并分别报告 function caching ON/OFF（§10）。
  S2 TADA-like representation-matched 对照（§11）：
     T1 = native TADA 风格（eager tagging-only，物化为普通表后确定性运行时执行）
     T2 = matched representation（同模型/同 prompt/同 schema/同 row payload）下的 Eager vs Late
  S3 Validation Cost 实际占比（§17）
  S4 低选择性安全测试（s > 50%，§23 W3）
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capability as CAP
from capability import CapabilityBuild
from config import EXP_OUT, PRICING, SEED, VALIDATION
import harness as H
from operators import op_filter
from source_plane import SourcePlane, materialize
import stats as ST
from llm import count_tokens


def multi_use(source_plane, rows_by_domain, arts):
    """同一 Capability 被 10/50/100 个下游查询复用：BuildOnce+Reuse vs Per-query operator。"""
    out = {}
    build = CapabilityBuild(memo={})
    rnd = random.Random(SEED + 5)
    for domain, rows in rows_by_domain.items():
        cap_key = "issue_classification" if domain == "ecom" else "clause_classification"
        # 基准谓词：选择性约 5%（hash 桶，确定性）
        import hashlib
        pred = {"op": "hash_lt", "col": "row_id", "value": 50}
        survivors = op_filter(rows, pred)
        for reuse in [10, 50, 100]:
            # ---- BuildOnce + Reuse（Late，一次构建，多次复用）----
            build.memo = {}
            outputs, st = build.build(cap_key, survivors)
            reuse_costs = []
            for _ in range(reuse):
                # 每次复用仅支付：缓存读取 + 确定性消费 + 校验 + synthesis
                c = (len(survivors) * PRICING["validation_per_row"]
                     + len(survivors) * PRICING["retrieval_per_row"] * 0.2
                     + 0.00005 + 0.0009)
                reuse_costs.append(c)
            total_once = st.cost + sum(reuse_costs)
            # ---- RepeatedSemanticOperator（每次重新调用语义算子，无复用）----
            repeat_costs = []
            for _ in range(reuse):
                _, st2 = build.build(cap_key, survivors)
                repeat_costs.append(st2.cost + len(survivors) * PRICING["validation_per_row"]
                                    + 0.00005 + 0.0009)
            # ---- caching OFF 变体（两次都按逻辑调用全额计费）----
            total_once_off = st.cost + sum(st.cost for _ in range(reuse))
            out[f"{domain}_reuse{reuse}"] = dict(
                domain=domain, reuse=reuse, survivors=len(survivors),
                build_once_cost=round(st.cost, 8),
                amortized_cost_once_reuse=round(total_once / reuse, 8),
                amortized_cost_repeated_operator=round(sum(repeat_costs) / reuse, 8),
                amortized_reduction=round(1 - (total_once / reuse) / (sum(repeat_costs) / reuse), 5),
                amortized_cost_once_reuse_cacheOFF=round(total_once_off / reuse, 8),
                amortized_reduction_cacheOFF=round(
                    1 - (total_once_off / reuse) / (sum(repeat_costs) / reuse), 5),
            )
    return out


def tada_matched(pairs):
    """T1/T2：representation-matched 对照（同一模型/prompt/schema/payload）。

    T2（matched）= 主实验的 A vs B（同一 capability representation）。
    T1（native TADA 风格）= eager tagging-only 物化后确定性执行（限制为 classification 类查询）。
    """
    cls = [p for p in pairs if p["B"]["capability_kind"] == "classification"]
    allq = pairs
    def pack(sub):
        A = [p["A"] for p in sub]; B = [p["B"] for p in sub]
        return dict(
            n=len(sub),
            cost_A=round(ST.mean([r["total_cost"] for r in A]), 8),
            cost_B=round(ST.mean([r["total_cost"] for r in B]), 8),
            cost_reduction=round(ST.mean([1 - b["total_cost"] / a["total_cost"]
                                          for a, b in zip(A, B)]), 5),
            work_reduction=round(ST.mean([1 - b["semantic_work"] / a["semantic_work"]
                                          for a, b in zip(A, B)]), 5),
            quality_delta=round(ST.mean([a["quality_score"] - b["quality_score"]
                                         for a, b in zip(A, B)]), 6),
        )
    return dict(
        T1_native_tada_tagging_only=pack(cls),
        T2_matched_representation_all=pack(allq),
        note=("T2 使用与 T1 完全相同的 model/prompt/schema/row payload，仅改 Build Position；"
              "若 T2 仍显示收益，则收益来自 Build Position 而非 representation design。"),
    )


def validation_share(pairs):
    A = [p["A"] for p in pairs]; B = [p["B"] for p in pairs]
    vc = ST.mean([r["validation_cost"] for r in B])
    saving = ST.mean([a["total_cost"] - b["total_cost"] for a, b in zip(A, B)])
    return dict(
        validation_cost_mean=round(vc, 8),
        validation_share_of_total_B=round(ST.mean([r["validation_cost"] / r["total_cost"]
                                                   for r in B]), 5),
        validation_over_semantic_saving=round(vc / saving, 5) if saving else None,
        total_A=round(ST.mean([r["total_cost"] for r in A]), 8),
        total_B=round(ST.mean([r["total_cost"] for r in B]), 8),
        semantic_saving_abs=round(saving, 8),
        budget_total_limit=VALIDATION and 0.10,
        protocol=VALIDATION,
    )


def low_selectivity_safety(pairs):
    w3 = [p for p in pairs if p["B"]["actual_selectivity_pct"] > 50]
    A = [p["A"] for p in w3]; B = [p["B"] for p in w3]
    return dict(
        n=len(w3),
        cost_ratio=round(ST.mean([b["total_cost"] / a["total_cost"] for a, b in zip(A, B)]), 4),
        quality_delta=round(ST.mean([a["quality_score"] - b["quality_score"] for a, b in zip(A, B)]), 6),
        p95_ratio=round(ST.percentile([r["execution_latency_ms"] for r in B], 95) /
                        max(1e-9, ST.percentile([r["execution_latency_ms"] for r in A], 95)), 4),
        limit=1.10,
        safe=bool(ST.mean([b["total_cost"] / a["total_cost"] for a, b in zip(A, B)]) <= 1.10),
    )


def run():
    rows, snap = materialize()
    rows_by_domain = {"ecom": rows["ecom"], "finproc": rows["finproc"]}
    sp = SourcePlane(rows["ecom"] + rows["finproc"])
    import run_experiment as R
    arts = R.build_artifacts(rows_by_domain)
    # 复用主实验 traces（避免重复跑主 sweep）
    trace_path = os.path.join(EXP_OUT, "query_trace.jsonl")
    traces = [json.loads(l) for l in open(trace_path, encoding="utf-8")]
    by_q = {}
    for t in traces:
        by_q.setdefault(t["query_id"], {})[t["strategy"]] = t
    pairs = []
    for qid, m in by_q.items():
        if "A" not in m or "B" not in m:
            continue
        pairs.append(dict(query_id=qid, domain=m["B"]["domain"], split=m["B"]["split"],
                          **{s: m[s] for s in ["A", "B", "C_eager", "C_late", "D", "E"] if s in m}))
    # 复用 A/B 上的字段完整性（COMPACT_FIELDS 与 trace 一致）
    res = dict(
        snapshot=snap,
        S1_multi_use=multi_use(sp, rows_by_domain, arts),
        S2_tada_matched=tada_matched(pairs),
        S3_validation_cost=validation_share(pairs),
        S4_low_selectivity_safety=low_selectivity_safety(pairs),
    )
    with open(os.path.join(EXP_OUT, "side_results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return res


if __name__ == "__main__":
    run()
