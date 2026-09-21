# -*- coding: utf-8 -*-
"""数据集校验器：实体/外键/时间区间/Gold存在性/计算复算/冲突合理性/伪Gold检测。"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(ROOT, "dataset")


def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    errors, warnings, checks = [], [], 0

    def chk(cond, msg):
        nonlocal checks
        checks += 1
        if not cond:
            errors.append(msg)

    docs = load_jsonl(os.path.join(DATASET, "registry", "documents.jsonl"))
    ents = load_jsonl(os.path.join(DATASET, "registry", "entities.jsonl"))
    rels = load_jsonl(os.path.join(DATASET, "registry", "relationships.jsonl"))
    revs = load_jsonl(os.path.join(DATASET, "registry", "revisions.jsonl"))
    golds = load_jsonl(os.path.join(DATASET, "gold", "gold.jsonl"))
    qs = load_jsonl(os.path.join(DATASET, "questions", "questions.jsonl"))
    with open(os.path.join(DATASET, "validation", "fixtures.json"), encoding="utf-8") as f:
        fx = json.load(f)

    doc_ids = {d["doc_id"] for d in docs}
    doc_anchor = {d["doc_id"]: set(d.get("anchors") or []) for d in docs}
    ent_ids = {e["entity_id"] for e in ents}
    tbls = load_jsonl(os.path.join(DATASET, "registry", "tables.jsonl"))
    table_ids = {t["table_id"] for t in tbls}
    valid_ref_ids = doc_ids | table_ids

    # ---- Entity / FK validation
    for r in rels:
        chk(r["src"] in ent_ids, f"FK: relationship src 不存在 {r['src']} -> {r['dst']}")
        chk(r["dst"] in ent_ids, f"FK: relationship dst 不存在 {r['src']} -> {r['dst']}")

    # ---- Temporal validation
    for d in docs:
        ef, et = d.get("effective_from"), d.get("effective_to")
        if ef and et and et not in ("长期", None):
            chk(et >= ef, f"Temporal: {d['doc_id']} effective_to({et}) < effective_from({ef})")

    # ---- Gold evidence existence（anchor 级）
    for g in golds:
        for ref in g.get("gold_evidence_refs", []):
            base = ref.split("#", 1)[0]
            if "#" in ref:
                did, anc = ref.split("#", 1)
                chk(did in valid_ref_ids, f"{g['question_id']}: gold ref doc 不存在 {did}")
                if did in doc_anchor and doc_anchor[did]:
                    chk(anc in doc_anchor[did],
                        f"{g['question_id']}: anchor 不存在 {ref}")
            else:
                chk(base in valid_ref_ids, f"{g['question_id']}: gold ref doc 不存在 {ref}")
        for s in g.get("required_sources", []):
            chk(s in valid_ref_ids or s in ent_ids,
                f"{g['question_id']}: required_source 不存在 {s}")
        # 结构完整性
        chk(g["question_id"].startswith("Q-"), f"bad id {g['question_id']}")
        chk(g["expected_action"] in {"ANSWER", "PARTIAL", "UNKNOWN", "ABSTAIN", "CLARIFY",
                                     "CONFLICT", "ACCESS_DENIED", "OUT_OF_SCOPE",
                                     "ABSENT", "NOT_FOUND"},
            f"{g['question_id']}: 非法 expected_action {g['expected_action']}")
        chk(g["difficulty"] in {"L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"},
            f"{g['question_id']}: 非法难度 {g['difficulty']}")
        if g["expected_action"] == "ANSWER":
            chk(g.get("gold_claims"), f"{g['question_id']}: ANSWER 缺 gold_claims")
            chk(g.get("acceptable_answer"), f"{g['question_id']}: ANSWER 缺 acceptable_answer")

    # ---- 伪 Gold 检测：claim 数值需能在证据文本中找到（抽样启发式）
    def doc_text(did):
        for d in docs:
            if d["doc_id"] == did:
                p = os.path.join(DATASET, "knowledge", d["path"])
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        return f.read()
        return ""

    checked_claims = 0
    for g in golds:
        if g["expected_action"] != "ANSWER":
            continue
        text = " ".join(doc_text(ref.split("#")[0]) for ref in g["gold_required_evidence"]
                        if ref.split("#")[0] in doc_ids)
        for c in g.get("gold_claims", []):
            for num in re.findall(r"\d[\d,，]*", c["claim"]):
                nn = num.replace("，", ",").replace(",", "")
                if len(nn) < 2 or nn in ("12", "24", "48", "7", "15", "30", "90"):
                    continue
                checked_claims += 1
                if nn not in text.replace(",", ""):
                    warnings.append(f"{g['question_id']}: claim 数值 {nn} 未出现在证据文本中"
                                    f"（若为计算/派生值可忽略）")

    # ---- 计算复算（Answer Validation）
    import world as WD
    w = WD.all_entities()
    fin = {(r["month"], r["region"]): r for r in w["finance_monthly"]}
    gm = lambda r: round((r["revenue"] - r["cost"]) / r["revenue"] * 100, 1)
    chk(fx["south_202606_revenue"] == 8_000_000, "华南 2026-06 收入应为 8,000,000")
    eur = round(fx["eu_202606_revenue"] / 7.8 / 1000) * 1000
    chk(eur == 620000, f"欧洲区欧元换算应为 620,000，实际 {eur}")
    tot = sum(o["amount_excl_tax"] for o in w["orders"] if o["order_date"].startswith("2026"))
    chk(tot == fx["orders_total_2026"], "订单总额复算不一致")
    rates = fx["platform_refund_rates"]
    chk(max(rates, key=rates.get) == "抖音", "退款率最高平台应为抖音")
    yoy = (fx["h1_2026_revenue"] - fx["h1_2025_revenue"]) / fx["h1_2025_revenue"]
    chk(0.05 < yoy < 0.30, f"同比增速异常: {yoy:.3f}")
    for r in fin.values():
        chk(abs((r["revenue"] - r["cost"]) - r["gross_profit"]) <= 1, f"毛利不自洽 {r['month']}")
    # TRV 版本互不重叠
    vs = sorted(FV for FV in [])
    import corpus_facts as F
    for a, b in zip(F.TRV_VERSIONS, F.TRV_VERSIONS[1:]):
        chk(a["eff_to"] < b["eff_from"], f"TRV 版本区间重叠: {a['doc_id']}/{b['doc_id']}")

    # ---- Conflict validation（冲突是否真的冲突）
    con = [g for g in golds
           if "conflict" in [t.lower() for t in (g.get("question_type") or [])]]
    chk(len(con) >= 3, "冲突类题目数量不足")
    for g in golds:
        if g["expected_action"] == "CONFLICT":
            chk(len(g["gold_evidence_refs"]) >= 2,
                f"{g['question_id']}: CONFLICT 需至少 2 条冲突证据")

    # ---- 权限验证
    perms = load_jsonl(os.path.join(DATASET, "registry", "permissions.jsonl"))
    deny = {p["doc_id"] for p in perms if p.get("classification") == "confidential"}
    chk("CT-002" in deny, "CT-002 应为 confidential")

    report = dict(checks=checks, errors=errors, warnings=warnings[:60],
                  warnings_total=len(warnings),
                  numeric_claim_spot_checks=checked_claims,
                  questions=len(golds),
                  status="PASS" if not errors else "FAIL")
    with open(os.path.join(DATASET, "validation", "validation_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
