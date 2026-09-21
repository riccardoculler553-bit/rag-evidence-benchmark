# -*- coding: utf-8 -*-
"""Deterministic Upstream Operators（§1：上游不得依赖任何 semantic capability）
+ Typed Result + Final Synthesis（LLM 只用于不可约语义部分）。

算子集合：FILTER / PROJECT / JOIN(key-based) / GROUP / AGG / ORDER / TOPK
另含三个"消费 capability 输出"的算子（semantic-consuming），它们在 plan 中位于 CapabilityBuild 之后。
"""
import hashlib
import json

from capability import CAPABILITIES
from llm import get_model, count_tokens


# ---------------------------------------------------------------- 确定性上游算子
def _pred_eval(pred, row):
    op = pred["op"]
    if op == "and":
        return all(_pred_eval(p, row) for p in pred["preds"])
    if op == "or":
        return any(_pred_eval(p, row) for p in pred["preds"])
    col, val = pred["col"], pred.get("value")
    if col == "row_id" and op == "hash_lt":
        # 选择率控制谓词（确定性、与语义无关）：hash(row_id) % 1000 < k
        return (int(hashlib.sha256(row["row_id"].encode()).hexdigest()[:8], 16) % 1000) < val
    if col == "row_id" and op == "hash_lt_salted":
        # 带 salt 的独立谓词族：用于 "distinct predicate" 工作负载（survivor 集互不嵌套）
        h = hashlib.sha256(f"{row['row_id']}|{pred.get('salt', 0)}".encode()).hexdigest()
        return (int(h[:8], 16) % 1000) < val
    actual = row["columns"].get(col)
    if op == "eq":
        return actual == val
    if op == "ne":
        return actual != val
    if op == "in":
        return actual in val
    if op == "gt":
        return actual is not None and actual > val
    if op == "ge":
        return actual is not None and actual >= val
    if op == "lt":
        return actual is not None and actual < val
    if op == "contains":
        return isinstance(actual, str) and val in actual
    raise ValueError(f"unknown predicate op: {op}")


def op_filter(rows, pred):
    return [r for r in rows if _pred_eval(pred, r)]


def op_project(rows, cols):
    return [{**r, "columns": {k: v for k, v in r["columns"].items() if k in cols}} for r in rows]


def op_join(left, right, key, right_key=None):
    right_key = right_key or key
    idx = {}
    for r in right:
        idx.setdefault(r["columns"].get(right_key), []).append(r)
    out = []
    for r in left:
        for m in idx.get(r["columns"].get(key), []):
            merged = dict(r)
            merged["columns"] = {**r["columns"], **{f"r_{k}": v for k, v in m["columns"].items()}}
            out.append(merged)
    return out


def op_group(rows, key):
    g = {}
    for r in rows:
        g.setdefault(r["columns"].get(key), []).append(r)
    return g


def op_order(rows, key, desc=False):
    return sorted(rows, key=lambda r: (r["columns"].get(key) is None, r["columns"].get(key)),
                  reverse=desc)


def op_topk(rows, key, k, desc=True):
    return op_order(rows, key, desc)[:k]


# ---------------------------------------------------------------- 消费 capability 的算子
def op_sem_filter(rows, outputs, label):
    return [r for r in rows if outputs.get(r["row_id"], {}).get("label") == label]


def op_sem_count(rows, outputs, label):
    return sum(1 for r in rows if outputs.get(r["row_id"], {}).get("label") == label)


def op_sem_topk(rows, outputs, k):
    def val(r):
        v = outputs.get(r["row_id"], {}).get("value")
        return -1e18 if v is None else float(v)
    return sorted(rows, key=val, reverse=True)[:k]


def op_sem_group_count(rows, outputs):
    g = {}
    for r in rows:
        lb = outputs.get(r["row_id"], {}).get("label")
        g[lb] = g.get(lb, 0) + 1
    return g


SEMANTIC_CONSUMERS = {"SEM_FILTER", "SEM_COUNT", "SEM_TOPK", "SEM_GROUP_COUNT"}


# ---------------------------------------------------------------- Logical Plan
def plan_hash(steps):
    return hashlib.sha256(json.dumps(steps, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- Synthesis（LLM 仅用于不可约语义部分）
SYNTH_PROMPT = ("根据结构化结果，用一句中文回答用户问题。只输出 JSON："
                "{{\"answer\": <value>, \"unit\": \"...|null\"}}\n<result>\n{result}\n</result>")
SYNTH_SCHEMA = {"type": "object", "required": ["answer"]}


def synthesis_hash():
    return hashlib.sha256((SYNTH_PROMPT + json.dumps(SYNTH_SCHEMA, sort_keys=True)).encode()).hexdigest()[:16]


class Synthesizer:
    """确定性 reader：把 Typed Result 渲染为最终 answer（1 次 LLM 调用计入成本）。"""

    def __init__(self, model=None):
        self.model = model or get_model()
        self.calls = 0

    def synthesize(self, result_repr, expected_type="number"):
        prompt = SYNTH_PROMPT.format(result=json.dumps(result_repr, ensure_ascii=False))
        _, t_in, t_out = self.model.complete(prompt, task="generic")
        self.calls += 1
        # 归一化解析：数值 / 字符串集合 / 标签
        if isinstance(result_repr, (int, float)):
            return result_repr, t_in, t_out
        if isinstance(result_repr, list):
            return result_repr, t_in, t_out
        if isinstance(result_repr, dict):
            return result_repr, t_in, t_out
        return str(result_repr), t_in, t_out
