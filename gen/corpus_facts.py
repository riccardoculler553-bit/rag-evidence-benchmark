# -*- coding: utf-8 -*-
"""政策/业务规则事实层 —— 文档文本与 Gold 答案共同从这里的常量推导，
保证“文档说什么”与“Gold 是什么”永不脱节。"""
import bisect

# ------------------------------------------------------- 差旅 TRV-001
TRV_VERSIONS = [
    dict(doc_id="TRV-001-v1", ver="v1", published="2024-12-15", eff_from="2025-01-01",
         eff_to="2025-06-30", tier1=400, tier2=300, other=250, status="superseded",
         spring_surcharge=False),
    dict(doc_id="TRV-001-v2", ver="v2", published="2025-06-10", eff_from="2025-07-01",
         eff_to="2025-12-31", tier1=450, tier2=350, other=280, status="superseded",
         spring_surcharge=True),
    dict(doc_id="TRV-001-v3", ver="v3", published="2026-05-20", eff_from="2026-01-01",
         eff_to=None, tier1=500, tier2=400, other=320, status="current",
         spring_surcharge=True),
]
TIER1_CITIES = ["北京", "上海", "广州", "深圳"]
TIER2_CITIES = ["杭州", "成都", "武汉", "南京", "西安", "苏州"]
TRV_SPECIAL_CITY = {"上海": {"since": "2026-07-01", "amount": 650,
                             "doc_id": "TRV-001-CN1", "published": "2026-06-05"}}
TRV_SURCHARGE = 0.20                 # 春节/展会期间上浮 20%，四舍五入到十元
TRV_EXPO_WINDOW = ("2026-04-15", "2026-05-05")   # 广交会（附录B）
TRV_SPRING_WINDOW = ("2026-02-15", "2026-02-21")  # 2026 春节假期
TRV_ADVANCE_DAYS = 3                 # 需提前 3 个工作日申请
TRV_FLOAT_LIMIT = 0.10               # 区域上浮授权上限 10%，须合规备案
TRV_CLIENT_HOTEL_OVERFLOW = 0.30     # 客户指定酒店：超出部分 ≤30% 可审批报销
TRV_VENDOR_TRIP_DISCOUNT = 0.20      # 供应商陪同出差：标准下调 20%


def trv_tier(city):
    if city in TIER1_CITIES:
        return "tier1"
    if city in TIER2_CITIES:
        return "tier2"
    return "other"


def trv_hotel(city, date):
    """返回指定日期某城市的普通员工住宿上限（元/晚）。"""
    tier = trv_tier(city)
    v = None
    for ver in TRV_VERSIONS:
        if ver["eff_from"] <= date and (ver["eff_to"] is None or date <= ver["eff_to"]):
            v = ver
    if v is None:
        return None
    amt = v[tier]
    refs = [f'{v["doc_id"]}#app-a'] if city else []
    refs = [f'{v["doc_id"]}#tbl-a']
    special_note = None
    if city in TRV_SPECIAL_CITY and date >= TRV_SPECIAL_CITY[city]["since"]:
        amt = TRV_SPECIAL_CITY[city]["amount"]
        refs.append(f'{TRV_SPECIAL_CITY[city]["doc_id"]}#sec-1')
        special_note = "特殊城市标准（2026-07-01起）"
    return dict(amount=amt, version=v["doc_id"], refs=refs,
                special=special_note, tier=tier, status=v["status"],
                published=v["published"], eff_from=v["eff_from"], eff_to=v["eff_to"])


def surcharge_amount(base):
    return int(round(base * (1 + TRV_SURCHARGE) / 10.0) * 10)


# 高管（M4 及以上）住宿标准 TRV-002
TRV_EXEC_VERSIONS = [
    dict(doc_id="TRV-002-v1", published="2024-12-15", eff_from="2025-01-01",
         eff_to="2025-06-30", tier1=700, tier2=550, status="superseded"),
    dict(doc_id="TRV-002-v2", published="2025-06-10", eff_from="2025-07-01",
         eff_to=None, tier1=800, tier2=650, status="current"),
]


def trv_exec_hotel(city, date):
    tier = trv_tier(city)
    v = None
    for ver in TRV_EXEC_VERSIONS:
        if ver["eff_from"] <= date and (ver["eff_to"] is None or date <= ver["eff_to"]):
            v = ver
    return dict(amount=v[tier], version=v["doc_id"], tier=tier, refs=[f'{v["doc_id"]}#tbl-b'],
                status=v["status"])


# 海外差旅 TRV-003（中国香港/海外不适用 TRV-001）
TRV_OVERSEAS = {
    "RG-EU": dict(amount=800, currency="CNY", foreign=("EUR", 100), refs=["TRV-003#sec-2"]),
    "RG-SEA": dict(amount=450, currency="CNY", foreign=None, refs=["TRV-003#sec-3"]),
    "RG-NA": dict(amount=None, currency="USD", foreign=("USD", 120), refs=["TRV-003#sec-4"]),
    "RG-HK": dict(amount=700, currency="CNY", foreign=None, refs=["TRV-003#sec-5"]),
}
TRV_OVERSEAS_EXEC_UPLIFT = 0.50      # VP 及以上上浮 50%

