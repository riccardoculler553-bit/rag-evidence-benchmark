# -*- coding: utf-8 -*-
"""实验 2 公平口径：工作负载级总成本对比（A / B / C）。

问题：per-cell 摊销把 A 的成本摊到"整个域的全部 query"（156 条），
而把 B/C 摊到"本 cell 的 query"（1–50 条），两者不可比。

本脚本给出统一口径：
  (1) WORKLOAD_TOTAL：执行整个矩阵（24 cells 全部 query）时三种策略的总 token / 总成本
  (2) PER_QUERY_GLOBAL：总成本 ÷ 该域 query 总数（同一分母）
  (3) PER_CELL（附注）：B/C 按 cell 摊销，A 按域摊销（仅用于展示，不作裁决依据）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import EXP_OUT, PRICING
from llm_glm import GLMClient


def cost(stats):
    return sum(GLMClient._cost(b, stats.get("pt_by_backend", {}).get(b, 0),
                               stats.get("ct_by_backend", {}).get(b, 0), 0)
               for b in stats.get("pt_by_backend", {}))


def exp1_totals():
    """实验 1（mock）工作负载级口径：直接读取 exp1_matrix.json 中的 workload_totals。"""
    path = os.path.join(EXP_OUT, "exp1_matrix.json")
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8")).get("workload_totals", {})


def main():
    e2 = json.load(open(os.path.join(EXP_OUT, "exp2_results.json"), encoding="utf-8"))
    cells = e2["cells"]
    domains = sorted({k.split("|")[0] for k in cells})
    out = {}
    for dom in domains:
        dcells = {k: v for k, v in cells.items() if k.startswith(dom + "|")}
        # A：该域最后一次 eager 构建（每 capability 一次），stats 已是"按域全部 query 摊销"后的值
        a_share = list(dcells.values())[0]["A"]["stats"]
        n_q_dom = sum(v["n_queries"] for v in dcells.values())
        a_total_pt = a_share["pt"] * n_q_dom
        a_total_ct = a_share["ct"] * n_q_dom
        a_total_cost = cost(dict(pt_by_backend={k: v * n_q_dom for k, v in
                                                a_share["pt_by_backend"].items()},
                                 ct_by_backend={k: v * n_q_dom for k, v in
                                                a_share["ct_by_backend"].items()}))
        b_pt = sum(v["B"]["stats"]["pt"] for v in dcells.values())
        b_ct = sum(v["B"]["stats"]["ct"] for v in dcells.values())
        b_cost = sum(cost(v["B"]["stats"]) for v in dcells.values())
        c_pt = sum(v["C"]["stats"]["pt"] for v in dcells.values())
        c_ct = sum(v["C"]["stats"]["ct"] for v in dcells.values())
        c_cost = sum(cost(v["C"]["stats"]) for v in dcells.values())
        b_rows = sum(v["B"]["stats"]["rows"] for v in dcells.values())
        c_rows = sum(v["C"]["stats"]["rows"] for v in dcells.values())
        a_rows = a_share["rows"] * n_q_dom
        out[dom] = dict(
            n_queries=n_q_dom,
            A=dict(build_rows=round(a_rows, 1), tokens=round(a_total_pt + a_total_ct),
                   cost_yuan=round(a_total_cost, 6),
                   cost_per_query=round(a_total_cost / n_q_dom, 8)),
            B=dict(build_rows=b_rows, tokens=b_pt + b_ct, cost_yuan=round(b_cost, 6),
                   cost_per_query=round(b_cost / n_q_dom, 8)),
            C=dict(build_rows=c_rows, tokens=c_pt + c_ct, cost_yuan=round(c_cost, 6),
                   cost_per_query=round(c_cost / n_q_dom, 8)),
        )
        out[dom]["C_over_B_total"] = round(c_cost / b_cost, 4)
        out[dom]["C_over_A_total"] = round(c_cost / a_total_cost, 4)
        out[dom]["C_over_B_rows"] = round(c_rows / b_rows, 4)
        out[dom]["C_over_A_rows"] = round(c_rows / a_rows, 4)
    # 全量（两域合计）
    tot = {k: dict(tokens=sum(out[d][k]["tokens"] for d in domains),
                   cost_yuan=round(sum(out[d][k]["cost_yuan"] for d in domains), 6),
                   build_rows=sum(out[d][k]["build_rows"] for d in domains))
           for k in ["A", "B", "C"]}
    n_q = sum(out[d]["n_queries"] for d in domains)
    for k in tot:
        tot[k]["cost_per_query"] = round(tot[k]["cost_yuan"] / n_q, 8)
    summary = dict(n_queries_total=n_q, per_domain=out, total=tot,
                   C_over_B_total=round(tot["C"]["cost_yuan"] / tot["B"]["cost_yuan"], 4),
                   C_over_A_total=round(tot["C"]["cost_yuan"] / tot["A"]["cost_yuan"], 4),
                   C_over_B_tokens=round(tot["C"]["tokens"] / tot["B"]["tokens"], 4),
                   C_over_A_tokens=round(tot["C"]["tokens"] / tot["A"]["tokens"], 4),
                   note=("统一口径：执行整个矩阵（24 cells / 全部 query）时的总成本。"
                         "A=每域一次性 eager 构建 + 全量复用；B=逐 query 重建；C=每 cell 首次构建+增量复用。"))
    with open(os.path.join(EXP_OUT, "exp2_workload_totals.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


def main_all():
    s2 = main()
    e1 = exp1_totals()
    if e1:
        print("\n== 实验 1（mock, N=10,000）工作负载级口径 ==")
        print(json.dumps(e1, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main_all()
