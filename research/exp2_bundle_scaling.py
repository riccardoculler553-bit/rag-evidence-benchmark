# -*- coding: utf-8 -*-
"""实验 2 第二轮真实探针：能力捆绑的规模-精度曲线 + 输入长度-成本斜率。

这是"语义特异性"假设唯一可能存活的地方：
  relational projection 中"多物化一列"的边际成本 ≈ 0；
  语义能力中"多抽一个字段"的边际成本 > 0（P2 已实测 sub-additive 但非零）。
若该边际成本伴随**精度下降**，则存在一个传统物化框架不建模的
"广度 × 精度 × 成本"约束优化问题；
若精度不随广度下降，则最优规则退化为"按需最大化捆绑"，
即经典的 generalized materialized view（无新意）。

Oracles 全部由模板/词表确定性推导（label / amount / currency / product / order_id /
discount_bool / defect_bool），free-text 字段不参与精度统计。
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "exp"))
import common as C                                    # noqa: E402
import world as W                                     # noqa: E402
from llm_glm import GLMClient, FallbackFailed         # noqa: E402
from source_plane import DEFECTS                      # noqa: E402

OUT = os.path.join(HERE, "experiment2_semantic_specificity")
ART = os.path.join(HERE, "artifacts", "model_calls")
CALLS = []

FIELDS8 = ["label", "amount", "currency", "product", "order_id", "has_discount",
           "has_defect", "summary"]
FIELDS4 = ["label", "amount", "has_discount", "has_defect"]
FIELDS2 = ["label", "amount"]

SCHEMA_HINT = {
    "label": "logistics_delay|product_quality|refund_request|address_change|other",
    "amount": "订单商品金额（数字）",
    "currency": "货币单位（如 元）",
    "product": "商品名称（原文中的商品名）",
    "order_id": "订单号（原文若无订单号则 null）",
    "has_discount": "是否提到平台促销原价（true/false）",
    "has_defect": "是否提到商品缺陷（true/false）",
    "summary": "一句话摘要",
}
SINGLE_PROMPT = {
    "label": ('你是电商客服工单分类器。只输出 JSON。\n可选标签：'
              'logistics_delay | product_quality | refund_request | address_change | other\n'
              '<payload>\n{payload}\n</payload>\n输出格式：{{"label": "..."}}'),
}


def bundle_prompt(fields):
    lines = "\n".join(f"- {f}：{SCHEMA_HINT[f]}" for f in fields)
    body = "{" + ", ".join(f'"{f}": null' for f in fields) + "}"
    body_esc = body.replace("{", "{{").replace("}", "}}")
    return ("你是电商客服工单结构化分析器。只输出 JSON，包含以下字段：\n"
            + lines + "\n<payload>\n{payload}\n</payload>\n输出格式：" + body_esc)


def single_prompt(field):
    if field in SINGLE_PROMPT:
        return SINGLE_PROMPT[field]
    return ("你是电商客服工单结构化分析器。只输出 JSON，包含以下单个字段：\n"
            f"- {field}：{SCHEMA_HINT[field]}\n"
            "<payload>\n{payload}\n</payload>\n"
            f'输出格式：{{{{"{field}": null}}}}')


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


def oracles_for(row, prod_names):
    pl = row["payload"]
    oid = re.search(r"订单([A-Za-z0-9\-]+)", pl)
    prod = next((n for n in prod_names if n in pl), None)
    return dict(label=row["oracle"]["labels"]["issue"], amount=row["oracle"]["values"]["amount"],
                currency="元", product=prod,
                order_id=(oid.group(1) if oid else None),
                has_discount=("原价" in pl),
                has_defect=any(d in pl for d in DEFECTS))


TRUE_SET = {"true", "True", "是", "yes"}


def field_ok(f, pred, oracle):
    if f == "summary":
        return None
    v = pred.get(f) if isinstance(pred, dict) else None
    if f == "amount":
        try:
            return int(abs(float(v) - float(oracle)) <= 1)
        except (TypeError, ValueError):
            return 0
    if f in ("has_discount", "has_defect"):
        if v is None:
            return 0
        got = (v is True) or (str(v).strip().lower() in ("true", "是", "yes", "1"))
        return int(got == bool(oracle))
    if f == "order_id":
        if v is None or str(v).strip().lower() in ("null", "none", ""):
            return int(oracle is None)
        return int(oracle is not None and str(v).strip().strip('"').lstrip("：:") == str(oracle))
    if f == "product":
        if v is None:
            return 0
        return int(oracle is not None and str(oracle) in str(v))
    if f == "currency":
        return int(v is not None and "元" in str(v))
    return int(str(v).strip().lower() == str(oracle).strip().lower())


def one_call(client, prompt, tag, **extra):
    t0 = time.time()
    try:
        text, pt, ct, meta = client.complete(prompt, task=tag)
    except FallbackFailed as e:
        CALLS.append(dict(tag=tag, status="FALLBACK_FAILED", error=str(e)[:200]))
        return dict(ok=False, text=None, pt=0, ct=0, meta=dict(backend="NONE"), **extra)
    CALLS.append(dict(tag=tag, ts=time.strftime("%Y-%m-%dT%H:%M:%S"), status="OK",
                      provider=("zhipu-open-platform" if str(meta.get("backend", "")).startswith("glm")
                                else "siliconflow"),
                      key_id=meta.get("backend"), backend=meta.get("backend"),
                      model=meta.get("model"), max_tokens=512, temperature=0, thinking="disabled",
                      prompt_tokens=pt, completion_tokens=ct,
                      cached_tokens=meta.get("cached_tokens", 0),
                      latency_ms=meta.get("latency_ms"),
                      wall_ms=round((time.time() - t0) * 1000, 1), retry_count=0, **extra))
    return dict(ok=True, text=text, pt=pt, ct=ct, meta=meta, **extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--max-qps", type=float, default=20.0)
    args = ap.parse_args()

    rows_by_domain, snap = C.materialize()
    ecom = rows_by_domain["ecom"]
    prods = [p["product_name"] for p in W.all_entities()["products"]]
    step = max(1, len(ecom) // (args.rows * 5))
    sample = ecom[::step][:args.rows]
    client = GLMClient(max_tokens=512, max_qps=args.max_qps,
                       log_path=os.path.join(ART, "key_switch_log_probe2.jsonl"))
    t0 = time.time()

    # ---------- A. 捆绑规模-精度曲线 ----------
    variants = [("V1", ["label"]), ("V2", FIELDS2), ("V4", FIELDS4), ("V8", FIELDS8)]
    recs = {}
    with cf.ThreadPoolExecutor(args.workers) as ex:
        jobs = []
        for r in sample:
            for name, fl in variants:
                jobs.append((r["row_id"], name, fl,
                             ex.submit(one_call, client, bundle_prompt(fl).format(payload=r["payload"]),
                                       "B_" + name, row_id=r["row_id"])))
            for f in FIELDS8:
                jobs.append((r["row_id"], "SEP8", [f],
                             ex.submit(one_call, client, single_prompt(f).format(payload=r["payload"]),
                                       "B_SEP_" + f, row_id=r["row_id"])))
        results = {}
        for rid, name, fl, fut in jobs:
            d = fut.result()
            results.setdefault(rid, {}).setdefault(name, []).append((fl, d))

    rows_out = []
    oracle_map = {r["row_id"]: oracles_for(r, prods) for r in sample}
    for rid, byvar in results.items():
        orc = oracle_map[rid]
        rec = dict(row_id=rid, oracle=orc)
        for name, fl in variants:
            items = byvar.get(name, [])
            if not items:
                continue
            fl0, d = items[0]
            o = jparse(d["text"]) or {}
            rec[name] = dict(pt=d["pt"], ct=d["ct"],
                             parse_ok=int(isinstance(o, dict)),
                             n_keys=len(o) if isinstance(o, dict) else 0,
                             per_field={f: field_ok(f, o, orc.get(f)) for f in fl0})
        sep = byvar.get("SEP8", [])
        rec["SEP8"] = dict(pt=sum(d["pt"] for _, d in sep), ct=sum(d["ct"] for _, d in sep),
                           per_field={fl[0]: field_ok(fl[0], jparse(d["text"]) or {}, orc.get(fl[0]))
                                      for fl, d in sep})
        rows_out.append(rec)

    def acc(name, fields=FIELDS8):
        vals = []
        for r in rows_out:
            pf = r.get(name, {}).get("per_field", {})
            vals += [v for f, v in pf.items() if v is not None]
        return round(st.mean(vals), 4) if vals else None

    def pt(name):
        v = [r[name]["pt"] for r in rows_out if name in r]
        return round(st.mean(v), 2) if v else None

    per_field_acc = {}
    for f in FIELDS8:
        if f == "summary":
            continue
        d = {}
        for n in ["V1", "V2", "V4", "V8", "SEP8"]:
            vals = [r[n]["per_field"][f] for r in rows_out
                    if n in r and f in r[n].get("per_field", {})
                    and r[n]["per_field"][f] is not None]
            d[n] = round(st.mean(vals), 4) if vals else None
        per_field_acc[f] = d
    bundle = dict(
        n=len(rows_out),
        mean_prompt_tokens={n: pt(n) for n in ["V1", "V2", "V4", "V8", "SEP8"]},
        mean_completion_tokens={n: (round(st.mean([r[n]["ct"] for r in rows_out if n in r]), 2)
                                    if any(n in r for r in rows_out) else None)
                                for n in ["V1", "V2", "V4", "V8", "SEP8"]},
        total_cost_units={n: ((pt(n) or 0) + (round(st.mean([r[n]["ct"] for r in rows_out
                                                            if n in r]), 2) if any(
            n in r for r in rows_out) else 0)) for n in ["V1", "V2", "V4", "V8", "SEP8"]},
        overall_field_accuracy={n: acc(n) for n in ["V1", "V2", "V4", "V8", "SEP8"]},
        per_field_accuracy=per_field_acc,
        parse_ok_rate={n: round(st.mean([r[n]["parse_ok"] for r in rows_out if n in r]), 4)
                       for n in ["V1", "V2", "V4", "V8"]},
        rows=rows_out,
    )
    v8, s8 = bundle["mean_prompt_tokens"]["V8"], bundle["mean_prompt_tokens"]["SEP8"]
    bundle["cost_ratio_V8_vs_8calls"] = round(v8 / s8, 4) if v8 and s8 else None
    bundle["accuracy_drop_V8_minus_V1"] = (
        round((acc("V8") or 0) - (acc("V1") or 0), 4))
    print(f"[bundle] pt V1={pt('V1')} V2={pt('V2')} V4={pt('V4')} V8={pt('V8')} SEP8={s8}",
          flush=True)
    print(f"[bundle] acc V1={acc('V1')} V2={acc('V2')} V4={acc('V4')} V8={acc('V8')} "
          f"SEP8={acc('SEP8')}", flush=True)

    # ---------- B. 输入长度 → 成本斜率 ----------
    filler = "（补充说明：本工单来自客服系统自动归档，编号仅用于内部追踪。）"
    ladder = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        jobs = []
        for r in sample[:16]:
            for mult in (1, 4, 16):
                pl = r["payload"] + "".join([filler] * (mult - 1))
                jobs.append((r["row_id"], mult, len(pl),
                             ex.submit(one_call, client,
                                       single_prompt("label").format(payload=pl),
                                       f"L_x{mult}", row_id=r["row_id"], mult=mult)))
        for rid, mult, ln, fut in jobs:
            d = fut.result()
            ladder.append(dict(row_id=rid, mult=mult, payload_len=ln, pt=d["pt"], ct=d["ct"]))
    by_mult = {}
    for x in ladder:
        by_mult.setdefault(x["mult"], []).append(x)
    slope = None
    xs = [x["payload_len"] for x in ladder]
    ys = [x["pt"] for x in ladder]
    mx, my = st.mean(xs), st.mean(ys)
    denom = sum((a - mx) ** 2 for a in xs) or 1e-9
    slope = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / denom
    length_probe = dict(
        per_mult={k: dict(n=len(v), mean_len=round(st.mean([x["payload_len"] for x in v]), 1),
                          mean_pt=round(st.mean([x["pt"] for x in v]), 2),
                          mean_ct=round(st.mean([x["ct"] for x in v]), 2))
                  for k, v in sorted(by_mult.items())},
        tokens_per_char_slope=round(slope, 4),
        tokens_per_extra_100_chars=round(slope * 100, 2),
        note="成本 = 输入 tokens 的严格函数；survivor 的 payload 规模直接决定单位成本。",
        rows=ladder)
    print(f"[length] slope={slope:.4f} tokens/char -> +{slope*100:.1f} tokens per 100 chars",
          flush=True)

    summ = client.summary()
    out = dict(probe="E2b_bundle_scaling_and_length", model="glm-4.5-air", snapshot=snap,
               n_calls=sum(1 for c in CALLS if c.get("status") == "OK"),
               used_tokens=client.total_tokens, cost_yuan=summ["total_cost_yuan"],
               wall_clock_sec=round(time.time() - t0, 1),
               all_primary_model_only=bool(not summ["using_fallback"]
                                           and summ["per_backend"]["free_fallback"]["calls"] == 0),
               usage=summ, bundling=bundle, input_length=length_probe)
    C.write_json(os.path.join(OUT, "bundle_scaling.json"), out)
    C.write_jsonl(os.path.join(ART, "glm_calls_probe2.jsonl"), CALLS)
    client.persist(os.path.join(OUT, "key_usage_probe2.json"))
    print(json.dumps(dict(tokens=client.total_tokens, cost=out["cost_yuan"],
                          calls=out["n_calls"], all_primary=out["all_primary_model_only"],
                          wall_s=out["wall_clock_sec"]), ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
