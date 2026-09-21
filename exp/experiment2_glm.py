# -*- coding: utf-8 -*-
"""实验 2（真实 GLM-4.5-Air，精简矩阵，双 key + 免费兜底）。

矩阵（严格按用户规范，禁止扩大）：
  Selectivity ∈ {1%, 10%, 50%, 100%}；Reuse ∈ {1, 10, 50}；每 cell ≤20 queries；域 ecom+finproc
  策略 A(Eager-Persistent) / B(Late-Per-Query) / C(Late-Persistent)

为遵守 token 预算（800万–1800万，实测远低于上限），在**保持 Source Snapshot / Logical Plan /
Capability / Prompt / Schema 不变**的前提下，使用同一关系的确定性子关系 M=300 行/域
（sub-relation slice）；规模差异在报告中显式披露。

强制：batch_size = 1（每行一次请求）；temperature=0；thinking=disabled。
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capability as CAP
import workload as WL
from capability import CapabilityBuild, capability_version
from config import EXP_OUT, SEED
from llm import count_tokens
from llm_glm import GLMClient, FallbackFailed, GLM_MODEL, GLM_KEYS, mask
from operators import (op_filter, op_sem_count, op_sem_filter, op_sem_topk, synthesis_hash)
from source_plane import materialize
from experiment1_matrix import _consumer_for, salt_pred

M_ROWS = 300
S_LIST = [1, 10, 50, 100]
REUSE_LIST = [1, 10, 50]
Q_PER_CELL = {1: 20, 10: 20, 50: 8, 100: 4}     # ≤20（高选择性用较少 query 保护预算）
DOMAINS = ["ecom", "finproc"]
MAX_TOKENS = 18_000_000
WORKERS = 16          # v2：keep-alive + 16 并发（实测 24 并发 51 QPS、零 429）
MAX_QPS = 25.0        # 令牌桶上限，留足安全边际


class Budget:
    def __init__(self, limit):
        self.limit = limit
        self.lock = threading.Lock()
        self.stopped = False

    def check(self, tokens):
        with self.lock:
            if tokens > self.limit:
                self.stopped = True
            return not self.stopped


def build_real(rows, cap_key, client, executor, budget, stats):
    """对给定行做真实 GLM CapabilityBuild（batch_size=1，逐行调用，全部并发提交）。"""
    task = CAP.CAPABILITIES[cap_key]["task"]
    tmpl = CAP.PROMPT_TEMPLATE[task]
    outs = {}
    kind = CAP.CAPABILITIES[cap_key]["kind"]
    labels = WL.LABELS.get(cap_key)

    def one(r):
        prompt = tmpl.format(payload=r["payload"])
        try:
            text, pt, ct, meta = client.complete(prompt, task=task)
        except FallbackFailed as e:
            return (r["row_id"], None, 0, 0,
                    dict(backend="NONE", error=f"FALLBACK_FAILED:{e}"), False)
        out = CAP.parse_model_output(text, kind, labels=labels)
        raw_ok = "{" in text
        return r["row_id"], out, pt, ct, meta, raw_ok

    if not budget.check(client.total_tokens):
        return {}, dict(rows=0, pt=0, ct=0, calls=0, parse_fail=0, stopped=True,
                        backends={}, latency_ms=0.0)
    t0 = time.time()
    for rid, out, pt, ct, meta, raw_ok in executor.map(one, rows):
        outs[rid] = out
        stats["pt"] += pt
        stats["ct"] += ct
        stats["calls"] += 1
        stats["latency_ms"] += meta.get("latency_ms", 0.0)
        b = meta.get("backend", "UNKNOWN")
        stats["backends"][b] = stats["backends"].get(b, 0) + 1
        pb = stats["pt_by_backend"].setdefault(b, 0)
        cb = stats["ct_by_backend"].setdefault(b, 0)
        stats["pt_by_backend"][b] = pb + pt
        stats["ct_by_backend"][b] = cb + ct
        if not raw_ok:
            stats["parse_fail"] += 1
    stats["rows"] += len(rows)
    stats["wall_s"] = stats.get("wall_s", 0.0) + (time.time() - t0)
    return outs, stats


def new_stats():
    return dict(rows=0, pt=0, ct=0, calls=0, parse_fail=0, backends={},
                pt_by_backend={}, ct_by_backend={}, latency_ms=0.0, wall_s=0.0)


def merge_stats(dst, src):
    for k, v in src.items():
        if isinstance(v, dict):
            d = dst.setdefault(k, {})
            for kk, vv in v.items():
                d[kk] = d.get(kk, 0) + vv
        else:
            dst[k] = dst.get(k, 0) + v


def consume(q, outputs):
    if q["consumer"][0] == "SEM_COUNT":
        return op_sem_count(q["surv"], outputs, q["label"])
    if q["consumer"][0] == "SEM_FILTER":
        return sorted(r["row_id"] for r in op_sem_filter(q["surv"], outputs, q["label"]))
    return [r["row_id"] for r in op_sem_topk(q["surv"], outputs, q["consumer"][1])]


def oracle_of(q):
    return q["oracle"]


def mock_quality_on(queries, build):
    """同一 cell 的 mock 质量（配对比较用：同谓词、同 consumer、同 oracle）。"""
    ok = 0
    for q in queries:
        outs, _ = build.build(q["cap_key"], q["surv"])
        ok += int(consume(q, outs) == q["oracle"])
    return ok / max(1, len(queries))


def _label(surv, cap_key):
    gf, gv = CAP.CAPABILITIES[cap_key]["oracle_path"]
    counts = {}
    for r in surv:
        lb = r["oracle"][gf][gv]
        counts[lb] = counts.get(lb, 0) + 1
    return max(counts, key=lambda x: counts[x]) if counts else None


def _oracle(surv, consumer, cap_key, label):
    gf, gv = CAP.CAPABILITIES[cap_key]["oracle_path"]
    if consumer[0] == "SEM_COUNT":
        return sum(1 for r in surv if r["oracle"][gf][gv] == label)
    if consumer[0] == "SEM_FILTER":
        return sorted(r["row_id"] for r in surv if r["oracle"][gf][gv] == label)
    srt = sorted(surv, key=lambda r: (r["oracle"][gf][gv] is None, -(r["oracle"][gf][gv] or 0)))
    return [r["row_id"] for r in srt[:consumer[1]]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=M_ROWS)
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--drill", action="store_true", help="key 轮换/兜底演练（少量 token）")
    ap.add_argument("--max-qps", type=float, default=MAX_QPS)
    args = ap.parse_args()

    rows, snap = materialize()
    rows_by_domain = {d: rows[d][:args.rows] for d in DOMAINS}
    client = GLMClient(max_qps=args.max_qps)
    budget = Budget(args.max_tokens)
    t_start = time.time()

    if args.drill:
        print("== key 轮换 / 兜底演练 ==")
        bad = GLMClient(keys=["bad-key-" + "0" * 20, "bad-key-" + "1" * 20])
        try:
            bad.complete("只回答一个字符：OK")
        except FallbackFailed as e:
            print("  预期降级结果：", e)
        client.complete("只回答一个字符：OK")     # 正常调用一次，确认主 key 可用
        print("  drill done")

    traces = []
    cell_results = {}
    # 单一大连接池：所有行级调用共享（keep-alive 由 llm_glm 线程本地连接保证）
    pool = cf.ThreadPoolExecutor(max_workers=args.workers)
    for domain in DOMAINS:
        rws = rows_by_domain[domain]
        # ---------- A: Eager-Persistent（每 capability 全表构建一次，摊销到该域全部 query）----------
        a_caps = ["issue_classification", "amount_extraction_ecom"] if domain == "ecom" else \
                 ["clause_classification", "amount_extraction_fin"]
        a_stats = new_stats()
        a_outs = {}
        for ck in a_caps:
            st = new_stats()
            outs, st = build_real(rws, ck, client, pool, budget, st)
            a_outs[ck] = outs
            merge_stats(a_stats, st)
        n_a_queries = sum(Q_PER_CELL[s] for s in S_LIST) * len(REUSE_LIST)

        for s in S_LIST:
            for reuse in REUSE_LIST:
                key = f"{domain}|s{s}|r{reuse}"
                kthr = max(1, int(round(s / 100.0 * 1000)))
                salt = hash((domain, s)) % 100000
                queries = []
                for j in range(Q_PER_CELL[s]):
                    ck = ("issue_classification" if j % 2 == 0 else "amount_extraction_ecom") \
                        if domain == "ecom" else \
                        ("clause_classification" if j % 2 == 0 else "amount_extraction_fin")
                    pred = salt_pred(salt, kthr)
                    surv = op_filter(rws, pred)
                    consumer = _consumer_for(ck, j)
                    label = _label(surv, ck) if consumer[0] != "SEM_TOPK" else None
                    queries.append(dict(cap_key=ck, pred=pred, surv=surv, consumer=consumer,
                                        label=label, oracle=_oracle(surv, consumer, ck, label)))
                cell = {}
                mock_q = mock_quality_on(queries, CapabilityBuild(memo={}))
                t_cell = time.time()
                # B: Late-Per-Query
                b_stats = new_stats()
                b_correct = 0
                for q in queries:
                    st = new_stats()
                    outs, st = build_real(q["surv"], q["cap_key"], client, pool, budget, st)
                    merge_stats(b_stats, st)
                    b_correct += int(consume(q, outs) == q["oracle"])
                cell["B"] = dict(stats=b_stats, quality=b_correct / len(queries))
                # C: Late-Persistent（增量补建）
                c_stats = new_stats()
                c_correct = 0
                cache = {}
                for q in queries:
                    missing = [r for r in q["surv"] if (q["cap_key"], r["row_id"]) not in cache]
                    if missing:
                        st = new_stats()
                        outs, st = build_real(missing, q["cap_key"], client, pool, budget, st)
                        merge_stats(c_stats, st)
                        for r in missing:
                            cache[(q["cap_key"], r["row_id"])] = outs[r["row_id"]]
                    outputs = {r["row_id"]: cache[(q["cap_key"], r["row_id"])] for r in q["surv"]}
                    c_correct += int(consume(q, outputs) == q["oracle"])
                cell["C"] = dict(stats=c_stats, quality=c_correct / len(queries))
                # A: 摊销（按该域 query 总数摊销 eager 构建）
                a_share = {k2: (a_stats[k2] / n_a_queries if isinstance(a_stats[k2], (int, float))
                                else {b: v / n_a_queries for b, v in a_stats[k2].items()})
                           for k2 in a_stats}
                a_correct = 0
                for q in queries:
                    outs = a_outs[q["cap_key"]]
                    a_correct += int(consume(q, outs) == q["oracle"])
                cell["A"] = dict(stats=a_share, quality=a_correct / len(queries),
                                 amortized_over_queries=n_a_queries)
                cell["n_queries"] = len(queries)
                cell["mock_quality"] = mock_q
                cell["wall_s"] = round(time.time() - t_cell, 2)
                cell_results[key] = cell
                traces.append(dict(cell=key, domain=domain, s=s, reuse=reuse,
                                   survivors=len(queries[0]["surv"]),
                                   A=cell["A"], B=cell["B"], C=cell["C"]))
                print(f"  cell {key}: B_pt={b_stats['pt']} C_pt={c_stats['pt']} "
                      f"tot={client.total_tokens} q={cell['B']['quality']:.2f}/"
                      f"{cell['C']['quality']:.2f}/{cell['A']['quality']:.2f} "
                      f"wall={cell['wall_s']}s rl={client.rate_limit_events} "
                      f"backends={b_stats['backends']}", flush=True)
                if client.total_tokens > args.max_tokens:
                    print("  BUDGET STOP", flush=True)
                    break
    pool.shutdown(wait=True)

    # ---- 成本（按实际后端分别计价，避免混合后端污染成本口径）----
    for key, cell in cell_results.items():
        nq = cell["n_queries"]
        for st_name in ["A", "B", "C"]:
            st = cell[st_name]["stats"]
            cost = sum(GLMClient._cost(b, st["pt_by_backend"].get(b, 0),
                                       st["ct_by_backend"].get(b, 0), 0)
                       for b in st["pt_by_backend"])
            cell[st_name]["cost_yuan"] = round(cost, 6)
            cell[st_name]["amortized_cost"] = round(cost if st_name == "A" else cost / nq, 6)
        cell["C_over_B"] = round(cell["C"]["amortized_cost"] /
                                 max(1e-12, cell["B"]["amortized_cost"]), 4)
        cell["C_over_A"] = round(cell["C"]["amortized_cost"] /
                                 max(1e-12, cell["A"]["amortized_cost"]), 4)
        cell["all_glm"] = set(cell["C"]["stats"]["backends"]) | set(cell["B"]["stats"]["backends"]) \
            <= {"glm_key0", "glm_key1"}

    summary = client.summary()
    client.persist()
    out = dict(
        snapshot=snap, model=GLM_MODEL, keys=[mask(k) for k in GLM_KEYS],
        rows_per_domain=args.rows, batch_size=1, temperature=0, thinking="disabled",
        cells=cell_results, key_usage=summary, wall_clock_sec=round(time.time() - t_start, 1),
        max_tokens_limit=args.max_tokens, used_tokens=client.total_tokens,
        engine=dict(version="v2", transport="keep-alive(thread-local)",
                    workers=args.workers, max_qps=args.max_qps,
                    rate_limit_events=summary["rate_limit_events"],
                    switches=summary["switches"],
                    fallback_used=summary["using_fallback"]),
        all_cells_glm_only=all(c.get("all_glm", False) for c in cell_results.values()),
        note=("预算受限的精简矩阵：同一 Source Snapshot/Plan/Capability/Prompt/Schema，"
              "仅将关系规模降为确定性子关系（M 行/域）以遵守 token 预算。"
              "v2 引擎：keep-alive + 令牌桶限流；429 走退避重试而非误切兜底。"),
    )
    with open(os.path.join(EXP_OUT, "exp2_results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(os.path.join(EXP_OUT, "exp2_query_trace.jsonl"), "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(json.dumps(dict(used_tokens=client.total_tokens, switches=summary["switches"],
                          fallback=summary["using_fallback"],
                          cost_yuan=summary["total_cost_yuan"]), ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
