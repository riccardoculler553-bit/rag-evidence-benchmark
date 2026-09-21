# -*- coding: utf-8 -*-
"""v1.3 最终三实验共享内核。

新增（相对 research/common.py）：
  * 语义能力分级 A/B/C/D（独立短分类 / 数值抽取 / 上下文依赖 / 字段间依赖），全部有确定性 oracle
  * 谓词重叠三型：DISJOINT / OVERLAP / NESTED
  * 物化作用域与容量（WORKLOAD / CAP_x% / CELL）——用于刻画 C vs A 的真实边界
  * Key Router（双 GLM key 加权调度 + 429 退避不换 key + fallback 隔离到 fallback_trace）
  * 每次 GLM 请求的全字段记录（§37）与预算估算（§21）
  * 极简可解释回归（纯 Python OLS，含 R² 与系数 SE）
"""
import concurrent.futures as cf
import hashlib
import json
import math
import os
import re
import statistics as st
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXP = os.path.join(ROOT, "exp")
for _p in (EXP, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import common as C                                             # noqa: E402
from llm_glm import GLMClient, FallbackFailed, GLM_PRICING      # noqa: E402
from source_plane import DEFECTS                                # noqa: E402
from source_plane import DEFECTS                                # noqa: E402

OUT = os.path.join(HERE, "final_three_experiments")
ART = os.path.join(OUT, "artifacts")
SEED = 20260919
EXPERIMENT_VERSION = "v1.3-final-three-experiments"


def new_experiment_id(tag):
    return f"{EXPERIMENT_VERSION}:{tag}:{hashlib.sha256((tag + str(time.time())).encode()).hexdigest()[:8]}"


# ================================================================ 能力分级 A/B/C/D
# Type A：独立短分类（不需要上下文）
# Type B：数值抽取（同句）
# Type C：上下文依赖（需要判断条款类型才能解释数值）
# Type D：字段间依赖（field A 的决定 field B 的解释）
CAP_V13 = {
    "A_issue_label": dict(kind="classification", domain="ecom", difficulty="A",
                          metric="macro_f1", fields=["label"]),
    "B_order_amount": dict(kind="extraction", domain="ecom", difficulty="B",
                           metric="field_f1", fields=["amount"]),
    "C_effective_limit": dict(kind="extraction", domain="finproc", difficulty="C",
                              metric="field_f1", fields=["effective_limit"]),
    "D_kind_and_value": dict(kind="structured", domain="finproc", difficulty="D",
                             metric="field_f1", fields=["clause_kind", "governing_value"]),
}

P_TMPL = {
    "A_issue_label": (
        "你是电商客服工单分类器。只输出 JSON。\n"
        "可选标签：logistics_delay | product_quality | refund_request | address_change | other\n"
        "<payload>\n{payload}\n</payload>\n输出格式：{{\"label\": \"...\"}}"),
    "B_order_amount": (
        "你是金额抽取器。只输出 JSON，抽取订单商品金额（数字，不带单位）。\n"
        "<payload>\n{payload}\n</payload>\n输出格式：{{\"amount\": 0}}"),
    "C_effective_limit": (
        "你是企业制度金额解析器。请注意：本条可能是普通条款、例外条款、脚注或附录，"
        "不同类型的金额含义不同（例外条款给出的是上浮后的实际限额）。\n"
        "只输出 JSON。\n<payload>\n{payload}\n</payload>\n"
        "输出格式：{{\"effective_limit\": 0}}"),
    "D_kind_and_value": (
        "你是企业制度结构化解析器。先判断条款类型，再据此解释金额：\n"
        "若类型为「例外」，governing_value 取上浮后的额度；否则取该条款给出的基准额度。\n"
        "clause_kind 取 条款|例外|脚注|附录。只输出 JSON。\n"
        "<payload>\n{payload}\n</payload>\n"
        "输出格式：{{\"clause_kind\": \"...\", \"governing_value\": 0}}"),
}

# 捆绑字段集（每项含 oracle 计算函数）
def _o_ecom(r):
    """ecom 行上**全部可确定性验证**的字段（避免出现无 oracle 的字段）。"""
    pl = r["payload"]
    m = re.search(r"（([^）]+)）", pl)
    oid = re.search(r"订单([A-Za-z0-9\-]+)", pl)
    return dict(label=r["oracle"]["labels"]["issue"], amount=r["oracle"]["values"]["amount"],
                currency="元", has_discount=int("原价" in pl),
                has_defect=int(any(d in pl for d in DEFECTS)),
                product=(m.group(1) if m else None),
                order_id=(oid.group(1) if oid else None))


def _o_fin(r):
    pl = r["payload"]
    return dict(clause_kind=r["oracle"]["labels"]["clause_kind"],
                governing_value=r["oracle"]["values"]["amount"],
                has_exception_pointer=int(("附则" in pl) or ("例外" in pl) or ("备案清单" in pl)),
                unit_is_wan=int("万元" in pl),
                policy_id=r["columns"]["policy"], city=r["columns"]["city"],
                role=r["columns"]["role"], mentions_2026=int("2026" in pl))


HINT = {
    "label": "logistics_delay|product_quality|refund_request|address_change|other",
    "amount": "订单商品金额（数字）", "currency": "货币单位", "has_discount": "是否提到促销原价(true/false)",
    "clause_kind": "条款|例外|脚注|附录", "governing_value": "该条款的治理额度（数字）",
    "has_exception_pointer": "是否指向例外/附则/备案清单(true/false)",
    "unit_is_wan": "金额单位是否为万元(true/false)", "policy_id": "制度编号",
    "city": "城市", "role": "适用角色", "mentions_2026": "是否提到 2026(true/false)",
    "effective_limit": "该条款的治理额度（例外条款给出上浮后额度）",
    "has_defect": "是否提到商品缺陷(true/false)",
    "product": "商品名称（原文若无则 null）",
    "order_id": "订单号（原文若无则 null）",
    "summary": "一句话摘要",
}
FIELDS4_ECOM = ["label", "amount", "currency", "has_discount"]
FIELDS8_ECOM = ["label", "amount", "currency", "has_discount",
                "has_defect", "product", "order_id", "summary"]
FIELDS1_FIN = ["clause_kind"]
FIELDS2_FIN = ["clause_kind", "governing_value"]
FIELDS4_FIN = ["clause_kind", "governing_value", "has_exception_pointer", "unit_is_wan"]
FIELDS8_FIN = ["clause_kind", "governing_value", "has_exception_pointer", "unit_is_wan",
               "policy_id", "city", "role", "mentions_2026"]


def bundle_prompt(fields):
    lines = "\n".join(f"- {f}：{HINT[f]}" for f in fields)
    body = "{" + ", ".join(f'"{f}": null' for f in fields) + "}"
    return ("你是结构化信息抽取器。只输出 JSON，包含以下字段：\n" + lines
            + "\n<payload>\n{payload}\n</payload>\n输出格式：" + body.replace("{", "{{").replace("}", "}}"))


def single_prompt(field):
    if field in P_TMPL:
        return P_TMPL[field]
    if field == "effective_limit":
        return P_TMPL["C_effective_limit"]
    body = ("{" + chr(34) + field + chr(34) + ": null" + "}")
    body = body.replace("{", "{{").replace("}", "}}")
    return ("你是结构化信息抽取器。只输出 JSON，包含一个字段：\n"
            + "- " + field + "：" + HINT[field]
            + "\n<payload>\n{payload}\n</payload>\n输出格式：" + body)

def jparse(text):
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    if not t.startswith("{"):
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            t = m.group(0)
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        return None


def field_ok(f, pred, oracle):
    if not isinstance(pred, dict):
        return 0
    v = pred.get(f)
    ov = oracle.get(f)
    if f in ("amount", "governing_value", "effective_limit"):
        try:
            return int(abs(float(v) - float(ov)) <= max(1.0, abs(float(ov)) * 0.01))
        except (TypeError, ValueError):
            return 0
    if f == "summary":
        return None                     # free-text，不参与自动评分
    if f in ("has_discount", "has_exception_pointer", "unit_is_wan", "mentions_2026",
             "has_defect"):
        if v is None:
            return 0
        got = (v is True) or (str(v).strip().lower() in ("true", "是", "yes", "1"))
        return int(got == bool(ov))
    if f == "order_id":
        if v is None or str(v).strip().lower() in ("null", "none", ""):
            return int(ov is None)
        return int(ov is not None and str(v).strip() == str(ov))
    if f == "product":
        if v is None:
            return int(ov is None)
        return int(ov is not None and str(ov) in str(v))
    if f == "clause_kind":
        return int(str(v).strip() == str(ov).strip())
    if v is None:
        return 0
    return int(str(ov).strip() in str(v))


# ================================================================ 谓词三型
PATTERNS_V13 = ["DISJOINT", "OVERLAP", "NESTED"]


def make_pred(pattern, i, R, kthr, salt):
    if pattern == "DISJOINT":
        return {"col": "row_id", "op": "hash_lt_salted", "value": kthr, "salt": salt + i}
    if pattern == "OVERLAP":
        core = max(1, kthr // 2)
        priv = max(1, kthr // 2)
        return {"op": "or", "preds": [
            {"col": "row_id", "op": "hash_lt", "value": core},
            {"col": "row_id", "op": "hash_lt_salted", "value": priv, "salt": salt + i}]}
    if pattern == "NESTED":
        v = min(1000, max(1, round(2 * kthr * (i + 1) / (R + 1))))
        return {"col": "row_id", "op": "hash_lt", "value": v}
    raise ValueError(pattern)


def make_workload_v13(rows, s_pct, reuse, pattern, caps, salt):
    kthr = max(1, int(round(s_pct / 100.0 * 1000)))
    out = []
    for i in range(reuse):
        pred = make_pred(pattern, i, reuse, kthr, salt)
        out.append(dict(qid=i, pred=pred, survivors=C.op_filter(rows, pred), caps=caps))
    return out


# ================================================================ 预算估算（§21）
BUDGET_TOTAL = 64_000_000
BUDGET_INTERNAL = 60_000_000
BUDGET_RESERVE = 4_000_000


def estimate_tokens(n_calls, tokens_in=180, tokens_out=60):
    return n_calls * (tokens_in + tokens_out)


def budget_plan(name, cells, rows_per_cell, strategies, calls_per_row, repeats=1,
                tokens_in=180, tokens_out=60, used=0):
    n_calls = cells * rows_per_cell * strategies * calls_per_row * repeats
    est = estimate_tokens(n_calls, tokens_in, tokens_out)
    return dict(experiment=name, cells=cells, rows_per_cell=rows_per_cell,
                strategies=strategies, calls_per_row=calls_per_row, repeats=repeats,
                estimated_calls=n_calls, estimated_tokens=est,
                estimated_cost_yuan=round(est / 1e6 * (GLM_PRICING["input_per_m"] * 0.75
                                                       + GLM_PRICING["output_short_per_m"] * 0.25), 4),
                already_used=used, cumulative_estimate=used + est,
                within_internal_budget=(used + est) <= BUDGET_INTERNAL,
                allowed=(used + est) <= BUDGET_INTERNAL)


# ================================================================ Key Router（§16-§22, §37）
class V13Client(GLMClient):
    """双 key 加权调度 + 429 只退避（不换 key）+ fallback 隔离 + 逐请求全字段记录。"""

    def __init__(self, experiment_id, log_dir=None, **kw):
        log_dir = log_dir or ART
        os.makedirs(log_dir, exist_ok=True)
        super().__init__(log_path=os.path.join(log_dir, "key_switch_log.jsonl"), **kw)
        self.experiment_id = experiment_id
        self.trace_path = os.path.join(log_dir, "glm_requests.jsonl")
        self.fallback_path = os.path.join(log_dir, "fallback_trace.jsonl")
        self.per_key = {f"glm_key{i}": dict(key_id=f"glm_key{i}", tokens_used=0, request_count=0,
                                            success_count=0, retry_count=0, rate_limit_count=0,
                                            auth_error_count=0, quota_error_count=0,
                                            consecutive_failures=0)
                        for i in range(len(self.keys))}
        self.fallback_used = False
        self.non_confirmatory = 0
        self._lock2 = threading.Lock()
        self._last_rl = 0

    def _pick_key(self):
        """quota-aware weighted scheduling：优先使用累计 token 更少的可用 key。"""
        avail = [i for i in range(len(self.keys)) if not self.glm_exhausted[i]]
        if not avail:
            return
        self.key_idx = min(avail, key=lambda i: self.per_key[f"glm_key{i}"]["tokens_used"])

    def complete(self, prompt, task="generic", cell_id=None, query_id=None, payload_hash=None):
        self._pick_key()
        with self._lock2:
            rl_before = self.rate_limit_events
            sw_before = self.switches
        t0 = time.time()
        try:
            text, pt, ct, meta = super().complete(prompt, task=task)
            err = None
        except FallbackFailed as e:
            text, pt, ct, meta, err = None, 0, 0, dict(backend="NONE"), repr(e)[:200]
        dt = (time.time() - t0) * 1000
        with self._lock2:
            rl_delta = self.rate_limit_events - rl_before
            sw_delta = self.switches - sw_before
        backend = meta.get("backend", "NONE")
        is_fb = (backend == "free_fallback")
        if is_fb:
            self.fallback_used = True
            self.non_confirmatory += 1
        rec = dict(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), experiment_id=self.experiment_id,
                   cell_id=cell_id, query_id=query_id, backend=backend, key_id=backend,
                   model=meta.get("model", "glm-4.5-air"), model_revision="glm-4.5-air@2026",
                   prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:16],
                   payload_hash=payload_hash,
                   input_tokens=pt, output_tokens=ct, total_tokens=pt + ct,
                   latency_ms=round(dt, 1), http_status=(200 if err is None else "ERROR"),
                   retry_count=rl_delta, rate_limit_count=rl_delta,
                   key_switches=sw_delta, provider=("zhipu" if backend.startswith("glm") else "siliconflow"),
                   fallback=is_fb, confirmatory=(not is_fb),
                   cost=round(GLMClient._cost(backend, pt, ct, meta.get("cached_tokens", 0)), 8),
                   error=err)
        with self._lock2:
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if is_fb:
                with open(self.fallback_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if backend.startswith("glm"):
            k = self.per_key[backend]
            k["request_count"] += 1
            k["tokens_used"] += pt + ct
            k["success_count"] += 1 if err is None else 0
            k["retry_count"] += rl_delta
            k["rate_limit_count"] += rl_delta
            k["consecutive_failures"] = 0 if err is None else k["consecutive_failures"] + 1
        return text, pt, ct, meta, rec

    def usage_v13(self):
        return dict(experiment_id=self.experiment_id, per_key=self.per_key,
                    switches=self.switches, rate_limit_events=self.rate_limit_events,
                    fallback_used=self.fallback_used, non_confirmatory_requests=self.non_confirmatory,
                    total_tokens=self.total_tokens,
                    total_cost_yuan=round(sum(v["cost"] for v in self.usage.values()), 6),
                    all_primary_model_only=bool(not self.using_fallback
                                                and self.usage["free_fallback"]["calls"] == 0),
                    budget=dict(total=BUDGET_TOTAL, internal=BUDGET_INTERNAL, reserve=BUDGET_RESERVE,
                                remaining=BUDGET_INTERNAL - self.total_tokens),
                    glm_pricing=GLM_PRICING)

    def persist_v13(self):
        C.write_json(os.path.join(ART, "key_usage.json"), self.usage_v13())
        with open(os.path.join(ART, "key_switch_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    event="EXPERIMENT_END", experiment_id=self.experiment_id,
                                    per_key=self.per_key, total_tokens=self.total_tokens),
                               ensure_ascii=False) + "\n")


def parallel_calls(client, jobs, workers=10):
    """jobs: [(prompt, tag, cell_id, query_id, payload_hash)] → 逐条记录。"""
    out = []

    def one(j):
        prompt, tag, cell_id, query_id, phash = j
        text, pt, ct, meta, rec = client.complete(prompt, task=tag, cell_id=cell_id,
                                                  query_id=query_id, payload_hash=phash)
        return dict(tag=tag, cell_id=cell_id, query_id=query_id, text=text, pt=pt, ct=ct,
                    meta=meta, rec=rec)
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(one, jobs):
            out.append(r)
    return out


# ================================================================ 极简 OLS
def _solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for j in range(col, n + 1):
            M[col][j] /= pv
        for r in range(n):
            if r != col and abs(M[r][col]) > 0:
                f = M[r][col]
                for j in range(col, n + 1):
                    M[r][j] -= f * M[col][j]
    return [M[i][n] for i in range(n)]


def _inv(A):
    n = len(A)
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        M[col] = [x / pv for x in M[col]]
        for r in range(n):
            if r != col and abs(M[r][col]) > 0:
                f = M[r][col]
                M[r] = [a - f * b for a, b in zip(M[r], M[col])]
    return [row[n:] for row in M]


def ols(X, y, names):
    """返回系数、SE、t、R²、n。自动剔除零方差列（避免奇异）。"""
    n = len(y)
    keep = []
    for j in range(len(X[0])):
        col = [row[j] for row in X]
        mu = sum(col) / n
        var = sum((v - mu) ** 2 for v in col) / n
        if j == 0 or var > 1e-12:
            keep.append(j)
    dropped = [names[j] for j in range(len(names)) if j not in keep]
    X = [[row[j] for j in keep] for row in X]
    names = [names[j] for j in keep]
    p = len(X[0])
    Xa = [row[:] for row in X]
    XtX = [[sum(Xa[k][i] * Xa[k][j] for k in range(n)) for j in range(p)] for i in range(p)]
    Xty = [sum(Xa[k][i] * y[k] for k in range(n)) for i in range(p)]
    XtXi = _inv(XtX)
    if XtXi is None:
        return None
    beta = [sum(XtXi[i][j] * Xty[j] for j in range(p)) for i in range(p)]
    yhat = [sum(Xa[k][i] * beta[i] for i in range(p)) for k in range(n)]
    resid = [y[k] - yhat[k] for k in range(n)]
    ssr = sum(r * r for r in resid)
    ybar = sum(y) / n
    sst = sum((v - ybar) ** 2 for v in y)
    dof = max(1, n - p)
    sigma2 = ssr / dof
    se = [math.sqrt(max(0.0, sigma2 * XtXi[i][i])) for i in range(p)]
    return dict(names=names, dropped_constant_columns=dropped,
                beta=[round(b, 6) for b in beta], se=[round(s, 6) for s in se],
                t=[round(b / s, 3) if s > 0 else None for b, s in zip(beta, se)],
                r2=round(1 - ssr / sst, 4) if sst > 0 else None,
                adj_r2=round(1 - (1 - (1 - ssr / sst)) * (n - 1) / dof, 4) if sst > 0 else None,
                n=n, resid_sd=round(math.sqrt(sigma2), 5))


# ================================================================ 极简 SVG
def svg_line_chart(path, series, title, xlabel, ylabel, width=760, height=430, logy=False):
    """series: [(name, [(x, y), ...], color)]"""
    pad_l, pad_r, pad_t, pad_b = 78, 190, 46, 56
    xs = [x for _, pts, _ in series for x, _ in pts]
    ys = [y for _, pts, _ in series for _, y in pts]
    if not xs or not ys:
        open(path, "w", encoding="utf-8").close()
        return path
    x0, x1 = min(xs), max(xs)
    if logy:
        ys = [v for v in ys if v > 0]
        y0, y1 = math.log10(min(ys)), math.log10(max(ys))
    else:
        y0, y1 = min(ys), max(ys)
    if x1 == x0:
        x1 = x0 + 1
    if y1 == y0:
        y1 = y0 + 1
    sx = lambda v: pad_l + (v - x0) / (x1 - x0) * (width - pad_l - pad_r)      # noqa: E731
    sy = lambda v: height - pad_b - ((math.log10(v) if logy else v) - y0) / (y1 - y0) * (height - pad_t - pad_b)  # noqa: E731
    L = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
         f'viewBox="0 0 {width} {height}" font-family="Segoe UI, PingFang SC, sans-serif">',
         f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
         f'<text x="{pad_l}" y="26" font-size="15" font-weight="600" fill="#1f2937">{title}</text>']
    for i in range(6):
        v = y0 + (y1 - y0) * i / 5
        yy = sy(10 ** v if logy else v)
        lab = f"{10 ** v:.3g}" if logy else f"{v:.3g}"
        L.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width - pad_r}" y2="{yy:.1f}" '
                 f'stroke="#eef2f7"/>')
        L.append(f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" font-size="10" fill="#6b7280" '
                 f'text-anchor="end">{lab}</text>')
    for i in range(5):
        v = x0 + (x1 - x0) * i / 4
        xx = sx(v)
        L.append(f'<text x="{xx:.1f}" y="{height - pad_b + 18}" font-size="10" fill="#6b7280" '
                 f'text-anchor="middle">{v:.3g}</text>')
    L.append(f'<text x="{width - pad_r + 6}" y="{height - pad_b + 18}" font-size="10" '
             f'fill="#6b7280">{xlabel}</text>')
    L.append(f'<text x="{pad_l - 8}" y="{pad_t - 14}" font-size="10" fill="#6b7280" '
             f'text-anchor="end">{ylabel}</text>')
    lx = width - pad_r + 12
    for idx, (name, pts, color) in enumerate(series):
        d = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts)
        L.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            L.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.6" fill="{color}"/>')
        yy = pad_t + idx * 20
        L.append(f'<line x1="{lx}" y1="{yy}" x2="{lx + 14}" y2="{yy}" stroke="{color}" '
                 f'stroke-width="2.5"/>')
        L.append(f'<text x="{lx + 20}" y="{yy + 4}" font-size="11" fill="#374151">{name}</text>')
    L.append("</svg>")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path


