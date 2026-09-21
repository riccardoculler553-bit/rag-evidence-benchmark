# -*- coding: utf-8 -*-
"""星环科技集团 (NebulaCore Holdings) 世界模型。
所有实体与结构化数据的唯一真值来源（Single Source of Truth）。
文档、问题、Gold 一律引用本模块产出的实体，禁止凭空编造。
"""
import random

random.seed(20260919)

GROUP_CN = "星环科技集团"
GROUP_EN = "NebulaCore Holdings"

REGIONS = {
    "RG-GROUP": "集团总部",
    "RG-CN": "中国大陆",
    "RG-SOUTH": "华南区",
    "RG-EAST": "华东区",
    "RG-NORTH": "华北区",
    "RG-HK": "中国香港",
    "RG-SEA": "东南亚",
    "RG-EU": "欧洲",
    "RG-NA": "北美",
}

REGION_TREE = {
    "集团": ["中国区", "欧洲区", "北美区", "东南亚区", "中国香港区"],
    "中国区": ["华南区", "华东区", "华北区"],
    "华南区": ["广州", "深圳"],
    "华东区": ["上海", "杭州"],
    "华北区": ["北京"],
}

TIER1_CITIES = ["北京", "上海", "广州", "深圳"]
TIER2_CITIES = ["杭州", "成都", "武汉", "南京", "西安", "苏州"]
OTHER_CITIES = ["佛山", "东莞", "合肥", "郑州", "长沙"]

DEPARTMENTS = ["财务部", "采购部", "人力资源部", "法务部", "销售部",
               "运营部", "客服部", "信息技术部", "合规部"]

DEPT_HEADS = {
    "财务部": "E001", "采购部": "E002", "人力资源部": "E003", "法务部": "E004",
    "销售部": "E005", "运营部": "E006", "客服部": "E007", "信息技术部": "E008",
    "合规部": "E009",
}

REGION_HEADS = {"RG-SOUTH": "E010", "RG-EAST": "E011", "RG-EU": "E013", "RG-NA": "E014"}

ROLE_GRADE = {
    "普通员工": ["P1", "P2", "P3", "P4", "P5"],
    "管理人员": ["M1", "M2", "M3", "M4", "M5"],
    "财务人员": ["P3", "P4", "P5"],
    "采购人员": ["P3", "P4"],
    "区域负责人": ["M4", "M5"],
    "外包人员": ["P1", "P2"],
    "实习生": ["I1"],
}

SURNAME = list("陈林黄张吴李王刘杨赵周徐孙马朱胡郭何高罗郑梁谢宋唐许韩冯邓曹彭")
GIVEN = ["明远", "晓芳", "国强", "丽华", "俊杰", "雅琴", "志强", "海燕", "文博", "静怡",
         "嘉豪", "淑芬", "建国", "雪梅", "浩然", "玉兰", "天宇", "春兰", "子轩", "慧敏",
         "志远", "丽娜", "伟东", "桂英", "鑫磊", "秀兰", "俊杰", "玉梅", "勇军", "红梅",
         "德海", "银花", "志刚", "桂花", "立新", "凤英", "永强", "秀英", "建军", "玉华"]

REGION_OFFICE = {
    "RG-GROUP": "上海", "RG-CN": "上海", "RG-SOUTH": "广州", "RG-EAST": "上海",
    "RG-NORTH": "北京", "RG-HK": "香港", "RG-SEA": "新加坡", "RG-EU": "柏林",
    "RG-NA": "纽约",
}

