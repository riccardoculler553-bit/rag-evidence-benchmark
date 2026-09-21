# -*- coding: utf-8 -*-
"""企业知识语料生成器：世界模型 → 文档视图 → 注册表。
所有文档由 corpus_facts.py 的事实常量渲染，保证文本与 Gold 一致。"""
import json
import os
import csv
import io

from world import (GROUP_CN, REGIONS, REGION_TREE, DEPARTMENTS, DEPT_HEADS,
                   REGION_HEADS, all_entities)
import corpus_facts as F

# ---------------------------------------------------------------- helpers


def md_table(headers, rows, align=None):
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


class Doc:
    def __init__(self, doc_id, title, path, domain, fmt, authority, published,
                 eff_from, eff_to, status="current", acl="internal", version_of=None,
                 supersedes=None, parser_status="CONFIDENT", lang="zh"):
        self.doc_id, self.title, self.path, self.domain, self.fmt = doc_id, title, path, domain, fmt
        self.authority, self.published, self.eff_from, self.eff_to = authority, published, eff_from, eff_to
        self.status, self.acl, self.version_of, self.supersedes = status, acl, version_of, supersedes
        self.parser_status, self.lang = parser_status, lang
        self.anchors = []
        self.body = ""

    def front_matter(self):
        return (f"---\ndoc_id: {self.doc_id}\ntitle: {self.title}\n"
                f"authority_level: {self.authority}\npublished_at: {self.published}\n"
                f"effective_from: {self.eff_from}\neffective_to: {self.eff_to or '长期'}\n"
                f"status: {self.status}\nclassification: {self.acl}\n---\n")

    def write(self, root):
        full = os.path.join(root, self.path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if self.fmt in ("md", "txt", "html", "yaml", "sql"):
            with open(full, "w", encoding="utf-8") as f:
                f.write(self.body if self.fmt == "md" else self.body)
        return self

    def meta(self):
        return dict(doc_id=self.doc_id, title=self.title, path=self.path, domain=self.domain,
                    format=self.fmt, authority_level=self.authority, published_at=self.published,
                    effective_from=self.eff_from, effective_to=self.eff_to, status=self.status,
                    classification=self.acl, version_of=self.version_of, supersedes=self.supersedes,
                    parser_status=self.parser_status, language=self.lang, anchors=self.anchors)


DOCS = []
EXTRA_FILES = []  # (relative_path, text_or_None, csv_rows)


def add(doc, body, anchors):
    doc.body = body
    doc.anchors = anchors
    DOCS.append(doc)
    return doc


def h(level, anchor, text):
    return f'{"#" * level} {text} <!-- a:{anchor} -->\n'


# ================================================================ TRV-001
def build_trv001(ver):
    v = ver
    dom = "policies"
    if v["status"] == "superseded":
        path = f"historical/TRV-001-{v['ver']}.md"
    else:
        path = f"policies/TRV-001-{v['ver']}.md"
    d = Doc(v["doc_id"], f"差旅费管理办法（{v['ver']}）", path, "policies", "md", 5,
            v["published"], v["eff_from"], v["eff_to"], v["status"],
            supersedes=None)
    prev = [x for x in F.TRV_VERSIONS if x["ver"] == f"v{int(v['ver'][1]) - 1}"]
    sup = prev[0]["doc_id"] if prev else None
    d.supersedes = sup
    body = [d.front_matter(), f"# 差旅费管理办法（{v['ver']}）\n"]
    body += [h(2, "sec-1", "第一章 总则"),
             f"1.1 目的：为规范{GROUP_CN}差旅费用管理、合理控制成本，制定本办法。 <!-- a:sec-1-1 -->\n",
             "1.2 适用范围：本办法适用于集团全体正式员工与外包人员在中国大陆境内因公出差的费用管理。"
             "中国香港、海外地区差旅不适用本办法，按《海外差旅政策》（TRV-003）执行。 <!-- a:sec-1-2 -->\n",
             f"1.3 申请时限：差旅申请须提前 {F.TRV_ADVANCE_DAYS} 个工作日提交。 <!-- a:sec-1-3 -->\n"]
    body += [h(2, "sec-2", "第二章 住宿标准"),
             f"2.1 普通员工住宿上限（详见附录A）：一线城市（北京、上海、广州、深圳）{v['tier1']} 元/晚；"
             f"二线城市（杭州、成都、武汉、南京、西安、苏州）{v['tier2']} 元/晚；其他城市 {v['other']} 元/晚。 <!-- a:sec-2-1 -->\n"]
    if v["ver"] == "v3":
        body += ["2.2 特殊城市：上海自 2026-07-01 起住宿上限调整为 650 元/晚，"
                 "见《关于上海地区住宿标准调整的通知》（TRV-001-CN1）。 <!-- a:sec-2-2 -->\n",
                 "2.3 管理人员：M3、M4 级管理人员可在普通员工标准基础上上浮 30% 执行；"
                 "M5 及 VP 不适用本章标准，按《高管差旅住宿标准》（TRV-002）执行。 <!-- a:sec-2-3 -->\n"]
    if v["spring_surcharge"]:
        body += [h(2, "sec-3", "第三章 特殊情况"),
                 "3.1 春节期间：春节法定假期前后 3 天内出差的，住宿上限上浮 20%。 <!-- a:sec-3-1 -->\n"]
        if v["ver"] == "v3":
            body += ["3.2 展会期间：出差日期落在附录B所列大型展会期间（含布展、撤展）的，"
                     "住宿上限上浮 20%。 <!-- a:sec-3-2 -->\n",
                     "3.3 客户指定酒店：因客户指定酒店导致实际房价超出标准的，超出部分不超过标准 30%、"
                     "且经部门负责人及财务负责人审批的，可予报销。 <!-- a:sec-3-3 -->\n",
                     "3.4 紧急客户事件：因紧急客户事件出差的，经部门负责人批准后可当天提交差旅申请，"
                     "不受第 1.3 条提前申请时限限制。 <!-- a:sec-3-4 -->\n",
                     "3.5 供应商陪同出差：有供应商人员全程陪同出差的，住宿标准按对应城市标准的 80% 执行。 <!-- a:sec-3-5 -->\n"]
    body += [h(2, "sec-4", "第四章 报销流程"),
             "4.1 普通流程：差旅结束后 15 个工作日内在报销系统提交，并附发票及行程单。 <!-- a:sec-4-1 -->\n",
             "4.2 紧急流程：紧急事件出差可事后 48 小时内补交申请与审批单。 <!-- a:sec-4-2 -->\n"]
    if v["ver"] == "v3":
        body += [h(2, "sec-5", "第五章 区域调节权限"),
                 "5.1 各区域可在集团标准基础上上浮执行，上浮幅度不得超过 10%，且须经合规部备案后方可生效；"
                 "未备案或超出上浮幅度的区域通知一律无效。 <!-- a:sec-5-1 -->\n"]
    body += [h(2, "app-a", "附录A 城市住宿标准表"),
             f"（{v['eff_from']} 起施行） <!-- a:tbl-a -->\n"]
    rows = [["北京", v["tier1"], "一线"], ["上海", v["tier1"], "一线"],
            ["广州", v["tier1"], "一线"], ["深圳", v["tier1"], "一线"]]
    for c in F.TIER2_CITIES:
        rows.append([c, v["tier2"], "二线"])
    for c in ["佛山", "东莞", "合肥", "郑州", "长沙"]:
        rows.append([c, v["other"], "其他"])
    if v["ver"] == "v3":
        rows.append(["上海（2026-07-01 起）", 650, "特殊城市，见 TRV-001-CN1"])
    body += [md_table(["城市", "住宿上限", "类别"], rows), "\n"]
    body += ["> 脚注1：本表金额单位均为人民币元/晚，含服务费，不含早餐。 <!-- a:fn-1 -->\n",
             "> 脚注2：附录B所列展会期间，上表标准上浮 20%（四舍五入到十元）。 <!-- a:fn-2 -->\n",
             h(2, "app-b", "附录B 大型展会清单"),
             md_table(["展会名称", "城市", "日期"], [
                 ["广交会（春季）", "广州", "2026-04-15 至 2026-05-05"],
                 ["进博会", "上海", "2026-11-05 至 2026-11-10"]])]
    return add(d, "\n".join(body),
               ["sec-1", "sec-1-1", "sec-1-2", "sec-1-3", "sec-2", "sec-2-1",
                "sec-3", "sec-4", "app-a", "tbl-a", "fn-1", "fn-2", "app-b"]
               + (["sec-2-2", "sec-2-3", "sec-3-1", "sec-3-2", "sec-3-3", "sec-3-4", "sec-3-5", "sec-5", "sec-5-1"]
                  if v["ver"] == "v3" else ["sec-3-1"]))


def build_trv_cn1():
    d = Doc("TRV-001-CN1", "关于上海地区住宿标准调整的通知", "policies/TRV-001-CN1.md",
            "policies", "md", 5, F.TRV_SPECIAL_CITY["上海"]["published"], "2026-07-01", None)
    body = [d.front_matter(), "# 关于上海地区住宿标准调整的通知\n",
            h(1, "sec-1", "经集团财务部与合规部批准，自 2026-07-01 起，上海地区差旅住宿上限由 500 元/晚调整为 650 元/晚（普通员工）。"),
            "本通知发布日期为 2026-06-05，生效日期为 2026-07-01。生效日前仍按 500 元/晚执行。\n",
            "本通知纳入《差旅费管理办法》（TRV-001-v3）第 2.2 条特殊城市条款。"]
    return add(d, "\n".join(body), ["sec-1"])


def build_trv002():
    docs = []
    for v in F.TRV_EXEC_VERSIONS:
        path = f"historical/TRV-002-{v['doc_id'][-2:]}.md" if v["status"] == "superseded" else "policies/TRV-002-v2.md"
        d = Doc(v["doc_id"], f"高管差旅住宿标准（{'v1' if 'v1' in v['doc_id'] else 'v2'}）", path,
                "policies", "md", 5, v["published"], v["eff_from"], v["eff_to"], v["status"])
        body = [d.front_matter(), f"# 高管差旅住宿标准\n",
                "适用对象：M4、M5 级管理人员及 VP（含区域负责人）。",
                h(2, "tbl-b", "住宿上限（人民币元/晚）"),
                md_table(["城市级别", "标准"], [["一线城市", v["tier1"]], ["二线城市", v["tier2"]]]),
                "高级管理人员出差原则上不适用《差旅费管理办法》普通员工标准。",
                "海外及中国香港地区按《海外差旅政策》（TRV-003）执行，高管标准可上浮 50%。"]
        docs.append(add(d, "\n".join(body), ["tbl-b"]))
    return docs


def build_trv003():
    d = Doc("TRV-003", "海外差旅政策", "policies/TRV-003.md", "policies", "md", 5,
            "2025-08-20", "2025-09-01", None)
    body = [d.front_matter(), "# 海外差旅政策\n",
            h(2, "sec-1", "第一条 本政策适用于中国香港及海外地区差旅，不适用《差旅费管理办法》。"),
            h(2, "sec-2", "第二条 欧洲区：普通员工住宿上限 800 元/晚；欧元区城市按 100 欧元/晚上限执行。"),
            h(2, "sec-3", "第三条 东南亚区：普通员工住宿上限 450 元/晚。"),
            h(2, "sec-4", "第四条 北美区：普通员工住宿上限 120 美元/晚；报销时按出差当月月初汇率折算为人民币。 <!-- a:fn-usd -->"),
            h(2, "sec-5", "第五条 中国香港：普通员工住宿上限 700 元/晚。"),
            h(2, "sec-6", "第六条 VP 及以上管理人员在上述标准基础上上浮 50% 执行。")]
    return add(d, "\n".join(body), ["sec-1", "sec-2", "sec-3", "sec-4", "sec-5", "sec-6", "fn-usd"])


def build_decoys():
    docs = []
    d1 = Doc("TRV-004", "外派人员住宿补贴管理办法", "policies/TRV-004.md", "policies", "md", 5,
             "2025-02-25", "2025-03-01", None)
    add(d1, d1.front_matter() + "# 外派人员住宿补贴管理办法\n\n"
        "常驻外派人员（连续驻外超过 90 天）享受每月 3,000 元租房补贴，按季度发放。\n"
        "本办法适用于外派常驻场景，与临时出差差旅报销互不混用。", ["sec-1"])
    d2 = Doc("TRV-005", "供应商来访差旅费用承担说明", "policies/TRV-005.md", "policies", "md", 3,
             "2025-05-10", "2025-05-15", None)
    add(d2, d2.front_matter() + "# 供应商来访差旅费用承担说明\n\n"
        "供应商人员来访发生的差旅、住宿费用原则上由供应商自行承担；集团员工陪同产生的费用按员工本人标准报销。",
        ["sec-1"])
    d3 = Doc("EXP-002", "差旅费用审核办法", "policies/EXP-002.md", "policies", "md", 4,
             "2025-03-01", "2025-03-10", None)
    add(d3, d3.front_matter() + "# 差旅费用审核办法\n\n"
        "第一条 财务审核要点：核对出差申请单、行程一致性、发票抬头与税号、超标审批链完整性。\n"
        "第二条 本办法为审核操作规程，住宿及餐费限额标准以《差旅费管理办法》《费用报销管理办法》为准。\n"
        "第三条 审核人员发现异常应在系统中挂起并通知提交人补正。", ["sec-1", "sec-2", "sec-3"])
    return docs


# ================================================================ EXP-001
def build_exp001():
    docs = []
    for v in F.EXP_VERSIONS:
        path = f"historical/EXP-001-{v['doc_id'][-2:]}.md" if v["status"] == "superseded" else "policies/EXP-001-v2.md"
        d = Doc(v["doc_id"], f"费用报销管理办法（{v['doc_id'][-2:]}）", path, "policies", "md", 5,
                v["published"], v["eff_from"], v["eff_to"], v["status"])
        body = [d.front_matter(), f"# 费用报销管理办法（{v['doc_id'][-2:]}）\n",
                h(2, "sec-1", "第一章 餐费与交通补贴"),
                f"2.1 出差期间餐费补贴：一线城市 {v['meal_t1']} 元/天，二线城市 {v['meal_t2']} 元/天，"
                f"无需提供发票。 <!-- a:tbl-meal -->",
                f"2.2 市内交通费：凭票实报实销，每人每天上限 {v['transport']} 元。 <!-- a:tbl-trans -->"]
        if v["status"] == "current":
            body += [h(2, "sec-3", "第三章 例外情形"),
                     f"3.1 展会期间（附录B所列展会）餐费补贴按 {v['expo_meal']} 元/天执行。 <!-- a:sec-3-1 -->",
                     f"3.2 加班餐补：工作日 20:00 之后加班的，可报销加班餐补 {v['overtime_meal']} 元/次。 <!-- a:sec-3-2 -->"]
        body += [h(2, "sec-4", "第四章 发票与提交"),
                 f"4.1 单笔金额达到 {F.EXP_INVOICE_THRESHOLD} 元（含）的报销须附合同或订单复印件。 <!-- a:sec-4-1 -->",
                 f"4.2 员工一般应在费用发生后 {F.EXP_SUBMIT_DAYS} 天内提交报销，超期须说明理由。 <!-- a:sec-4-2 -->",
                 h(2, "sec-5", "第五章 附则"),
                 "5.1 本制度未尽事宜由财务部负责解释。",
                 "5.2 本制度未对周末提交报销作出特别规定。 <!-- a:fn-weekend -->"]
        docs.append(add(d, "\n".join(body),
                        ["sec-1", "tbl-meal", "tbl-trans", "sec-4", "sec-4-1", "sec-4-2",
                         "sec-5", "fn-weekend"] + (["sec-3", "sec-3-1", "sec-3-2"] if v["status"] == "current" else [])))
    return docs


# ================================================================ PROC
def build_proc():
    docs = []
    for v in F.PROC_VERSIONS:
        path = f"historical/PROC-001-{v['doc_id'][-2:]}.md" if v["status"] == "superseded" else "policies/PROC-001-v3.md"
        d = Doc(v["doc_id"], f"采购管理办法（{v['doc_id'][-2:]}）", path, "policies", "md", 5,
                v["published"], v["eff_from"], v["eff_to"], v["status"])
        body = [d.front_matter(), f"# 采购管理办法（{v['doc_id'][-2:]}）\n",
                h(2, "sec-1", "第一章 总则"),
                "1.1 本办法适用于集团全部货物与服务采购活动。",
                h(2, "sec-4", "第四章 审批权限"),
                f"4.1 单笔采购金额超过 {v['approval_1']:,} 元（不含税）的，须经采购总监审批。 <!-- a:sec-4-1 -->",
                f"4.2 单笔采购金额超过 {v['approval_2']:,} 元（不含税）的，须经 CFO 与 CEO 联签。 <!-- a:sec-4-2 -->",
                f"4.3 单一来源采购须提交董事会批准。 <!-- a:sec-4-3 -->",
                h(2, "sec-5", "第五章 供应商与履约管理")]
        if v["status"] == "current":
            body += ["5.4 供应商综合评级为 A 且近半年交付延期率高于 5% 的，向其下单前须取得合规部额外审批。 <!-- a:sec-5-4 -->"]
        body += ["5.5 采购须通过合格供应商名录执行。"]
        if v["status"] == "current":
            body += [h(2, "sec-6", "第六章 免审批情形"),
                     "6.1 单笔金额低于 5,000 元且当月累计低于 20,000 元的零星采购，免于采购总监审批。 <!-- a:sec-6-1 -->",
                     "6.2 框架协议内已定价商品的按单执行，免于逐单审批。 <!-- a:sec-6-2 -->",
                     "6.3 生产紧急备件采购可先行执行，须在 48 小时内完成补审批。 <!-- a:sec-6-3 -->",
                     "6.4 其他免审批情形见附录C。 <!-- a:sec-6-4 -->",
                     h(2, "app-c", "附录C 免审批情形补充清单"),
                     "C.1 年度集中采购目录内的标准办公用品，免于逐单审批。 <!-- a:app-c -->"]
        body += [h(2, "app-ndaa", "附录：NDA 签署要求"),
                 "NDA.1 所有供应商准入前必须签署保密协议（NDA）。 <!-- a:sec-nda -->",
                 f"NDA.2 例外：对于低敏级物料供应商，若单笔采购金额低于 {F.NDA_EXEMPT['amount_lt']:,} 元，"
                 "可以豁免签署 NDA。 <!-- a:sec-nda-exempt -->"]
        docs.append(add(d, "\n".join(body),
                        ["sec-1", "sec-4", "sec-4-1", "sec-4-2", "sec-4-3", "sec-5", "app-ndaa",
                         "sec-nda", "sec-nda-exempt"]
                        + (["sec-5-4", "sec-6", "sec-6-1", "sec-6-2", "sec-6-3", "sec-6-4", "app-c"]
                           if v["status"] == "current" else [])))
    return docs


def build_proc_others():
    docs = []
    d1 = Doc("PROC-002", "供应商管理制度", "policies/PROC-002.md", "procurement", "md", 5,
             "2025-06-01", "2025-06-15", None)
    add(d1, d1.front_matter() + "# 供应商管理制度\n\n"
        "## 第一章 准入与评级 <!-- a:sec-1 -->\n\n"
        "1.1 供应商综合评级分为 A、B、C 三级：A=综合评分≥90；B=75~89；C=<75。\n"
        "1.2 评级每年复核一次，重大质量事故可即时降级。\n\n"
        "## 第二章 保密要求 <!-- a:sec-2 -->\n\n"
        "2.1 供应商 NDA 签署与豁免要求按《采购管理办法》附录执行。\n\n"
        "## 第三章 付款与交付 <!-- a:sec-3 -->\n\n"
        "3.1 付款条件、交付周期以各供应商合同及框架协议为准。", ["sec-1", "sec-2", "sec-3"])
    d2 = Doc("PROC-003", "合同审批制度", "policies/PROC-003.md", "legal", "md", 5,
             "2025-04-01", "2025-04-15", None)
    add(d2, d2.front_matter() + "# 合同审批制度\n\n"
        "第一条 合同金额超过 100 万元的，须经法务部与 CFO 会签。\n"
        "第二条 合同补充协议的效力优先于主合同对应条款；补充协议未变更的条款继续有效。\n"
        "第三条 变更通知仅对其声明的条款范围生效，不得扩张解释。 <!-- a:sec-3 -->", ["sec-1", "sec-2", "sec-3"])
    return docs


# ================================================================ RMA / FAQ
def build_rma():
    d = Doc("RMA-001", "售后退款政策", "policies/RMA-001.md", "sales", "md", 5,
            "2024-12-20", "2025-01-01", None)
    body = [d.front_matter(), "# 售后退款政策\n",
            h(2, "sec-1", "第一条 退款期限"),
            f"1.1 普通客户：自收货之日起 {F.RMA_ORDINARY_DAYS} 天内可申请无理由退款。 <!-- a:sec-1-1 -->",
            f"1.2 VIP 客户（最近 12 个月累计消费≥{F.RMA_VIP_SPEND:,} 元）：可申请退款期限延长至 "
            f"{F.RMA_VIP_DAYS} 天。 <!-- a:sec-1-2 -->",
            h(2, "sec-2", "第二条 到账时效"),
            f"2.1 审核通过后 {F.RMA_ARRIVAL_DAYS} 原路退回。 <!-- a:sec-2-1 -->",
            h(2, "sec-3", "第三条 数字商品例外"),
            "3.1 数字商品（软件激活码、电子书、虚拟服务等）不支持无理由退款；"
            "但存在质量问题的，仍可按规定退款。 <!-- a:sec-3-1 -->",
            h(2, "sec-4", "第四条 特殊支付方式"),
            f"4.1 货到付款、分期支付等特殊支付方式的退款到账时间为 {F.RMA_SPECIAL_PAY_DAYS}。 <!-- a:sec-4-1 -->"]
    return add(d, "\n".join(body), ["sec-1", "sec-1-1", "sec-1-2", "sec-2", "sec-2-1",
                                    "sec-3", "sec-3-1", "sec-4", "sec-4-1"])


def build_faq():
    docs = []
    d1 = Doc("FAQ-001", "客服FAQ：差旅报销篇", "faq/FAQ-001-差旅报销.md", "faq", "md", 2,
             "2026-02-10", "2026-02-10", None)
    add(d1, d1.front_matter() + "# 客服FAQ：差旅报销篇\n\n"
        "问：出差住宿能报多少？\n"
        "答：一般每晚上限 500 元，部分特殊情况 480 元封顶，具体以系统审批为准。\n\n"
        "问：报销多久到账？\n答：一般 5-7 个工作日。\n"
        "（本FAQ由客服团队维护，如与正式制度不一致，以正式制度为准。）", ["sec-1"])
    d2 = Doc("FAQ-002", "客服FAQ：退款到账", "faq/FAQ-002-退款.md", "faq", "md", 2,
             "2026-03-05", "2026-03-05", None)
    add(d2, d2.front_matter() + "# 客服FAQ：退款到账\n\n"
        "问：退款多久到账？\n答：3-5 天原路退回。\n"
        "（如与《售后退款政策》表述不一致，以正式政策为准。）", ["sec-1"])
    d3 = Doc("SOP-003", "客服升级处理说明", "faq/SOP-003-升级处理.md", "faq", "md", 3,
             "2026-01-20", "2026-02-01", None)
    add(d3, d3.front_matter() + "# 客服升级处理说明\n\n"
        "1. VIP 客户投诉走专属通道，由资深客服优先审核处理。 <!-- a:sec-1 -->\n"
        f"2. 特殊支付方式（货到付款、分期）退款到账时间为 {F.RMA_SPECIAL_PAY_DAYS}，"
        "与普通支付方式不同，需主动向客户说明。 <!-- a:sec-2 -->\n"
        "3. 涉及政策解释冲突时升级至运营部。", ["sec-1", "sec-2"])
    for i, (fid, title, qa) in enumerate([
        ("FAQ-010", "发票常见问题", "问：增值税专票开票信息在哪里查？答：在结算中心-开票资料页。\n问：电子发票可以报销吗？答：可以，需验真。"),
        ("FAQ-011", "报销时效问题", "问：报销超期了还能提吗？答：一般可补提，需说明理由并经部门负责人确认。"),
        ("FAQ-012", "年假使用", "问：年假可以跨年吗？答：原则上当年有效，经审批可延至次年3月底。"),
        ("FAQ-013", "加班审批", "问：加班一定要提前审批吗？答：是的，未经审批的加班原则上不计加班费。"),
        ("FAQ-014", "采购流程", "问：急用的东西怎么买？答：生产紧急备件可先执行后补审批（48小时内）。"),
    ]):
        d = Doc(fid, f"客服FAQ：{title}", f"faq/{fid}-{title}.md", "faq", "md", 2,
                "2026-01-10", "2026-01-10", None)
        add(d, d.front_matter() + f"# 客服FAQ：{title}\n\n{qa}\n", ["sec-1"])
    return docs


# ================================================================ SEC / BEN / OT / MET / ORG
def build_sec_ben():
    docs = []
    d = Doc("SEC-001", "数据安全与权限管理制度", "policies/SEC-001.md", "policies", "md", 5,
            "2025-05-01", "2025-05-15", None)
    body = [d.front_matter(), "# 数据安全与权限管理制度\n",
            h(2, "sec-1", "第一条 文档分级"),
            "1.1 集团文档分为四级：public（公开）、internal（内部）、confidential（机密）、secret（绝密）。",
            "1.2 供应商真实报价、财务明细属于 confidential 级，仅限财务相关角色与系统管理员访问。 <!-- a:sec-1-2 -->",
            h(2, "sec-2", "第二条 权限生命周期"),
            "2.1 权限授予、撤销须于次日生效，并强制刷新所有缓存视图。 <!-- a:sec-2-1 -->",
            "2.2 员工离职当天回收全部权限。",
            h(2, "sec-3", "第三条 审计"),
            "3.1 权限变更记录保存不少于 3 年。"]
    docs.append(add(d, "\n".join(body), ["sec-1", "sec-1-2", "sec-2", "sec-2-1", "sec-3"]))
    d = Doc("BEN-001", "员工福利制度", "policies/BEN-001.md", "hr", "md", 5,
            "2025-01-10", "2025-02-01", None)
    body = [d.front_matter(), "# 员工福利制度\n",
            h(2, "sec-1", "第一章 年假"),
            "1.1 年假标准：累计工龄不满 5 年的 5 天；满 5 年不满 10 年的 10 天；满 10 年的 15 天。 <!-- a:tbl-annual -->",
            "1.2 例外：试用期员工年假按当年度剩余月份比例折算。 <!-- a:sec-1-2 -->",
            h(2, "sec-2", "第二章 补充福利"),
            "2.1 补充商业医疗保险仅适用于正式员工；外包、实习人员不适用。 <!-- a:sec-2-1 -->",
            "2.2 外包人员享有法定范围内的基本保障，由外包服务商负责。"]
    docs.append(add(d, "\n".join(body), ["sec-1", "tbl-annual", "sec-1-2", "sec-2", "sec-2-1"]))
    d = Doc("OT-001", "加班管理制度", "policies/OT-001.md", "hr", "md", 5,
            "2025-01-10", "2025-02-01", None)
    add(d, d.front_matter() + "# 加班管理制度\n\n"
        "第一条 加班补偿：工作日加班 1.5 倍工资，周末加班 2 倍，法定节假日 3 倍。 <!-- a:sec-1 -->\n"
        "第二条 加班须提前在系统申请审批。\n"
        "第三条 例外：M4 及以上管理人员不适用加班费，按调休或年度奖金机制处理。 <!-- a:sec-3 -->",
        ["sec-1", "sec-3"])
    d = Doc("ITC-001", "信息系统变更制度", "policies/ITC-001.md", "technology", "md", 5,
            "2025-03-01", "2025-03-15", None)
    add(d, d.front_matter() + "# 信息系统变更制度\n\n"
        "第一条 生产系统变更须经变更评审并附回滚方案。\n"
        "第二条 紧急变更可先执行，须在 24 小时内补办评审记录。\n"
        "第三条 变更记录须包含：计划时间、实际执行时间、记录时间。 <!-- a:sec-3 -->", ["sec-3"])
    d = Doc("MET-001", "指标口径说明", "finance/MET-001-指标口径.md", "finance", "md", 4,
            "2026-01-05", "2026-01-10", None)
    body = [d.front_matter(), "# 指标口径说明\n",
            h(2, "sec-1", "1. 毛利率 =（营业收入 − 营业成本）÷ 营业收入，按不含税口径。 <!-- a:def-gm -->"),
            "2. GMV：下单口径，含取消订单与退款订单。 <!-- a:def-gmv -->",
            "3. 净GMV = GMV − 取消订单金额 − 全额退款订单金额。 <!-- a:def-netgmv -->",
            "4. 收入：权责发生制确认，不含增值税。",
            "5. 预算执行率 = 实际发生额 ÷ 预算额。 <!-- a:def-budget -->",
            "6. 术语对应：毛利润率与毛利率为同一指标；平台服务费、平台手续费、渠道服务费、交易服务费在不同平台语境下为同义表述，但费率随平台不同。 <!-- a:sec-syn -->"]
    docs.append(add(d, "\n".join(body),
                    ["sec-1", "def-gm", "def-gmv", "def-netgmv", "def-budget", "sec-syn"]))
    return docs


def build_org():
    docs = []
    w = all_entities()
    d = Doc("ORG-001", "2025年度组织手册", "historical/ORG-001-2025组织手册.md", "hr", "md", 5,
            "2025-12-20", "2026-01-01", "2026-05-31", status="superseded")
    emp_lines = []
    for e in w["employees"][:40]:
        dept = "财务部" if e["employee_id"] == "E012" else e["department"]
        emp_lines.append(f"- {e['employee_id']} {e['name']}｜{dept}｜{REGIONS[e['region']]}｜{e['role']}")
    first = add(d, d.front_matter() + "# 2025年度组织手册\n\n"
        "本手册为 2026 年初组织快照，2026 年年中调整后以最新公告为准。\n\n"
        "## 主要人员名录 <!-- a:tbl-org -->\n\n" + "\n".join(emp_lines) + "\n", ["tbl-org"])
    d = Doc("ORG-002", "组织架构与人员异动公告", "hr/ORG-002-组织架构与异动.md", "hr", "md", 5,
            "2026-06-05", "2026-06-05", None)
    body = [d.front_matter(), "# 组织架构与人员异动公告\n",
            h(2, "sec-1", "一、组织架构"),
            "```\n集团\n ├─ 中国区\n │   ├─ 华南区（广州、深圳）\n │   ├─ 华东区（上海、杭州）\n │   └─ 华北区（北京）\n ├─ 中国香港区\n ├─ 东南亚区\n ├─ 欧洲区\n └─ 北美区\n```\n"]
    dept_rows = [[dept, f"{DEPT_HEADS[dept]}"] for dept in DEPARTMENTS]
    body += [h(2, "sec-2", "二、部门负责人表"), md_table(["部门", "负责人ID"], dept_rows), "\n"]
    body += [h(2, "sec-3", "三、人员异动"),
             "3.1 自 2026-06-01 起，林晓芳（E012）由财务部调至运营部，任华东区运营专员。 <!-- a:sec-3-1 -->",
             "3.2 杜鹏（E044）于 2026-03-31 离职，相关权限已回收。 <!-- a:sec-3-2 -->"]
    return [first, add(d, "\n".join(body), ["sec-1", "sec-2", "sec-3", "sec-3-1", "sec-3-2"])]


# ================================================================ conflicts
def build_conflicts():
    docs = []
    d1 = Doc("CON-001", "华东区销售部通知：住宿标准调整", "conflicts/CON-001-华东销售通知.md",
             "conflicts", "md", 3, "2026-03-01", "2026-03-15", None)
    add(d1, d1.front_matter() + "# 华东区销售部通知\n\n"
        "经华东区销售部研究决定，自 2026-03-15 起，华东区销售部员工一线城市差旅住宿上限上调至 700 元/晚。\n"
        "（发布部门：华东区销售部；authority_level: 3）", ["sec-1"])
    d2 = Doc("CON-002a", "运营部通知：住宿报销上限", "conflicts/CON-002a-运营部通知.md",
             "conflicts", "md", 3, "2026-04-01", "2026-04-10", None)
    add(d2, d2.front_matter() + "# 运营部通知\n\n"
        "自 2026-04-10 起，运营部员工一线城市差旅住宿报销上限按 520 元/晚执行。"
        "已向合规部备案（备案号 BA-2026-018）。", ["sec-1"])
    d3 = Doc("CON-002b", "行政部通知：住宿报销上限", "conflicts/CON-002b-行政部通知.md",
             "conflicts", "md", 3, "2026-04-02", "2026-04-15", None)
    add(d3, d3.front_matter() + "# 行政部通知\n\n"
        "自 2026-04-15 起，全体员工一线城市差旅住宿报销上限按 530 元/晚执行。"
        "已向合规部备案（备案号 BA-2026-019）。", ["sec-1"])
    d4 = Doc("COMP-REG-001", "合规备案登记表", "audit/COMP-REG-001-备案登记.md", "audit", "md", 4,
             "2026-06-30", "2026-06-30", None)
    add(d4, d4.front_matter() + "# 合规备案登记表（截至 2026-06-30）\n\n"
        + md_table(["备案号", "事项", "备案日期"],
                   [["BA-2026-011", "华南区市内交通补贴上浮10%", "2026-02-01"],
                    ["BA-2026-018", "运营部一线住宿520元/晚", "2026-04-05"],
                    ["BA-2026-019", "行政部一线住宿530元/晚", "2026-04-06"]]) + "\n\n"
        "备注：截至本表出具日，未收到华东区销售部 700 元/晚通知的备案申请。 <!-- a:fn-reg -->",
        ["tbl-reg", "fn-reg"])
    return docs


# ================================================================ finance docs
def build_finance_docs(w):
    docs = []
    fin = w["finance_monthly"]
    by = {}
    for r in fin:
        by.setdefault(r["month"], {})[r["region"]] = r
    order_regions = ["RG-SOUTH", "RG-EAST", "RG-NORTH", "RG-HK", "RG-SEA", "RG-EU"]
    # 2026-01..2026-08 月报：单位“万元”（陷阱）；2025-12 月报：单位“元”
    for month in ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
                  "2026-07", "2026-08", "2025-12"]:
        y, m = month.split("-")
        rows = []
        for reg in order_regions:
            r = by[month][reg]
            rows.append([REGIONS[reg], r["revenue"], r["cost"], r["gross_profit"]])
        unit, div = ("万元", 10_000) if y == "2026" else ("元", 1)
        disp = [[x[0], round(x[1] / div), round(x[2] / div), round(x[3] / div)] for x in rows]
        d = Doc(f"FIN-RPT-{month.replace('-', '')}", f"{y}年{int(m)}月经营分析报告",
                f"finance/FIN-RPT-{month.replace('-', '')}.md", "finance", "md", 4,
                f"{int(y) if y=='2025' else int(y)}-{m}-25" if y == "2025" else f"{y}-{m}-25",
                f"{y}-{m}-01", None)
        body = [d.front_matter(), f"# {y}年{int(m)}月经营分析报告\n",
                h(2, "tbl-fin", f"各区域经营数据（金额单位：{unit}，人民币）"),
                md_table(["区域", "收入", "成本", "毛利"], disp),
                f"> 脚注：本表金额单位为{unit}；毛利率=（收入−成本）÷收入，口径见《指标口径说明》。 <!-- a:fn-unit -->\n",
                f"（发布日期：{y}-{m}-25；数据快照日期：{month} 月末）"]
        docs.append(add(d, "\n".join(body), ["tbl-fin", "fn-unit"]))
    # 欧洲区说明
    eu6 = by["2026-06"]["RG-EU"]
    eur = round(eu6["revenue"] / 7.8 / 1000) * 1000
    d = Doc("FIN-EU-NOTE", "欧洲区财务列报说明", "finance/FIN-EU-NOTE.md", "finance", "md", 4,
            "2026-07-05", "2026-07-05", None)
    add(d, d.front_matter() + "# 欧洲区财务列报说明\n\n"
        f"欧洲区本地报表以欧元列示。2026 年 6 月欧洲区本地报表收入为 {eur:,} 欧元，"
        "按月初汇率 7.8 折合人民币列报；人民币口径数据以集团月报为准。 <!-- a:sec-1 -->\n",
        ["sec-1"])
    d = Doc("FIN-SALES-NOTE", "销售与订单数据口径说明", "finance/FIN-SALES-NOTE.md", "finance", "md", 4,
            "2026-01-05", "2026-01-05", None)
    add(d, d.front_matter() + "# 销售与订单数据口径说明\n\n"
        f"1. 订单明细表、订单导出文件中的金额字段均为不含税口径。 <!-- a:sec-1 -->\n"
        f"2. 增值税率：{int(F.TAX_RATE * 100)}%。含税金额 = 不含税金额 ×（1 + 税率）。 <!-- a:sec-2 -->\n"
        "3. 退款金额同样按不含税口径记录。", ["sec-1", "sec-2"])
    # 半年度经营分析（因果题素材）
    d = Doc("FIN-YOY-2026H1", "2026年半年度经营分析", "finance/FIN-YOY-2026H1.md", "finance", "md", 4,
            "2026-07-20", "2026-07-20", None)
    body = [d.front_matter(), "# 2026年半年度经营分析\n",
            h(2, "sec-1", "一、总体经营情况"),
            h(2, "sec-2", "二、毛利率变动分析"),
            "2.1 2026 年上半年集团综合毛利率较 2025 年同期有所下降。 <!-- a:sec-2-1 -->",
            "2.2 主要受电子元器件、包装材料等原材料采购价格上涨影响，采购成本占收入比重上升。 <!-- a:sec-2-2 -->",
            "2.3 同时，国际运输成本自 2025 年下半年以来持续上涨，对物流相关毛利产生负面影响。 <!-- a:sec-2-3 -->",
            "2.4 本报告未对上述因素做归因权重分解，亦未排除其他未列示因素的影响。 <!-- a:fn-causal -->"]
    docs.append(add(d, "\n".join(body), ["sec-1", "sec-2", "sec-2-1", "sec-2-2", "sec-2-3", "fn-causal"]))
    # 预算说明
    d = Doc("FIN-BUDGET-2026", "2026年度部门预算说明", "finance/FIN-BUDGET-2026.md", "finance", "md", 4,
            "2026-01-15", "2026-01-15", None)
    rows = [[b["department"], f"{b['budget']:,}", f"{b['actual']:,}"] for b in w["dept_budget_2026"]]
    add(d, d.front_matter() + "# 2026年度部门预算说明\n\n"
        "预算执行率 = 实际发生额 ÷ 预算额（截至 2026-08-31）。\n\n"
        + md_table(["部门", "预算（元）", "实际（元）"], rows) + "\n", ["tbl-budget"])
    # 事业部级毛利表（Top-N 平手素材）—— 同时输出 CSV
    rows = [[b["bu"], b["revenue"], b["cost"]] for b in w["bu_margin_2026h1"]]
    d = Doc("FIN-BU-2026H1", "2026年上半年事业部毛利表", "finance/FIN-BU-2026H1.md", "finance", "md", 4,
            "2026-07-25", "2026-07-25", None)
    add(d, d.front_matter() + "# 2026年上半年事业部毛利表\n\n"
        "（金额单位：元，不含税） <!-- a:tbl-bu -->\n\n"
        + md_table(["事业部", "收入", "成本"], rows) + "\n", ["tbl-bu"])
    return docs


