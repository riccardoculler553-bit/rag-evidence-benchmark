# -*- coding: utf-8 -*-
"""Typed QueryIR 工作负载（§19：主实验直接提供 QueryIR，CompilerError ≡ 0）。

每条 query 为 paired query：同一 QueryIR 在 A/B/C/D/E 五组下执行。
切分：按 source entity 分组（禁止按行随机切分）——ecom 按 platform，finproc 按 policy。
"""
import hashlib
import json
import os
import random

from config import (SEED, SWEEP, QUERIES_PER_SWEEP_POINT, NATURAL_QUERIES_PER_DOMAIN,
                    EXP_DATA, N_ROWS_PER_DOMAIN)
from operators import plan_hash

# ---- entity → split 映射（60/20/20，按实体整组切分）----
ECOM_ENTITIES = ["天猫", "京东", "抖音", "Shopify", "Shopee"]
ECOM_SPLIT = {"天猫": "build", "京东": "build", "抖音": "build", "Shopify": "dev", "Shopee": "blind"}
FIN_ENTITIES = ["TRV-001-v3", "TRV-001-v2", "TRV-001-CN1", "EXP-001-v2", "PROC-001-v3"]
FIN_SPLIT = {"TRV-001-v3": "build", "TRV-001-v2": "build", "TRV-001-CN1": "build",
             "EXP-001-v2": "dev", "PROC-001-v3": "blind"}

LABELS = {
    "issue_classification": ["logistics_delay", "product_quality", "refund_request",
                             "address_change", "other"],
    "clause_classification": ["条款", "例外", "脚注", "附录"],
}


def _natural_pred(domain, entity):
    if domain == "ecom":
        return {"op": "eq", "col": "platform", "value": entity}
    return {"op": "eq", "col": "policy", "value": entity}


def _and(*preds):
    preds = [p for p in preds if p]
    if len(preds) == 1:
        return preds[0]
    return {"op": "and", "preds": list(preds)}


def _hash_bucket_k(rows, natural, target_n, key_col="row_id"):
    """二分求 hash 桶阈值，使 AND(natural, hash<k) 的基数尽量接近 target_n。"""
    def count(k):
        n = 0
        for r in rows:
            if natural and not _match(r, natural):
                continue
            if int(hashlib.sha256(r[key_col].encode()).hexdigest()[:8], 16) % 1000 < k:
                n += 1
        return n
    lo, hi = 0, 1000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count(mid) <= target_n:
            lo = mid
        else:
            hi = mid - 1
    return lo, count(lo)


def _match(row, pred):
    from operators import _pred_eval
    return _pred_eval(pred, row)


def _oracle_answer(rows, cap_kind, consumer, oracle_key):
    """确定性 oracle：对 survivor 集合用真值标签/数值计算答案。"""
    if consumer["op"] == "SEM_COUNT":
        return sum(1 for r in rows if r["oracle"][oracle_key[0]][oracle_key[1]] == consumer["label"])
    if consumer["op"] == "SEM_FILTER":
        return sorted(r["row_id"] for r in rows
                      if r["oracle"][oracle_key[0]][oracle_key[1]] == consumer["label"])
    if consumer["op"] == "SEM_TOPK":
        k = consumer["k"]
        srt = sorted(rows, key=lambda r: (
            r["oracle"][oracle_key[0]][oracle_key[1]] is None,
            -(r["oracle"][oracle_key[0]][oracle_key[1]] or 0)))
        return [r["row_id"] for r in srt[:k]]
    if consumer["op"] == "SEM_GROUP_COUNT":
        g = {}
        for r in rows:
            lb = r["oracle"][oracle_key[0]][oracle_key[1]]
            g[lb] = g.get(lb, 0) + 1
        return g
    raise ValueError(consumer["op"])


CAP_SPEC = {
    ("ecom", "classification"): ("issue_classification", ("labels", "issue"), "SEM_COUNT"),
    ("ecom", "extraction"): ("amount_extraction_ecom", ("values", "amount"), "SEM_TOPK"),
    ("finproc", "classification"): ("clause_classification", ("labels", "clause_kind"), "SEM_COUNT"),
    ("finproc", "extraction"): ("amount_extraction_fin", ("values", "amount"), "SEM_TOPK"),
}


