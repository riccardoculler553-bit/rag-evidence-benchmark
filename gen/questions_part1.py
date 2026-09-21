# -*- coding: utf-8 -*-
"""问题与 Gold 生成 —— 第一部分：事实/时序/范围/例外/冲突/否定/穷举/计算/HR/实体解析。
所有 Gold 数值均从 world + corpus_facts 推导，保证机器可验证。"""

from world import REGIONS, TIER1_CITIES, TIER2_CITIES
import corpus_facts as F
from corpus_facts import (trv_hotel, surcharge_amount, trv_exec_hotel, gross_margin,
                          ct_payment_days, TAX_RATE)

CURRENT = "2026-09-01"   # “目前/当前”锚定日期


def W(support="PASS", coverage="PASS", scope="PASS", temporal="PASS",
      authority="PASS", conflict="NOT_PRESENT"):
    return dict(support=support, coverage=coverage, scope=scope, temporal=temporal,
                authority=authority, conflict=conflict)


def REQ(target, scope="集团", effective_at=CURRENT, completeness="single",
        precision="exact", derivation=False, conflict_policy="surface", citation=True):
    return dict(target=target, scope=scope, effective_at=effective_at,
                completeness=completeness, precision=precision, derivation=derivation,
                conflict_policy=conflict_policy, citation=citation)


def mk_q(question, qtype, difficulty, required_sources, gold_refs, claims, expected,
         acceptable=None, must_not=None, warrant=None, signature=None, failure=None,
         requirements=None, evidence_sets=None, req_ev=None, opt_ev=None, irr_ev=None,
         dependencies=None, stages=None, evidence_stages=None, order_variants=None,
         evidence_order_variants=None, pair_of=None, judge=None, asked_as=None,
         note=None, trace=None):
    return dict(
        question=question, question_type=qtype, difficulty=difficulty,
        required_sources=required_sources, gold_evidence_refs=gold_refs,
        required_dependencies=dependencies or [],
        gold_claims=claims, warrant_requirements=warrant or W(),
        expected_action=expected, acceptable_answer=acceptable,
        must_not_claim=must_not or [],
        requirements=requirements or REQ(""),
        reasoning_signature=signature or ["direct_lookup"],
        failure_target=failure or ["RETRIEVAL_MISS"],
        acceptable_evidence_sets=evidence_sets or [],
        gold_required_evidence=req_ev or gold_refs,
        gold_optional_evidence=opt_ev or [],
        gold_irrelevant_evidence=irr_ev or [],
        evidence_stages=stages or evidence_stages or [],
        evidence_order_variants=evidence_order_variants or order_variants or [],
        pair_of=pair_of, judge_target=judge, asked_as=asked_as, notes=note,
        trace=trace or {},
    )


def claim(text, status="SUPPORTED", scope="CN", eff=CURRENT, force="exact"):
    return dict(claim=text, status=status, scope=scope, effective_at=eff, claim_force=force)


def fmt(n):
    return f"{n:,}"


# ================================================================ generators
def q_temporal(w):
    qs = []
    cases = [("广州", "2025-03-15"), ("北京", "2025-12-15"), ("深圳", "2025-10-15"),
             ("上海", "2026-03-15"), ("上海", "2026-06-15"), ("上海", "2026-08-15"),
             ("广州", "2026-05-15"), ("杭州", "2026-01-15"), ("成都", "2025-09-15"),
             ("武汉", "2025-11-15"), ("苏州", "2026-04-15"), ("西安", "2026-02-10"),
             ("南京", "2026-06-10"), ("杭州", "2025-08-10"), ("成都", "2026-07-12"),
             ("北京", "2026-04-02"), ("深圳", "2026-01-20"), ("武汉", "2026-03-08"),
             ("西安", "2025-10-06"), ("苏州", "2025-11-25"), ("南京", "2025-09-18"),
             ("合肥", "2026-05-18"), ("郑州", "2026-02-25"), ("佛山", "2026-07-22")]
    for city, date in cases:
        h = trv_hotel(city, date)
        ym = date[:7].replace("-", "年") + "月"
        refs = h["refs"]
        qs.append(mk_q(
            f"{ym}{city}普通员工差旅住宿上限是多少？",
            ["temporal", "single_doc"], "L3", [h["version"]], refs,
            [claim(f"{ym}{city}普通员工住宿上限为 {h['amount']} 元/晚", scope="CN", eff=date)],
            "ANSWER", f"{h['amount']} 元/晚",
            must_not=[f"{city}住宿上限长期不变", "不知道，无法确定"],
            signature=["temporal_filter", "table_lookup"],
            failure=["TEMPORAL_LEAK", "RETRIEVAL_MISS"],
            requirements=REQ(f"{city}住宿上限", "中国大陆", date),
            dependencies=["effective_date", "version_selection"],
            trace=dict(chosen=h["version"], why="该日期落在该版本的生效区间",
                       superseded=[x["doc_id"] for x in F.TRV_VERSIONS if x["doc_id"] != h["version"]],
                       distractors=["TRV-002", "TRV-003", "TRV-004"])))
    # 当前值
    for city in ["上海", "广州", "杭州", "北京", "深圳", "成都", "南京", "西安"]:
        h = trv_hotel(city, CURRENT)
        qs.append(mk_q(
            f"目前{city}普通员工差旅住宿上限是多少？",
            ["temporal", "single_doc"], "L3", ["TRV-001-v3"], h["refs"],
            [claim(f"截至当前（{CURRENT}），{city}普通员工住宿上限为 {h['amount']} 元/晚")],
            "ANSWER", f"{h['amount']} 元/晚",
            must_not=["450 元", "500 元（若为上海，未考虑特殊城市调整）"],
            signature=["temporal_filter", "scope_filter", "table_lookup"],
            failure=["TEMPORAL_LEAK"], requirements=REQ(f"{city}住宿上限", "中国大陆", CURRENT),
            trace=dict(chosen="TRV-001-v3", why="current 版本",
                       superseded=["TRV-001-v1", "TRV-001-v2"])))
    # published ≠ effective
    qs += [
        mk_q("《关于上海地区住宿标准调整的通知》（TRV-001-CN1）何时发布、何时生效？",
             ["temporal"], "L2", ["TRV-001-CN1"], ["TRV-001-CN1#sec-1"],
             [claim("发布日期 2026-06-05，生效日期 2026-07-01")],
             "ANSWER", "发布 2026-06-05；生效 2026-07-01",
             must_not=["2026-06-05 即生效"],
             signature=["temporal_filter"], failure=["TEMPORAL_LEAK"],
             requirements=REQ("发布/生效时间"), note="published ≠ effective"),
        mk_q("2026年6月20日出差上海，普通员工住宿上限是多少？",
             ["temporal", "scope"], "L4", ["TRV-001-v3"], ["TRV-001-v3#tbl-a"],
             [claim("500 元/晚（特殊城市 650 元标准自 2026-07-01 才生效）", eff="2026-06-20")],
             "ANSWER", "500 元/晚",
             must_not=["650 元", "480 元"],
             signature=["temporal_filter"], failure=["TEMPORAL_LEAK"],
             requirements=REQ("上海住宿上限", "中国大陆", "2026-06-20")),
        mk_q("2026年7月10日出差上海，普通员工住宿上限是多少？",
             ["temporal"], "L3", ["TRV-001-CN1", "TRV-001-v3"],
             ["TRV-001-CN1#sec-1", "TRV-001-v3#sec-2-2"],
             [claim("650 元/晚", eff="2026-07-10")], "ANSWER", "650 元/晚",
             must_not=["500 元"],
             signature=["temporal_filter", "cross_reference"], failure=["TEMPORAL_LEAK"],
             requirements=REQ("上海住宿上限", "中国大陆", "2026-07-10")),
        mk_q("2025年版本的住宿标准与2026年版本相比变化了什么？",
             ["temporal", "conflict_fake"], "L3", ["TRV-001-v1", "TRV-001-v2", "TRV-001-v3"],
             ["TRV-001-v1#tbl-a", "TRV-001-v2#tbl-a", "TRV-001-v3#tbl-a"],
             [claim("一线城市住宿上限：2025上半年 400 → 2025下半年 450 → 2026起 500 元/晚，属时间演化而非冲突")],
             "ANSWER", "一线 400→450→500；二线 300→350→400；其他 250→280→320",
             must_not=["两版政策存在冲突，无法确定"],
             signature=["temporal_filter", "conflict_resolution"], failure=["CONFLICT_IGNORE"],
             warrant=W(conflict="RESOLVED"),
             requirements=REQ("版本对比", completeness="exhaustive"),
             trace=dict(why="同 scope 不同时间 → superseded 演化，不得判为真冲突")),
        mk_q("若查询时间从2025年12月改为2026年6月，上海普通员工住宿标准是否变化？",
             ["temporal", "counterfactual"], "L3", ["TRV-001-v2", "TRV-001-v3"],
             ["TRV-001-v2#tbl-a", "TRV-001-v3#tbl-a"],
             [claim("变化：2025-12 为 450 元/晚，2026-06 为 500 元/晚")], "ANSWER", "变化：450 → 500",
             signature=["temporal_filter"], failure=["TEMPORAL_LEAK"],
             requirements=REQ("上海住宿上限", "中国大陆", "2026-06")),
    ]
    # As-of 快照题（§99）
    asof_cases = [("2025-05-20", "上海", 400), ("2025-07-10", "上海", 450),
                  ("2025-12-31", "广州", 450), ("2026-01-05", "广州", 500),
                  ("2026-06-30", "上海", 500), ("2026-07-02", "上海", 650),
                  ("2025-06-30", "杭州", 300), ("2025-07-02", "杭州", 350)]
    for date, city, amt in asof_cases:
        qs.append(mk_q(
            f"截至 {date}（As-of 查询），{city}普通员工差旅住宿上限是多少？",
            ["temporal", "snapshot"], "L4", ["TRV-001-v3"],
            [f"{trv_hotel(city, date)['version']}#tbl-a"],
            [claim(f"{amt} 元/晚（as-of {date}）", eff=date)],
            "ANSWER", f"{amt} 元/晚",
            must_not=["当前最新标准（应按快照日期取值）"],
            signature=["temporal_filter", "snapshot_query"], failure=["TEMPORAL_LEAK"],
            requirements=REQ(f"{city}住宿上限(as-of {date})", "中国大陆", date)))
    return qs