def build_finance_structured(w):
    files = []
    # CSV
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(w["finance_monthly"][0].keys()))
    writer.writeheader()
    writer.writerows(w["finance_monthly"])
    files.append(("structured/fin_monthly.csv", buf.getvalue()))
    files.append(("structured/fin_monthly.json",
                  json.dumps(w["finance_monthly"], ensure_ascii=False, indent=1)))
    buf = io.StringIO()
    cw = csv.DictWriter(buf, fieldnames=["department", "budget", "actual"])
    cw.writeheader(); cw.writerows(w["dept_budget_2026"])
    files.append(("structured/dept_budget_2026.csv", buf.getvalue()))
    buf = io.StringIO()
    cw = csv.DictWriter(buf, fieldnames=["bu", "revenue", "cost"])
    cw.writeheader(); cw.writerows(w["bu_margin_2026h1"])
    files.append(("structured/bu_margin_2026h1.csv", buf.getvalue()))
    tax = "tax_type,rate\n增值税(一般纳税人),0.13\n"
    files.append(("structured/tax_rates.csv", tax))
    sql = ("-- 员工主数据（快照 2026-08-31）\nCREATE TABLE employee_directory (\n  employee_id TEXT PRIMARY KEY,\n  name TEXT,\n  department TEXT,\n  region TEXT,\n  role TEXT,\n  grade TEXT,\n  employment_type TEXT,\n  status TEXT\n);\n")
    for e in w["employees"][:60]:
        sql += (f"INSERT INTO employee_directory VALUES ('{e['employee_id']}','{e['name']}',"
                f"'{e['department']}','{REGIONS[e['region']]}','{e['role']}','{e['grade']}',"
                f"'{e['employment_type']}','{e['status']}');\n")
    files.append(("structured/employee_directory.sql", sql))
    return files


