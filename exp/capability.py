# -*- coding: utf-8 -*-
"""CapabilityBuild：唯一研究型节点（§8：semantic classification + attribute extraction）。

关键性质（§10）：CapabilityBuild 的产出是可缓存、可哈希、可复现的语义状态（Capability Artifact）。
位置由 harness 决定：EAGER | LATE；本模块不感知位置，只负责"给定行集合 → 构建输出"。
"""
import hashlib
import json
import math
import os

from config import PRICING, LATENCY, VALIDATION
from llm import get_model, model_hash, count_tokens

PROMPT_TEMPLATE = {
    "issue_classification": (
        "你是电商客服工单分类器。只输出 JSON。\n"
        "可选标签：logistics_delay | product_quality | refund_request | address_change | other\n"
        "规则：只依据文本证据判断；无法判断时输出 other。\n"
        "<payload>\n{payload}\n</payload>\n"
        "输出格式：{{\"label\": \"...\"}}"),
    "clause_classification": (
        "你是企业制度条款分类器。只输出 JSON。\n"
        "可选标签：条款 | 例外 | 脚注 | 附录\n"
        "<payload>\n{payload}\n</payload>\n"
        "输出格式：{{\"label\": \"...\"}}"),
    "amount_extraction": (
        "你是金额抽取器。只输出 JSON，抽取文本中的目标金额数字（不归一单位）。\n"
        "<payload>\n{payload}\n</payload>\n"
        "输出格式：{{\"value\": <number|null>, \"raw\": \"...\", \"unit\": \"元|万元|null\"}}"),
}

OUTPUT_SCHEMA = {
    "issue_classification": {"type": "object", "required": ["label"],
                             "properties": {"label": {"type": "string"}}},
    "clause_classification": {"type": "object", "required": ["label"],
                              "properties": {"label": {"type": "string"}}},
    "amount_extraction": {"type": "object", "required": ["value"],
                          "properties": {"value": {"type": ["number", "null"]},
                                         "raw": {"type": ["string", "null"]},
                                         "unit": {"type": ["string", "null"]}}},
}

CAPABILITY_IMPL_REVISION = "cap-impl-v1.2"


def parse_model_output(text, kind, labels=None):
    """共用 parser/normalizer（§3.1 固定项，对所有策略完全一致）。

    兼容真实模型的常见输出噪声：markdown 代码块围栏、前后缀说明文字。
    只做确定性归一，不改变 prompt / schema，也不随策略变化。
    """
    import re
    if text is None:
        return {"label": "other"} if kind == "classification" else {"value": None}
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    if not t.startswith("{"):
        m = re.search(r"\{.*?\}", t, re.S)
        if m:
            t = m.group(0)
    try:
        out = json.loads(t)
    except Exception:  # noqa: BLE001
        return {"label": "other"} if kind == "classification" else {"value": None}
    if kind == "classification":
        lb = str(out.get("label", "other")).strip()
        if labels and lb not in labels:
            return {"label": "other"}
        return {"label": lb}
    v = out.get("value")
    try:
        v = None if v is None else float(v)
    except (TypeError, ValueError):
        v = None
    return {"value": v, "raw": out.get("raw"), "unit": out.get("unit")}

CAPABILITIES = {
    "issue_classification": dict(
        capability_id="cap.issue_classification", domain="ecom", kind="classification",
        task="issue_classification", metric="macro_f1", output_field="label",
        oracle_path=("labels", "issue")),
    "amount_extraction_ecom": dict(
        capability_id="cap.amount_extraction_ecom", domain="ecom", kind="extraction",
        task="amount_extraction", metric="field_f1", output_field="value",
        oracle_path=("values", "amount")),
    "clause_classification": dict(
        capability_id="cap.clause_classification", domain="finproc", kind="classification",
        task="clause_classification", metric="macro_f1", output_field="label",
        oracle_path=("labels", "clause_kind")),
    "amount_extraction_fin": dict(
        capability_id="cap.amount_extraction_fin", domain="finproc", kind="extraction",
        task="amount_extraction", metric="field_f1", output_field="value",
        oracle_path=("values", "amount")),
}