def svg_bar_chart(path, groups, series, title, width=820, height=430):
    """groups: ['w1','w2']; series: [(name, [v1,v2], color)]"""
    pad_l, pad_r, pad_t, pad_b = 84, 200, 46, 60
    vals = [v for _, vs, _ in series for v in vs if v is not None]
    vmax = max(vals) if vals else 1
    gw = (width - pad_l - pad_r) / max(1, len(groups))
    bw = gw / (len(series) + 1.2)
    L = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
         f'viewBox="0 0 {width} {height}" font-family="Segoe UI, PingFang SC, sans-serif">',
         f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
         f'<text x="{pad_l}" y="26" font-size="15" font-weight="600" fill="#1f2937">{title}</text>']
    for i in range(5):
        yy = height - pad_b - (height - pad_t - pad_b) * i / 4
        L.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width - pad_r}" y2="{yy:.1f}" stroke="#eef2f7"/>')
        L.append(f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" font-size="10" fill="#6b7280" '
                 f'text-anchor="end">{vmax * i / 4:.3g}</text>')
    for gi, g in enumerate(groups):
        gx = pad_l + gi * gw
        L.append(f'<text x="{gx + gw / 2:.1f}" y="{height - pad_b + 18}" font-size="11" '
                 f'fill="#374151" text-anchor="middle">{g}</text>')
        for si, (name, vs, color) in enumerate(series):
            v = vs[gi] if gi < len(vs) else None
            if v is None:
                continue
            h = (height - pad_t - pad_b) * (v / vmax)
            bx = gx + (si + 0.6) * bw
            L.append(f'<rect x="{bx:.1f}" y="{height - pad_b - h:.1f}" width="{bw * 0.82:.1f}" '
                     f'height="{h:.1f}" fill="{color}" rx="2"/>')
            L.append(f'<text x="{bx + bw * 0.41:.1f}" y="{height - pad_b - h - 4:.1f}" '
                     f'font-size="9" fill="#4b5563" text-anchor="middle">{v:.3g}</text>')
    lx = width - pad_r + 12
    for idx, (name, _, color) in enumerate(series):
        yy = pad_t + idx * 20
        L.append(f'<rect x="{lx}" y="{yy - 7}" width="14" height="9" fill="{color}" rx="2"/>')
        L.append(f'<text x="{lx + 20}" y="{yy + 1}" font-size="11" fill="#374151">{name}</text>')
    L.append("</svg>")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path