# ================================================================ procurement docs
def build_procurement_docs(w):
    docs, files = [], []
    d = Doc("SUP-EVAL-2026A", "2026年上半年供应商评估与质量报告", "procurement/SUP-EVAL-2026A.md",
            "procurement", "md", 4, "2026-07-30", "2026-07-30", None)
    sup = {s["supplier_id"]: s for s in w["suppliers"]}
    rows = [[sup[s]["supplier_name"], s, sup[s]["rating"], f'{sup[s]["delay_rate_pct"]}%',
             sup[s]["payment_terms"]] for s in ["S001", "S003", "S004", "S005", "S006", "S017"]]
    body = [d.front_matter(), "# 2026年上半年供应商评估与质量报告\n",
            h(2, "tbl-eval", "重点供应商评估结果"),
            md_table(["供应商", "编号", "评级", "交付延期率", "付款条件"], rows),
            "1.1 星辰物流（S001）交付延期率连续两个考核期高于 5%，建议加强履约督导。 <!-- a:sec-1 -->",
            "1.2 蓝海包装（S004）延期率 12%，评级维持 C，列入观察名单。",
            "1.3 恒远电子（S003）履约良好，延期率 3%。"]
    docs.append(add(d, "\n".join(body), ["tbl-eval", "sec-1"]))
    # 供应商注册表 CSV
    buf = io.StringIO()
    cw = csv.DictWriter(buf, fieldnames=list(w["suppliers"][0].keys()))
    cw.writeheader(); cw.writerows(w["suppliers"])
    files.append(("structured/supplier_registry.csv", buf.getvalue()))
    # 谈判纪要
    d = Doc("NEG-001", "星辰物流年度谈判纪要", "procurement/NEG-001-星辰物流谈判纪要.md",
            "procurement", "md", 2, "2025-12-20", "2026-01-01", None)
    add(d, d.front_matter() + "# 星辰物流（S001）年度谈判纪要\n\n"
        "时间：2025-12-20｜参与：采购部、星辰物流\n\n"
        "1. 议定 2026 年度付款条件：验收后 60 天付款（维持）。 <!-- a:sec-1 -->\n"
        "2. 运输报价为含运费总价，燃油附加费另计。 <!-- a:sec-2 -->\n"
        "3. 星辰物流提出将评级考核与旺季运力保障挂钩。", ["sec-1", "sec-2"])
    # PO 记录（审计素材）
    po_rows = [["PR-2026-0218", "2026-02-10", "市场部", "S003", 62000, "未获采购总监审批"],
               ["PR-2026-0231", "2026-02-05", "客服部", "S006", 48000, "已审批（采购总监）"],
               ["PR-2026-0102", "2026-01-08", "运营部", "S004", 32000, "已审批（采购总监）"],
               ["PR-2026-0340", "2026-03-02", "信息技术部", "S002", 158000, "已审批（采购总监+CFO）"],
               ["PR-2026-0421", "2026-04-11", "采购部", "S017", 8600, "已审批（部门负责人）"],
               ["PR-2026-0515", "2026-05-06", "运营部", "S001", 96000, "已审批（采购总监）"]]
    buf = io.StringIO()
    cw = csv.writer(buf)
    cw.writerow(["po_id", "date", "department", "supplier_id", "amount_tax_incl", "approval_status"])
    cw.writerows(po_rows)
    files.append(("structured/po_records.csv", buf.getvalue()))
    return docs, files