def prompt_hash(task: str) -> str:
    return hashlib.sha256(PROMPT_TEMPLATE[task].encode()).hexdigest()[:16]


def schema_hash(task: str) -> str:
    return hashlib.sha256(json.dumps(OUTPUT_SCHEMA[task], sort_keys=True).encode()).hexdigest()[:16]


def capability_version(cap_key: str) -> str:
    c = CAPABILITIES[cap_key]
    h = hashlib.sha256()
    h.update(c["capability_id"].encode())
    h.update(CAPABILITY_IMPL_REVISION.encode())
    h.update(prompt_hash(c["task"]).encode())
    h.update(schema_hash(c["task"]).encode())
    h.update(model_hash().encode())
    return h.hexdigest()[:16]


class BuildStats:
    __slots__ = ("rows", "tokens_in", "tokens_out", "calls", "sim_ms", "cost", "cache_hits")

    def __init__(self):
        self.rows = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0
        self.sim_ms = 0.0
        self.cost = 0.0
        self.cache_hits = 0

    def add_call(self, tokens_in, tokens_out, cache_hit=False):
        self.rows += 1
        self.calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.sim_ms += (tokens_in * LATENCY["ms_per_input_token"]
                        + tokens_out * LATENCY["ms_per_output_token"]
                        + LATENCY["ms_per_call_overhead"])
        self.cost += (tokens_in / 1000 * PRICING["input_per_1k"]
                      + tokens_out / 1000 * PRICING["output_per_1k"]
                      + PRICING["per_call_overhead"])
        self.cache_hits += 1 if cache_hit else 0

    def merge(self, other):
        for s in self.__slots__:
            setattr(self, s, getattr(self, s) + getattr(other, s))

    def as_dict(self):
        return {s: getattr(self, s) for s in self.__slots__}


class CapabilityBuild:
    """Capability 的唯一实现；EAGER / LATE 只影响调用方传入的行集合。"""

    def __init__(self, model=None, memo=None):
        self.model = model or get_model()
        # 物理记忆化：加速运行；成本仍按逻辑调用计费（config.CACHE_POLICY.cost_accounting=logical）
        self.memo = memo if memo is not None else {}
        self.memo_enabled = True

    def build(self, cap_key, rows, account=True):
        """对给定行集合构建 capability 输出。返回 (outputs, stats)。"""
        cap = CAPABILITIES[cap_key]
        tmpl = PROMPT_TEMPLATE[cap["task"]]
        outputs = {}
        stats = BuildStats()
        for r in rows:
            key = (cap_key, r["payload_hash"])
            if self.memo_enabled and key in self.memo:
                out, t_in, t_out = self.memo[key]
                cache_hit = True
            else:
                prompt = tmpl.format(payload=r["payload"])
                comp, t_in, t_out = self.model.complete(prompt, task=cap["task"])
                out = json.loads(comp)
                cache_hit = False
                if self.memo_enabled:
                    self.memo[key] = (out, t_in, t_out)
            outputs[r["row_id"]] = out
            if account:
                stats.add_call(t_in, t_out, cache_hit=cache_hit)
        return outputs, stats


# ================================================================ Artifact（§6/§27）
def build_artifact(cap_key, rows, build: CapabilityBuild):
    outputs, stats = build.build(cap_key, rows)
    rows_hash = hashlib.sha256("".join(sorted(r["payload_hash"] for r in rows)).encode()).hexdigest()
    art_hash = hashlib.sha256(json.dumps(sorted(outputs.items()),
                                         ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return dict(
        capability_id=CAPABILITIES[cap_key]["capability_id"],
        capability_version=capability_version(cap_key),
        input_rows_hash=rows_hash[:32],
        artifact_hash=art_hash[:32],
        model_hash=model_hash(),
        prompt_hash=prompt_hash(CAPABILITIES[cap_key]["task"]),
        output_schema_hash=schema_hash(CAPABILITIES[cap_key]["task"]),
        n_rows=len(rows),
        build_tokens_in=stats.tokens_in,
        build_tokens_out=stats.tokens_out,
        build_cost=round(stats.cost, 8),
        build_latency_ms=round(stats.sim_ms, 3),
        outputs=outputs,
    )


def load_artifact(artifact):
    """Replay：只读冻结 artifact，输出必须与 live build 完全一致。"""
    return artifact["outputs"]


# ================================================================ 质量度量（§18）
def macro_f1(y_true, y_pred):
    labels = sorted(set(y_true) | set(y_pred))
    if not labels:
        return 0.0
    f1s = []
    for lb in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lb and p == lb)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lb and p == lb)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lb and p != lb)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(f1s) / len(f1s)


