# -*- coding: utf-8 -*-
"""Phase 0/1：Source Plane + 确定性 Oracle 数据集生成。

Source Plane 统一接口（§29）：
    list / metadata / read(locator) / revision / payload_hash
每条进入 CapabilityBuild 的行必须携带并校验 raw_payload_hash（§3.3）。

数据集来源：rag-evidence-benchmark 的世界模型与结构化文件（真实来源，记录 revision 与 payload_hash），
并按 dterministic 模板扩样到 N=10,000/domain（§7、§22）。每条 oracle 由生成规则直接给出，
与任何模型输出无关（deterministic oracle）。
"""
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import EXP_DATA, N_ROWS_PER_DOMAIN, SEED, ROOT

sys.path.insert(0, os.path.join(ROOT, "gen"))
import world as W  # noqa: E402
import corpus_facts as F  # noqa: E402


def sha256_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ================================================================ 源注册表
SOURCE_FILES = {
    "ecom_orders_2026": "dataset/knowledge/structured/orders_2026.csv",
    "ecom_orders_2025": "dataset/knowledge/structured/orders_2025.json",
    "ecom_sku_registry": "dataset/knowledge/structured/sku_registry.csv",
    "fin_supplier_registry": "dataset/knowledge/structured/supplier_registry.csv",
    "fin_po_records": "dataset/knowledge/structured/po_records.csv",
    "policy_trv_v3": "dataset/knowledge/policies/TRV-001-v3.md",
    "policy_proc_v3": "dataset/knowledge/policies/PROC-001-v3.md",
    "policy_rma": "dataset/knowledge/policies/RMA-001.md",
    "fin_budget": "dataset/knowledge/finance/FIN-BUDGET-2026.md",
}


def build_source_registry():
    reg = {}
    for sid, rel in SOURCE_FILES.items():
        path = os.path.join(ROOT, rel)
        rev = sha256_file(path) if os.path.exists(path) else None
        reg[sid] = dict(source_id=sid, path=rel, revision_id=(rev or "")[:16],
                        revision_hash=rev, exists=os.path.exists(path))
    return reg


class SourcePlane:
    """最小 Source Plane：list / metadata / read(locator) / revision / payload_hash。"""

    def __init__(self, rows):
        self.registry = build_source_registry()
        self.rows = {r["row_id"]: r for r in rows}
        self.locator_index = {r["locator"]: r["row_id"] for r in rows}
        self._payload_cache = {}

    # ---- 接口 ----
    def list_sources(self):
        return sorted(self.registry.keys())

    def metadata(self, source_id):
        return self.registry[source_id]

    def revision(self, source_id):
        return self.registry[source_id]["revision_id"]

    def read(self, locator):
        """读取 payload（含 raw_payload_hash 校验，§3.3）。"""
        rid = self.locator_index.get(locator)
        if rid is None:
            return None
        r = self.rows[rid]
        payload = r["payload"]
        if sha256_text(payload) != r["payload_hash"]:
            raise RuntimeError(f"PAYLOAD_HASH_MISMATCH:{locator}")
        return payload

    def payload_hash(self, locator):
        return self.rows[self.locator_index[locator]]["payload_hash"]

    def relation(self, domain):
        return [r for r in self.rows.values() if r["domain"] == domain]


# ================================================================ Phase 0：ECOM
ECOM_ISSUES = ["logistics_delay", "product_quality", "refund_request", "address_change", "other"]
DEFECTS = ["音质断续", "无法充电", "外壳划痕", "连接不稳定", "屏幕闪烁"]
REGIONS_CN = ["广州", "上海", "北京", "杭州", "成都", "深圳"]

ECOM_TEMPLATES = {
    # 模板中的 {tgt} 为抽取 oracle（目标金额），其余数字为干扰项
    "logistics_delay": "客户{name}反馈：{platform}订单{oid}（{prod}）已{days}天未更新物流轨迹，"
                       "商品金额{tgt}元，要求加急处理。",
    "product_quality": "客户{name}反馈：{prod}出现{defect}，订单金额{tgt}元，"
                       "另提及平台促销原价{high}元，希望换货。",
    "product_quality_reordered": "客户{name}反馈：{prod}出现{defect}，平台促销原价{high}元，"
                                 "订单金额{tgt}元，希望换货。",
    "refund_request": "客户{name}申请退款：{prod}，订单金额{tgt}元，"
                      "已签收{dd}天。{extra}",
    "address_change": "客户{name}要求修改收货地址至{region}：订单{oid}，"
                      "商品金额{tgt}元，请在发货前处理。",
    "other": "客户{name}咨询：{prod}（订单{oid}）的开票信息与保修政策，金额{tgt}元。",
}
REFUND_EXTRA = ["客户同时抱怨物流曾延误2天。", ""]