# ================================================================ legal
def build_legal_docs():
    docs = []
    d = Doc("CT-001", "恒远电子采购主合同", "legal/CT-001-恒远主合同.md", "legal", "md", 5,
            "2025-10-01", "2025-10-01", None)
    body = [d.front_matter(), "# 恒远电子采购主合同（CT-001）\n",
            "甲方：星环科技集团　乙方：恒远电子科技有限公司（S003）",
            h(2, "sec-3", "第三条 付款"),
            "3.1 甲方于验收合格后 30 天内支付货款。",
            h(2, "sec-4", "第四条 价格"),
            "4.1 本合同单价均为含税单价。"]
    docs.append(add(d, "\n".join(body), ["sec-3", "sec-4"]))
    d = Doc("CT-001-S1", "恒远电子采购合同补充协议一", "legal/CT-001-S1-补充协议.md", "legal", "md", 5,
            "2026-02-10", "2026-03-01", None)
    body = [d.front_matter(), "# 补充协议一（CT-001-S1）\n",
            h(2, "sec-1", "第一条 将主合同第三条付款期限变更为：验收合格后 60 天内支付。本协议自 2026-03-01 起生效。"),
            "第二条 本协议未变更的其他条款，继续按主合同执行。"]
    docs.append(add(d, "\n".join(body), ["sec-1", "sec-2"]))
    d = Doc("CT-001-N1", "恒远电子采购合同变更通知", "legal/CT-001-N1-变更通知.md", "legal", "md", 5,
            "2026-05-20", "2026-06-01", None)
    body = [d.front_matter(), "# 变更通知（CT-001-N1）\n",
            h(2, "sec-1", "第一条 自 2026-06-01 起，全部供货单价在现行价格基础上上调 3%。"),
            "第二条 本通知仅涉及价格条款，付款期限等其他条款不因本通知变更。 <!-- a:fn-scope -->"]
    docs.append(add(d, "\n".join(body), ["sec-1", "fn-scope"]))
    d = Doc("LEG-001", "法务意见书：供应商NDA豁免", "legal/LEG-001-法务意见书.md", "legal", "md", 4,
            "2025-11-10", "2025-11-15", None)
    body = [d.front_matter(), "# 法务意见书\n",
            h(2, "sec-1", "一、关于 NDA 豁免"),
            "2.1 经审查，低敏级物料供应商且单笔采购金额低于 10,000 元的，可豁免签署 NDA，"
            "该口径与《采购管理办法》附录一致。 <!-- a:sec-2 -->",
            h(2, "sec-3", "二、关于合同效力"),
            "3.1 补充协议生效后，主合同被变更条款以补充协议为准；变更通知仅在声明范围内有效。"]
    docs.append(add(d, "\n".join(body), ["sec-1", "sec-2", "sec-3"]))
    d = Doc("CT-002", "供应商报价单（恒远电子 2026）", "legal/CT-002-报价单.md", "legal", "md", 2,
            "2026-01-15", "2026-01-15", None)
    d.acl = "confidential"
    body = [d.front_matter(), "# 供应商报价单（机密）\n",
            h(2, "sec-1", "恒远电子（S003）2026 年度含税报价：A 型连接器 218 元/件；B 型线束 96 元/件。"),
            "本报价单为机密（confidential）级，仅限财务相关角色与系统管理员访问。"]
    docs.append(add(d, "\n".join(body), ["sec-1"]))
    return docs