def q_exception(w):
    qs = []
    # 脚注/例外上浮
    qs += [
        mk_q("2026年广交会期间（2026-04-20）出差广州，普通员工住宿上限是多少？",
             ["exception", "table", "derivation"], "L4",
             ["TRV-001-v3"], ["TRV-001-v3#tbl-a", "TRV-001-v3#fn-2", "TRV-001-v3#app-b"],
             [claim("600 元/晚（500 × 1.2，四舍五入到十元）", eff="2026-04-20")],
             "ANSWER", "600 元/晚",
             must_not=["500 元（未读展会脚注）"],
             dependencies=["table_header", "footnote", "arithmetic"],
             signature=["table_lookup", "footnote_dependency", "exception_override", "arithmetic"],
             failure=["EXCEPTION_MISS", "NUMERIC_ERROR"],
             requirements=REQ("展会期间广州住宿上限", "中国大陆", "2026-04-20", derivation=True)),
        mk_q("2026年春节假期（2026-02-18）出差北京，普通员工住宿上限是多少？",
             ["exception", "derivation"], "L4", ["TRV-001-v3"],
             ["TRV-001-v3#sec-3-1", "TRV-001-v3#tbl-a"],
             [claim("600 元/晚（500 × 1.2）", eff="2026-02-18")], "ANSWER", "600 元/晚",
             must_not=["500 元"], dependencies=["arithmetic"],
             signature=["temporal_filter", "exception_override", "arithmetic"],
             failure=["EXCEPTION_MISS"], requirements=REQ("春节期间北京住宿上限", derivation=True)),
        mk_q("2025年12月（春节条款已生效版本）若春节期间出差上海，普通员工住宿上限是多少？",
             ["exception", "derivation"], "L4", ["TRV-001-v2"],
             ["TRV-001-v2#sec-3-1", "TRV-001-v2#tbl-a"],
             [claim("540 元/晚（450 × 1.2，按 v2 版本）")], "ANSWER", "540 元/晚",
             signature=["temporal_filter", "exception_override", "arithmetic"],
             failure=["EXCEPTION_MISS"], requirements=REQ("春节期间上海住宿上限（v2）", derivation=True)),
        mk_q("客户指定酒店导致房价超出住宿标准，能否报销？",
             ["exception"], "L2", ["TRV-001-v3"], ["TRV-001-v3#sec-3-3"],
             [claim("超出部分不超过标准 30% 且经部门负责人及财务审批的可予报销")],
             "ANSWER", "超出部分 ≤ 标准 30%，经审批可报销",
             must_not=["一律不能报销", "可以全额报销"],
             signature=["exception_lookup"], failure=["EXCEPTION_MISS"],
             requirements=REQ("客户指定酒店报销规则")),
        mk_q("2026年8月出差上海，客户指定酒店实付 845 元/晚，最多可报销多少住宿费？",
             ["exception", "derivation"], "L5", ["TRV-001-v3", "TRV-001-CN1"],
             ["TRV-001-CN1#sec-1", "TRV-001-v3#sec-3-3"],
             [claim("标准 650 元，可报销上限 650 × 1.3 = 845 元，全额可报（经审批）", eff="2026-08")],
             "ANSWER", "845 元/晚", must_not=["650 元", "无法确定"],
             signature=["temporal_filter", "exception_override", "arithmetic"],
             failure=["EXCEPTION_MISS", "NUMERIC_ERROR"],
             requirements=REQ("客户指定酒店报销上限", derivation=True)),
        mk_q("差旅申请是否必须提前 3 个工作日提交？",
             ["exception", "hidden_exception"], "L2", ["TRV-001-v3"],
             ["TRV-001-v3#sec-1-3", "TRV-001-v3#sec-3-4"],
             [claim("一般须提前 3 个工作日；紧急客户事件经部门负责人批准可当天提交", force="usually")],
             "ANSWER", "一般须提前3个工作日；紧急客户事件可当天申请（例外）",
             must_not=["必须提前3个工作日，无任何例外"],
             signature=["exception_override"], failure=["EXCEPTION_MISS"],
             requirements=REQ("差旅申请时限")),
        mk_q("紧急客户事件出差是否允许当天提交申请？",
             ["exception"], "L2", ["TRV-001-v3"], ["TRV-001-v3#sec-3-4"],
             [claim("允许，经部门负责人批准后当天提交，不受提前 3 个工作日限制")],
             "ANSWER", "允许（需部门负责人批准）",
             signature=["exception_lookup"], failure=["EXCEPTION_MISS"],
             requirements=REQ("紧急客户事件申请规则")),
        mk_q("有供应商人员全程陪同出差时，员工住宿标准如何执行？",
             ["exception"], "L3", ["TRV-001-v3"], ["TRV-001-v3#sec-3-5"],
             [claim("按对应城市标准的 80% 执行")], "ANSWER", "标准的 80%",
             must_not=["不变，仍按全标准"],
             signature=["exception_lookup"], failure=["EXCEPTION_MISS"],
             requirements=REQ("供应商陪同出差住宿标准")),
        mk_q("2026年8月（上海特殊城市标准下）供应商陪同出差，住宿上限是多少？",
             ["exception", "derivation"], "L5", ["TRV-001-CN1", "TRV-001-v3"],
             ["TRV-001-CN1#sec-1", "TRV-001-v3#sec-3-5"],
             [claim("650 × 0.8 = 520 元/晚")], "ANSWER", "520 元/晚",
             signature=["temporal_filter", "exception_override", "arithmetic"],
             failure=["EXCEPTION_MISS", "NUMERIC_ERROR"], requirements=REQ("供应商陪同上海住宿上限", derivation=True)),
        # NDA 反证
        mk_q("所有供应商都必须签署 NDA 吗？",
             ["exception", "counter_evidence"], "L3", ["PROC-001-v3"],
             ["PROC-001-v3#sec-nda", "PROC-001-v3#sec-nda-exempt"],
             [claim("不是。低敏级物料供应商且单笔采购金额低于 10,000 元的可豁免")],
             "ANSWER", "否，低敏级且金额<10,000元可豁免",
             must_not=["是，所有供应商必须签 NDA"],
             signature=["exception_override", "counter_evidence"], failure=["EXCEPTION_MISS"],
             requirements=REQ("NDA豁免条件")),
        mk_q("向环宇办公用品（S006，低敏级）单笔采购 8,000 元，是否必须先签 NDA？",
             ["exception", "multi_hop"], "L4", ["PROC-001-v3"],
             ["PROC-001-v3#sec-nda-exempt"],
             [claim("不需要，符合低敏级且 <10,000 元的豁免条件")], "ANSWER", "否，可豁免",
             signature=["entity_resolution", "exception_override"], failure=["EXCEPTION_MISS"],
             requirements=REQ("S006 NDA 要求")),
        mk_q("向恒远电子（S003，常规级）单笔采购 8,000 元，是否可以豁免 NDA？",
             ["exception"], "L4", ["PROC-001-v3"], ["PROC-001-v3#sec-nda-exempt"],
             [claim("不可以。豁免仅适用于低敏级物料供应商，S003 为常规级")], "ANSWER", "否，不可豁免",
             signature=["scope_filter", "exception_override"], failure=["SCOPE_LEAK"],
             requirements=REQ("S003 NDA 要求"),
             trace=dict(distractors=["S006 案例同款金额，物料等级不同"])),
    ]
    return qs


