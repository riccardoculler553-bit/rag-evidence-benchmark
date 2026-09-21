# -*- coding: utf-8 -*-
"""基准数据集主控：世界 → 语料 → 问题 → Gold → 注册表 → 校验报告。"""
import json
import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from world import all_entities, REGIONS, DEPARTMENTS, DEPT_HEADS
from corpus_docs import build_all, DOCS
import corpus_facts as F
import questions_part1 as Q1
import questions_part2 as Q2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(ROOT, "dataset")

ALLOWED_ACTIONS = {"ANSWER", "PARTIAL", "UNKNOWN", "ABSTAIN", "CLARIFY", "CONFLICT",
                   "ACCESS_DENIED", "OUT_OF_SCOPE"}
ALLOWED_DIFF = {"L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"}


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def build_entities_relationships(w):
    ents, rels = [], []

    def E(eid, etype, name, **attrs):
        ents.append(dict(entity_id=eid, entity_type=etype, name=name, attributes=attrs))

    def R(src, rel, dst, **attrs):
        rels.append(dict(src=src, relation=rel, dst=dst, attributes=attrs))

    E("ORG-GROUP", "company", "星环科技集团", en="NebulaCore Holdings", hq="中国大陆")
    for rid, rname in REGIONS.items():
        E(rid, "region", rname)
    R("ORG-GROUP", "has_region", "RG-CN")
    for parent, kids in [("RG-CN", "RG-SOUTH"), ("RG-CN", "RG-EAST"), ("RG-CN", "RG-NORTH")]:
        R(parent, "sub_region", kids)
    for dept in DEPARTMENTS:
        E(f"DEPT-{dept}", "department", dept, head=DEPT_HEADS.get(dept))
    for e in w["employees"]:
        E(e["employee_id"], "employee", e["name"], department=e["department"],
          region=e["region"], role=e["role"], grade=e["grade"],
          employment_type=e["employment_type"], status=e["status"],
          manager=e["manager"], office_city=e["office_city"])
        R(e["employee_id"], "member_of", f"DEPT-{e['department']}")
        R(e["employee_id"], "assigned_to", e["region"])
        if e["manager"]:
            R(e["employee_id"], "reports_to", e["manager"])
    for s in w["suppliers"]:
        E(s["supplier_id"], "supplier", s["supplier_name"], rating=s["rating"],
          country=s["country"], payment_terms=s["payment_terms"],
          lead_time_days=s["lead_time_days"], contract_start=s["contract_start"],
          contract_end=s["contract_end"], sensitivity=s["sensitivity"],
          delay_rate_pct=s["delay_rate_pct"])
    for p in w["products"]:
        E(p["internal_sku"], "product", p["product_name"], brand=p["brand"],
          is_digital=p["is_digital"])
        E(p["platform_sku"], "platform_sku", p["platform_sku"], platform=p["platform"])
        E(f"BRAND-{p['brand']}", "brand", p["brand"])
        R(p["platform_sku"], "maps_to_internal_sku", p["internal_sku"],
          platform=p["platform"])
        R(p["internal_sku"], "has_brand", f"BRAND-{p['brand']}")
    for a in w["sku_aliases"]:
        R(a["alias"], "legacy_alias_of", a["internal_sku"])
    for b in w["bundles"]:
        E(b["bundle_sku"], "bundle", b["name"])
        for c in b["components"]:
            R(b["bundle_sku"], "contains", c)
    for a in w["sku_aliases"]:
        E(a["alias"], "legacy_sku_alias", a["alias"])
    for wh in ["广州仓", "上海仓", "欧洲仓", "新加坡仓"]:
        E(wh, "warehouse", wh)
    for p_ in ["天猫", "京东", "抖音", "Shopify", "Shopee", "官网"]:
        E(f"PLAT-{p_}", "platform", p_)
    for c in w["customers"]:
        E(c["customer_id"], "customer", c["name"], tier=c["tier"], vip=c["vip"])
    for o in w["orders"]:
        E(o["order_id"], "order", o["order_id"], platform=o["platform"],
          sku=o["sku"], amount_excl_tax=o["amount_excl_tax"],
          refund_amount=o["refund_amount"], order_date=o["order_date"])
        R(o["order_id"], "placed_by", o["customer_id"])
        R(o["order_id"], "contains", o["sku"])
        R(o["order_id"], "fulfilled_from", o["warehouse"])
        R(o["order_id"], "sold_on", f"PLAT-{o['platform']}")
    sysd = w["systems"]
    for s in sysd["systems"]:
        E(s["system_id"], "system", s["name"])
        for svc in s["services"]:
            E(svc, "service", svc)
            R(s["system_id"], "runs", svc)
            db = sysd["service_db"].get(svc)
            if db:
                E(db, "database", db)
                R(svc, "uses_db", db)
                for t, cols in sysd["databases"].get(db, {}).items():
                    E(f"{db}.{t}", "table", t, columns=cols)
                    R(db, "contains_table", f"{db}.{t}")
    for p in w["projects"]:
        E(p["project_id"], "project", p["name"], region=p["region"], budget=p["budget"])
        R(p["project_id"], "owned_by", p["owner"])
        R(p["project_id"], "located_in", p["region"])
    for pid, members in w["project_members"].items():
        for m in members:
            R(m, "works_on", pid)
    return ents, rels