# ================================================================ ecommerce
def build_ecommerce_docs(w):
    docs, files = [], []
    d = Doc("EC-001", "平台费用规则说明", "ecommerce/EC-001-平台费用规则.md", "ecommerce", "md", 3,
            "2026-01-08", "2026-01-15", None)
    add(d, d.front_matter() + "# 平台费用规则说明\n\n"
        "1. 天猫：平台服务费 = 订单金额 × 2.5%。 <!-- a:sec-1 -->\n"
        "2. 京东：平台手续费 = 订单金额 × 2%。 <!-- a:sec-2 -->\n"
        "3. 抖音：渠道服务费 = 订单金额 × 5%。 <!-- a:sec-3 -->\n"
        "4. Shopify：交易服务费 = 订单金额 × 2.9% + 0.3 美元/单。 <!-- a:sec-4 -->\n"
        "5. 以上费率均按不含税订单金额计算。", ["sec-1", "sec-2", "sec-3", "sec-4"])
    # SKU registry
    rows = []
    for p in w["products"]:
        rows.append([p["internal_sku"], p["product_name"], p["brand"], p["platform_sku"],
                     p["platform"], "是" if p["is_digital"] else "否"])
    for a in w["sku_aliases"]:
        rows.append([a["alias"], f"（旧编号，对应 {a['internal_sku']}）", "-", "-", "-", "否"])
    buf = io.StringIO()
    cw = csv.writer(buf)
    cw.writerow(["internal_sku", "product_name", "brand", "platform_sku", "platform", "is_digital"])
    cw.writerows(rows)
    files.append(("structured/sku_registry.csv", buf.getvalue()))
    d = Doc("SKU-REG", "SKU 主数据登记说明", "ecommerce/SKU-REG-主数据.md", "ecommerce", "md", 3,
            "2026-01-05", "2026-01-05", None)
    body = [d.front_matter(), "# SKU 主数据登记说明\n",
            h(2, "sec-1", "1. 平台 SKU 与内部 SKU 的映射关系以《sku_registry.csv》为准，历史旧编号（如 SK-10028、TM-10028）已停用，仅作追溯。"),
            h(2, "sec-2", "2. 组合装：B2001 = M10028 + M10029（AeroBuds Pro X2 无线套装）；B2002 = M10001 + M10033。 <!-- a:sec-bundle -->"),
            h(2, "sec-3", "3. M10028S 为 M10028 的升级换代款（X2S），两者为不同商品，严禁混用。 <!-- a:sec-near -->")]
    docs.append(add(d, "\n".join(body), ["sec-1", "sec-2", "sec-3", "sec-bundle", "sec-near"]))
    # 物流异常说明（引用真实订单）
    douyin_2603 = [o for o in w["orders"] if o["platform"] == "抖音" and o["order_date"].startswith("2026-03")]
    oid = douyin_2603[0]["order_id"]
    d = Doc("EC-002", "物流异常说明", "ecommerce/EC-002-物流异常.md", "ecommerce", "md", 3,
            "2026-03-20", "2026-03-20", None)
    add(d, d.front_matter() + "# 物流异常说明\n\n"
        f"1. 订单 {oid} 因未在承诺 48 小时内发货，被平台判定为“发货超时异常”。 <!-- a:sec-1 -->\n"
        "2. 根因：广州仓库存同步延迟——仓务系统（SYS-WMS）库存接口当日出现两次同步失败，"
        "导致可售库存虚高而无法及时推单。 <!-- a:sec-2 -->\n"
        "3. 处置：对受影响订单补偿优惠券，并对库存同步任务增加重试与告警。", ["sec-1", "sec-2"])
    # 订单结构化
    o26 = [o for o in w["orders"] if o["order_date"].startswith("2026")]
    o25 = [{k: v for k, v in o.items() if k != "note"}
           for o in w["orders"] if o["order_date"].startswith("2025")]
    buf = io.StringIO()
    cw = csv.DictWriter(buf, fieldnames=[k for k in o26[0].keys() if k != "note"],
                        extrasaction="ignore")
    cw.writeheader(); cw.writerows(o26)
    files.append(("structured/orders_2026.csv", buf.getvalue()))
    files.append(("structured/orders_2025.json",
                  json.dumps(o25, ensure_ascii=False, indent=1)))
    return docs, files