def q_scope(w):
    qs = []
    # 对比维度：role × region × time
    qs += [
        mk_q("2026年8月上海 VP 住宿上限是多少？",
             ["scope", "role"], "L4", ["TRV-002-v2", "TRV-001-v3"],
             ["TRV-002-v2#tbl-b", "TRV-001-v3#sec-2-3"],
             [claim("800 元/晚（高管标准，不适用普通员工标准）", eff="2026-08")],
             "ANSWER", "800 元/晚",
             must_not=["500 元", "650 元（高管不适用特殊城市普通标准）"],
             signature=["scope_filter", "role_filter", "table_lookup"],
             failure=["SCOPE_LEAK"], requirements=REQ("VP住宿上限", "中国大陆", "2026-08"),
             trace=dict(distractors=["TRV-001 普通标准 500/650", "FAQ 480"])),
        mk_q("李静（E058，VP）2026年8月出差上海，住宿上限是多少？若她以普通员工身份执行差旅标准呢？",
             ["scope", "counterfactual"], "L5", ["TRV-002-v2", "TRV-001-CN1"],
             ["TRV-002-v2#tbl-b", "TRV-001-CN1#sec-1"],
             [claim("VP：800 元/晚"), claim("若按普通员工标准：650 元/晚（上海特殊城市）", status="HYPOTHETICAL")],
             "ANSWER", "VP 800 元/晚；普通员工口径为 650 元/晚",
             signature=["entity_resolution", "role_filter", "counterfactual"],
             failure=["SCOPE_LEAK"], requirements=REQ("VP与普通员工对比")),
        mk_q("欧洲区普通员工住宿上限是多少？",
             ["scope"], "L3", ["TRV-003"], ["TRV-003#sec-2"],
             [claim("800 元/晚（欧元区城市按 100 欧元/晚）")], "ANSWER", "800 元/晚（或 100 欧元/晚）",
             must_not=["500 元（中国大陆标准）"],
             signature=["scope_filter"], failure=["SCOPE_LEAK"],
             requirements=REQ("欧洲区住宿上限", "欧洲")),
        mk_q("北美区普通员工住宿上限是多少？",
             ["scope", "numeric_trap"], "L3", ["TRV-003"], ["TRV-003#sec-4", "TRV-003#fn-usd"],
             [claim("120 美元/晚，报销按当月月初汇率折算人民币")], "ANSWER", "120 美元/晚",
             must_not=["120 元人民币", "900 元人民币"],
             signature=["scope_filter", "currency_check"], failure=["SCOPE_LEAK", "NUMERIC_ERROR"],
             requirements=REQ("北美区住宿上限", "北美")),
        mk_q("VP 到欧洲区出差，住宿上限是多少？",
             ["scope", "derivation"], "L4", ["TRV-003"], ["TRV-003#sec-2", "TRV-003#sec-6"],
             [claim("800 × 1.5 = 1,200 元/晚（欧洲普通标准上浮 50%）")], "ANSWER", "1,200 元/晚",
             signature=["scope_filter", "role_filter", "arithmetic"], failure=["NUMERIC_ERROR"],
             requirements=REQ("VP欧洲住宿上限", "欧洲", derivation=True)),
        mk_q("欧洲区普通员工也适用 500 元的住宿上限吗？",
             ["scope", "extrapolation"], "L4", ["TRV-003"], ["TRV-003#sec-2"],
             [claim("不适用。欧洲区按海外差旅政策执行（800 元/晚）", status="REFUTED")],
             "ANSWER", "否，欧洲区为 800 元/晚",
             must_not=["是，集团统一 500 元"],
             signature=["scope_filter"], failure=["SCOPE_LEAK"],
             requirements=REQ("欧洲区适用标准", "欧洲")),
        mk_q("VP 是否也适用 500 元的普通员工住宿标准？",
             ["scope", "role_extrapolation"], "L3", ["TRV-001-v3", "TRV-002-v2"],
             ["TRV-001-v3#sec-2-3", "TRV-002-v2#tbl-b"],
             [claim("不适用。M5/VP 按《高管差旅住宿标准》执行（一线 800 元/晚）", status="REFUTED")],
             "ANSWER", "否，VP 为 800 元/晚",
             must_not=["是，VP 也是 500 元"],
             signature=["role_filter"], failure=["SCOPE_LEAK"],
             requirements=REQ("VP适用标准")),
        mk_q("公司对实习生出差的住宿标准是多少？",
             ["scope", "negative"], "L4", ["TRV-001-v3"],
             ["TRV-001-v3#sec-1-2"],
             [claim("知识库未明确规定实习生差旅住宿标准（办法适用对象为正式员工与外包人员）",
                    status="NOT_SPECIFIED")],
             "UNKNOWN", None,
             must_not=["与普通员工相同，500 元", "300 元"],
             signature=["scope_filter", "abstention"], failure=["OVERCLAIM"],
             warrant=W(coverage="PARTIAL"), requirements=REQ("实习生住宿标准", completeness="single"),
             note="适用范围未列实习生 → 不得外推"),
        mk_q("外包人员适用《差旅费管理办法》吗？",
             ["scope"], "L2", ["TRV-001-v3"], ["TRV-001-v3#sec-1-2"],
             [claim("适用，办法适用于全体正式员工与外包人员在中国大陆境内差旅")],
             "ANSWER", "适用",
             signature=["scope_filter"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("办法适用对象")),
        mk_q("中国香港普通员工差旅住宿上限是多少？",
             ["scope"], "L3", ["TRV-003"], ["TRV-003#sec-5"],
             [claim("700 元/晚")], "ANSWER", "700 元/晚",
             must_not=["500 元", "650 元"],
             signature=["scope_filter"], failure=["SCOPE_LEAK"],
             requirements=REQ("中国香港住宿上限", "中国香港")),
    ]
    return qs


def q_conflict(w):
    qs = []
    qs += [
        mk_q("华东区销售部 2026年8月一线城市住宿上限是多少？",
             ["conflict", "authority"], "L6",
             ["TRV-001-v3", "CON-001", "COMP-REG-001"],
             ["TRV-001-v3#sec-2-1", "TRV-001-v3#sec-5-1", "CON-001#sec-1", "COMP-REG-001#fn-reg"],
             [claim("700 元通知无效：上浮 40% 超过 10% 授权且未备案；有效标准为 500 元/晚",
                    eff="2026-08")],
             "ANSWER", "500 元/晚（700 元通知无效）",
             must_not=["700 元", "两份文件冲突，无法确定"],
             warrant=W(conflict="RESOLVED"),
             signature=["conflict_detection", "authority_check", "scope_filter", "regulation_check"],
             failure=["AUTHORITY_MISS", "CONFLICT_IGNORE", "OVERCLAIM"],
             requirements=REQ("华东区销售部住宿上限", "华东区", "2026-08", conflict_policy="resolve"),
             trace=dict(chosen="TRV-001-v3#sec-2-1", why="L5 正式制度 + 区域调节权限规则裁决",
                        conflict=["CON-001 (L3, 700元)"], conflict_resolution="超出10%授权且未备案 → 无效",
                        distractors=["CON-002a", "CON-002b"])),
        mk_q("2026年4月20日运营部员工出差广州，住宿报销上限是多少？",
             ["conflict"], "L6", ["CON-002a", "CON-002b", "TRV-001-v3", "COMP-REG-001"],
             ["CON-002a#sec-1", "CON-002b#sec-1"],
             [claim("存在真冲突：运营部通知 520 元（BA-2026-018）与行政部全员通知 530 元（BA-2026-019）"
                    "同级别、同时间窗、均在备案且均未超 10% 上浮，无法依权威或时间消解",
                    status="CONFLICTED")],
             "CONFLICT", None,
             must_not=["520 元（二选一）", "530 元（二选一）", "500 元（忽略区域通知）"],
             warrant=W(conflict="UNRESOLVED"),
             signature=["conflict_detection", "conflict_surface"],
             failure=["CONFLICT_IGNORE"],
             requirements=REQ("运营部住宿报销上限", "运营部", "2026-04-20", conflict_policy="surface"),
             evidence_order_variants=[["CON-002a", "CON-002b"], ["CON-002b", "CON-002a"]],
             trace=dict(conflict=["CON-002a(520)", "CON-002b(530)"],
                        why="真冲突：同 L3、同 scope 交叠、同时间、均已备案 → surface"),
             note="证据顺序交换后结论应保持 CONFLICTED"),
        mk_q("FAQ 里说住宿一般 500 元、有时 480 元封顶，以哪个为准？",
             ["conflict", "authority"], "L4", ["TRV-001-v3", "FAQ-001"],
             ["TRV-001-v3#sec-2-1", "FAQ-001#sec-1"],
             [claim("以正式制度为准；FAQ 仅为客服参考口径（authority_level 2 < 5）")],
             "ANSWER", "以正式制度为准（一线 500 元/晚）",
             must_not=["480 元", "以 FAQ 为准"],
             warrant=W(authority="PASS"),
             signature=["authority_check"], failure=["AUTHORITY_MISS"],
             requirements=REQ("住宿标准权威来源"),
             trace=dict(chosen="TRV-001-v3", why="L5 > L2",
                        distractors=["FAQ-001 480 元：语义相近但权威级低"])),
        mk_q("退款多久到账？",
             ["authority", "numeric_precision"], "L3", ["RMA-001", "FAQ-002"],
             ["RMA-001#sec-2-1", "FAQ-002#sec-1"],
             [claim("审核通过后 3-5 个工作日原路退回（正式政策口径；FAQ 的“3-5 天”表述不规范）")],
             "ANSWER", "3-5 个工作日",
             must_not=["3-5 天（自然日）", "7 天"],
             signature=["authority_check", "numeric_precision"], failure=["AUTHORITY_MISS", "NUMERIC_ERROR"],
             requirements=REQ("退款到账时效")),
        mk_q("截至 2026-06-30，上海普通员工住宿标准是多少？",
             ["temporal", "snapshot"], "L4", ["TRV-001-v3"],
             ["TRV-001-v3#tbl-a"],
             [claim("500 元/晚（As-of 2026-06-30；650 元标准尚未生效）", eff="2026-06-30")],
             "ANSWER", "500 元/晚",
             must_not=["650 元", "450 元"],
             signature=["temporal_filter", "snapshot_query"], failure=["TEMPORAL_LEAK"],
             requirements=REQ("上海住宿上限(as-of)", "中国大陆", "2026-06-30")),
        mk_q("华南区市内交通补贴上浮 10% 是否合规有效？",
             ["authority"], "L4", ["COMP-REG-001", "TRV-001-v3"],
             ["COMP-REG-001#tbl-reg", "TRV-001-v3#sec-5-1"],
             [claim("合规有效：上浮幅度 10% 未超授权，且已备案（BA-2026-011）")],
             "ANSWER", "合规有效（已备案，幅度未超限）",
             signature=["authority_check"], failure=["AUTHORITY_MISS"],
             requirements=REQ("华南区备案有效性")),
    ]
    return qs


def q_negative_exhaustive(w):
    qs = []
    qs += [
        mk_q("公司是否规定周末可以提交报销？",
             ["negative"], "L3", ["EXP-001-v2"], ["EXP-001-v2#fn-weekend", "EXP-001-v2#sec-5"],
             [claim("制度未对周末提交报销作出特别规定（明确列为未尽事宜，由财务部解释）",
                    status="ABSENT_EXPLICIT")],
             "ABSENT", "制度未规定（未尽事宜由财务部解释）",
             must_not=["周末可以提交", "周末不可以提交"],
             signature=["abstention", "scope_completeness"], failure=["OVERCLAIM"],
             warrant=W(coverage="PASS"), requirements=REQ("周末报销规定", completeness="single"),
             note="检索域完整（报销制度全集），可判 ABSENT"),
        mk_q("公司有没有员工宠物保险福利？",
             ["negative"], "L2", ["BEN-001"], ["BEN-001#sec-2"],
             [claim("福利制度中无宠物保险相关内容", status="ABSENT")],
             "ABSENT", "无此福利规定",
             must_not=["有宠物保险"],
             signature=["abstention"], failure=["OVERCLAIM"],
             requirements=REQ("宠物保险福利", completeness="exhaustive"),
             trace=dict(why="福利制度全集已检索，无该条目 → ABSENT")),
        mk_q("北美区员工是否有额外的特殊住房补贴？",
             ["negative", "scope"], "L4", ["TRV-004", "TRV-003"],
             ["TRV-004#sec-1", "TRV-003#sec-4"],
             [claim("知识库未检索到北美区专项住房补贴文件（外派补贴 TRV-004 未区分区域、北美差旅政策仅覆盖住宿上限）",
                    status="UNKNOWN_COVERAGE")],
             "UNKNOWN", None,
             must_not=["有，每月 3,000 元（外派补贴不等于北美专项住房补贴）"],
             signature=["abstention", "coverage_check"], failure=["OVERCLAIM"],
             warrant=W(coverage="PARTIAL"), requirements=REQ("北美住房补贴", "北美"),
             note="北美政策文件覆盖不完整 → 不得判 ABSENT"),
        mk_q("华北区区域负责人是谁？",
             ["negative", "hr"], "L3", ["ORG-002"], ["ORG-002#sec-2"],
             [claim("人员注册表中未定义华北区区域负责人（中国区下仅设省级区域负责人于华南/华东；"
                    "华北区负责人未登记）", status="NOT_SPECIFIED")],
             "UNKNOWN", None,
             must_not=["陈明远", "罗志成"],
             signature=["abstention", "coverage_check"], failure=["OVERCLAIM"],
             warrant=W(coverage="PARTIAL"), requirements=REQ("华北区负责人")),
        mk_q("《采购管理办法》（v3）规定了哪些免于逐单审批的情形？",
             ["exhaustive"], "L5", ["PROC-001-v3"],
             ["PROC-001-v3#sec-6-1", "PROC-001-v3#sec-6-2", "PROC-001-v3#sec-6-3", "PROC-001-v3#app-c"],
             [claim("共 4 项：①单笔<5,000 且当月累计<20,000；②框架协议内已定价商品；"
                    "③生产紧急备件（48小时内补审批）；④年度集中采购目录内标准办公用品（仅列于附录C）",
                    status="SUPPORTED", force="exhaustive_in_corpus")],
             "ANSWER", "上述 4 项",
             must_not=["只列正文 3 项而漏掉附录C第4项"],
             signature=["exhaustive_scan", "cross_reference"],
             failure=["COMPLETENESS_ERROR"],
             requirements=REQ("免审批情形", completeness="exhaustive"),
             trace=dict(why="第4项只在附录C → almost-complete 陷阱：漏读附录则少 1 项")),
        mk_q("正文第六章列出的免审批情形有哪些？",
             ["exhaustive", "pair"], "L3", ["PROC-001-v3"],
             ["PROC-001-v3#sec-6-1", "PROC-001-v3#sec-6-2", "PROC-001-v3#sec-6-3"],
             [claim("正文列出 3 项：零星采购、框架协议内已定价商品、紧急备件", force="scope_limited")],
             "ANSWER", "正文 3 项（第4项在附录C，不属于正文列举）",
             pair_of="PROC-001-v3#sec-6",
             signature=["exhaustive_scan", "scope_filter"], failure=["COMPLETENESS_ERROR"],
             requirements=REQ("正文免审批情形", completeness="exhaustive")),
        mk_q("《差旅费管理办法》中普通员工住宿标准可以上浮的情形有哪些？",
             ["exhaustive"], "L5", ["TRV-001-v3"],
             ["TRV-001-v3#sec-2-3", "TRV-001-v3#sec-3-1", "TRV-001-v3#sec-3-2",
              "TRV-001-v3#sec-3-3", "TRV-001-v3#sec-5-1"],
             [claim("共 5 类：①M3/M4 上浮 30%；②春节假期上浮 20%；③展会期间上浮 20%；"
                    "④客户指定酒店超 30% 部分经审批；⑤区域调节上浮 ≤10%（须备案）",
                    force="exhaustive_in_corpus")],
             "ANSWER", "上述 5 类",
             must_not=["遗漏客户指定酒店条款", "遗漏区域调节条款"],
             signature=["exhaustive_scan"], failure=["COMPLETENESS_ERROR"],
             requirements=REQ("住宿上浮情形", completeness="exhaustive")),
        mk_q("哪些情形需要董事会批准？",
             ["exhaustive"], "L3", ["PROC-001-v3"], ["PROC-001-v3#sec-4-3"],
             [claim("单一来源采购须提交董事会批准（制度中唯一董事会审批事项）", force="exhaustive_in_corpus")],
             "ANSWER", "单一来源采购",
             signature=["exhaustive_scan"], failure=["COMPLETENESS_ERROR"],
             requirements=REQ("董事会批准情形", completeness="exhaustive")),
        mk_q("哪些采购情形可以免于采购总监审批？",
             ["exhaustive", "pair"], "L4", ["PROC-001-v3"],
             ["PROC-001-v3#sec-6-1", "PROC-001-v3#sec-6-2", "PROC-001-v3#sec-6-3", "PROC-001-v3#app-c"],
             [claim("4 项免审批情形均免于逐单审批（含采购总监环节）", force="exhaustive_in_corpus")],
             "ANSWER", "同免审批 4 项情形",
             pair_of="PROC-001-v3#sec-4",
             signature=["exhaustive_scan"], failure=["COMPLETENESS_ERROR"],
             requirements=REQ("免采购总监审批情形", completeness="exhaustive")),
    ]
    return qs


def q_claim_force(w):
    qs = []
    qs += [
        mk_q("报销制度说员工“一般应”在 30 天内提交报销。员工在 35 天后提交，是否一定不被接受？",
             ["claim_force"], "L4", ["EXP-001-v2"], ["EXP-001-v2#sec-4-2"],
             [claim("不能得出“一定不被接受”：条款为“一般应”，且超期可说明理由提交", status="CANNOT_UPGRADE",
                    force="usually")],
             "UNKNOWN", "不能断定一定不被接受；“一般”不等于“必须”，超期可说明理由",
             must_not=["一定不被接受", "一定被接受"],
             signature=["claim_force_check"], failure=["OVERCLAIM"],
             warrant=W(support="PARTIAL"), requirements=REQ("超期报销后果", precision="approximate")),
        mk_q("市内交通费“每人每天上限 80 元”，80 元是定额还是上限？",
             ["claim_force", "numeric_precision"], "L2", ["EXP-001-v2"],
             ["EXP-001-v2#tbl-trans"],
             [claim("是上限（凭票实报实销，不超过 80 元）", force="upper_bound")],
             "ANSWER", "上限（实报实销，≤80 元/天）",
             must_not=["每天固定报销 80 元"],
             signature=["numeric_precision_check"], failure=["NUMERIC_ERROR"],
             requirements=REQ("交通费语义", precision="exact")),
        mk_q("餐费补贴“一线城市 110 元/天”，这是上限还是定额？",
             ["claim_force", "numeric_precision"], "L2", ["EXP-001-v2"],
             ["EXP-001-v2#tbl-meal"],
             [claim("是定额补贴标准（无需发票按天计发），非上限", force="exact")],
             "ANSWER", "定额补贴 110 元/天",
             must_not=["上限 110 元"],
             signature=["numeric_precision_check"], failure=["NUMERIC_ERROR"],
             requirements=REQ("餐补语义", precision="exact")),
        mk_q("客服 FAQ 说住宿“一般每晚上限 500 元”，能否据此断定所有员工所有城市都是恰好 500 元？",
             ["claim_force", "adversarial"], "L4", ["FAQ-001", "TRV-001-v3"],
             ["FAQ-001#sec-1", "TRV-001-v3#sec-2-1"],
             [claim("不能：口径为“一般”且为上限表述；实际标准随城市/角色/时间变化（400-800 元不等）",
                    status="CANNOT_UPGRADE")],
             "ANSWER", "不能断定；FAQ 为一般性口径，正式标准随城市、角色与时间变化",
             must_not=["是，所有情况都是恰好 500 元"],
             signature=["claim_force_check", "authority_check"], failure=["OVERCLAIM", "AUTHORITY_MISS"],
             requirements=REQ("FAQ口径强度", precision="approximate")),
        mk_q("S001 星辰物流“连续两个考核期延期率高于 5%”，能否断定其下一期延期率一定高于 5%？",
             ["claim_force"], "L5", ["SUP-EVAL-2026A"], ["SUP-EVAL-2026A#sec-1"],
             [claim("不能：历史数据不构成对未来周期的保证", status="CANNOT_UPGRADE")],
             "UNKNOWN", "不能断定",
             must_not=["一定高于 5%"],
             signature=["claim_force_check", "temporal_filter"], failure=["OVERCLAIM"],
             requirements=REQ("S001未来延期率")),
        mk_q("差旅费管理办法“未尽事宜由财务部解释”，能否据此断定财务部可以修改住宿标准？",
             ["claim_force"], "L5", ["EXP-001-v2", "TRV-001-v3"],
             ["EXP-001-v2#sec-5"],
             [claim("不能：解释权 ≠ 制度修订权；修订须按制度发布流程进行", status="CANNOT_UPGRADE")],
             "UNKNOWN", "不能断定财务部可修改标准",
             must_not=["财务部可以单方面修改住宿标准"],
             signature=["claim_force_check"], failure=["OVERCLAIM"],
             requirements=REQ("财务部解释权范围")),
    ]
    return qs


def q_numeric_unit(w):
    fin = w["finance_monthly"]
    bym = {(r["month"], r["region"]): r for r in fin}
    qs = []
    r6 = bym[("2026-06", "RG-SOUTH")]
    qs += [
        mk_q("2026年6月华南区收入是多少？",
             ["numeric_trap", "table"], "L4", ["FIN-RPT-202606", "TBL-FIN-MONTHLY"],
             ["FIN-RPT-202606#tbl-fin", "FIN-RPT-202606#fn-unit"],
             [claim(f"8,000,000 元（月报表内数字为 800，单位为万元；800 万元 = 8,000,000 元）")],
             "ANSWER", "8,000,000 元（800 万元）",
             must_not=["800 元", "800 万元（表述对但须说明单位）→ 不得答“800”"],
             dependencies=["table_header", "unit"],
             signature=["table_lookup", "unit_dependency"],
             failure=["NUMERIC_ERROR"], requirements=REQ("华南区2026-06收入", derivation=True),
             trace=dict(distractors=["表内“800”若不带单位会误读为 800 元"])),
        mk_q("欧洲区 2026年6月本地报表收入是多少欧元？",
             ["numeric_trap", "multi_hop"], "L4", ["FIN-EU-NOTE", "TBL-FIN-MONTHLY"],
             ["FIN-EU-NOTE#sec-1"],
             [claim("620,000 欧元（按 7.8 汇率折合人民币列报）")],
             "ANSWER", "620,000 欧元",
             must_not=["4,836,000 欧元（那是人民币数）"],
             signature=["currency_check", "table_lookup"], failure=["NUMERIC_ERROR"],
             requirements=REQ("欧洲区2026-06欧元收入", "欧洲", derivation=True)),
        mk_q("北美区普通员工住宿上限是 120 吗？单位是什么？",
             ["numeric_trap"], "L3", ["TRV-003"], ["TRV-003#sec-4"],
             [claim("120 美元/晚（USD），报销按月初汇率折算人民币")],
             "ANSWER", "120 美元/晚",
             must_not=["120 元人民币"],
             signature=["currency_check"], failure=["NUMERIC_ERROR"],
             requirements=REQ("北美住宿上限单位", "北美")),
        mk_q("订单明细表中的金额字段是含税还是不含税？含税金额如何换算？",
             ["numeric_trap"], "L3", ["FIN-SALES-NOTE"], ["FIN-SALES-NOTE#sec-1", "FIN-SALES-NOTE#sec-2"],
             [claim("不含税；含税金额 = 不含税金额 × 1.13")], "ANSWER", "不含税；×1.13",
             signature=["table_lookup", "unit_dependency"], failure=["NUMERIC_ERROR"],
             requirements=REQ("订单金额口径")),
        mk_q("星辰物流 2026 年运输报价是否包含运费？",
             ["numeric_trap"], "L3", ["NEG-001"], ["NEG-001#sec-2"],
             [claim("报价为含运费总价，燃油附加费另计")], "ANSWER", "含运费（燃油附加费另计）",
             signature=["direct_lookup"], failure=["NUMERIC_ERROR"],
             requirements=REQ("S001报价口径")),
        mk_q("2026年6月华东区毛利率是多少？（百分比，保留一位小数）",
             ["calculation", "derivation"], "L4", ["TBL-FIN-MONTHLY", "MET-001"],
             ["MET-001#def-gm", "TBL-FIN-MONTHLY"],
             [claim(f"{gross_margin(r6['revenue'], r6['cost']) * 100:.1f}%（收入 {fmt(r6['revenue'])}，"
                    f"成本 {fmt(r6['cost'])}）", force="approx")],
             "ANSWER", f"{gross_margin(r6['revenue'], r6['cost']) * 100:.1f}%",
             signature=["arithmetic", "definition_retrieval"], failure=["DERIVATION_ERROR"],
             requirements=REQ("华东区毛利率", derivation=True),
             trace=dict(why="答案不在任何文本中，必须 Evidence→Arithmetic→Claim")),
    ]
    # 12 个月度毛利率计算题
    cases = [("2026-01", "RG-SOUTH"), ("2026-02", "RG-EAST"), ("2026-03", "RG-NORTH"),
             ("2026-04", "RG-SOUTH"), ("2026-05", "RG-EU"), ("2026-06", "RG-NORTH"),
             ("2026-07", "RG-HK"), ("2026-08", "RG-SEA"), ("2025-12", "RG-SOUTH"),
             ("2025-11", "RG-EAST"), ("2026-03", "RG-EU"), ("2026-08", "RG-SOUTH"),
             ("2026-02", "RG-SOUTH"), ("2026-04", "RG-EAST"), ("2026-05", "RG-NORTH"),
             ("2026-06", "RG-EU"), ("2026-07", "RG-EAST"), ("2026-08", "RG-EU"),
             ("2026-01", "RG-EU"), ("2026-02", "RG-SEA"), ("2025-10", "RG-SOUTH"),
             ("2025-09", "RG-EAST"), ("2026-05", "RG-HK"), ("2026-07", "RG-NORTH")]
    rname = dict(REGIONS)  # RG-xxx -> 中文名
    for m, reg in cases:
        r = bym[(m, reg)]
        gm = gross_margin(r["revenue"], r["cost"]) * 100
        qs.append(mk_q(
            f"{m.replace('-', '年')}月{rname[reg]}的毛利率是多少？（保留一位小数）",
            ["calculation", "derivation", "table"], "L4", ["TBL-FIN-MONTHLY", "MET-001"],
            ["MET-001#def-gm", "TBL-FIN-MONTHLY"],
            [claim(f"{gm:.1f}%", force="approx")], "ANSWER", f"{gm:.1f}%",
            signature=["arithmetic", "definition_retrieval", "table_lookup"],
            failure=["DERIVATION_ERROR"],
            requirements=REQ(f"{rname[reg]}{m}毛利率", scope=rname[reg], effective_at=m,
                             derivation=True)))
    # 同比
    h1_26 = sum(r["revenue"] for r in fin if r["month"].startswith("2026-0") and r["month"] <= "2026-06")
    h1_25 = sum(r["revenue"] for r in fin if r["month"].startswith("2025-0") and r["month"] <= "2025-06")
    yoy = (h1_26 - h1_25) / h1_25 * 100
    qs.append(mk_q("2026年上半年集团总收入是多少？较2025年上半年同比增长百分之多少？（保留一位小数）",
                   ["calculation", "derivation", "aggregation"], "L5",
                   ["TBL-FIN-MONTHLY"], ["TBL-FIN-MONTHLY"],
                   [claim(f"2026H1 收入 {fmt(h1_26)} 元；同比 +{yoy:.1f}%", force="approx")],
                   "ANSWER", f"{fmt(h1_26)} 元，同比 +{yoy:.1f}%",
                   signature=["aggregation", "arithmetic"], failure=["DERIVATION_ERROR", "COMPLETENESS_ERROR"],
                   requirements=REQ("2026H1收入与同比", completeness="exhaustive", derivation=True)))
    # 预算执行率
    for d in w["dept_budget_2026"][:5]:
        rate = d["actual"] / d["budget"] * 100
        qs.append(mk_q(f"{d['department']}2026年预算执行率是多少？（保留一位小数）",
                       ["calculation", "derivation"], "L3", ["FIN-BUDGET-2026", "MET-001"],
                       ["FIN-BUDGET-2026#tbl-budget", "MET-001#def-budget"],
                       [claim(f"{rate:.1f}%（预算 {fmt(d['budget'])}，实际 {fmt(d['actual'])}）", force="approx")],
                       "ANSWER", f"{rate:.1f}%",
                       signature=["arithmetic", "definition_retrieval"], failure=["DERIVATION_ERROR"],
                       requirements=REQ(f"{d['department']}预算执行率", derivation=True)))
    return qs


def q_ranking_agg(w):
    qs = []
    bu = w["bu_margin_2026h1"]
    mgs = sorted(((b["bu"], (b["revenue"] - b["cost"]) / b["revenue"] * 100) for b in bu),
                 key=lambda x: -x[1])
    top3 = [mgs[0][0], mgs[1][0], mgs[2][0]]
    qs += [
        mk_q("2026年上半年毛利率最高的事业部是哪个？",
             ["ranking", "derivation"], "L4", ["FIN-BU-2026H1", "MET-001"],
             ["FIN-BU-2026H1#tbl-bu", "MET-001#def-gm"],
             [claim(f"{mgs[0][0]}（{mgs[0][1]:.1f}%）")], "ANSWER", mgs[0][0],
             signature=["aggregation", "sort"], failure=["DERIVATION_ERROR"],
             requirements=REQ("毛利率最高事业部", completeness="single", derivation=True)),
        mk_q("2026年上半年毛利率最高的前三个事业部是哪些？（需正确处理平手）",
             ["ranking", "derivation"], "L5", ["FIN-BU-2026H1", "MET-001"],
             ["FIN-BU-2026H1#tbl-bu", "MET-001#def-gm"],
             [claim(f"Top3：{top3[0]}（{mgs[0][1]:.1f}%）、{top3[1]}（{mgs[1][1]:.1f}%）、{top3[2]}（{mgs[2][1]:.1f}%）；"
                    f"SaaS BU 与物流 BU 并列 25.0%，Top3 必须同时包含二者")],
             "ANSWER", f"{top3[0]}、{top3[1]}、{top3[2]}（并列25.0%的两个都入选）",
             must_not=["只取一个 25% 的事业部", "顺序必须严格固定（并列项顺序任意）→ 不得因并列顺序不同判错"],
             signature=["aggregation", "sort", "tie_handling"], failure=["DERIVATION_ERROR"],
             requirements=REQ("Top3毛利率事业部", completeness="exhaustive", derivation=True),
             trace=dict(why="B=25% C=25% 平手 → 检验 tie 处理与排序稳定性")),
        mk_q("2026年全平台订单总金额（不含税）是多少？",
             ["aggregation", "structured"], "L5", ["TBL-ORDERS-2026"],
             ["TBL-ORDERS-2026", "FIN-SALES-NOTE#sec-1"],
             [claim(f"{fmt(sum(o['amount_excl_tax'] for o in w['orders'] if o['order_date'].startswith('2026')))} 元",
                    force="derived")],
             "ANSWER", "需对 orders_2026.csv 全量扫描求和（金额不含税）",
             signature=["structured_scan", "aggregation"], failure=["COMPLETENESS_ERROR", "NUMERIC_ERROR"],
             requirements=REQ("2026订单总额", completeness="exhaustive", derivation=True),
             note="RAG ≠ Everything：答案不存在于任何文档，必须结构化聚合"),
        mk_q("公司目前有多少名在职员工？",
             ["aggregation", "structured"], "L4", ["TBL-EMP-DIR"],
             ["TBL-EMP-DIR"],
             [claim(f"{sum(1 for e in w['employees'] if e['status'] == '在职')} 名（快照 2026-08-31）",
                    force="derived")],
             "ANSWER", "需对员工快照按 status=在职 计数",
             signature=["structured_scan", "aggregation"], failure=["COMPLETENESS_ERROR"],
             requirements=REQ("在职员工数", completeness="exhaustive", derivation=True)),
    ]
    # 平台退款率
    from collections import defaultdict
    plat = defaultdict(lambda: [0, 0])
    for o in w["orders"]:
        if o["order_date"].startswith("2026"):
            plat[o["platform"]][0] += 1
            if o["refund_amount"] > 0:
                plat[o["platform"]][1] += 1
    rates = {p: (c[1] / c[0]) for p, c in plat.items()}
    worst = max(rates, key=rates.get)
    qs += [
        mk_q("2026年哪个平台订单退款率最高？",
             ["ranking", "structured", "derivation"], "L5", ["TBL-ORDERS-2026"],
             ["TBL-ORDERS-2026"],
             [claim(f"{worst}（退款率 {rates[worst] * 100:.1f}%）", force="derived")],
             "ANSWER", worst,
             signature=["structured_scan", "aggregation", "sort"],
             failure=["DERIVATION_ERROR"], requirements=REQ("退款率最高平台", derivation=True)),
        mk_q("2026年天猫平台订单退款率是多少？（保留一位小数）",
             ["calculation", "structured"], "L4", ["TBL-ORDERS-2026"], ["TBL-ORDERS-2026"],
             [claim(f"{rates['天猫'] * 100:.1f}%", force="derived")], "ANSWER", f"{rates['天猫'] * 100:.1f}%",
             signature=["structured_scan", "arithmetic"], failure=["DERIVATION_ERROR"],
             requirements=REQ("天猫退款率", derivation=True)),
    ]
    # PO 单据
    for po, amt, dep in [("PR-2026-0218", 62000, "市场部"), ("PR-2026-0340", 158000, "信息技术部")]:
        qs.append(mk_q(f"采购申请单 {po} 的金额是多少？属于哪个部门？",
                       ["table", "structured"], "L2", ["TBL-PO"], ["TBL-PO"],
                       [claim(f"{fmt(amt)} 元（含税），{dep}")], "ANSWER", f"{fmt(amt)} 元（含税），{dep}",
                       signature=["table_lookup"], failure=["RETRIEVAL_MISS"],
                       requirements=REQ(f"{po}金额")))
    return qs


def q_hr_entity(w):
    qs = []
    emps = {e["employee_id"]: e for e in w["employees"]}
    # 实体解析：SKU
    prods = {p["internal_sku"]: p for p in w["products"]}
    qs += [
        mk_q("平台 SKU TM-88231 对应什么商品？属于什么品牌？",
             ["entity_resolution", "multi_hop"], "L3", ["TBL-SKU"],
             ["TBL-SKU", "SKU-REG#sec-1"],
             [claim("M10028 AeroBuds Pro X2，品牌：声科")], "ANSWER", "AeroBuds Pro X2（声科）",
             signature=["entity_resolution", "join"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("TM-88231对应商品"),
             trace=dict(why="PlatformSKU → InternalSKU → Product → Brand")),
        mk_q("旧编号 SK-10028 对应什么商品？",
             ["entity_resolution", "numeric_trap"], "L4", ["TBL-SKU", "SKU-REG"],
             ["TBL-SKU", "SKU-REG#sec-1"],
             [claim("M10001 NebulaPhone 12（旧编号易与 M10028 混淆，实际对应 M10001）")],
             "ANSWER", "NebulaPhone 12（M10001）",
             must_not=["AeroBuds Pro X2（M10028）"],
             signature=["entity_resolution"], failure=["NUMERIC_ERROR", "RETRIEVAL_MISS"],
             requirements=REQ("SK-10028对应商品"),
             trace=dict(distractors=["M10028 数字相近"])),
        mk_q("M10028S 和 M10028 是同一款商品吗？",
             ["entity_resolution"], "L3", ["SKU-REG"], ["SKU-REG#sec-near"],
             [claim("不是。M10028S 是 X2S 升级换代款，与 M10028（X2）为不同商品")],
             "ANSWER", "不是，两者为不同商品",
             must_not=["是同一款"],
             signature=["entity_resolution"], failure=["NUMERIC_ERROR"],
             requirements=REQ("M10028S与M10028关系")),
        mk_q("组合装 B2001 包含哪些商品？",
             ["entity_resolution"], "L3", ["SKU-REG"], ["SKU-REG#sec-bundle"],
             [claim("M10028（AeroBuds Pro X2）+ M10029（AeroBuds 充电盒）")],
             "ANSWER", "M10028 + M10029",
             signature=["entity_resolution"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("B2001构成")),
        mk_q("M10036 是什么类型的商品？可以无理由退款吗？",
             ["entity_resolution", "multi_hop"], "L4", ["TBL-SKU", "RMA-001"],
             ["TBL-SKU", "RMA-001#sec-3-1"],
             [claim("电子书（数字商品）；数字商品不支持无理由退款，质量问题除外")],
             "ANSWER", "数字商品，不支持无理由退款（质量问题除外）",
             must_not=["可以 30 天无理由退款"],
             signature=["entity_resolution", "exception_override"], failure=["EXCEPTION_MISS"],
             requirements=REQ("M10036退款政策")),
    ]
    # HR 事实
    hr_cases = ["E037", "E015", "E023", "E052", "E010", "E060", "E061", "E044", "E001",
                "E008", "E020", "E013", "E002", "E003", "E004", "E005", "E006", "E007",
                "E009", "E011", "E014", "E058", "E022", "E046"]
    for eid in hr_cases:
        e = emps[eid]
        status_txt = "" if e["status"] == "在职" else "（已于 2026-03-31 离职）"
        qs.append(mk_q(
            f"{e['name']}（{eid}）属于哪个部门、哪个区域？目前是否在职？",
            ["single_doc", "hr"], "L1", ["TBL-EMP-DIR", "ORG-002"],
            ["TBL-EMP-DIR"],
            [claim(f"{e['department']}，{REGIONS[e['region']]}，{e['status']}{status_txt}")],
            "ANSWER", f"{e['department']}／{REGIONS[e['region']]}／{e['status']}",
            signature=["entity_resolution"], failure=["RETRIEVAL_MISS"],
            requirements=REQ(f"{eid}组织信息")))
    qs += [
        mk_q("林晓芳（E012）2026年8月属于哪个部门？",
             ["temporal", "structured_vs_doc"], "L4", ["ORG-002", "TBL-EMP-DIR"],
             ["ORG-002#sec-3-1", "TBL-EMP-DIR"],
             [claim("运营部（2026-06-01 调岗；2025 年度组织手册中的“财务部”为历史快照）", eff="2026-08")],
             "ANSWER", "运营部",
             must_not=["财务部（2025 组织手册为过时快照）"],
             signature=["temporal_filter", "authority_check", "entity_resolution"],
             failure=["TEMPORAL_LEAK", "CONFLICT_IGNORE"],
             requirements=REQ("E012当前部门", "中国大陆", "2026-08"),
             trace=dict(chosen="ORG-002#sec-3-1（2026-06-05 公告）",
                        superseded=["ORG-001（2025 快照）"], why="异动公告时间更新")),
        mk_q("林晓芳（E012）2026年3月属于哪个部门？",
             ["temporal", "structured_vs_doc"], "L4", ["ORG-001"],
             ["ORG-001#tbl-org"],
             [claim("财务部（调岗发生于 2026-06-01）", eff="2026-03")], "ANSWER", "财务部",
             must_not=["运营部"],
             signature=["temporal_filter"], failure=["TEMPORAL_LEAK"],
             requirements=REQ("E012部门", "中国大陆", "2026-03")),
        mk_q("张伟（E037）是否属于财务部？",
             ["negative", "hr"], "L1", ["TBL-EMP-DIR"], ["TBL-EMP-DIR"],
             [claim("否，属于销售部（华南区）", status="REFUTED")], "ANSWER", "否，销售部",
             signature=["entity_resolution"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("E037部门")),
        mk_q("采购部负责人是谁？",
             ["hr", "hierarchy"], "L1", ["ORG-002"], ["ORG-002#sec-2"],
             [claim("赵国强（E002）")], "ANSWER", "赵国强（E002）",
             signature=["direct_lookup"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("采购部负责人")),
        mk_q("艾米丽（E060）能享受补充商业医疗保险吗？",
             ["multi_hop", "hr"], "L4", ["TBL-EMP-DIR", "BEN-001"],
             ["TBL-EMP-DIR", "BEN-001#sec-2-1"],
             [claim("不能。E060 为外包人员，补充医保仅适用于正式员工")], "ANSWER", "不能（外包人员）",
             signature=["entity_resolution", "scope_filter"], failure=["SCOPE_LEAK"],
             requirements=REQ("E060补充医保")),
        mk_q("韩梅（E061，试用期实习生）年假按什么标准执行？",
             ["multi_hop", "hr"], "L4", ["TBL-EMP-DIR", "BEN-001"],
             ["TBL-EMP-DIR", "BEN-001#sec-1-2"],
             [claim("试用期员工年假按当年度剩余月份比例折算（不适用全额标准）")],
             "ANSWER", "按剩余月份比例折算",
             signature=["entity_resolution", "exception_override"], failure=["EXCEPTION_MISS"],
             requirements=REQ("E061年假标准")),
        mk_q("E037 参与的项目所在区域的预算执行率是多少？（保留一位小数）",
             ["multi_hop", "derivation"], "L6", ["PRD-002", "MTG-002"],
             ["PRD-002#sec-1", "MTG-002#sec-1"],
             [claim("78.0%（E037 → 华东仓自动化项目（华东区）→ 预算 1,200 万，实际 936 万）",
                    force="derived")],
             "ANSWER", "78.0%",
             signature=["entity_resolution", "multi_hop", "arithmetic"],
             failure=["RETRIEVAL_MISS", "DERIVATION_ERROR"],
             requirements=REQ("项目区域预算执行率", derivation=True),
             trace=dict(why="Employee→Project→Region→Budget→Execution 五跳")),
        mk_q("华南区负责人是谁？其区域总经理岗位属于哪个部门？",
             ["hr", "hierarchy"], "L2", ["ORG-002", "TBL-EMP-DIR"],
             ["TBL-EMP-DIR"],
             [claim("罗志成（E010），销售部，M4")], "ANSWER", "罗志成（E010），销售部",
             signature=["entity_resolution"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("华南区负责人")),
        mk_q("公司组织层级中，广州位于哪个节点之下？",
             ["hierarchy"], "L1", ["ORG-002"], ["ORG-002#sec-1"],
             [claim("集团 → 中国区 → 华南区 → 广州")], "ANSWER", "中国区 → 华南区 → 广州",
             signature=["hierarchy_traversal"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("广州组织层级")),
    ]
    return qs


def q_supplier_join(w):
    sups = {s["supplier_id"]: s for s in w["suppliers"]}
    qs = []
    qs += [
        mk_q("S001 星辰物流为什么需要额外合规审批才能下单？",
             ["multi_hop", "conflict_resolution"], "L5",
             ["SUP-EVAL-2026A", "PROC-001-v3", "TBL-SUPPLIER"],
             ["PROC-001-v3#sec-5-4", "SUP-EVAL-2026A#tbl-eval", "SUP-EVAL-2026A#sec-1"],
             [claim("S001 评级为 A 且近半年交付延期率 8%（>5%），触发《采购管理办法》第 5.4 条的额外合规审批要求")],
             "ANSWER", "评级 A + 延期率 8% > 5% → 触发 5.4 条额外合规审批",
             must_not=["因为评级低", "因为付款条件"],
             warrant=W(coverage="PASS"),
             signature=["entity_resolution", "multi_hop", "condition_matching"],
             failure=["RETRIEVAL_MISS", "EXCEPTION_MISS"],
             requirements=REQ("S001额外审批原因", derivation=True),
             trace=dict(chosen="PROC-001-v3#sec-5-4 + SUP-EVAL-2026A",
                        why="Supplier+Quality+Policy 三源 Join",
                        distractors=["S003/S004 案例（评级或延期率不满足）"])),
        mk_q("向 S004 蓝海包装下单是否触发额外合规审批？",
             ["multi_hop"], "L5", ["PROC-001-v3", "SUP-EVAL-2026A"],
             ["PROC-001-v3#sec-5-4", "SUP-EVAL-2026A#tbl-eval", "RISK-001#sec-1"],
             [claim("不触发该条款：该条款仅适用于评级 A 供应商，S004 评级为 C（但被列入观察名单，风险报告建议降级/替换）")],
             "ANSWER", "否（评级 C 不满足触发条件）；但被列入观察名单",
             must_not=["是，因为延期率 12% > 5%（忽略了评级 A 前提）"],
             signature=["multi_hop", "condition_matching"], failure=["SCOPE_LEAK", "EXCEPTION_MISS"],
             requirements=REQ("S004审批要求")),
        mk_q("S001 的付款条件是什么？其 2026 年运输报价如何计费？",
             ["multi_hop", "structured_join"], "L3", ["TBL-SUPPLIER", "NEG-001"],
             ["TBL-SUPPLIER", "NEG-001#sec-1", "NEG-001#sec-2"],
             [claim("付款条件：验收后 60 天；报价为含运费总价，燃油附加费另计")],
             "ANSWER", "60 天；含运费总价（燃油附加费另计）",
             signature=["structured_join"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("S001付款与报价条件")),
        mk_q("S003 恒远电子的合同期到什么时候？交付延期率是多少？",
             ["structured_join"], "L2", ["TBL-SUPPLIER", "SUP-EVAL-2026A"],
             ["TBL-SUPPLIER", "SUP-EVAL-2026A#tbl-eval"],
             [claim("合同期至 2027-09-30；延期率 3%")], "ANSWER", "2027-09-30；3%",
             signature=["structured_join"], failure=["RETRIEVAL_MISS"],
             requirements=REQ("S003合同与履约")),
        mk_q("PR-2026-0218 是否违反了采购审批规定？为什么？",
             ["multi_hop", "audit", "derivation"], "L6",
             ["TBL-PO", "AUD-001", "PROC-001-v3", "TBL-TAX"],
             ["AUD-001#case1", "PROC-001-v3#sec-4-1", "AUD-001#fn-tax", "TBL-TAX"],
             [claim("是。62,000 元为含税价，不含税 = 62,000 ÷ 1.13 ≈ 54,867 元 > 50,000 元，"
                    "按 v3 制度（2026-01-01 起生效，事件发生于 2026-02-10）须经采购总监审批而未获审批",
                    force="derived")],
             "ANSWER", "是，违反审批规定（不含税约 54,867 元 > 50,000 元且未审批）",
             must_not=["不违规（直接用含税 62,000 对比会更高但单位口径错；用 48,000 案例会得出相反结论）"],
             warrant=W(temporal="PASS", coverage="PASS"),
             signature=["multi_hop", "numeric_trap", "temporal_filter", "arithmetic"],
             failure=["NUMERIC_ERROR", "TEMPORAL_LEAK", "DERIVATION_ERROR"],
             requirements=REQ("PR-2026-0218合规性", effective_at="2026-02-10", derivation=True),
             trace=dict(why="PDF(审计)+CSV(PO)+Policy+税率表 四源；含税/不含税陷阱")),
        mk_q("PR-2026-0231（48,000 元含税）是否需要采购总监审批？是否违规？",
             ["multi_hop", "derivation"], "L5", ["TBL-PO", "AUD-001", "PROC-001-v3", "TBL-TAX"],
             ["AUD-001#case2", "PROC-001-v3#sec-4-1", "AUD-001#fn-tax"],
             [claim("不含税 = 48,000 ÷ 1.13 ≈ 42,478 元 < 50,000 元，本不需要采购总监审批；"
                    "已审批不属于违规（超配置审批不构成违规）", force="derived")],
             "ANSWER", "不需要审批；已审批不构成违规",
             must_not=["违规（必须与 62,000 案例同判）"],
             signature=["multi_hop", "numeric_trap", "arithmetic"], failure=["NUMERIC_ERROR"],
             requirements=REQ("PR-2026-0231合规性", effective_at="2026-02-05", derivation=True)),
    ]
    return qs


def q_supplier_facts(w):
    """长尾供应商单事实题（近邻实体与冷门字段覆盖）。"""
    qs = []
    sups = {s["supplier_id"]: s for s in w["suppliers"]}
    for sid in ["S001", "S001C", "S002", "S003", "S004", "S005", "S006", "S007",
                "S008", "S009", "S017", "S020", "S024", "S028"]:
        s = sups[sid]
        qs.append(mk_q(
            f"供应商 {s['supplier_name']}（{sid}）的评级、付款条件和交付周期分别是多少？",
            ["single_doc", "structured_join"], "L1", ["TBL-SUPPLIER"], ["TBL-SUPPLIER"],
            [claim(f"评级 {s['rating']}；付款条件 {s['payment_terms']}；交付周期 "
                   f"{s['lead_time_days']} 天")],
            "ANSWER", f"{s['rating']}／{s['payment_terms']}／{s['lead_time_days']}天",
            signature=["entity_resolution", "table_lookup"], failure=["RETRIEVAL_MISS"],
            requirements=REQ(f"{sid}主数据"),
            trace=dict(distractors=["名称近邻供应商（如 S001 vs S001C、S008 vs S009）"])))
    return qs


def q_table_cell(w):
    """Sibling Structure：同构表格的不同列/行必须区分（附件CSV）。"""
    qs = []
    limit_map = {  # 来自 attachments/city_hotel_standard_2026.csv
        "一线": (400, 450, 500), "二线": (300, 350, 400), "其他": (250, 280, 320)}
    tier_of = {}
    for c in ["北京", "上海", "广州", "深圳"]:
        tier_of[c] = "一线"
    for c in ["杭州", "成都", "武汉", "南京", "西安", "苏州"]:
        tier_of[c] = "二线"
    for c in ["佛山", "东莞", "合肥", "郑州", "长沙"]:
        tier_of[c] = "其他"
    col_cases = [("limit_2025H1", "2025年上半年", 0), ("limit_2025H2", "2025年下半年", 1),
                 ("limit_2026", "2026年", 2)]
    all_cities = (["北京", "上海", "广州", "深圳"] + ["杭州", "成都", "武汉", "南京", "西安", "苏州"]
                  + ["佛山", "东莞", "合肥", "郑州", "长沙"])
    for col, label, idx in col_cases:
        for city in all_cities:
            amt = limit_map[tier_of[city]][idx]
            qs.append(mk_q(
                f"附件《城市住宿标准汇总表》中，{city}在{label}列的标准是多少？",
                ["table", "sibling_structure"], "L2",
                ["ATT-CITY-STD"], ["ATT-CITY-STD"],
                [claim(f"{amt} 元/晚（{tier_of[city]}城市 {col} 列）")],
                "ANSWER", f"{amt} 元/晚",
                must_not=["相邻列的数值（列选择错误）"],
                signature=["table_lookup", "column_disambiguation"],
                failure=["NUMERIC_ERROR", "RETRIEVAL_MISS"],
                requirements=REQ(f"{city}{label}标准"),
                trace=dict(why="同构表 3 个数值列，检验列选择")))
    return qs


def q_platform_stats(w):
    """平台维度结构化统计（RAG ≠ Everything）。"""
    from collections import defaultdict
    gmv = defaultdict(float)
    cnt = defaultdict(lambda: [0, 0])
    for o in w["orders"]:
        if o["order_date"].startswith("2026"):
            gmv[o["platform"]] += o["amount_excl_tax"]
            cnt[o["platform"]][0] += 1
            if o["refund_amount"] > 0:
                cnt[o["platform"]][1] += 1
    qs = []
    for plat in ["天猫", "京东", "抖音", "Shopify", "Shopee"]:
        qs.append(mk_q(
            f"2026年{plat}平台订单总金额（不含税）是多少？",
            ["aggregation", "structured"], "L4", ["TBL-ORDERS-2026"], ["TBL-ORDERS-2026"],
            [claim(f"{fmt(round(gmv[plat]))} 元", force="derived")],
            "ANSWER", f"{fmt(round(gmv[plat]))} 元",
            signature=["structured_scan", "aggregation"], failure=["COMPLETENESS_ERROR", "NUMERIC_ERROR"],
            requirements=REQ(f"{plat}2026订单总额", completeness="exhaustive", derivation=True)))
    for plat in ["京东", "Shopify", "Shopee", "天猫"]:
        rate = cnt[plat][1] / cnt[plat][0] * 100
        qs.append(mk_q(
            f"2026年{plat}平台订单退款率是多少？（保留一位小数）",
            ["calculation", "structured"], "L4", ["TBL-ORDERS-2026"], ["TBL-ORDERS-2026"],
            [claim(f"{rate:.1f}%", force="derived")], "ANSWER", f"{rate:.1f}%",
            signature=["structured_scan", "arithmetic"], failure=["DERIVATION_ERROR"],
            requirements=REQ(f"{plat}退款率", derivation=True)))
    return qs


def q_contrastive(w):
    """对比式问题族：只改动一个维度（role / region / time），检验 Scope 理解。"""
    qs = []
    base_city, base_date = "上海", "2026-08-15"
    dims = [
        # (question, expected, refs, claims_txt, must_not, sig)
        (f"{base_city}普通员工 {base_date[:7].replace('-', '年')}月住宿上限是多少？",
         "650 元/晚（特殊城市）", ["TRV-001-CN1#sec-1", "TRV-001-v3#sec-2-2"],
         "650 元/晚", ["500 元"], "scope_city"),
        ("北京普通员工 2026年8月住宿上限是多少？",
         "500 元/晚", ["TRV-001-v3#tbl-a"], "500 元/晚", ["650 元"], "scope_city"),
        ("上海 VP 2026年8月住宿上限是多少？",
         "800 元/晚（高管标准）", ["TRV-002-v2#tbl-b", "TRV-001-v3#sec-2-3"],
         "800 元/晚", ["650 元", "500 元"], "scope_role"),
        ("上海普通员工 2025年8月住宿上限是多少？",
         "450 元/晚（v2 版本）", ["TRV-001-v2#tbl-a"], "450 元/晚", ["500 元", "650 元"], "scope_time"),
        ("欧洲区普通员工 2026年8月住宿上限是多少？",
         "800 元/晚（或 100 欧元）", ["TRV-003#sec-2"], "800 元/晚", ["500 元", "650 元"], "scope_region"),
        ("上海 M3 级管理人员 2026年8月住宿上限是多少？",
         "650 × 1.3 = 845 元/晚（可上浮 30%）", ["TRV-001-v3#sec-2-3", "TRV-001-CN1#sec-1"],
         "845 元/晚", ["650 元"], "scope_role"),
        ("上海普通员工 2026年6月住宿上限是多少？",
         "500 元/晚（特殊城市标准 7 月才生效）", ["TRV-001-v3#tbl-a"],
         "500 元/晚", ["650 元"], "scope_time"),
        ("广交会期间（2026-04-20）上海普通员工住宿上限是多少？",
         "600 元/晚（500 × 1.2）", ["TRV-001-v3#fn-2", "TRV-001-v3#tbl-a"],
         "600 元/晚", ["500 元", "650 元"], "scope_exception"),
    ]
    for (q, acc, refs, cl, mn, tag) in dims:
        qs.append(mk_q(
            q, ["scope", "contrastive"], "L5", ["TRV-001-v3"], refs,
            [claim(cl)], "ANSWER", acc, must_not=mn,
            signature=["scope_filter", "contrastive_dimension", tag],
            failure=["SCOPE_LEAK", "TEMPORAL_LEAK"],
            requirements=REQ("单维度对比", completeness="single"),
            trace=dict(why="对比式问题族：与族内其他题仅一个维度不同，" + tag)))
    return qs