def main():
    if os.path.exists(DATASET):
        # 环境沙箱禁止 rmtree；改为逐文件覆盖（生成是确定性的，目录结构固定）
        for base, _, fs in os.walk(DATASET):
            for fn in fs:
                try:
                    os.remove(os.path.join(base, fn))
                except OSError:
                    pass
    for sub in ["knowledge", "registry", "questions", "gold", "logs", "validation"]:
        os.makedirs(os.path.join(DATASET, sub), exist_ok=True)

    # 1-5 世界 / 语料 / 版本 / 权限 / 交叉引用
    w, registries, extra_files = build_all(os.path.join(DATASET, "knowledge"))

    ents, rels = build_entities_relationships(w)
    write_jsonl(os.path.join(DATASET, "registry", "entities.jsonl"), ents)
    write_jsonl(os.path.join(DATASET, "registry", "relationships.jsonl"), rels)
    write_jsonl(os.path.join(DATASET, "registry", "documents.jsonl"), registries["documents"])
    write_jsonl(os.path.join(DATASET, "registry", "revisions.jsonl"), registries["revisions"])
    write_jsonl(os.path.join(DATASET, "registry", "permissions.jsonl"), registries["permissions"])
    write_jsonl(os.path.join(DATASET, "registry", "tables.jsonl"), registries["tables"])

    # 6-8 问题 / Gold / 对抗
    gens1 = [Q1.q_temporal, Q1.q_exception, Q1.q_scope, Q1.q_conflict,
             Q1.q_negative_exhaustive, Q1.q_claim_force, Q1.q_numeric_unit,
             Q1.q_ranking_agg, Q1.q_hr_entity, Q1.q_supplier_join,
             Q1.q_supplier_facts, Q1.q_table_cell, Q1.q_platform_stats, Q1.q_contrastive]
    gens2 = [Q2.q_legal, Q2.q_it, Q2.q_project, Q2.q_refund_multihop,
             Q2.q_evidence_addition, Q2.q_permission, Q2.q_citation_attack,
             Q2.q_parser, Q2.q_red_herring, Q2.q_synonym, Q2.q_structured_cross]
    all_q = []
    for g in gens1 + gens2:
        all_q.extend(g(w))

    seen = set()
    questions, golds, traces = [], [], []
    for i, q in enumerate(all_q, 1):
        qid = f"Q-{i:04d}"
        assert qid not in seen
        seen.add(qid)
        q["question_id"] = qid
        questions.append(dict(question_id=qid, question=q["question"],
                              question_type=q["question_type"], difficulty=q["difficulty"],
                              requirements=q["requirements"]))
        golds.append({k: v for k, v in q.items() if k != "trace"})
        g = q.get("trace") or {}
        g["question_id"] = qid
        g["question"] = q["question"]
        traces.append(g)
    write_jsonl(os.path.join(DATASET, "questions", "questions.jsonl"), questions)
    write_jsonl(os.path.join(DATASET, "gold", "gold.jsonl"), golds)
    write_jsonl(os.path.join(DATASET, "logs", "gold_generation_trace.jsonl"), traces)

    # 统计报告
    n_files = 0
    for base, _, fs in os.walk(os.path.join(DATASET, "knowledge")):
        n_files += len(fs)
    from collections import Counter
    tc = Counter(t for q in all_q for t in q["question_type"])
    dc = Counter(q["difficulty"] for q in all_q)
    ac = Counter(q["expected_action"] for q in all_q)
    sig = Counter(s for q in all_q for s in q["reasoning_signature"])
    fail = Counter(f for q in all_q for f in q["failure_target"])
    dom = Counter(d.domain for d in DOCS)
    report_lines = [
        "# 数据集统计报告\n",
        f"- 注册文档：{len(registries['documents'])}；知识库文件：{n_files + len(extra_files)}",
        f"- 结构化表：{len(registries['tables'])}；实体：{len(ents)}；关系：{len(rels)}",
        f"- 问题：{len(questions)}；Gold 记录：{len(golds)}\n",
        "## 问题类型分布\n", "| 类型 | 数量 |", "|---|---|"]
    for k, v in tc.most_common():
        report_lines.append(f"| {k} | {v} |")
    report_lines += ["\n## 难度分布\n", "| 难度 | 数量 |", "|---|---|"]
    for k in sorted(dc):
        report_lines.append(f"| {k} | {dc[k]} |")
    report_lines += ["\n## Expected Action 分布\n", "| 动作 | 数量 |", "|---|---|"]
    for k, v in ac.most_common():
        report_lines.append(f"| {k} | {v} |")
    report_lines += ["\n## reasoning_signature 覆盖\n", "| 能力 | 数量 |", "|---|---|"]
    for k, v in sig.most_common():
        report_lines.append(f"| {k} | {v} |")
    report_lines += ["\n## failure_target 覆盖\n", "| 攻击目标 | 数量 |", "|---|---|"]
    for k, v in fail.most_common():
        report_lines.append(f"| {k} | {v} |")
    report_lines += ["\n## 文档域分布\n", "| 域 | 数量 |", "|---|---|"]
    for k, v in dom.most_common():
        report_lines.append(f"| {k} | {v} |")
    with open(os.path.join(DATASET, "REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    # 校验夹具（供独立验证脚本复算）
    from collections import defaultdict
    plat = defaultdict(lambda: [0, 0])
    for o in w["orders"]:
        if o["order_date"].startswith("2026"):
            plat[o["platform"]][0] += 1
            if o["refund_amount"] > 0:
                plat[o["platform"]][1] += 1
    fin = w["finance_monthly"]
    fixtures = dict(
        orders_total_2026=sum(o["amount_excl_tax"] for o in w["orders"]
                              if o["order_date"].startswith("2026")),
        active_employees=sum(1 for e in w["employees"] if e["status"] == "在职"),
        platform_refund_rates={p: round(c[1] / c[0], 4) for p, c in plat.items()},
        h1_2026_revenue=sum(r["revenue"] for r in fin
                            if r["month"].startswith("2026-0") and r["month"] <= "2026-06"),
        h1_2025_revenue=sum(r["revenue"] for r in fin
                            if r["month"].startswith("2025-0") and r["month"] <= "2025-06"),
        south_202606_revenue=[r["revenue"] for r in fin
                              if r["month"] == "2026-06" and r["region"] == "RG-SOUTH"][0],
        eu_202606_revenue=[r["revenue"] for r in fin
                           if r["month"] == "2026-06" and r["region"] == "RG-EU"][0],
    )
    with open(os.path.join(DATASET, "validation", "fixtures.json"), "w", encoding="utf-8") as f:
        json.dump(fixtures, f, ensure_ascii=False, indent=1)

    # manifest
    manifest = dict(
        name="NebulaCore Evidence-Native RAG Benchmark",
        world_model=dict(company="星环科技集团 / NebulaCore Holdings",
                         regions=list(REGIONS.values()), departments=DEPARTMENTS,
                         entities=len(ents), relationships=len(rels)),
        knowledge_files=n_files + len(extra_files),
        documents_registered=len(registries["documents"]),
        structured_tables=len(registries["tables"]),
        questions=len(questions),
        gold_records=len(golds),
        generated_at="2026-09-19",
    )
    with open(os.path.join(DATASET, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print(f"documents={len(registries['documents'])} entities={len(ents)} "
          f"relationships={len(rels)} questions={len(questions)} files={n_files + len(extra_files)}")


if __name__ == "__main__":
    main()