# ================================================================ IT
def build_it_docs(sysd):
    docs = []
    d = Doc("IT-ARCH-001", "系统架构说明", "technology/IT-ARCH-001-架构.md", "technology", "md", 4,
            "2026-01-20", "2026-02-01", None)
    sys_rows = [[s["system_id"], s["name"], ", ".join(s["services"])] for s in sysd["systems"]]
    body = [d.front_matter(), "# 系统架构说明\n",
            h(2, "sec-1", "一、系统与服务清单"),
            md_table(["系统", "名称", "服务"], sys_rows),
            h(2, "sec-2", "二、服务-数据库映射"),
            md_table(["服务", "数据库"], [[k, v] for k, v in sysd["service_db"].items()]),
            "API 的调用与数据归属以上表为准；具体表结构见《数据库 Schema 说明》（IT-DB-001）。 <!-- a:xref-db -->"]
    docs.append(add(d, "\n".join(body), ["sec-1", "sec-2", "xref-db"]))
    d = Doc("IT-API-001", "订单 API 文档", "technology/IT-API-001-订单API.md", "technology", "md", 4,
            "2026-01-25", "2026-02-01", None)
    body = [d.front_matter(), "# 订单 API 文档\n",
            h(2, "sec-1", "1. POST /orders/{{id}}/cancel —— 取消订单"),
            "2. 由订单中台 order-api 服务提供。 <!-- a:sec-svc -->",
            "3. 处理流程：\n   3.1 校验订单状态（仅“待发货”可取消）；\n"
            "   3.2 调用 inventory-api 释放占用库存；\n"
            "   3.3 将订单状态更新为 CANCELLED，并记录取消原因。 <!-- a:sec-flow -->",
            "4. 服务与数据库的对应关系参见《系统架构说明》（IT-ARCH-001）。 <!-- a:xref-arch -->"]
    docs.append(add(d, "\n".join(body), ["sec-1", "sec-svc", "sec-flow", "xref-arch"]))
    d = Doc("IT-DB-001", "数据库 Schema 说明", "technology/IT-DB-001-schema.md", "technology", "md", 4,
            "2026-01-22", "2026-02-01", None)
    rows = []
    for db, tables in sysd["databases"].items():
        for t, cols in tables.items():
            rows.append([db, t, ", ".join(cols)])
    body = [d.front_matter(), "# 数据库 Schema 说明\n",
            h(2, "sec-1", "核心库表清单"), md_table(["数据库", "表", "字段"], rows),
            "order_info.status 记录订单状态（PAID/SHIPPED/CANCELLED/REFUNDED）。 <!-- a:sec-note -->"]
    docs.append(add(d, "\n".join(body), ["sec-1", "sec-note"]))
    d = Doc("IT-OPS-001", "运维手册（摘要）", "technology/IT-OPS-001-运维手册.md", "technology", "md", 3,
            "2026-02-10", "2026-02-10", None)
    add(d, d.front_matter() + "# 运维手册（摘要）\n\n"
        "1. 生产发布窗口：周二/周四 22:00 后。\n2. 所有发布须具备回滚方案。\n"
        "3. 退款相关接口故障按 P1 级响应。", ["sec-1"])
    d = Doc("CHG-2026-004", "变更记录 CHG-2026-004", "technology/CHG-2026-004-变更记录.md",
            "technology", "md", 3, "2026-06-13", "2026-06-13", None)
    add(d, d.front_matter() + "# 变更记录 CHG-2026-004\n\n"
        "- 变更对象：order-api v2.3 发布\n"
        "- 事件发生时间（event_at）：2026-06-12 22:00\n"
        "- 记录时间（recorded_at）：2026-06-13 09:30\n"
        "- 公告发布时间（published_at）：2026-06-14 10:00\n"
        "- 变更内容：取消订单接口增加风控校验，订单状态流转逻辑不变。 <!-- a:sec-1 -->\n", ["sec-1"])
    d = Doc("INC-2026-018", "故障记录 INC-2026-018", "technology/INC-2026-018-故障.md",
            "technology", "md", 3, "2026-05-21", "2026-05-21", None)
    add(d, d.front_matter() + "# 故障记录 INC-2026-018\n\n"
        "1. 时间：2026-05-20 14:10 至 16:40，退款到账延迟。 <!-- a:sec-1 -->\n"
        "2. 影响面：refund-api 调用 pay-api 超时，涉及订单 213 笔，均已恢复。\n"
        "3. 后续：为退款链路增加降级队列。", ["sec-1"])
    # YAML 服务地图
    yl = ["systems:"]
    for s in sysd["systems"]:
        yl.append(f"  - id: {s['system_id']}")
        yl.append(f"    name: {s['name']}")
        yl.append(f"    services: [{', '.join(s['services'])}]")
    return docs, [("structured/system_service_map.yaml", "\n".join(yl) + "\n")]