# ---------------------------------------------------------------- employees
_SPECIAL_EMPLOYEES = [
    # id, name, dept, region, role, grade, type, join, status, manager, note
    ("E001", "陈明远", "财务部", "RG-CN", "管理人员", "M5", "正式", "2016-03-01", "在职", None, "集团CFO"),
    ("E002", "赵国强", "采购部", "RG-CN", "管理人员", "M4", "正式", "2017-06-12", "在职", None, "采购总监"),
    ("E003", "孙丽华", "人力资源部", "RG-CN", "管理人员", "M4", "正式", "2018-01-15", "在职", None, "HR总监"),
    ("E004", "周正", "法务部", "RG-CN", "管理人员", "M4", "正式", "2017-09-01", "在职", None, "法务总监"),
    ("E005", "马俊", "销售部", "RG-CN", "管理人员", "M5", "正式", "2015-05-20", "在职", None, "销售VP"),
    ("E006", "吴敏", "运营部", "RG-CN", "管理人员", "M4", "正式", "2018-04-02", "在职", None, "运营总监"),
    ("E007", "郑洁", "客服部", "RG-CN", "管理人员", "M3", "正式", "2019-02-11", "在职", None, "客服负责人"),
    ("E008", "冯军", "信息技术部", "RG-CN", "管理人员", "M5", "正式", "2016-08-15", "在职", None, "CTO"),
    ("E009", "许静", "合规部", "RG-CN", "管理人员", "M4", "正式", "2019-06-03", "在职", None, "合规总监"),
    ("E010", "罗志成", "销售部", "RG-SOUTH", "区域负责人", "M4", "正式", "2017-11-01", "在职", "E005", "华南区总经理"),
    ("E011", "梁诗琪", "运营部", "RG-EAST", "区域负责人", "M4", "正式", "2018-03-19", "在职", "E006", "华东区总经理"),
    ("E012", "林晓芳", "财务部", "RG-SOUTH", "财务人员", "P5", "正式", "2019-07-01", "在职", "E001", "2026-06-01由财务部调岗至运营部"),
    ("E013", "穆勒", "销售部", "RG-EU", "区域负责人", "M4", "正式", "2020-01-06", "在职", "E005", "欧洲区总经理"),
    ("E014", "约翰逊", "销售部", "RG-NA", "区域负责人", "M4", "正式", "2020-05-11", "在职", "E005", "北美区总经理"),
    ("E015", "周凯", "运营部", "RG-EAST", "管理人员", "M3", "正式", "2019-09-02", "在职", "E011", "华东仓自动化项目负责人"),
    ("E020", "刘洋", "运营部", "RG-CN", "管理人员", "M2", "正式", "2020-10-12", "在职", "E006", "星链智能客服项目负责人"),
    ("E023", "王磊", "财务部", "RG-CN", "财务人员", "P4", "正式", "2021-03-15", "在职", "E001", "财务共享中心"),
    ("E037", "张伟", "销售部", "RG-SOUTH", "普通员工", "P3", "正式", "2022-04-18", "在职", "E010", "广州"),
    ("E044", "杜鹏", "运营部", "RG-SOUTH", "普通员工", "P3", "正式", "2021-08-02", "离职", "E006", "2026-03-31离职"),
    ("E052", "高翔", "运营部", "RG-EAST", "普通员工", "P4", "正式", "2020-11-23", "在职", "E015", "华东仓自动化项目成员"),
    ("E058", "李静", "财务部", "RG-CN", "管理人员", "M5", "正式", "2014-02-17", "在职", None, "VP（中国区）"),
    ("E060", "艾米丽", "客服部", "RG-EAST", "外包人员", "P1", "外包", "2025-06-01", "在职", "E007", "劳务外包"),
    ("E061", "韩梅", "人力资源部", "RG-CN", "实习生", "I1", "实习", "2026-07-01", "在职", "E003", "暑期实习生"),
]