def gen_ecom_rows():
    w = W.all_entities()
    orders = w["orders"]
    prods = {p["internal_sku"]: p for p in w["products"]}
    custs = {c["customer_id"]: c for c in w["customers"]}
    rnd = random.Random(SEED + 11)
    rows = []
    for i in range(N_ROWS_PER_DOMAIN):
        o = orders[(i * 7 + 3) % len(orders)]
        # 确定性 issue 混合：五类均衡覆盖（乘子与类别数互质 + 低频位移）
        issue = ECOM_ISSUES[(i * 7 + i // 5) % len(ECOM_ISSUES)]
        p = prods[o["sku"]]
        c = custs[o["customer_id"]]
        tgt = int(o["amount_excl_tax"] or 199)
        high = tgt + 600 + (i % 7) * 100
        tpl_key = issue
        if issue == "product_quality" and i % 6 == 0:
            tpl_key = "product_quality_reordered"   # 干扰数字前置 → 抽取易错
        txt = ECOM_TEMPLATES[tpl_key].format(
            name=c["name"][:4], platform=o["platform"], oid=o["order_id"],
            prod=p["product_name"], tgt=tgt, high=high,
            days=2 + i % 6, dd=3 + i % 20, defect=DEFECTS[i % len(DEFECTS)],
            region=REGIONS_CN[i % len(REGIONS_CN)],
            extra=REFUND_EXTRA[i % 2])
        rid = f"ECOM-{i + 1:05d}"
        rows.append(dict(
            row_id=rid, domain="ecom", source_id="ecom_orders_2026",
            revision_id="derived-from-orders-snapshot",
            locator=f"phase0://ecom/{rid}", payload=txt, payload_hash=sha256_text(txt),
            columns=dict(platform=o["platform"], sku=o["sku"], warehouse=o["warehouse"],
                         order_date=o["order_date"], customer_tier=c["tier"],
                         amount_excl_tax=tgt, is_digital=p["is_digital"]),
            oracle=dict(labels=dict(issue=issue), values=dict(amount=tgt)),
        ))
    return rows


# ================================================================ Phase 0：FINPROC
FIN_CLAUSE_KINDS = ["条款", "例外", "脚注", "附录"]
CITIES = (F.TIER1_CITIES + F.TIER2_CITIES + ["佛山", "东莞", "合肥", "郑州", "长沙"])
SUBJECTS = ["住宿", "餐费补贴", "市内交通补贴", "加班餐补", "住宿报销"]
POLICIES = ["TRV-001-v3", "TRV-001-v2", "TRV-001-CN1", "EXP-001-v2", "PROC-001-v3", "RMA-001"]
ROLES = ["普通员工", "M3 管理人员", "M4 管理人员", "VP", "外包人员"]


def gen_finproc_rows():
    rnd = random.Random(SEED + 29)
    rows = []
    for i in range(N_ROWS_PER_DOMAIN):
        kind = FIN_CLAUSE_KINDS[(i * 7 + i // 5) % len(FIN_CLAUSE_KINDS)]
        city = CITIES[i % len(CITIES)]
        pol = POLICIES[(i * 3) % len(POLICIES)]
        subj = SUBJECTS[(i * 7) % len(SUBJECTS)]
        role = ROLES[i % len(ROLES)]
        amt = 300 + (i % 11) * 50
        pct = 10 + (i % 4) * 5
        new_amt = int(round(amt * (1 + pct / 100.0)))
        if kind == "条款":
            tail = "本条自 2026-01-01 起施行。" if i % 7 else "（例外情形除外，见附则。）"
            txt = (f"{pol} 第{1 + i % 9}.{1 + i % 5}条：{role}在{city}的{subj}标准为 {amt} 元。"
                   f"{tail}")
        elif kind == "例外":
            txt = (f"{pol} 例外条款：因大型展会或紧急客户事件，{city}的{subj}上浮 {pct}%，"
                   f"即 {new_amt} 元；注：需经部门负责人审批。")
        elif kind == "脚注":
            if i % 9 == 0:  # 单位陷阱：万元
                wan = round(amt / 10000.0, 2)
                txt = (f"注：{pol} 附表金额单位为人民币万元；{city}{subj}上限为 {wan} 万元，"
                       f"不含服务费。")
            else:
                txt = (f"注：{pol} 附表金额单位均为人民币元；{city}{subj}上限为 {amt} 元，"
                       f"不含服务费。")
        else:
            tail = "（详见注：备案清单。）" if i % 5 == 0 else ""
            txt = (f"附录{chr(65 + i % 6)}：{pol} 免审批/特殊情形清单（第 {1 + i % 8} 项），"
                   f"{city}{subj}标准 {amt} 元，适用于{role}。{tail}")
        rid = f"FIN-{i + 1:05d}"
        rows.append(dict(
            row_id=rid, domain="finproc", source_id="policy_trv_v3",
            revision_id="derived-from-policy-snapshot",
            locator=f"phase0://finproc/{rid}", payload=txt, payload_hash=sha256_text(txt),
            columns=dict(policy=pol, city=city, city_tier=("一线" if city in F.TIER1_CITIES else
                                                           ("二线" if city in F.TIER2_CITIES else "其他")),
                         effective_from="2026-01-01", role=role),
            oracle=dict(labels=dict(clause_kind=kind),
                        values=dict(amount=(new_amt if kind == "例外" else amt))),
        ))
    return rows


# ================================================================ 数据集落盘
def materialize(force=False):
    os.makedirs(EXP_DATA, exist_ok=True)
    paths = {d: os.path.join(EXP_DATA, f"{d}_rows.jsonl") for d in ["ecom", "finproc"]}
    if not force and all(os.path.exists(p) for p in paths.values()):
        rows = {d: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
                for d, p in paths.items()}
        return rows, dataset_snapshot_hash()
    rows = dict(ecom=gen_ecom_rows(), finproc=gen_finproc_rows())
    for d, p in paths.items():
        with open(p, "w", encoding="utf-8") as f:
            for r in rows[d]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(EXP_DATA, "source_registry.json"), "w", encoding="utf-8") as f:
        json.dump(build_source_registry(), f, ensure_ascii=False, indent=1)
    return rows, dataset_snapshot_hash()


def dataset_snapshot_hash():
    h = hashlib.sha256()
    for fn in sorted(os.listdir(EXP_DATA)):
        p = os.path.join(EXP_DATA, fn)
        if os.path.isfile(p):
            h.update(fn.encode())
            h.update(sha256_file(p).encode())
    return h.hexdigest()[:32]


if __name__ == "__main__":
    rows, h = materialize(force=True)
    print({k: len(v) for k, v in rows.items()}, h)
    print(rows["ecom"][0]["payload"])
    print(rows["finproc"][2]["payload"])
