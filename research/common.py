# -*- coding: utf-8 -*-
"""最终三实验共享内核（Zero-token 语义成本仿真）。

设计原则（严格遵守用户指令 §19 / §20 / §24）：
  * 复用 v1.2 的固定项：source snapshot、capability implementation、prompt、schema、
    tokenizer、pricing、batch_size=1。**不修改 exp/ 下任何既有代码**，只在其上做只读复用。
  * 语义成本来自 deterministic-mock-semantic 的**真实 token 计数**（prompt/completion），
    不使用任何人为设定的假设常数；因此成本模型本身也是可审计的。
  * 策略只是"在什么位置、对哪些行、是否持久化地调用 CapabilityBuild"的调度决策，
    不改变任何 prompt / schema / parser（因果隔离）。
  * 全部策略共享同一 `unit[(cap_key, row_id)] -> (tokens_in, tokens_out, cost, ms)` 表，
    保证同一行的能力构建成本在任何策略下完全相同。
"""
import hashlib
import json
import math
import os
import statistics as st
import sys
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXP = os.path.join(ROOT, "exp")
if EXP not in sys.path:
    sys.path.insert(0, EXP)

from config import PRICING, LATENCY                                  # noqa: E402
from capability import CAPABILITIES, PROMPT_TEMPLATE, macro_f1, field_f1  # noqa: E402
from llm import get_model, count_tokens, model_hash                   # noqa: E402
from source_plane import materialize                                  # noqa: E402

# ================================================================ 能力菜单
CAP_MENU = ["issue_classification", "amount_extraction_ecom",
            "clause_classification", "amount_extraction_fin"]
NATIVE_CAPS = {
    "ecom": ["issue_classification", "amount_extraction_ecom"],
    "finproc": ["clause_classification", "amount_extraction_fin"],
}


def caps_for_breadth(domain, c):
    """breadth c ∈ {1,2,4}：1/2 用本域原生的分类/抽取能力；4 追加另域两个能力（辅助能力）。"""
    native = NATIVE_CAPS[domain]
    if c <= 2:
        return native[:c]
    return [CAP_MENU[0], CAP_MENU[1], CAP_MENU[2], CAP_MENU[3]]


def is_native(domain, cap_key):
    return cap_key in NATIVE_CAPS[domain]


# ================================================================ 确定性谓词族
@lru_cache(maxsize=4_000_000)
def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def pred_eval(pred, row):
    """与 exp/operators.py 同一谓词族 + 一个新增的确定性分桶算子 hash_mod_eq。

    新增算子只用于构造 PRED_MUTUALLY_EXCLUSIVE（互斥分区），
    仍满足"上游算子不得依赖任何 semantic capability"（§1）。
    """
    op = pred["op"]
    if op == "and":
        return all(pred_eval(p, row) for p in pred["preds"])
    if op == "or":
        return any(pred_eval(p, row) for p in pred["preds"])
    rid = row["row_id"]
    if op == "hash_lt":
        return _h(rid) % 1000 < pred["value"]
    if op == "hash_lt_salted":
        return _h(f"{rid}|{pred.get('salt', 0)}") % 1000 < pred["value"]
    if op == "hash_mod_eq":
        return _h(f"{rid}|{pred.get('salt', 0)}") % pred["modulus"] == pred["value"]
    if op == "payload_len_gt":
        # 确定性、非语义的源属性谓词：用于构造"survivor 系统性更长"的长度偏斜工作负载
        return len(row["payload"]) > pred["value"]
    actual = row["columns"].get(pred["col"])
    v = pred.get("value")
    if op == "eq":
        return actual == v
    if op == "in":
        return actual in v
    if op == "gt":
        return actual is not None and actual > v
    if op == "lt":
        return actual is not None and actual < v
    raise ValueError(f"unknown pred op {op}")


def op_filter(rows, pred):
    return [r for r in rows if pred_eval(pred, r)]