def build_employees():
    emps = []
    for (eid, name, dept, region, role, grade, etype, join, status, mgr, note) in _SPECIAL_EMPLOYEES:
        emps.append(dict(employee_id=eid, name=name, department=dept, region=region,
                         role=role, grade=grade, employment_type=etype, join_date=join,
                         status=status, manager=mgr,
                         office_city=REGION_OFFICE[region], note=note))
    used = {e["employee_id"] for e in emps}
    idx = 0
    for i in range(1, 140):
        eid = f"E{i:03d}"
        if eid in used:
            continue
        if len(emps) >= 120:
            break
        idx += 1
        dept = DEPARTMENTS[idx % len(DEPARTMENTS)]
        region = ["RG-SOUTH", "RG-EAST", "RG-NORTH", "RG-CN", "RG-HK", "RG-SEA", "RG-EU"][idx % 7]
        r = idx % 10
        if r < 6:
            role, grade, etype = "普通员工", ROLE_GRADE["普通员工"][idx % 5], "正式"
        elif r < 7:
            role, grade, etype = "管理人员", ROLE_GRADE["管理人员"][idx % 4], "正式"
        elif r < 8:
            role, grade, etype = "财务人员" if dept == "财务部" else "采购人员", "P4", "正式"
        elif r < 9:
            role, grade, etype = "外包人员", "P2", "外包"
        else:
            role, grade, etype = "实习生", "I1", "实习"
        name = SURNAME[idx % len(SURNAME)] + GIVEN[(idx * 7) % len(GIVEN)]
        join = f"{2020 + idx % 6}-{1 + idx % 12:02d}-{1 + idx % 27:02d}"
        mgr = DEPT_HEADS.get(dept)
        emps.append(dict(employee_id=eid, name=name, department=dept, region=region,
                         role=role, grade=grade, employment_type=etype, join_date=join,
                         status="在职", manager=mgr, office_city=REGION_OFFICE[region], note=""))
    return emps


# ---------------------------------------------------------------- suppliers
_SPECIAL_SUPPLIERS = [
    ("S001", "星辰物流有限公司", "中国", "物流", "A", "60天", 5, "2025-01-01", "2027-12-31", "常规", 8),
    ("S001C", "星辰物流(广州)有限公司", "中国", "物流", "B", "45天", 7, "2025-06-01", "2027-05-31", "常规", 6),
    ("S002", "云图信息技术有限公司", "中国", "软件", "B", "30天", 15, "2025-03-01", "2026-12-31", "常规", 4),
    ("S003", "恒远电子科技有限公司", "中国", "电子元器件", "A", "45天", 10, "2025-10-01", "2027-09-30", "常规", 3),
    ("S004", "蓝海包装制品有限公司", "中国", "包装材料", "C", "30天", 8, "2024-06-01", "2026-11-30", "常规", 12),
    ("S005", "中科软件股份有限公司", "中国", "软件", "A", "30天", 20, "2025-02-01", "2027-01-31", "常规", 2),
    ("S006", "环宇办公用品有限公司", "中国", "办公用品", "B", "30天", 3, "2024-01-01", "2026-12-31", "低敏级", 2),
    ("S007", "Global Parts GmbH", "德国", "零部件", "A", "45天", 25, "2025-04-01", "2027-03-31", "常规", 4),
    ("S008", "ABC Logistics Singapore Pte Ltd", "新加坡", "物流", "B", "30天", 6, "2025-05-01", "2026-10-31", "常规", 5),
    ("S009", "ABC Logistics Holding Ltd", "中国香港", "物流", "A", "45天", 9, "2024-11-01", "2027-06-30", "常规", 6),
    ("S017", "迅捷耗材供应链有限公司", "中国", "办公耗材", "B", "15天", 2, "2025-07-01", "2027-06-30", "低敏级", 3),
]

_SUP_EXTRA_NAMES = ["华信电线", "锐驰机械", "蓝天化工", "优选面料", "恒信模具", "捷达运输",
                    "明达光电", "泰和金属", "新绿环保", "卓越标识", "瑞丰纸业", "腾飞五金",
                    "康泰医疗器械", "慧联通信", "源创能源", "百川数据", "安捷检测", "正大咨询"]


def build_suppliers():
    sups = []
    for (sid, name, country, cat, rating, terms, lead, cs, ce, sens, delay) in _SPECIAL_SUPPLIERS:
        sups.append(dict(supplier_id=sid, supplier_name=name, country=country, category=cat,
                         rating=rating, payment_terms=terms, lead_time_days=lead,
                         contract_start=cs, contract_end=ce, sensitivity=sens,
                         delay_rate_pct=delay))
    for i, n in enumerate(_SUP_EXTRA_NAMES):
        sid = f"S{20 + i:03d}"
        sups.append(dict(supplier_id=sid, supplier_name=f"{n}有限公司", country="中国",
                         category=["包装材料", "物流", "软件", "电子元器件", "办公用品"][i % 5],
                         rating=["A", "B", "C"][i % 3], payment_terms=["30天", "45天", "60天"][i % 3],
                         lead_time_days=3 + i % 20, contract_start="2025-01-01",
                         contract_end="2026-12-31", sensitivity="常规", delay_rate_pct=1 + i % 14))
    return sups


