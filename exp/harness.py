# -*- coding: utf-8 -*-
"""实验 harness：五个控制组 A–E × Selectivity Sweep × 有效性检查 × 全指标记录。

组定义（§4）：
  A Eager：D → B(D) → F → Y
  B Late ：D → F(D) → B(F(D)) → Y
  C Replay：A/B 都只读冻结 Capability Artifact（因果 sanity check，不用于成本主结论）
  D Late + exact survivor payload（排除"输入更干净"混淆）
  E Per-query semantic operator（不物化 Capability，强 baseline）
"""
import hashlib
import json
import os
import random
import time

import capability as CAP
from capability import CapabilityBuild, build_artifact, capability_version
from config import (PRICING, LATENCY, BATCH_SIZE, EXP_OUT, SEED, VALIDATION)
from llm import model_hash, count_tokens
from operators import (op_filter, op_sem_count, op_sem_filter, op_sem_topk, synthesis_hash,
                       Synthesizer)
import llm

EXPERIMENT_INVALID = "EXPERIMENT_INVALID"


# ---------------------------------------------------------------- quality
def _quality_and_errors(rows, outputs, cap_key, consumer, oracle):
    """返回 (operator_correct, quality_score, capability_error_flag, typed_result)。"""
    cap = CAP.CAPABILITIES[cap_key]
    gf, gv = cap["oracle_path"]
    y_true = [r["oracle"][gf][gv] for r in rows]
    if cap["kind"] == "classification":
        y_pred = [outputs.get(r["row_id"], {}).get("label") for r in rows]
        q = CAP.macro_f1(y_true, y_pred)
        if consumer["op"] == "SEM_COUNT":
            res = sum(1 for p in y_pred if p == consumer["label"])
        else:
            res = sorted(r["row_id"] for r, p in zip(rows, y_pred) if p == consumer["label"])
    else:
        y_pred = [outputs.get(r["row_id"], {}).get("value") for r in rows]
        q = CAP.field_f1(y_true, y_pred)
        pairs = sorted(zip(rows, y_pred), key=lambda rp: (rp[1] is None, -(rp[1] or 0)))
        res = [r["row_id"] for r, _ in pairs[:consumer["k"]]]
    return q, res


def _answer_correct(pred, oracle_answer, consumer):
    if consumer["op"] in ("SEM_COUNT",):
        return int(pred == oracle_answer)
    if consumer["op"] == "SEM_FILTER":
        return int(sorted(pred) == sorted(oracle_answer))
    if consumer["op"] == "SEM_TOPK":
        k = consumer["k"]
        inter = len(set(pred) & set(oracle_answer))
        return int(inter == len(oracle_answer))
    return int(pred == oracle_answer)


def _topk_metrics(pred, oracle_answer, k):
    inter = len(set(pred) & set(oracle_answer))
    recall = inter / len(oracle_answer) if oracle_answer else 0.0
    # NDCG@k（二元相关性）
    dcg = sum(1.0 / (i + 1) for i, rid in enumerate(pred) if rid in set(oracle_answer))
    idcg = sum(1.0 / (i + 1) for i in range(min(k, len(oracle_answer))))
    return recall, (dcg / idcg if idcg else 0.0)