# ================================================================ 单位成本表
class UnitCost:
    """unit[(cap_key, row_id)] = (tokens_in, tokens_out, cost_yuan, service_ms)。

    由 deterministic-mock-semantic 逐行真实计数（一次构建、全局复用），
    因此 A/B/C/D 任何策略对同一行的成本完全相同。
    """

    def __init__(self):
        self.model = get_model()
        self.table = {}
        self.calls = 0
        self.C = {}
        self.TI = {}
        self.TO = {}
        self.MS = {}
        self.n_rows = 0

    def build(self, rows_by_domain):
        pos = 0
        for domain, rows in rows_by_domain.items():
            for r in rows:
                r["_i"] = pos
                pos += 1
        self.n_rows = pos
        for cap in CAP_MENU:
            self.C[cap] = [0.0] * pos
            self.TI[cap] = [0] * pos
            self.TO[cap] = [0] * pos
            self.MS[cap] = [0.0] * pos
        for domain, rows in rows_by_domain.items():
            for cap in CAP_MENU:
                task = CAPABILITIES[cap]["task"]
                tmpl = PROMPT_TEMPLATE[task]
                Cc, TIc, TOc, MSc = self.C[cap], self.TI[cap], self.TO[cap], self.MS[cap]
                for r in rows:
                    key = (cap, r["row_id"])
                    if key in self.table:
                        continue
                    prompt = tmpl.format(payload=r["payload"])
                    comp, tin, tout = self.model.complete(prompt, task=task)
                    cost = (tin / 1000 * PRICING["input_per_1k"]
                            + tout / 1000 * PRICING["output_per_1k"]
                            + PRICING["per_call_overhead"])
                    ms = (tin * LATENCY["ms_per_input_token"]
                          + tout * LATENCY["ms_per_output_token"]
                          + LATENCY["ms_per_call_overhead"])
                    self.table[key] = (tin, tout, cost, ms)
                    Cc[r["_i"]] = cost
                    TIc[r["_i"]] = tin
                    TOc[r["_i"]] = tout
                    MSc[r["_i"]] = ms
                    self.calls += 1
        return self

    def agg(self, cap, rows):
        """对 row 列表做 O(1) 的 C 级聚合：返回 (n, cost, tokens_in, tokens_out, ms)。"""
        idx = list(map(_pos, rows))
        Cc, TIc, TOc, MSc = self.C[cap], self.TI[cap], self.TO[cap], self.MS[cap]
        if not idx:
            return 0, 0.0, 0, 0, 0.0
        return (len(idx), math.fsum(map(Cc.__getitem__, idx)),
                sum(map(TIc.__getitem__, idx)), sum(map(TOc.__getitem__, idx)),
                math.fsum(map(MSc.__getitem__, idx)))

    def agg_idx(self, cap, idx):
        Cc, TIc, TOc, MSc = self.C[cap], self.TI[cap], self.TO[cap], self.MS[cap]
        if not idx:
            return 0, 0.0, 0, 0, 0.0
        return (len(idx), math.fsum(map(Cc.__getitem__, idx)),
                sum(map(TIc.__getitem__, idx)), sum(map(TOc.__getitem__, idx)),
                math.fsum(map(MSc.__getitem__, idx)))

    def get(self, cap, row_id):
        return self.table[(cap, row_id)]

    def cost(self, cap, row_id):
        return self.table[(cap, row_id)][2]

    def ms(self, cap, row_id):
        return self.table[(cap, row_id)][3]

    def payload_len(self, row_id):
        return None  # 见 payload_lengths()


def _pos(r):
    return r["_i"]


def payload_lengths(rows_by_domain):
    out = {}
    for rows in rows_by_domain.values():
        for r in rows:
            out[r["row_id"]] = len(r["payload"])
    return out


# ================================================================ 谓词模式
PATTERNS = ["PRED_SHARED", "PRED_DISTINCT", "PRED_NESTED", "PRED_OVERLAP", "PRED_MUTEX"]