# ------------------------------------------------------- 报销 EXP-001
EXP_VERSIONS = [
    dict(doc_id="EXP-001-v1", published="2024-12-20", eff_from="2025-01-01", eff_to="2025-12-31",
         meal_t1=100, meal_t2=80, transport=80, status="superseded"),
    dict(doc_id="EXP-001-v2", published="2025-12-20", eff_from="2026-01-01", eff_to=None,
         meal_t1=110, meal_t2=80, transport=80, status="current",
         expo_meal=150, overtime_meal=30),
]
EXP_INVOICE_THRESHOLD = 5000         # 单笔≥5000 需附合同复印件
EXP_SUBMIT_DAYS = 30                 # “一般应”30天内提交
EXP_EXPO_WINDOW = TRV_EXPO_WINDOW

# ------------------------------------------------------- 采购 PROC-001
PROC_VERSIONS = [
    dict(doc_id="PROC-001-v2", published="2024-12-10", eff_from="2025-01-01", eff_to="2025-12-31",
         approval_1=50_000, approval_2=200_000, status="superseded"),
    dict(doc_id="PROC-001-v3", published="2025-12-15", eff_from="2026-01-01", eff_to=None,
         approval_1=50_000, approval_2=200_000, status="current"),
]
TAX_RATE = 0.13                      # 增值税率（销售口径说明）
PROC_DELAY_RATE_THRESHOLD = 5        # 评级A且延期率>5% 需额外合规审批
PROC_EXEMPT_ITEMS = [                # 免审批情形：3 项在正文，第 4 项只在附录C
    dict(item="单笔金额低于5,000元且当月累计低于20,000元的零星采购", ref="PROC-001-v3#sec-6-1"),
    dict(item="框架协议内已定价商品的按单执行", ref="PROC-001-v3#sec-6-2"),
    dict(item="生产紧急备件采购（须在48小时内补审批）", ref="PROC-001-v3#sec-6-3"),
    dict(item="年度集中采购目录内的标准办公用品", ref="PROC-001-v3#app-c"),
]
NDA_EXEMPT = dict(sensitivity="低敏级", amount_lt=10_000, ref="PROC-001-v2#app-ndaa",
                  legal_ref="LEG-001#sec-2")

# ------------------------------------------------------- 售后退款 RMA-001
RMA_ORDINARY_DAYS = 30
RMA_VIP_DAYS = 90
RMA_VIP_SPEND = 50_000
RMA_ARRIVAL_DAYS = "3-5 个工作日"
RMA_SPECIAL_PAY_DAYS = "7 个工作日"
RMA_DIGITAL_EXCEPT_QUALITY = True

# ------------------------------------------------------- 权限 SEC-001
ACL_LEVELS = {"public": 0, "internal": 1, "confidential": 2, "secret": 3}
ROLE_CLEARANCE = {"employee": 1, "finance": 2, "admin": 3}
PERM_EVENTS = [
    dict(employee_id="E023", role="finance", action="grant", date="2026-01-05",
         scope="finance_confidential"),
    dict(employee_id="E023", role="finance", action="revoke", date="2026-07-01",
         scope="finance_confidential"),
]

# ------------------------------------------------------- 合同 CT-001
CT_VERSIONS = [
    dict(doc_id="CT-001", ver="主合同v1", signed="2025-10-01", eff_from="2025-10-01",
         payment_days=30, price_note="含税单价", status="superseded(付款条款)"),
    dict(doc_id="CT-001-S1", ver="补充协议v2", published="2026-02-10", eff_from="2026-03-01",
         payment_days=60, status="current(付款条款)"),
    dict(doc_id="CT-001-N1", ver="变更通知v3", published="2026-05-20", eff_from="2026-06-01",
         price_change="+3%", payment_days=60, status="current(价格条款)"),
]


def ct_payment_days(date):
    if date >= "2026-03-01":
        return 60, "CT-001-S1#sec-1"
    return 30, "CT-001#sec-3"


# ------------------------------------------------------- 项目 PRJ-001
PRJ_DECISION = dict(
    chosen="方案B", date="2026-02-01", ref="DEC-001#sec-2",
    reasons=[
        dict(factor="方案B外购总成本320万元，显著低于方案A自研的480万元", refs=["SOL-001#tbl-1", "MTG-001#sec-2"]),
        dict(factor="方案B交付周期4个月，短于方案A的9个月，可赶上旺季", refs=["SOL-001#tbl-1"]),
        dict(factor="2026-01-15会议：集团要求2026年IT预算整体压缩，优先控本", refs=["MTG-001#sec-2"]),
    ],
    note="决策记录未声明预算因素为唯一根因",
)

# ------------------------------------------------------- 财务
FIN_SPECIAL = dict()  # 见 world.build_finance_monthly 的 800 万固定值
TAX_RATE_NOTE_REF = "FIN-SALES-NOTE#sec-1"


def gross_margin(revenue, cost):
    return (revenue - cost) / revenue


def yoy(cur, prev):
    return (cur - prev) / prev