# ---------------------------------------------------------------- products
_PRODUCTS = [
    ("M10001", "NebulaPhone 12", "星环手机", "TM-88001", "天猫", False),
    ("M10005", "NebulaPad 8", "星环平板", "JD-50005", "京东", False),
    ("M10010", "AeroBuds Air", "声科无线耳机入门款", "TM-88010", "天猫", False),
    ("M10028", "AeroBuds Pro X2", "声科旗舰降噪耳机", "TM-88231", "天猫", False),
    ("M10029", "AeroBuds 充电盒", "声科无线充电盒", "JD-55210", "京东", False),
    ("M10030", "FitOne 智能手环", "声科运动手环", "DY-70030", "抖音", False),
    ("M10031", "AeroBuds Pro X2 海外版", "声科旗舰降噪耳机(海外)", "SP-33001", "Shopee", False),
    ("M10028S", "AeroBuds Pro X2S 升级版", "声科升级降噪耳机(2026)", "TM-88232", "天猫", False),
    ("M10032", "NebulaBook 14 笔记本", "星环笔记本", "JD-51032", "京东", False),
    ("M10033", "智能音箱 EchoNeb", "星环智能音箱", "TM-88033", "天猫", False),
    ("M10034", "车载充电器 CarVolt", "星环车充", "DY-70034", "抖音", False),
    ("M10035", "NebulaWatch 3", "星环手表", "SP-33035", "Shopee", False),
    ("M10036", "电子书《企业数字化转型指南》", "星环出版社电子书", "EB-90001", "天猫", True),
    ("M10037", "智能办公软件激活码(年卡)", "星环SaaS激活码", "EB-90002", "京东", True),
    ("M10038", "云端存储套餐(100GB/年)", "星环云服务", "EB-90003", "官网", True),
]


def build_products():
    prods = []
    for (sku, name, cat, psku, platform, digital) in _PRODUCTS:
        prods.append(dict(internal_sku=sku, product_name=name, category=cat,
                          platform_sku=psku, platform=platform, is_digital=digital,
                          brand="声科" if name.startswith(("AeroBuds", "FitOne")) else "星环"))
    return prods


BUNDLES = [
    dict(bundle_sku="B2001", components=["M10028", "M10029"], name="AeroBuds Pro X2 无线套装"),
    dict(bundle_sku="B2002", components=["M10001", "M10033"], name="手机+音箱家庭套装"),
]
SKU_ALIASES = [  # 故意制造容易混淆的近似编号
    dict(alias="SK-10028", internal_sku="M10001", note="平台旧编号，与M10028数字相近，易误配"),
    dict(alias="TM-10028", internal_sku="M10001", note="历史遗留编号，对应旧款而非M10028"),
]

# ---------------------------------------------------------------- customers
_CUSTOMERS = [
    ("C001", "张氏贸易有限公司", "VIP"), ("C002", "李记食品有限公司", "普通会员"),
    ("C003", "华远科技有限公司", "VIP"), ("C004", "恒达建材有限公司", "普通会员"),
    ("C005", "锦绣服装有限公司", "普通会员"), ("C006", "优品电器有限公司", "VIP"),
    ("C007", "四季酒店管理公司", "VIP"), ("C008", "蓝湾文旅有限公司", "普通会员"),
    ("C009", "宏图教育集团", "普通会员"), ("C010", "锐力体育用品公司", "VIP"),
    ("C011", "天籁音响设备公司", "普通会员"), ("C012", "绿源农业合作社", "普通会员"),
    ("C013", "迅达物流集团", "VIP"), ("C014", "晨光文具贸易公司", "普通会员"),
    ("C015", "奥体健身连锁", "普通会员"), ("C016", "康桥医疗集团", "VIP"),
    ("C017", "远洋电子科技公司", "普通会员"), ("C018", "明珠百货公司", "普通会员"),
    ("C019", "光合传媒有限公司", "普通会员"), ("C020", "国润投资集团", "VIP"),
]