# ================================================================ projects
def build_project_docs():
    docs = []
    d = Doc("PRD-001", "PRD：星链智能客服项目", "projects/PRD-001.md", "projects", "md", 3,
            "2025-11-20", "2025-11-20", None)
    add(d, d.front_matter() + "# PRD：星链智能客服项目\n\n"
        "1. 背景：客服人力成本年增 25%，高峰期响应时长超标。 <!-- a:sec-1 -->\n"
        "2. 目标：上线智能客服，分流 40% 常见问题。\n"
        "3. 约束：2026 年内完成上线。", ["sec-1"])
    d = Doc("SOL-001", "星链项目候选方案对比", "projects/SOL-001-方案对比.md", "projects", "md", 3,
            "2025-12-15", "2025-12-15", None)
    body = [d.front_matter(), "# 候选方案对比\n",
            h(2, "tbl-1", "方案对比"),
            md_table(["维度", "方案A（自研）", "方案B（采购中科软件S005）"],
                     [["总成本", "480 万元", "320 万元"],
                      ["交付周期", "9 个月", "4 个月"],
                      ["团队", "新增5名算法工程师", "含一年维保"]])]
    docs.append(add(d, "\n".join(body), ["tbl-1"]))
    d = Doc("MTG-001", "星链项目评审会议纪要", "projects/MTG-001-会议纪要.md", "projects", "md", 1,
            "2026-01-15", "2026-01-15", None)
    body = [d.front_matter(), "# 星链项目评审会议纪要（2026-01-15）\n",
            h(2, "sec-2", "二、讨论要点"),
            "2.1 财务部通报：2026 年 IT 预算整体压缩，要求优先控本。 <!-- a:mtg-budget -->",
            "2.2 与会方对比了方案A与方案B的成本与交付周期（详见《候选方案对比》SOL-001）。",
            "2.3 运营部提示：旺季前上线时间不可推迟。"]
    docs.append(add(d, "\n".join(body), ["sec-2", "mtg-budget"]))
    d = Doc("DEC-001", "星链项目决策记录", "projects/DEC-001-决策记录.md", "projects", "md", 4,
            "2026-02-01", "2026-02-01", None)
    body = [d.front_matter(), "# 星链项目决策记录\n",
            h(2, "sec-2", "二、决策"),
            "2.1 决定采用方案B（采购中科软件）。 <!-- a:dec-choice -->",
            "2.2 决策依据：方案B总成本（320万）低于方案A（480万），交付周期（4个月）短于方案A（9个月），"
            "满足旺季前上线要求。 <!-- a:dec-reasons -->",
            "2.3 本记录未对决策因素做权重排序，亦未声明预算因素为唯一原因。 <!-- a:fn-dec -->"]
    docs.append(add(d, "\n".join(body), ["sec-2", "dec-choice", "dec-reasons", "fn-dec"]))
    d = Doc("ACC-001", "星链项目验收报告", "projects/ACC-001-验收报告.md", "projects", "md", 4,
            "2026-07-10", "2026-07-10", None)
    add(d, d.front_matter() + "# 星链项目验收报告\n\n"
        "验收结论：通过。智能客服分流率达 43%，达成 PRD 目标。 <!-- a:sec-1 -->", ["sec-1"])
    d = Doc("PRD-002", "PRD：华东仓自动化项目", "projects/PRD-002.md", "projects", "md", 3,
            "2026-02-10", "2026-02-10", None)
    add(d, d.front_matter() + "# PRD：华东仓自动化项目\n\n"
        "1. 目标：华东仓（上海）分拣效率提升 30%。\n"
        "2. 负责人：周凯（E015）；预算 1,200 万元。 <!-- a:sec-1 -->\n"
        "3. 项目组成员：E015、E052、E037。", ["sec-1"])
    d = Doc("MTG-002", "华东仓自动化项目周会纪要（2026-03）", "projects/MTG-002-周会纪要.md",
            "projects", "md", 1, "2026-03-06", "2026-03-06", None)
    add(d, d.front_matter() + "# 华东仓自动化项目周会纪要（2026-03-06）\n\n"
        "1. 设备到货延期两周，整体进度可控。\n2. 预算执行截至 2026-08-31 为 936 万元。 <!-- a:sec-1 -->",
        ["sec-1"])
    return docs


# ================================================================ audit
def build_audit_docs():
    docs = []
    d = Doc("AUD-001", "2026年一季度内部审计报告", "audit/AUD-001-内审报告.md", "audit", "md", 4,
            "2026-04-20", "2026-04-20", None)
    body = [d.front_matter(), "# 2026年一季度内部审计报告\n",
            h(2, "sec-1", "一、发现事项"),
            "1.1 市场部 2026-02-10 采购申请单 PR-2026-0218，金额 62,000 元（含税），"
            "未获采购总监审批即提交供应商。 <!-- a:case1 -->",
            "1.2 客服部 2026-02-05 采购申请单 PR-2026-0231，金额 48,000 元（含税），已获采购总监审批。 <!-- a:case2 -->",
            h(2, "sec-2", "二、审计意见"),
            "2.1 增值税一般纳税人适用税率 13%；判断审批义务时以不含税金额对照《采购管理办法》第四章。 <!-- a:fn-tax -->",
            "2.2 本报告仅陈述已核实的采购申请事实，未对制度适用性作最终裁定。"]
    docs.append(add(d, "\n".join(body), ["sec-1", "case1", "case2", "sec-2", "fn-tax"]))
    d = Doc("AUD-002", "整改通知（2026-001）", "audit/AUD-002-整改通知.md", "audit", "md", 4,
            "2026-04-25", "2026-04-25", None)
    add(d, d.front_matter() + "# 整改通知\n\n"
        "针对《2026年一季度内部审计报告》发现事项 1.1（PR-2026-0218），责令市场部于 2026-05-15 前"
        "完成补充审批流程整改，并全员学习《采购管理办法》。", ["sec-1"])
    d = Doc("RISK-001", "2026年供应链风险报告", "audit/RISK-001-风险报告.md", "audit", "md", 4,
            "2026-06-30", "2026-06-30", None)
    add(d, d.front_matter() + "# 2026年供应链风险报告\n\n"
        "1. 蓝海包装（S004）延期率 12%，存在断供风险，建议降级并启用备选供应商。 <!-- a:sec-1 -->\n"
        "2. 单一来源采购占比上升，集中度风险偏高。", ["sec-1"])
    return docs