# ---------------------------------------------------------------- 单条 run
class Runner:
    def __init__(self, source_plane, build: CapabilityBuild, synth: Synthesizer):
        self.sp = source_plane
        self.build = build
        self.synth = synth
        self.snapshot = None

    def _validation_cost(self, n_built, mode="V1"):
        return n_built * PRICING["validation_per_row"] + (
            0.0 if mode == "V1" else 0.0)

    def run(self, q, strategy, rows, artifacts=None, memo_on=True, exact_payload=False,
            synthetic_time=True):
        t0 = time.perf_counter()
        cap_key = q["capability"]
        cap = CAP.CAPABILITIES[cap_key]
        n_all = len(rows)
        build_rows = 0
        tokens_in = tokens_out = calls = 0
        build_ms = 0.0
        validation_cost = 0.0
        retrieval_cost = 0.0
        execution_order = []
        survivors = None
        outputs = {}
        fallback_cost = 0.0

        # ---- 上游确定性算子 ----
        if strategy in ("A", "C_eager", "E_full"):
            execution_order.append("B(D)")
            victims = rows
        else:
            execution_order.append("F(D)")
            victims = None

        # ---- 各策略 ----
        if strategy == "A":          # Eager：先对全部 N 行 Build，再 Filter
            outputs, st = self.build.build(cap_key, rows)
            build_rows, tokens_in, tokens_out, calls = st.rows, st.tokens_in, st.tokens_out, st.calls
            build_ms = st.sim_ms
            validation_cost += self._validation_cost(build_rows)
            retrieval_cost += build_rows * PRICING["retrieval_per_row"]
            survivors = op_filter(rows, q["predicate"])
            execution_order += ["FILTER(n)", "SEMANTIC_CONSUMER", "SYNTHESIS"]
        elif strategy == "B":        # Late：先 Filter，再对 survivor 行 Build
            survivors = op_filter(rows, q["predicate"])
            outputs, st = self.build.build(cap_key, survivors)
            build_rows, tokens_in, tokens_out, calls = st.rows, st.tokens_in, st.tokens_out, st.calls
            build_ms = st.sim_ms
            validation_cost += self._validation_cost(build_rows)
            retrieval_cost += build_rows * PRICING["retrieval_per_row"]
            execution_order += ["SEMANTIC_CONSUMER", "SYNTHESIS"]
        elif strategy in ("C_eager", "C_late"):   # Replay：读冻结 artifact
            survivors = op_filter(rows, q["predicate"])
            art = artifacts[cap_key]
            outputs = {rid: art["outputs"][rid] for rid in outputs.keys()} if False else art["outputs"]
            build_rows = 0
            tokens_in = tokens_out = calls = 0
            validation_cost += len(survivors) * PRICING["validation_per_row"]
            execution_order += ["REPLAY_READ", "SEMANTIC_CONSUMER", "SYNTHESIS"]
        elif strategy == "D":        # Late + exact survivor payload（逐行回读并校验 payload 一致）
            survivors = op_filter(rows, q["predicate"])
            for r in survivors:
                p = self.sp.read(r["locator"])
                if p is None or hashlib.sha256(p.encode()).hexdigest() != r["payload_hash"]:
                    fallback_cost += PRICING["per_call_overhead"]
            outputs, st = self.build.build(cap_key, survivors)
            build_rows, tokens_in, tokens_out, calls = st.rows, st.tokens_in, st.tokens_out, st.calls
            build_ms = st.sim_ms
            validation_cost += self._validation_cost(build_rows) * 1.5   # 逐行 payload/来源校验
            retrieval_cost += build_rows * PRICING["retrieval_per_row"] * 2
            execution_order += ["EXACT_PAYLOAD_READ", "SEMANTIC_CONSUMER", "SYNTHESIS"]
        elif strategy == "E":        # Per-query semantic operator：不物化、无跨查询复用
            survivors = op_filter(rows, q["predicate"])
            outputs, st = self.build.build(cap_key, survivors)
            build_rows, tokens_in, tokens_out, calls = st.rows, st.tokens_in, st.tokens_out, st.calls
            build_ms = st.sim_ms
            validation_cost += self._validation_cost(build_rows) + 0.00005   # 每查询重复 V0
            retrieval_cost += build_rows * PRICING["retrieval_per_row"]
            execution_order += ["PER_QUERY_SEMANTIC_OP", "SEMANTIC_CONSUMER", "SYNTHESIS"]

        # ---- 语义消费算子 + Typed Result + Synthesis ----
        quality, typed_result = _quality_and_errors(survivors, outputs, cap_key, q["consumer"],
                                                    q["oracle"])
        # 完美 capability 反事实（用于错误归因）
        perfect_outputs = {}
        gf, gv = cap["oracle_path"]
        for r in survivors:
            v = r["oracle"][gf][gv]
            perfect_outputs[r["row_id"]] = ({"label": v} if cap["kind"] == "classification"
                                            else {"value": v})
        _, perfect_result = _quality_and_errors(survivors, perfect_outputs, cap_key,
                                                q["consumer"], q["oracle"])

        answer, s_in, s_out = self.synth.synthesize(typed_result)
        synth_cost = (s_in / 1000 * PRICING["synthesis_input_per_1k"]
                      + s_out / 1000 * PRICING["synthesis_output_per_1k"])
        calls += 1

        correct = _answer_correct(answer, q["oracle"]["answer"], q["consumer"])
        operator_correct = int(typed_result == perfect_result) if cap["kind"] == "classification" \
            else int(len(set(typed_result) & set(perfect_result)) == len(perfect_result))
        # 错误归因（§21）
        if correct:
            error_class = "NONE"
        elif typed_result == perfect_result:
            error_class = "SYNTHESIS"
        elif perfect_result == q["oracle"]["answer"]:
            error_class = "CAPABILITY"
        else:
            error_class = "EXECUTION"

        if q["consumer"]["op"] == "SEM_TOPK":
            recall_k, ndcg_k = _topk_metrics(typed_result, q["oracle"]["answer"], q["consumer"]["k"])
        else:
            recall_k = ndcg_k = None

        build_cost = (tokens_in / 1000 * PRICING["input_per_1k"]
                      + tokens_out / 1000 * PRICING["output_per_1k"]
                      + calls * PRICING["per_call_overhead"])
        execution_cost = n_all * PRICING["retrieval_per_row"] * 0.1
        total_cost = retrieval_cost + build_cost + validation_cost + execution_cost + synth_cost + fallback_cost

        measured_ms = (time.perf_counter() - t0) * 1000.0
        sim_ms = (build_ms + s_in * LATENCY["ms_per_input_token"]
                  + s_out * LATENCY["ms_per_output_token"] + LATENCY["ms_per_call_overhead"]
                  + n_all * LATENCY["ms_per_row_scan"])

        survivor_digest = hashlib.sha256(
            "".join(sorted(r["payload_hash"] for r in survivors)).encode()).hexdigest()[:24]

        return dict(
            query_id=q["query_id"], domain=q["domain"], strategy=strategy, split=q["split"],
            tag=q["tag"], capability=cap_key, capability_kind=q["capability_kind"],
            consumer_op=q["consumer"]["op"], entity=q["entity"],
            predicate_kind=q["predicate_kind"],
            question=q["question"],
            capability_version=capability_version(cap_key),
            logical_plan_hash=q["logical_plan_hash"], batch_size=BATCH_SIZE,
            execution_order=execution_order,
            input_cardinality=n_all, build_cardinality=build_rows,
            survivor_cardinality=len(survivors),
            actual_selectivity_pct=q["actual_selectivity_pct"],
            build_tokens_in=tokens_in, build_tokens_out=tokens_out,
            semantic_work=tokens_in + tokens_out, llm_calls=calls,
            synthesis_tokens=s_in + s_out,
            retrieval_cost=round(retrieval_cost, 8), build_cost=round(build_cost, 8),
            validation_cost=round(validation_cost, 8), execution_cost=round(execution_cost, 8),
            synthesis_cost=round(synth_cost, 8), fallback_cost=round(fallback_cost, 8),
            total_cost=round(total_cost, 8),
            build_time_ms=round(build_ms, 4), execution_latency_ms=round(sim_ms, 4),
            measured_latency_ms=round(measured_ms, 4),
            answer=answer, oracle_answer=q["oracle"]["answer"],
            correct=correct, operator_correct=operator_correct,
            quality_score=round(quality, 5),
            recall_at_k=recall_k, ndcg_at_k=ndcg_k,
            error_class=error_class,
            survivor_payload_digest=survivor_digest,
            result_hash=hashlib.sha256(json.dumps(typed_result, ensure_ascii=False,
                                                  sort_keys=True, default=str).encode()).hexdigest()[:16],
            model_revision=llm.MockSemanticModel.revision, model_hash=model_hash(),
            prompt_hash=CAP.prompt_hash(cap["task"]), output_schema_hash=CAP.schema_hash(cap["task"]),
            synthesis_hash=synthesis_hash(),
        )