def build_customers():
    return [dict(customer_id=cid, name=n, tier=t, vip=(t == "VIP")) for cid, n, t in _CUSTOMERS]


# ---------------------------------------------------------------- orders
PLATFORMS = ["天猫", "京东", "抖音", "Shopify", "Shopee"]
WAREHOUSES = {"天猫": "广州仓", "京东": "上海仓", "抖音": "广州仓", "Shopify": "欧洲仓", "Shopee": "新加坡仓"}


def build_orders():
    orders = []
    prods = build_products()
    physical = [p for p in prods if not p["is_digital"]]
    digital = [p for p in prods if p["is_digital"]]
    custs = build_customers()
    seq = 0
    for month in range(1, 21):  # 2025-01 .. 2026-08
        year = 2025 if month <= 12 else 2026
        m = month if month <= 12 else month - 12
        n_orders = 14 + (month % 4)
        for _ in range(n_orders):
            seq += 1
            plat = PLATFORMS[seq % len(PLATFORMS)]
            is_dig = (seq % 23 == 0)
            p = (digital if is_dig else physical)[seq % (len(digital) if is_dig else len(physical))]
            qty = 1 + seq % 3
            price = {False: 199 + (seq % 17) * 60, True: 99 + (seq % 5) * 100}[is_dig]
            discount = 0 if seq % 3 else round(price * qty * 0.05)
            # 退款率：抖音刻意最高
            refund_p = {"抖音": 0.24, "天猫": 0.10, "京东": 0.08, "Shopify": 0.06, "Shopee": 0.07}[plat]
            refund = 0
            if (seq * 7) % 100 < refund_p * 100:
                refund = round(price * qty - discount)
            cust = custs[seq % len(custs)]
            oid = "O-2026-0512" if False else f"O-{year}-{seq:04d}"
            orders.append(dict(order_id=oid, shop_id=f"SHOP-{plat}-{1 + seq % 3}",
                               platform=plat, sku=p["internal_sku"], quantity=qty,
                               unit_price=price, discount=discount,
                               amount_excl_tax=price * qty - discount,
                               refund_amount=refund, customer_id=cust["customer_id"],
                               warehouse=WAREHOUSES[plat],
                               order_date=f"{year}-{m:02d}-{1 + seq % 27:02d}"))
    # —— 关键测试订单：VIP 客户购买数字商品申请退款（§68 场景）
    special = dict(order_id="O-2026-0512", shop_id="SHOP-天猫-1", platform="天猫",
                   sku="M10036", quantity=1, unit_price=199, discount=0,
                   amount_excl_tax=199, refund_amount=199, customer_id="C001",
                   warehouse="广州仓", order_date="2026-05-12",
                   note="VIP客户C001购买电子书，2026-05-20申请无理由退款")
    orders.append(special)
    return orders


# ---------------------------------------------------------------- finance
_FIN_REGIONS = [("RG-SOUTH", 8_400_000), ("RG-EAST", 6_800_000), ("RG-NORTH", 3_600_000),
                ("RG-HK", 2_300_000), ("RG-SEA", 2_900_000), ("RG-EU", 4_500_000)]


def build_finance_monthly():
    """2025-01 ~ 2026-08 月度财务数据（人民币；欧洲区报表另以欧元列示）。"""
    rows = []
    for i, month in enumerate(range(1, 21)):
        year = 2025 if month <= 12 else 2026
        m = month if month <= 12 else month - 12
        season = 1 + 0.06 * ((m % 12) - 6) / 6  # 简单季节因子
        for reg, base in _FIN_REGIONS:
            rev = round(base * season * (1.15 ** (i / 12)))
            if reg == "RG-SOUTH" and year == 2026 and m == 6:
                rev = 8_000_000  # 固定值，配合“万元单位陷阱”题（表内显示 800 万元）
            if reg == "RG-EU" and year == 2026 and m == 6:
                rev = 4_836_000  # 固定值：按 7.8 汇率 = 620,000 欧元（欧洲区列报说明）
            margin = 0.30 - 0.02 * ((i + hash(reg)) % 3)
            cost = round(rev * (1 - margin))
            gp = rev - cost
            expense = round(rev * 0.12)
            budget = round(rev * 1.05)
            rows.append(dict(month=f"{year}-{m:02d}", region=reg, region_name=REGIONS[reg],
                             revenue=rev, cost=cost, gross_profit=gp, expense=expense,
                             budget=budget, actual=rev, currency="CNY"))
    return rows


