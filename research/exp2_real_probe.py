# -*- coding: utf-8 -*-
"""实验 2（真实 GLM-4.5-Air 微探针）：语义能力 vs 通用昂贵 UDF 的行为差异。

只测四件"如果不成立就直接杀死 semantic-specific 假设"的事（预算 < 0.8M tokens）：

  P1 成本是否 payload 相关：unit_cost 与 payload 长度的关系（UDF 无此性质）
  P2 能力捆绑是否 sub-additive：一次调用要 k 个字段 vs k 次单字段调用
       —— 若 sub-additive，则存在"捆绑选择"这一 relational projection 不需要的决策
  P3 语义保持扰动下的稳定性：改写不改变语义 → 答案不变，但 payload_hash 变 → 句法缓存失效
       —— 语义等价的输入不等价于关系元组相等
  P4 能力依赖的共享读数成本：B 的 prompt 里带 A 的输出，边际成本是否更低

引擎使用 v2 安全实现（keep-alive / 令牌桶 / 429 退避不换 key / 仅 401·403·额度耗尽才换）。
本探针为 **auxiliary probe**，不参与任何因果对照（§17）；仍强制记录 all_primary_model_only。
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "exp"))
import common as C                                        # noqa: E402
from llm_glm import GLMClient, FallbackFailed, GLM_PRICING  # noqa: E402

OUT = os.path.join(HERE, "experiment2_semantic_specificity")
ART = os.path.join(HERE, "artifacts", "model_calls")

CALLS = []
LOCK = None


def log_call(rec):
    CALLS.append(rec)


def one_call(client, prompt, tag, **extra):
    t0 = time.time()
    try:
        text, pt, ct, meta = client.complete(prompt, task=tag)
    except FallbackFailed as e:
        log_call(dict(tag=tag, status="FALLBACK_FAILED", error=str(e)[:200],
                      ts=time.strftime("%Y-%m-%dT%H:%M:%S")))
        return dict(ok=False, text=None, pt=0, ct=0, meta=dict(backend="NONE"), **extra)
    log_call(dict(tag=tag, ts=time.strftime("%Y-%m-%dT%H:%M:%S"), status="OK",
                  provider=("zhipu-open-platform" if str(meta.get("backend", "")).startswith("glm")
                            else "siliconflow"),
                  key_id=meta.get("backend"), backend=meta.get("backend"),
                  model=meta.get("model"), max_tokens=512, temperature=0, thinking="disabled",
                  prompt_tokens=pt, completion_tokens=ct,
                  cached_tokens=meta.get("cached_tokens", 0),
                  cost_yuan=round(GLMClient._cost(meta.get("backend", "glm_key0"), pt, ct,
                                                  meta.get("cached_tokens", 0)), 8),
                  latency_ms=meta.get("latency_ms"), wall_ms=round((time.time() - t0) * 1000, 1),
                  retry_count=0, **extra))
    return dict(ok=True, text=text, pt=pt, ct=ct, meta=meta, **extra)


def jparse(text):
    """与 capability.parse_model_output 同族的最小归一（仅用于探针统计）。"""
    import re
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


# ---------------------------------------------------------------- 探针 prompt
P_LABEL = ("你是电商客服工单分类器。只输出 JSON。\n"
           "可选标签：logistics_delay | product_quality | refund_request | address_change | other\n"
           "<payload>\n{payload}\n</payload>\n输出格式：{{\"label\": \"...\"}}")

P_LABEL_AMOUNT = ("你是电商客服工单分析器。只输出 JSON，包含 label 与 amount 两个字段。\n"
                  "label 可选：logistics_delay | product_quality | refund_request | address_change | other\n"
                  "amount 为订单商品金额（数字，不带单位）。\n"
                  "<payload>\n{payload}\n</payload>\n"
                  "输出格式：{{\"label\": \"...\", \"amount\": 0}}")

P_QUAD = ("你是电商客服工单分析器。只输出 JSON，包含 label、amount、urgency、evidence 四个字段。\n"
          "label 可选：logistics_delay | product_quality | refund_request | address_change | other\n"
          "amount 为订单商品金额（数字）。urgency 取 low|medium|high。evidence 为原文中最关键的一句。\n"
          "<payload>\n{payload}\n</payload>\n"
          "输出格式：{{\"label\": \"...\", \"amount\": 0, \"urgency\": \"...\", \"evidence\": \"...\"}}")

P_AMOUNT = ("你是金额抽取器。只输出 JSON，抽取订单商品金额（数字，不带单位）。\n"
            "<payload>\n{payload}\n</payload>\n输出格式：{{\"amount\": 0}}")
P_URGENCY = ("判断该工单紧急程度。只输出 JSON。urgency 取 low|medium|high。\n"
             "<payload>\n{payload}\n</payload>\n输出格式：{{\"urgency\": \"...\"}}")
P_EVIDENCE = ("抽取原文中最关键的一句作为证据。只输出 JSON。\n"
              "<payload>\n{payload}\n</payload>\n输出格式：{{\"evidence\": \"...\"}}")

P_AMOUNT_CTX = ("以下是从原文中已抽取的实体。请只输出 JSON，抽取订单商品金额（数字）。\n"
                "{ctx}\n<payload>\n{payload}\n</payload>\n输出格式：{{\"amount\": 0}}")


def perturb(t):
    """语义保持的确定性扰动（不改任何关键词与数字，只改标点/空白/前后缀）。"""
    t = t.replace("，", ", ").replace("：", ": ").replace("。", ". ")
    t = t.replace(" ", "  ")
    return "【客服记录】" + t.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=24)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-qps", type=float, default=20.0)
    ap.add_argument("--max-tokens", type=int, default=800_000)
    args = ap.parse_args()

    rows_by_domain, snap = C.materialize()
    ecom = rows_by_domain["ecom"]
    # 按 payload 长度分层抽样，保证 P1 的成本-长度关系有跨度
    order = sorted(ecom, key=lambda r: len(r["payload"]))
    step = max(1, len(order) // (args.rows * 4))
    sample = order[::step][: args.rows]
    print(f"[probe] rows={len(sample)}  len range "
          f"{len(sample[0]['payload'])}..{len(sample[-1]['payload'])}", flush=True)

    client = GLMClient(max_tokens=512, log_path=os.path.join(ART, "key_switch_log_probe.jsonl"),
                       max_qps=args.max_qps)
    t0 = time.time()

    # ---------------- P1：成本 vs payload 长度 ----------------
    p1 = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(one_call, client, P_LABEL.format(payload=r["payload"]), "P1",
                          row_id=r["row_id"], payload_len=len(r["payload"]),
                          oracle=r["oracle"]["labels"]["issue"]) for r in sample]
        for f in futs:
            d = f.result()
            out = jparse(d.get("text"))
            p1.append(dict(row_id=d["row_id"], payload_len=d["payload_len"], pt=d["pt"], ct=d["ct"],
                           backend=d["meta"].get("backend"), latency_ms=d["meta"].get("latency_ms"),
                           pred=(out or {}).get("label"), oracle=d["oracle"],
                           correct=int((out or {}).get("label") == d["oracle"])))
    pts = [x["pt"] for x in p1]
    lens = [x["payload_len"] for x in p1]
    mean_pt = st.mean(pts)
    cov = sum((a - st.mean(lens)) * (b - mean_pt) for a, b in zip(lens, pts)) / len(pts)
    sd = (st.pstdev(lens) * st.pstdev(pts)) or 1e-9
    p1_res = dict(n=len(p1), payload_len_range=[min(lens), max(lens)],
                  prompt_tokens_range=[min(pts), max(pts)],
                  mean_prompt_tokens=round(mean_pt, 2),
                  pearson_len_pt=round(cov / sd, 4),
                  pt_per_char=round(mean_pt / st.mean(lens), 5),
                  label_accuracy=round(st.mean([x["correct"] for x in p1]), 4),
                  rows=p1)
    print(f"[probe] P1 done: pearson={p1_res['pearson_len_pt']} acc={p1_res['label_accuracy']}",
          flush=True)

    # ---------------- P2：能力捆绑 sub-additivity ----------------
    p2_rows = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        jobs = []
        for r in sample:
            pl = r["payload"]
            jobs.append(("V1", ex.submit(one_call, client, P_LABEL.format(payload=pl), "P2_V1",
                                         row_id=r["row_id"], payload_len=len(pl))))
            jobs.append(("V2", ex.submit(one_call, client, P_LABEL_AMOUNT.format(payload=pl),
                                         "P2_V2", row_id=r["row_id"], payload_len=len(pl))))
            jobs.append(("V4", ex.submit(one_call, client, P_QUAD.format(payload=pl), "P2_V4",
                                         row_id=r["row_id"], payload_len=len(pl))))
            for nm, tpl in (("V4sep_label", P_LABEL), ("V4sep_amount", P_AMOUNT),
                            ("V4sep_urgency", P_URGENCY), ("V4sep_evidence", P_EVIDENCE)):
                jobs.append(("V4SEP", ex.submit(one_call, client, tpl.format(payload=pl), nm,
                                                row_id=r["row_id"], payload_len=len(pl))))
        by_row = {}
        for kind, f in jobs:
            d = f.result()
            o = jparse(d.get("text")) or {}
            rec = by_row.setdefault(d["row_id"], dict(row_id=d["row_id"],
                                                      payload_len=d["payload_len"], sep=[]))
            if kind in ("V1", "V2", "V4"):
                rec[kind] = dict(pt=d["pt"], ct=d["ct"],
                                 label=o.get("label"), amount=o.get("amount"),
                                 keys=sorted(o.keys()), parse_ok=int(d["text"] is not None and
                                                                     ("{" in (d["text"] or ""))))
            else:
                rec["sep"].append(dict(pt=d["pt"], ct=d["ct"]))
        oracle = {r["row_id"]: r["oracle"] for r in sample}
        for rid, rec in by_row.items():
            o = oracle[rid]
            rec["oracle_label"] = o["labels"]["issue"]
            rec["oracle_amount"] = o["values"]["amount"]
            for k in ("V1", "V2", "V4"):
                if k in rec:
                    rec[k]["label_ok"] = int(rec[k]["label"] == rec["oracle_label"])
                    try:
                        rec[k]["amount_ok"] = int(abs(float(rec[k]["amount"])
                                                      - float(rec["oracle_amount"])) <= 1)
                    except (TypeError, ValueError):
                        rec[k]["amount_ok"] = 0
            rec["sep_pt_total"] = sum(s["pt"] for s in rec["sep"])
            rec["sep_ct_total"] = sum(s["ct"] for s in rec["sep"])
            p2_rows.append(rec)

    def m(k, f):
        v = [r[k][f] for r in p2_rows if k in r and r[k].get(f) is not None]
        return round(st.mean(v), 3) if v else None
    v1pt, v2pt, v4pt = m("V1", "pt"), m("V2", "pt"), m("V4", "pt")
    sep_pt = round(st.mean([r["sep_pt_total"] for r in p2_rows]), 2)
    sep_ct = round(st.mean([r["sep_ct_total"] for r in p2_rows]), 2)
    p2_res = dict(
        n=len(p2_rows),
        mean_prompt_tokens=dict(V1_1field=v1pt, V2_2fields=v2pt, V4_4fields=v4pt,
                                V4SEP_4separate_calls=sep_pt),
        mean_completion_tokens=dict(V4_4fields=m("V4", "ct"), V4SEP_4separate_calls=sep_ct),
        marginal_prompt_token_per_field=dict(
            f2_minus_f1=round(v2pt - v1pt, 2) if v1pt and v2pt else None,
            f4_minus_f2_over2=round((v4pt - v2pt) / 2, 2) if v2pt and v4pt else None,
            separate_per_field=round(sep_pt / 4, 2)),
        sub_additive_cost=bool(v4pt and v4pt < sep_pt * 0.75),
        cost_ratio_4fields_vs_4calls=round(v4pt / sep_pt, 4) if v4pt and sep_pt else None,
        accuracy=dict(
            V1_label=m("V1", "label_ok"), V2_label=m("V2", "label_ok"), V4_label=m("V4", "label_ok"),
            V2_amount=m("V2", "amount_ok"), V4_amount=m("V4", "amount_ok"),
            V4_parse_ok=m("V4", "parse_ok")),
        rows=p2_rows)
    print(f"[probe] P2 done: V4 pt={v4pt} vs 4calls pt={sep_pt} ratio="
          f"{p2_res['cost_ratio_4fields_vs_4calls']} acc4={p2_res['accuracy']['V4_label']}",
          flush=True)

    # ---------------- P3：语义保持扰动 ----------------
    p3 = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        jobs = []
        for r in sample[:20]:
            jobs.append((r["row_id"], "orig", r["payload"],
                         ex.submit(one_call, client, P_LABEL.format(payload=r["payload"]),
                                   "P3_orig", row_id=r["row_id"])))
            pp = perturb(r["payload"])
            jobs.append((r["row_id"], "perturbed", pp,
                         ex.submit(one_call, client, P_LABEL.format(payload=pp),
                                   "P3_perturbed", row_id=r["row_id"])))
        got = {}
        for rid, kind, pl, f in jobs:
            d = f.result()
            o = jparse(d.get("text")) or {}
            got.setdefault(rid, {})[kind] = dict(label=o.get("label"), pt=d["pt"],
                                                 hash=hashlib.sha256(pl.encode()).hexdigest()[:16])
        for rid, v in got.items():
            if "orig" in v and "perturbed" in v:
                p3.append(dict(row_id=rid, label_orig=v["orig"]["label"],
                               label_pert=v["perturbed"]["label"],
                               same_label=int(v["orig"]["label"] == v["perturbed"]["label"]),
                               hash_same=int(v["orig"]["hash"] == v["perturbed"]["hash"]),
                               pt_delta=v["perturbed"]["pt"] - v["orig"]["pt"]))
    p3_res = dict(n=len(p3),
                  label_stability=round(st.mean([x["same_label"] for x in p3]), 4),
                  syntactic_key_stability=round(st.mean([x["hash_same"] for x in p3]), 4),
                  mean_pt_delta=round(st.mean([x["pt_delta"] for x in p3]), 2), rows=p3)
    print(f"[probe] P3 done: label_stability={p3_res['label_stability']} "
          f"hash_stability={p3_res['syntactic_key_stability']}", flush=True)

    # ---------------- P4：依赖共享读数成本 ----------------
    p4 = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        jobs = []
        for r in sample:
            jobs.append(("plain", ex.submit(one_call, client, P_AMOUNT.format(payload=r["payload"]),
                                            "P4_plain", row_id=r["row_id"])))
            ctx = (f"已抽取实体：platform={r['columns']['platform']}, "
                   f"sku={r['columns']['sku']}, warehouse={r['columns']['warehouse']}")
            jobs.append(("ctx", ex.submit(one_call, client,
                                          P_AMOUNT_CTX.format(ctx=ctx, payload=r["payload"]),
                                          "P4_ctx", row_id=r["row_id"])))
        got = {}
        for kind, f in jobs:
            d = f.result()
            got.setdefault(d["row_id"], {})[kind] = dict(pt=d["pt"], ct=d["ct"])
        for rid, v in got.items():
            if "plain" in v and "ctx" in v:
                p4.append(dict(row_id=rid, pt_plain=v["plain"]["pt"], pt_ctx=v["ctx"]["pt"],
                               delta=v["ctx"]["pt"] - v["plain"]["pt"]))
    p4_res = dict(n=len(p4),
                  mean_pt_plain=round(st.mean([x["pt_plain"] for x in p4]), 2),
                  mean_pt_with_context=round(st.mean([x["pt_ctx"] for x in p4]), 2),
                  mean_delta=round(st.mean([x["delta"] for x in p4]), 2),
                  delta_ratio=round(st.mean([x["delta"] for x in p4])
                                    / st.mean([x["pt_plain"] for x in p4]), 4), rows=p4)
    print(f"[probe] P4 done: delta={p4_res['mean_delta']} ratio={p4_res['delta_ratio']}", flush=True)

    summ = client.summary()
    used = client.total_tokens
    out = dict(
        probe="E2_real_micro_probe", model="glm-4.5-air", temperature=0, thinking="disabled",
        snapshot=snap, n_calls=sum(1 for c in CALLS if c.get("status") == "OK"),
        usage=summ, used_tokens=used, cost_yuan=summ["total_cost_yuan"],
        wall_clock_sec=round(time.time() - t0, 1),
        all_primary_model_only=bool(not summ["using_fallback"] and
                                    summ["per_backend"]["free_fallback"]["calls"] == 0),
        P1_cost_vs_length=p1_res, P2_bundling=p2_res, P3_perturbation=p3_res,
        P4_dependency_context=p4_res,
        pricing=GLM_PRICING,
        note=("辅助探针（auxiliary），不参与主因果对照；用于检验 semantic-specific 机制是否存在。"
              "P2 的捆绑 prompt 为探针专用，不用于任何策略对比。"),
    )
    C.write_json(os.path.join(OUT, "real_probe.json"), out)
    C.write_csv(os.path.join(OUT, "real_probe_trace.csv"), p1 + [dict(**x) for x in p2_rows])
    os.makedirs(ART, exist_ok=True)
    C.write_jsonl(os.path.join(ART, "glm_calls_probe.jsonl"), CALLS)
    client.persist(os.path.join(OUT, "key_usage_probe.json"))
    print(json.dumps(dict(tokens=used, cost=out["cost_yuan"], calls=out["n_calls"],
                          all_primary=out["all_primary_model_only"],
                          switches=summ["switches"], wall_s=out["wall_clock_sec"]),
                     ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