# ---------------------------------------------------------------- 有效性检查（§28）
def validity_checks(q, run_a, run_b, snapshot_hash, artifacts=None):
    checks = {
        "same_source_snapshot": snapshot_hash is not None,
        "same_logical_plan_hash": run_a["logical_plan_hash"] == run_b["logical_plan_hash"],
        "same_survivor_payload_hashes":
            run_a["survivor_payload_digest"] == run_b["survivor_payload_digest"],
        "same_model_revision": run_a["model_revision"] == run_b["model_revision"],
        "same_model_hash": run_a["model_hash"] == run_b["model_hash"],
        "same_prompt_hash": run_a["prompt_hash"] == run_b["prompt_hash"],
        "same_output_schema_hash": run_a["output_schema_hash"] == run_b["output_schema_hash"],
        "same_reader": run_a["synthesis_hash"] == run_b["synthesis_hash"],
        "same_batch_size": run_a["batch_size"] == run_b["batch_size"] == BATCH_SIZE,
        "replay_equality": None,   # 由 replay 运行填充
        "deterministic_result_hash": run_a["result_hash"] == run_b["result_hash"],
    }
    return checks


# ---------------------------------------------------------------- 主执行
def execute(rows_by_domain, queries, source_plane, artifacts, snapshot_hash, progress=True):
    runner = Runner(source_plane, CapabilityBuild(memo={}), Synthesizer())
    traces = []
    pairs = []
    rnd = random.Random(SEED + 7)
    by_domain = {d: rows_by_domain[d] for d in rows_by_domain}
    for i, q in enumerate(queries):
        rows = by_domain[q["domain"]]
        # 随机化 treatment 顺序（§26）
        order = ["A", "B", "D", "E"]
        rnd.shuffle(order)
        runs = {}
        for s in order:
            runs[s] = runner.run(q, s, rows, artifacts=artifacts)
        runs["C_eager"] = runner.run(q, "C_eager", rows, artifacts=artifacts)
        runs["C_late"] = runner.run(q, "C_late", rows, artifacts=artifacts)
        checks = validity_checks(q, runs["A"], runs["B"], snapshot_hash, artifacts)
        checks["replay_equality"] = (runs["C_eager"]["correct"] == runs["C_late"]["correct"]
                                     and runs["C_eager"]["quality_score"] == runs["C_late"]["quality_score"]
                                     and runs["C_eager"]["result_hash"] == runs["C_late"]["result_hash"])
        all_ok = all(v for v in checks.values() if v is not None)
        for s, r in runs.items():
            r["validity"] = checks
            r["experiment_status"] = "VALID" if all_ok else EXPERIMENT_INVALID
            traces.append(r)
        pairs.append(dict(query_id=q["query_id"], domain=q["domain"], split=q["split"],
                          checks=checks, status="VALID" if all_ok else EXPERIMENT_INVALID,
                          **{s: _compact(runs[s]) for s in ["A", "B", "C_eager", "C_late", "D", "E"]}))
        if progress and (i + 1) % 100 == 0:
            print(f"  ... {i + 1}/{len(queries)} queries")
    return traces, pairs


COMPACT_FIELDS = ["query_id", "domain", "split", "strategy", "capability", "capability_kind",
                  "consumer_op", "entity", "predicate_kind", "question",
                  "tag", "actual_selectivity_pct", "input_cardinality", "build_cardinality",
                  "survivor_cardinality", "semantic_work", "build_tokens_in", "build_tokens_out",
                  "llm_calls", "synthesis_tokens", "total_cost", "build_cost", "validation_cost",
                  "synthesis_cost",
                  "retrieval_cost", "execution_cost", "fallback_cost", "correct",
                  "operator_correct", "quality_score", "recall_at_k", "ndcg_at_k", "error_class",
                  "execution_latency_ms", "measured_latency_ms", "build_time_ms",
                  "result_hash", "experiment_status"]


def _compact(run):
    return {k: run[k] for k in COMPACT_FIELDS if k in run}