def field_f1(y_true, y_pred, tol=0.01):
    """抽取任务的 exact-match / field F1（数值字段用容差匹配）。"""
    def eq(a, b):
        if a is None or b is None:
            return a is None and b is None
        try:
            return abs(float(a) - float(b)) <= max(tol, abs(float(a)) * tol)
        except (TypeError, ValueError):
            return str(a) == str(b)
    tp = sum(1 for t, p in zip(y_true, y_pred) if eq(t, p) and t is not None)
    fp = sum(1 for t, p in zip(y_true, y_pred) if eq(t, p) and t is None)
    fn = sum(1 for t, p in zip(y_true, y_pred) if not eq(t, p))
    precision = tp / (tp + fp) if tp + fp else (1.0 if not fn else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    if tp == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def classification_metrics(y_true, y_pred):
    labels = sorted(set(y_true) | set(y_pred))
    per = {}
    for lb in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lb and p == lb)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lb and p == lb)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lb and p != lb)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        per[lb] = dict(tp=tp, fp=fp, fn=fn, precision=prec, recall=rec,
                       f1=(2 * prec * rec / (prec + rec)) if prec + rec else 0.0)
    return dict(macro_f1=macro_f1(y_true, y_pred), per_label=per)


# ================================================================ Certificate（§15/§16）
def build_certificate(cap_key, calib_rows, outputs, metric_name=None):
    """V1 Cached Certificate：以 calibration split 认证 capability version 的错误率。"""
    cap = CAPABILITIES[cap_key]
    gf, gv = cap["oracle_path"]
    y_true = [r["oracle"][gf][gv] for r in calib_rows]
    if cap["kind"] == "classification":
        y_pred = [outputs[r["row_id"]].get("label") for r in calib_rows]
        metric = macro_f1(y_true, y_pred)
    else:
        y_pred = [outputs[r["row_id"]].get("value") for r in calib_rows]
        metric = field_f1(y_true, y_pred)
    err = 1.0 - metric
    n = len(calib_rows)
    # Wilson 区间（保守）
    z = 1.96
    if n:
        denom = 1 + z * z / n
        center = (err + z * z / (2 * n)) / denom
        half = z * math.sqrt(max(err * (1 - err) / n + z * z / (4 * n * n), 0)) / denom
        ci = [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]
    else:
        ci = [0.0, 1.0]
    return dict(
        capability_id=cap["capability_id"], version=capability_version(cap_key),
        capability_impl_revision=CAPABILITY_IMPL_REVISION,
        operator_family=cap["kind"], source_family=cap["domain"],
        model_hash=model_hash(), prompt_hash=prompt_hash(cap["task"]),
        schema_hash=schema_hash(cap["task"]),
        validation_set_hash=hashlib.sha256(
            "".join(sorted(r["payload_hash"] for r in calib_rows)).encode()).hexdigest()[:32],
        n=n, metric=metric_name or cap["metric"], observed_error=round(err, 4),
        confidence_interval=ci, status=("PASS" if ci[1] <= 0.20 else "REVIEW"),
        validation_protocol=dict(mode=VALIDATION["mode"],
                                 sequential_sampling=VALIDATION["sequential_sampling"],
                                 epsilon=VALIDATION["epsilon"], delta=VALIDATION["delta"]),
    )


def structural_validation_cost(n_rows, prices=None):
    """V0 Structural：schema/type/key/snapshot/provenance + payload hash 校验成本。"""
    return n_rows * PRICING["validation_per_row"] + n_rows * 0.0  # 常数项另计