def build_queries(rows_by_domain):
    rnd = random.Random(SEED + 101)
    queries = []
    for domain in ["ecom", "finproc"]:
        rows = rows_by_domain[domain]
        entities = ECOM_ENTITIES if domain == "ecom" else FIN_ENTITIES
        splits = ECOM_SPLIT if domain == "ecom" else FIN_SPLIT
        qn = 0
        for s_pct in SWEEP:
            target_n = max(1, int(round(s_pct / 100.0 * len(rows))))
            for j in range(QUERIES_PER_SWEEP_POINT):
                entity = entities[(j * 2 + 1) % len(entities)]
                natural = _natural_pred(domain, entity)
                nat_count = sum(1 for r in rows if _match(r, natural))
                if target_n <= nat_count * 0.9:
                    k, actual = _hash_bucket_k(rows, natural, target_n)
                    pred = _and(natural, {"op": "hash_lt", "col": "row_id", "value": k})
                    pred_kind = "natural_and_hash_sweep"
                else:
                    k, actual = _hash_bucket_k(rows, None, target_n)
                    pred = {"op": "hash_lt", "col": "row_id", "value": k}
                    pred_kind = "hash_sweep_only"
                kind = "classification" if (j % 2 == 0) else "extraction"
                cap_key, oracle_key, default_consumer = CAP_SPEC[(domain, kind)]
                if kind == "classification":
                    label = LABELS[cap_key][(j // 2) % len(LABELS[cap_key])]
                    consumer = ({"op": "SEM_COUNT", "label": label} if j % 4 == 0
                                else {"op": "SEM_FILTER", "label": label})
                else:
                    consumer = {"op": "SEM_TOPK", "k": 3}
                qn += 1
                queries.append(_make_query(
                    domain, rows, qn, s_pct, target_n, actual, pred, pred_kind, entity,
                    cap_key, oracle_key, consumer, splits[entity],
                    f"{domain}-sweep-{s_pct}pct-{j:02d}"))
        # 自然谓词查询（realism check）
        for j in range(NATURAL_QUERIES_PER_DOMAIN):
            entity = entities[j % len(entities)]
            natural = _natural_pred(domain, entity)
            survivors = [r for r in rows if _match(r, natural)]
            n = len(survivors)
            kind = "classification" if (j % 2 == 0) else "extraction"
            cap_key, oracle_key, _ = CAP_SPEC[(domain, kind)]
            if kind == "classification":
                label = LABELS[cap_key][(j // 2) % len(LABELS[cap_key])]
                consumer = {"op": "SEM_COUNT", "label": label}
            else:
                consumer = {"op": "SEM_TOPK", "k": 3}
            qn += 1
            queries.append(_make_query(
                domain, rows, qn, round(100.0 * n / len(rows), 2), n, n, natural, "natural",
                entity, cap_key, oracle_key, consumer, splits[entity],
                f"{domain}-natural-{j:02d}"))
    return queries


def _make_query(domain, rows, qn, s_pct, target_n, actual_n, pred, pred_kind, entity,
                cap_key, oracle_key, consumer, split, tag):
    survivors = [r for r in rows if _match(r, pred)]
    # 语义消费目标：从 survivor 的真值分布中确定性选取（保证答案非平凡且有区分度）
    if consumer["op"] in ("SEM_COUNT", "SEM_FILTER"):
        counts = {}
        for r in survivors:
            lb = r["oracle"][oracle_key[0]][oracle_key[1]]
            counts[lb] = counts.get(lb, 0) + 1
        order = [l for l in LABELS[cap_key] if l in counts]
        if consumer["op"] == "SEM_COUNT":
            label = max(order, key=lambda l: (counts[l], -order.index(l))) if order else LABELS[cap_key][0]
        else:  # SEM_FILTER：优先选择非全集、非空集的标签
            cand = [l for l in order if 0 < counts[l] < len(survivors)] or order
            label = max(cand, key=lambda l: (counts[l], -cand.index(l))) if cand else LABELS[cap_key][0]
        consumer = {**consumer, "label": label}
    answer = _oracle_answer(survivors, None, consumer, oracle_key)
    plan = [
        {"op": "SOURCE_SCAN", "relation": domain},
        {"op": "FILTER", "pred": pred},
        {"op": "CAPABILITY_BUILD", "capability": cap_key},
        {"op": consumer["op"], **{k: v for k, v in consumer.items() if k != "op"}},
        {"op": "SYNTHESIS", "schema": "answer_schema_v1"},
    ]
    q = dict(
        query_id=f"{domain.upper()}-Q{qn:04d}",
        domain=domain,
        capability=cap_key,
        capability_kind="classification" if cap_key in LABELS else "extraction",
        predicate=pred,
        predicate_kind=pred_kind,
        entity=entity,
        consumer=consumer,
        logical_plan=plan,
        logical_plan_hash=plan_hash(plan),
        split=split,
        target_selectivity_pct=s_pct,
        actual_selectivity_pct=round(100.0 * len(survivors) / len(rows), 4),
        input_cardinality=len(rows),
        survivor_cardinality=len(survivors),
        survivor_payload_hashes=sorted(r["payload_hash"] for r in survivors),
        oracle=dict(answer=answer, oracle_survivor_count=len(survivors),
                    oracle_labels=[r["oracle"][oracle_key[0]][oracle_key[1]] for r in survivors]),
        question=_question_text(domain, cap_key, consumer, entity),
        tag=tag,
    )
    return q


def _question_text(domain, cap_key, consumer, entity):
    scope = f"平台={entity}" if domain == "ecom" else f"制度={entity}"
    if consumer["op"] == "SEM_COUNT":
        return (f"在{scope}的记录中，语义类别为「{consumer['label']}」的共有多少条？")
    if consumer["op"] == "SEM_FILTER":
        return f"在{scope}的记录中，找出语义类别为「{consumer['label']}」的记录。"
    return f"在{scope}的记录中，金额最高的前 {consumer['k']} 条是哪些？"


def persist(queries):
    os.makedirs(EXP_DATA, exist_ok=True)
    path = os.path.join(EXP_DATA, "queries.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for q in queries:
            f.write(json.dumps({k: v for k, v in q.items() if k != "survivor_payload_hashes"},
                               ensure_ascii=False) + "\n")
    h = hashlib.sha256()
    for q in queries:
        h.update(q["query_id"].encode())
        h.update(q["logical_plan_hash"].encode())
    return h.hexdigest()[:32]