# ================================================================ permissions
def build_permissions_registry(DOC_LIST):
    lines = []
    for d in DOC_LIST:
        roles = {"public": ["employee", "finance", "admin"],
                 "internal": ["employee", "finance", "admin"],
                 "confidential": ["finance", "admin"],
                 "secret": ["admin"]}[d.acl]
        lines.append(dict(doc_id=d.doc_id, classification=d.acl, allowed_roles=roles))
    for ev in F.PERM_EVENTS:
        lines.append(dict(type="acl_event", **ev))
    return lines


# ================================================================ tables registry
def build_tables_registry():
    T = []
    T.append(dict(table_id="TBL-FIN-MONTHLY", file="structured/fin_monthly.csv", format="csv",
                  unit="元", currency="CNY", tax_basis="不含税",
                  columns=["month", "region", "revenue", "cost", "gross_profit", "expense",
                           "budget", "actual"], rows=120,
                  note="欧洲区以人民币折算列报；本地欧元报表见 FIN-EU-NOTE"))
    T.append(dict(table_id="TBL-DEPT-BUDGET", file="structured/dept_budget_2026.csv", format="csv",
                  unit="元", currency="CNY", tax_basis="不适用",
                  columns=["department", "budget", "actual"], rows=9, note="截至2026-08-31"))
    T.append(dict(table_id="TBL-BU-MARGIN", file="structured/bu_margin_2026h1.csv", format="csv",
                  unit="元", currency="CNY", tax_basis="不含税",
                  columns=["bu", "revenue", "cost"], rows=5, note="2026上半年"))
    T.append(dict(table_id="TBL-SUPPLIER", file="structured/supplier_registry.csv", format="csv",
                  unit="不适用", currency="不适用", tax_basis="不适用",
                  columns=["supplier_id", "supplier_name", "country", "category", "rating",
                           "payment_terms", "lead_time_days", "contract_start", "contract_end",
                           "sensitivity", "delay_rate_pct"], rows=29, note="主数据快照2026-08-31"))
    T.append(dict(table_id="TBL-PO", file="structured/po_records.csv", format="csv",
                  unit="元", currency="CNY", tax_basis="含税(amount_tax_incl)",
                  columns=["po_id", "date", "department", "supplier_id", "amount_tax_incl",
                           "approval_status"], rows=6, note="金额为含税口径"))
    T.append(dict(table_id="TBL-SKU", file="structured/sku_registry.csv", format="csv",
                  unit="不适用", currency="不适用", tax_basis="不适用",
                  columns=["internal_sku", "product_name", "brand", "platform_sku", "platform",
                           "is_digital"], rows=18, note="含停用旧编号"))
    T.append(dict(table_id="TBL-ORDERS-2026", file="structured/orders_2026.csv", format="csv",
                  unit="元", currency="CNY", tax_basis="不含税",
                  columns=["order_id", "shop_id", "platform", "sku", "quantity", "unit_price",
                           "discount", "amount_excl_tax", "refund_amount", "customer_id",
                           "warehouse", "order_date"], rows=None,
                  note="金额不含税；口径见 FIN-SALES-NOTE"))
    T.append(dict(table_id="TBL-ORDERS-2025", file="structured/orders_2025.json", format="json",
                  unit="元", currency="CNY", tax_basis="不含税",
                  columns=["order_id", "shop_id", "platform", "sku", "quantity", "unit_price",
                           "discount", "amount_excl_tax", "refund_amount", "customer_id",
                           "warehouse", "order_date"], rows=None, note="金额不含税"))
    T.append(dict(table_id="TBL-EMP-DIR", file="structured/employee_directory.sql", format="sql",
                  unit="不适用", currency="不适用", tax_basis="不适用",
                  columns=["employee_id", "name", "department", "region", "role", "grade",
                           "employment_type", "status"], rows=60, note="快照2026-08-31"))
    T.append(dict(table_id="TBL-TAX", file="structured/tax_rates.csv", format="csv",
                  unit="比率", currency="不适用", tax_basis="不适用",
                  columns=["tax_type", "rate"], rows=1, note="增值税13%"))
    return T


# ================================================================ attachments
def build_attachments():
    files = []
    buf = io.StringIO()
    cw = csv.writer(buf)
    cw.writerow(["city", "tier", "limit_2025H1", "limit_2025H2", "limit_2026", "unit", "note"])
    for c in ["北京", "上海", "广州", "深圳"]:
        note = "2026-07-01起调整为650" if c == "上海" else ""
        cw.writerow([c, "一线", 400, 450, 500, "人民币元/晚", note])
    for c in ["杭州", "成都", "武汉", "南京", "西安", "苏州"]:
        cw.writerow([c, "二线", 300, 350, 400, "人民币元/晚", ""])
    for c in ["佛山", "东莞", "合肥", "郑州", "长沙"]:
        cw.writerow([c, "其他", 250, 280, 320, "人民币元/晚", ""])
    files.append(("attachments/city_hotel_standard_2026.csv", buf.getvalue()))
    expo = "expo_name,city,start,end,surcharge\n广交会（春季）,广州,2026-04-15,2026-05-05,20%\n进博会,上海,2026-11-05,2026-11-10,20%\n"
    files.append(("attachments/expo_list_2026.csv", expo))
    # 将附件注册为可引用文档（Sibling Structure 测试素材）
    d = Doc("ATT-CITY-STD", "城市住宿标准汇总表（附件CSV）",
            "attachments/city_hotel_standard_2026.csv", "attachments", "csv", 3,
            "2026-01-10", "2026-01-10", None)
    add(d, "", [])
    d = Doc("ATT-EXPO", "大型展会清单（附件CSV）", "attachments/expo_list_2026.csv",
            "attachments", "csv", 3, "2026-01-10", "2026-01-10", None)
    add(d, "", [])
    return files


# ================================================================ parser-error doc
def build_parser_error_doc():
    d = Doc("PARSER-001", "2025年度供应商对账单（扫描件转录）", "attachments/PARSER-001-对账单.md",
            "procurement", "md", 3, "2026-01-30", "2026-01-30", None, parser_status="PARTIAL")
    body = [d.front_matter(), "# 2025年度供应商对账单（扫描件转录）\n",
            "【表格跨页，上接第 3 页】 <!-- a:pg1 -->\n",
            md_table(["供应商", "月份", "应付金额"], [["星辰物流", "2025-10", "184,220"],
                                                     ["星辰物流", "2025-11", "【本行因扫描件污损无法识别】"]]),
            "【表格其余部分在下一页，OCR 置信度低】 <!-- a:pg2 -->\n",
            "注：本转录件为 OCR 产物，parser_status=PARTIAL。"]
    return add(d, "\n".join(body), ["pg1", "pg2"])


# ================================================================ main build
def build_all(out_root):
    DOCS.clear()
    w = all_entities()
    sysd = w["systems"]

    for v in F.TRV_VERSIONS:
        build_trv001(v)
    build_trv_cn1()
    build_trv002()
    build_trv003()
    build_decoys()
    build_exp001()
    build_proc()
    build_proc_others()
    build_rma()
    build_faq()
    build_sec_ben()
    build_org()
    build_conflicts()
    build_finance_docs(w)
    pdocs, pfiles = build_procurement_docs(w)
    build_legal_docs()
    edocs, efiles = build_ecommerce_docs(w)
    itdocs, itfiles = build_it_docs(sysd)
    build_project_docs()
    build_audit_docs()
    build_parser_error_doc()

    os.makedirs(out_root, exist_ok=True)
    # write docs
    for d in DOCS:
        d.write(out_root)
    extra_files = list(pfiles) + list(efiles) + list(itfiles) + build_finance_structured(w) + build_attachments()
    for rel, text in extra_files:
        full = os.path.join(out_root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
    # csv snapshot of employees
    buf = io.StringIO()
    cw = csv.DictWriter(buf, fieldnames=list(w["employees"][0].keys()))
    cw.writeheader(); cw.writerows(w["employees"])
    full = os.path.join(out_root, "structured", "hr_employees_snapshot.csv")
    with open(full, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    extra_files.append(("structured/hr_employees_snapshot.csv", None))

    registries = dict(
        documents=[d.meta() for d in DOCS],
        revisions=[dict(revision_id=d.doc_id, doc_id=d.version_of or d.doc_id, version=d.doc_id,
                        published_at=d.published, effective_from=d.eff_from,
                        effective_to=d.eff_to, supersedes=d.supersedes, status=d.status)
                   for d in DOCS],
        permissions=build_permissions_registry(DOCS),
        tables=build_tables_registry(),
    )
    return w, registries, [f for f, _ in extra_files]