BU_MARGIN_2026H1 = [  # 刻意制造 25% 平手：Top3 应包含两个 25%
    dict(bu="电商BU", revenue=52_000_000, cost=37_960_000),    # 27.0%
    dict(bu="SaaS BU", revenue=21_000_000, cost=15_750_000),   # 25.0%
    dict(bu="物流BU", revenue=18_000_000, cost=13_500_000),    # 25.0%
    dict(bu="企业服务BU", revenue=12_000_000, cost=9_240_000), # 23.0%
    dict(bu="跨境电商BU", revenue=9_000_000, cost=7_110_000),  # 21.0%
]

DEPT_BUDGET_2026 = [
    dict(department=d, budget=b, actual=a)
    for d, b, a in [("销售部", 4_800_000, 4_416_000), ("运营部", 3_600_000, 3_276_000),
                    ("信息技术部", 5_200_000, 4_784_000), ("采购部", 900_000, 954_000),
                    ("客服部", 1_500_000, 1_260_000), ("人力资源部", 1_200_000, 1_092_000),
                    ("合规部", 600_000, 504_000), ("财务部", 800_000, 744_000),
                    ("法务部", 500_000, 460_000)]
]


# ---------------------------------------------------------------- IT systems
def build_systems():
    return dict(
        systems=[
            dict(system_id="SYS-OMS", name="订单中台(OMS)", owner_dept="信息技术部",
                 services=["order-api", "refund-api", "inventory-api"]),
            dict(system_id="SYS-PAY", name="支付平台", owner_dept="信息技术部",
                 services=["pay-api", "settle-api"]),
            dict(system_id="SYS-WMS", name="仓务系统", owner_dept="运营部",
                 services=["stock-api", "pick-api"]),
            dict(system_id="SYS-CRM", name="客户关系系统", owner_dept="销售部",
                 services=["customer-api"]),
            dict(system_id="SYS-DATA", name="数据仓库", owner_dept="信息技术部",
                 services=["etl-job", "report-api"]),
        ],
        service_db={"order-api": "oms_db", "refund-api": "oms_db", "pay-api": "pay_db",
                    "settle-api": "pay_db", "inventory-api": "wms_db"},
        databases={
            "oms_db": {"order_info": ["order_id", "status", "cancel_reason", "updated_at", "amount"],
                       "refund_order": ["refund_id", "order_id", "amount", "state"]},
            "pay_db": {"payment": ["pay_id", "order_id", "channel", "state"]},
            "wms_db": {"inventory": ["sku", "warehouse", "qty"]},
        },
    )


# ---------------------------------------------------------------- projects
def build_projects():
    return [
        dict(project_id="PRJ-001", name="星链智能客服项目", owner="E020", region="RG-CN",
             budget=4_800_000, status="已验收",
             docs=["PRD-001", "SOL-001", "MTG-001", "DEC-001", "ACC-001"]),
        dict(project_id="PRJ-002", name="华东仓自动化项目", owner="E015", region="RG-EAST",
             budget=12_000_000, actual=9_360_000, status="进行中",
             docs=["PRD-002", "MTG-002"]),
    ]


PROJECT_MEMBERS = {"PRJ-001": ["E020", "E052", "E023"], "PRJ-002": ["E015", "E052", "E037"]}


def all_entities():
    return dict(
        employees=build_employees(), suppliers=build_suppliers(),
        products=build_products(), customers=build_customers(),
        orders=build_orders(), finance_monthly=build_finance_monthly(),
        bu_margin_2026h1=BU_MARGIN_2026H1, dept_budget_2026=DEPT_BUDGET_2026,
        systems=build_systems(), projects=build_projects(),
        bundles=BUNDLES, sku_aliases=SKU_ALIASES, project_members=PROJECT_MEMBERS,
    )


if __name__ == "__main__":
    w = all_entities()
    for k, v in w.items():
        print(k, len(v) if hasattr(v, "__len__") else v)