def make_predicate(pattern, i, R, kthr, salt):
    if pattern == "PRED_SHARED":
        return {"col": "row_id", "op": "hash_lt", "value": kthr}
    if pattern == "PRED_DISTINCT":
        return {"col": "row_id", "op": "hash_lt_salted", "value": kthr, "salt": salt + i}
    if pattern == "PRED_NESTED":
        # 递增阈值 → 强嵌套（S_1 ⊂ S_2 ⊂ ...）；均值选择率 ≈ kthr
        v = min(1000, max(1, round(2 * kthr * (i + 1) / (R + 1))))
        return {"col": "row_id", "op": "hash_lt", "value": v}
    if pattern == "PRED_OVERLAP":
        core = max(1, kthr // 2)
        priv = max(1, kthr // 2)
        return {"op": "or", "preds": [
            {"col": "row_id", "op": "hash_lt", "value": core},
            {"col": "row_id", "op": "hash_lt_salted", "value": priv, "salt": salt + i},
        ]}
    raise ValueError(pattern)


def make_workload(rows, s_pct, reuse, pattern, caps, domain, salt):
    """返回 queries: [{qid, pred, survivors, caps}]，survivors 为确定性预计算的 row 列表。"""
    N = len(rows)
    kthr = max(1, int(round(s_pct / 100.0 * 1000)))
    queries = []
    if pattern == "PRED_MUTEX":
        # 互斥分区：确定性全序上切 R 个互不重叠的块，块大小 = min(s·N, N/R)
        order = sorted(rows, key=lambda r: _h(f"{r['row_id']}|{salt}"))
        chunk = max(1, min(int(round(s_pct / 100.0 * N)), max(1, N // reuse)))
        for i in range(reuse):
            seg = order[i * chunk:(i + 1) * chunk]
            queries.append(dict(qid=i, pred={"col": "row_id", "op": "mutex_partition",
                                             "part": i, "chunk": chunk, "of": reuse, "salt": salt},
                                survivors=seg, caps=caps))
    else:
        for i in range(reuse):
            pred = make_predicate(pattern, i, reuse, kthr, salt)
            queries.append(dict(qid=i, pred=pred, survivors=op_filter(rows, pred), caps=caps))
    return queries


# ================================================================ 物化存储（含作用域/容量）
class Store:
    """可持久化能力工件存储。

    capacity=None → 无限容量（原生 set，O(1)，无 LRU 开销）
    capacity=k    → 有限容量 LRU 淘汰（模拟有限缓存）
    """

    def __init__(self, capacity=None):
        from collections import OrderedDict
        self.capacity = capacity
        if capacity is None:
            self.data = set()
            self.lru = None
        else:
            self.lru = OrderedDict()
            self.data = self.lru
        self.evictions = 0

    def has(self, cap, rid):
        return (cap, rid) in self.data

    def put(self, cap, rid):
        k = (cap, rid)
        if self.capacity is None:
            self.data.add(k)
            return
        self.lru[k] = True
        self.lru.move_to_end(k)
        if len(self.lru) > self.capacity:
            self.lru.popitem(last=False)
            self.evictions += 1

    def touch(self, cap, rid):
        if self.capacity is None:
            return
        k = (cap, rid)
        if k in self.lru:          # 容量受限时该行可能已被 LRU 淘汰
            self.lru.move_to_end(k)

    def size(self):
        return len(self.data)


# ================================================================ 策略实现
def _build(unit, cap, rid):
    tin, tout, cost, ms = unit.get(cap, rid)
    return dict(tin=tin, tout=tout, cost=cost, ms=ms)


def simulate(strategy, queries, all_rows, unit, scope_capacity=None, reset_per_query=False,
             adaptive_opts=None):
    """执行一个策略，返回 dict(metrics, per_query, store_events, decisions)。

    策略语义（与用户规范 §四 一致）：
      A  EAGER     : t=0 对工作负载全部能力 × 全表构建并持久化
      B  PER_QUERY : 每 query 过滤后对 survivor 构建，不持久化
      C  LATE_PERSIST: 过滤后只对存储中缺失的 (cap,row) 构建并持久化
      D  ADAPTIVE  : 在线决策（只用已观测信息，见 _decide）
      CBO          : 教科书写法的 myopic 成本模型（点估计，无滞后、无覆盖度感知）
    """
    store_capacity = scope_capacity
    store = Store(capacity=store_capacity)
    all_ids = [r["row_id"] for r in all_rows]
    caps_all = sorted({c for q in queries for c in q["caps"]})

    m = dict(build_rows=0, unique_builds=0, tokens_in=0, tokens_out=0, calls=0,
             build_cost=0.0, build_ms=0.0, retrieval_cost=0.0, validation_cost=0.0,
             synthesis_cost=0.0, filter_rows=0, filter_ms=0.0, cache_hits_bytes=0,
             evictions=0, mat_rows_max=0)
    per_query = []
    decisions = []
    hist_sets = []

    def do_build(cap, rid, persist, qrec, is_rebuild=False):
        u = _build(unit, cap, rid)
        m["build_rows"] += 1
        m["unique_builds"] += 1
        m["tokens_in"] += u["tin"]
        m["tokens_out"] += u["tout"]
        m["calls"] += 1
        m["build_cost"] += u["cost"]
        m["build_ms"] += u["ms"]
        m["retrieval_cost"] += PRICING["retrieval_per_row"]
        m["validation_cost"] += PRICING["validation_per_row"] if persist else 0.0
        if persist:
            store.put(cap, rid)
        return u["ms"]

    # ---- A: EAGER（t=0 全表 × 全部能力）----
    if strategy == "A":
        for cap in caps_all:
            n, c, ti, to, ms = unit.agg(cap, all_rows)
            m["build_rows"] += n
            m["unique_builds"] += n
            m["tokens_in"] += ti
            m["tokens_out"] += to
            m["calls"] += n
            m["build_cost"] += c
            m["build_ms"] += ms
            m["retrieval_cost"] += PRICING["retrieval_per_row"] * n
            m["validation_cost"] += PRICING["validation_per_row"] * n
            for r in all_rows:
                store.put(cap, r["row_id"])
        plans = ["EAGER_ALL", "REUSE"]
    else:
        plans = []

    for q in queries:
        if reset_per_query:
            store = Store(capacity=store_capacity)
        qcost = 0.0
        qms = 0.0
        n_surv = len(q["survivors"])
        m["filter_rows"] += len(all_rows)
        m["filter_ms"] += len(all_rows) * LATENCY["ms_per_row_scan"]
        qms += len(all_rows) * LATENCY["ms_per_row_scan"]
        built_this_q = 0
        hit = 0

        if strategy == "A":
            for cap in q["caps"]:
                for r in q["survivors"]:
                    store.touch(cap, r["row_id"])
                    hit += 1
                    m["cache_hits_bytes"] += 1
        elif strategy == "B":
            for cap in q["caps"]:
                n, c, ti, to, ms = unit.agg(cap, q["survivors"])
                m["build_rows"] += n
                m["unique_builds"] += n
                m["tokens_in"] += ti
                m["tokens_out"] += to
                m["calls"] += n
                m["build_cost"] += c
                m["build_ms"] += ms
                m["retrieval_cost"] += PRICING["retrieval_per_row"] * n
                qms += ms
                built_this_q += n
        elif strategy in ("C", "D", "CBO"):
            if strategy == "C":
                plan = "LATE_PERSIST"
                decisions.append(dict(qid=q["qid"], plan=plan, survivors=n_surv,
                                      store_before=store.size()))
            elif strategy == "CBO":
                plan = _cbo_plan(q, store, all_rows, unit, hist_sets, adaptive_opts or {})
                decisions.append(dict(qid=q["qid"], plan=plan, survivors=n_surv,
                                      store_before=store.size()))
            else:
                plan = _decide(q, store, all_rows, unit, hist_sets, decisions,
                               adaptive_opts or {})
            if plan == "EAGER":
                # 一次性 eager：把该能力集合的全表补齐（此后全部查询命中）
                for cap in q["caps"]:
                    for r in all_rows:
                        if not store.has(cap, r["row_id"]):
                            qms += do_build(cap, r["row_id"], True, None)
                            built_this_q += 1
                for cap in q["caps"]:
                    for r in q["survivors"]:
                        store.touch(cap, r["row_id"])
                        hit += 1
                        m["cache_hits_bytes"] += 1
            else:
                persist = (plan == "LATE_PERSIST")
                full_cover = (store.capacity is None
                              and store.size() >= len(all_rows) * len(caps_all))
                if full_cover:
                    # 全表已物化 → 全部命中（等价加速路径，与逐行结果一致）
                    n_hit = len(q["survivors"]) * len(q["caps"])
                    hit += n_hit
                    m["cache_hits_bytes"] += n_hit
                else:
                    for cap in q["caps"]:
                        for r in q["survivors"]:
                            rid = r["row_id"]
                            if store.has(cap, rid):
                                store.touch(cap, rid)
                                hit += 1
                                m["cache_hits_bytes"] += 1
                            else:
                                qms += do_build(cap, rid, persist, None)
                                built_this_q += 1
        else:
            raise ValueError(strategy)

        synth_ms, synth_cost = _synthesis(q, n_surv)
        m["synthesis_cost"] += synth_cost
        qms += synth_ms
        per_query.append(dict(qid=q["qid"], survivors=n_surv, built=built_this_q,
                              hits=hit, ms=qms, cost=qcost,
                              materialized=store.size()))
        hist_sets.append({r["row_id"] for r in q["survivors"]})
        m["mat_rows_max"] = max(m["mat_rows_max"], store.size())

    m["evictions"] = store.evictions
    m["materialized_rows_final"] = store.size()
    metrics = finalize_metrics(m, queries, all_rows, caps_all, per_query)
    return dict(metrics=metrics, per_query=per_query, decisions=decisions,
                plans=plans, store_final=store.size())


def _synthesis(q, n_surv):
    """最终 Synthesis：每个 query 1 次 LLM 调用（不可约语义部分）。跨策略完全相同。"""
    prompt = f"result_rows={n_surv}"
    tin = count_tokens(prompt) + 8
    tout = 6
    cost = (tin / 1000 * PRICING["synthesis_input_per_1k"]
            + tout / 1000 * PRICING["synthesis_output_per_1k"]
            + PRICING["per_call_overhead"])
    ms = tin * LATENCY["ms_per_input_token"] + tout * LATENCY["ms_per_output_token"]
    return ms, cost


def finalize_metrics(m, queries, all_rows, caps_all, per_query):
    R = len(queries)
    N = len(all_rows)
    total = m["build_cost"] + m["retrieval_cost"] + m["validation_cost"] + m["synthesis_cost"]
    lats = sorted(p["ms"] for p in per_query)
    uniq = m["unique_builds"]
    mat = m["materialized_rows_final"]
    possible = N * len(caps_all)
    return dict(
        total_cost=round(total, 8),
        cost_per_query=round(total / max(1, R), 8),
        build_cost=round(m["build_cost"], 8),
        retrieval_cost=round(m["retrieval_cost"], 8),
        validation_cost=round(m["validation_cost"], 8),
        synthesis_cost=round(m["synthesis_cost"], 8),
        semantic_tokens=m["tokens_in"] + m["tokens_out"],
        semantic_calls=m["calls"],
        semantic_rows_built=m["build_rows"],
        unique_rows_built=uniq,
        build_rows_per_query=round(m["build_rows"] / max(1, R), 3),
        materialized_rows=mat,
        materialization_coverage=round(mat / max(1, possible), 6),
        capacity_possible=possible,
        cache_hit_rate=round(m["cache_hits_bytes"] / max(1, m["cache_hits_bytes"] + uniq), 6),
        rebuild_rate=round(m["build_rows"] / max(1, uniq), 6),
        evictions=m["evictions"],
        filter_rows=m["filter_rows"],
        filter_rows_per_query=round(m["filter_rows"] / max(1, R), 1),
        validation_share=round(m["validation_cost"] / total, 6) if total else 0.0,
        p50_ms=round(st.median(lats), 3) if lats else 0.0,
        p95_ms=round(lats[min(len(lats) - 1, int(math.ceil(0.95 * len(lats))) - 1)], 3) if lats else 0.0,
        p99_ms=round(lats[min(len(lats) - 1, int(math.ceil(0.99 * len(lats))) - 1)], 3) if lats else 0.0,
        build_ms_total=round(m["build_ms"], 3),
        n_queries=R, n_rows=N, n_caps=len(caps_all),
    )


# ================================================================ Oracle
def oracle(queries, all_rows, unit, caps_all):
    """离线 clairvoyant oracle（真正的下界，逐能力可分解）。

    每个能力独立比较三个规范计划，且**各自承担自己的 validation / retrieval**：
      EAGER        : 全表构建 + 全表验证
      CLAIRVOYANT  : survivor 并集构建一次 + 并集验证（信息完全前瞻）
      PER_QUERY    : 每 query 重建、不持久化 → 无需 validation
    由于能力之间无共享成本，逐能力取 min 即为全局下界。
    """
    val_p, ret_p = PRICING["validation_per_row"], PRICING["retrieval_per_row"]
    per_cap = {}
    total = 0.0
    uniq_total = 0
    for cap in caps_all:
        union = set()
        per_query_sum = 0.0
        n_built = 0
        for q in queries:
            if cap in q["caps"]:
                idx = list(map(_pos, q["survivors"]))
                union.update(idx)
                n, c, _ti, _to, _ms = unit.agg_idx(cap, idx)
                per_query_sum += c
                n_built += n
        eager_build = unit.agg(cap, all_rows)[1]
        union_build = unit.agg_idx(cap, list(union))[1]
        n_all = len(all_rows)
        plans = dict(
            EAGER=eager_build + val_p * n_all + ret_p * n_all,
            CLAIRVOYANT_LATE=union_build + val_p * len(union) + ret_p * len(union),
        )
        # PER_QUERY：按实际构建次数计 retrieval，且无需 validation（n_built 已在上方统计）
        plans["PER_QUERY"] = per_query_sum + ret_p * n_built
        best_key = min(plans, key=lambda k: plans[k])
        per_cap[cap] = dict(n_union=len(union), n_per_query_builds=n_built,
                            union_build=round(union_build, 8),
                            eager_build=round(eager_build, 8),
                            per_query_build=round(per_query_sum, 8),
                            plan_costs={k: round(v, 8) for k, v in plans.items()},
                            best_plan=best_key, best=round(plans[best_key], 8))
        total += plans[best_key]
        uniq_total += len(union)
    syn = sum(_synthesis(q, len(q["survivors"]))[1] for q in queries)
    total += syn
    return dict(total_cost=round(total, 8), cost_per_query=round(total / max(1, len(queries)), 8),
                unique_rows_built=uniq_total, materialized_rows=uniq_total,
                per_capability=per_cap, synthesis_cost=round(syn, 8),
                best_plans={c: per_cap[c]["best_plan"] for c in per_cap})


def regret(cost, oracle_cost):
    if oracle_cost <= 0:
        return 0.0
    return (cost - oracle_cost) / oracle_cost


# ================================================================ 在线策略
def estimate(q, store, all_rows, unit, hist_sets, privileged_horizon=None, opts=None):
    """在线估计器：**只使用已观测信息**（§四：禁止 oracle / future query / future answer）。

    可观测特征：
      obs_s        已观测选择率（历史 survivor / N）
      obs_overlap  历史查询与当前查询 survivor 集合的平均 Jaccard（复用密度的无偏代理）
      per_row_cost 已观测的 per-row 单位成本（在线均值，payload 相关）
      covered      存储已覆盖的 (cap,row) 比例（materialized coverage）
      r_hat        工作负载长度推断：默认只用"已观测规模"（不做任何未来外推）；
                   privileged_horizon 仅在诊断组 D+ 中用于把"未知视界"与"估计误差"分离
    """
    N = len(all_rows)
    n_hist = len(hist_sets)
    cur = {r["row_id"] for r in q["survivors"]}
    obs_s = (st.mean([len(h) for h in hist_sets]) / N) if n_hist else len(cur) / N
    overlaps = []
    for prev in hist_sets[-8:]:
        u = len(cur | prev)
        if u:
            overlaps.append(len(cur & prev) / u)
    obs_overlap = st.mean(overlaps) if overlaps else (1.0 if n_hist else 0.0)
    covered = store.size() / max(1, N * len(q["caps"]))
    p_reuse = min(0.999, max(0.0, obs_overlap))
    exp_uses, pp = 0.0, p_reuse
    for _ in range(12):
        exp_uses += pp
        pp *= p_reuse
    probe = [r["row_id"] for c in q["caps"] for r in q["survivors"][:32]]
    if (opts or {}).get("cost_model", "survivor_conditioned") == "global_mean":
        # 朴素成本模型：用整表平均单位成本（不条件化到 survivor）→ 无法看到
        # "survivor 系统性更长/更贵"这一真实性质
        all_ids = [r["row_id"] for r in all_rows[:128]]
        per_row_cost = st.mean([unit.cost(c, i) for c in q["caps"] for i in all_ids])
    else:
        per_row_cost = st.mean([unit.cost(c, i) for c in q["caps"] for i in probe]) if probe else 0.0
    gain = exp_uses * per_row_cost - PRICING["validation_per_row"]
    r_hat = float(privileged_horizon) if privileged_horizon else max(1.0, float(n_hist))
    cover_est = 1 - (1 - min(0.999, max(0.0, obs_s))) ** max(1.0, r_hat)
    return dict(obs_s=obs_s, obs_overlap=obs_overlap, per_row_cost=per_row_cost,
                covered=covered, r_hat=r_hat, cover_est=cover_est,
                exp_uses=exp_uses, persist_gain=gain)


def _cbo_plan(q, store, all_rows, unit, hist_sets, opts):
    """Simple CBO（教科书式）：用已观测统计做点估计，逐 query 最小化**即时+期望**成本。

    规划空间只含 {PER_QUERY, LATE_PERSIST}（不做离线物化决策、无覆盖度逻辑、无滞后）。
    """
    e = estimate(q, store, all_rows, unit, hist_sets, opts.get("privileged_horizon"), opts)
    return "LATE_PERSIST" if e["persist_gain"] > 0 else "PER_QUERY"


def _decide(q, store, all_rows, unit, hist_sets, decisions, opts):
    """D — Adaptive：Simple CBO 的估计器 + 两个额外决策维度。

    (1) 覆盖度感知的离线物化分支：若在线推断的**并集覆盖**接近全表，
        则一次性 EAGER 补齐（Simple CBO 的规划空间里没有这个分支）；
    (2) 滞后（hysteresis）：切换物化模式需要连续 2 次一致证据，抑制抖动。
    """
    e = estimate(q, store, all_rows, unit, hist_sets, opts.get("privileged_horizon"), opts)
    rec = dict(qid=q["qid"], survivors=len(q["survivors"]), store_before=store.size(),
               cover_est=round(e["cover_est"], 4), obs_s=round(e["obs_s"], 5),
               obs_overlap=round(e["obs_overlap"], 4), high_cover=False)
    if opts.get("allow_eager", True) and e["cover_est"] >= 0.75 and e["covered"] < 0.5:
        rec["high_cover"] = True
        if decisions and decisions[-1].get("high_cover"):
            rec["plan"] = "EAGER"
            decisions.append(rec)
            return "EAGER"
        rec["plan"], rec["note"] = "LATE_PERSIST", "hysteresis_arm"
        decisions.append(rec)
        return "LATE_PERSIST"
    rec["plan"] = "LATE_PERSIST" if e["persist_gain"] > 0 else "PER_QUERY"
    decisions.append(rec)
    return rec["plan"]


# ================================================================ 质量（native caps）
def quality_of(queries, rows_by_domain, unit, domain):
    """质量在策略间恒定（同一 survivor → 同一 artifact → 同一答案），此处计算其绝对值。

    返回 native capability 的 macro-F1 / field-F1 与答案级正确率代理。
    """
    from capability import CapabilityBuild
    b = CapabilityBuild()
    rows = rows_by_domain[domain]
    idx = {r["row_id"]: r for r in rows}
    out = {}
    for cap in NATIVE_CAPS[domain]:
        ids = sorted({r["row_id"] for q in queries for r in q["survivors"] if r["row_id"] in idx})
        sub = [idx[i] for i in ids]
        if not sub:
            continue
        outputs, _ = b.build(cap, sub)
        gf, gv = CAPABILITIES[cap]["oracle_path"]
        yt = [r["oracle"][gf][gv] for r in sub]
        if CAPABILITIES[cap]["kind"] == "classification":
            yp = [outputs[r["row_id"]].get("label") for r in sub]
            out[cap] = round(macro_f1(yt, yp), 4)
        else:
            yp = [outputs[r["row_id"]].get("value") for r in sub]
            out[cap] = round(field_f1(yt, yp), 4)
    return out


# ================================================================ IO / hash
def sha_text(t):
    return hashlib.sha256(t.encode()).hexdigest()[:32]


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def write_csv(path, rows, fields=None):
    import csv
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not rows:
        open(path, "w", encoding="utf-8").close()
        return path
    fields = fields or list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                        for k, v in r.items() if k in fields})
    return path


CONFIG_HASH_FIELDS = ["model_hash", "prompt_hash", "schema_hash", "capability_impl_revision",
                      "pricing_version", "batch_size", "temperature", "tokenizer"]


def fixed_items_manifest():
    from capability import CAPABILITY_IMPL_REVISION, prompt_hash, schema_hash
    from config import MODEL_REVISION, TEMPERATURE, TOKENIZER, BATCH_SIZE
    return dict(
        model_id="deterministic-mock-semantic", model_revision=MODEL_REVISION,
        model_hash=model_hash(), temperature=TEMPERATURE, tokenizer=TOKENIZER,
        batch_size=BATCH_SIZE,
        capability_impl_revision=CAPABILITY_IMPL_REVISION,
        prompt_hashes={t: prompt_hash(t) for t in ["issue_classification",
                                                   "clause_classification", "amount_extraction"]},
        schema_hashes={t: schema_hash(t) for t in ["issue_classification",
                                                   "clause_classification", "amount_extraction"]},
        pricing_version=PRICING["pricing_version"],
        pricing={k: v for k, v in PRICING.items()},
    )
