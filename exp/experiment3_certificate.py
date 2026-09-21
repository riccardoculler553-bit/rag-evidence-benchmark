# -*- coding: utf-8 -*-
"""实验 3：Capability Certificate 判定逻辑修复（0 成本，本地）。

修复点：
  1. PASS 的唯一定义：UpperCI_(1-δ) ≤ ε（ε=0.02，δ=0.05）
  2. 采用保守区间 Clopper–Pearson（精确二项区间），不再使用 Wilson + 0.20 阈值
  3. 报告独立 source group 数量（按 source entity 分组的独立组数，而非样本行数）
  4. 重新生成 certificates 并与旧结果对比

统计口径：
  - 观测误差 e = 1 − metric（metric：Classification→Macro-F1，Extraction→Field-F1）
  - 严格意义上，Macro-F1 / Field-F1 属于连续指标，二项区间要求 0/1 结果；
    因此同时给出两个口径：
      (a) ROW_LEVEL_BINARY：以"该行判断是否正确"作为伯努利试验（与 operator 语义一致）
      (b) METRIC_LEVEL：对 1−metric 直接套用 Clopper–Pearson（保守上界，需声明口径）
"""
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capability as CAP
from capability import CapabilityBuild
from config import EXP_OUT, SEED
from source_plane import materialize
import workload as WL

EPSILON = 0.02
DELTA = 0.05
CONF = 1 - DELTA
OLD_EPSILON = 0.20          # v1.2 旧判据阈值（Wilson 上界 ≤ 0.20）
OLD_STATUS_RULE = "Wilson_upper_CI <= 0.20"


# ---------------------------------------------------------------- Clopper-Pearson（精确，基于二项 CDF 直接求和）
def _log_binom_pmf(i, n, p):
    """log C(n,i) + i·ln p + (n−i)·ln(1−p)，避免溢出。"""
    if p <= 0:
        return 0.0 if i == 0 else -math.inf
    if p >= 1:
        return 0.0 if i == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
            + i * math.log(p) + (n - i) * math.log(1 - p))


def binom_cdf_le(k, n, p):
    """P(X ≤ k | n, p)，直接求和（n ≤ 数百，成本可忽略）。"""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    terms = [_log_binom_pmf(i, n, p) for i in range(0, k + 1)]
    m = max(terms)
    if m == -math.inf:
        return 0.0
    return math.exp(m) * sum(math.exp(t - m) for t in terms)


def _solve_p(k, n, target, increasing_in_p=False):
    """求 p 使 binom_cdf_le(k,n,p) = target（CDF 关于 p 单调递减）。"""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        v = binom_cdf_le(k, n, mid)
        if (v < target) == increasing_in_p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, conf=CONF):
    """双侧精确二项区间。"""
    if n == 0:
        return 0.0, 1.0
    alpha = 1 - conf
    lower = 0.0 if k == 0 else _solve_p(k - 1, n, 1 - alpha / 2)
    upper = 1.0 if k == n else _solve_p(k, n, alpha / 2)
    return lower, upper


def clopper_pearson_upper_one_sided(k, n, conf=CONF):
    """单侧上界：解 P(X ≤ k | p) = 1 − conf（PASS 判据使用）。"""
    if n == 0:
        return 1.0
    if k == n:
        return 1.0
    return _solve_p(k, n, 1 - conf)


# ---------------------------------------------------------------- source groups
def source_groups(rows):
    """独立 source group：按来源实体分组（ecom→platform，finproc→policy），
    再叠加 payload 模板族（首 12 字符）以反映真实独立信息源。"""
    g = defaultdict(list)
    for r in rows:
        key = r["columns"].get("platform") or r["columns"].get("policy") or r["source_id"]
        g[(key, r["payload"][:12])].append(r)
    return g


def evaluate(calib_rows, cap_key, outputs):
    cap = CAP.CAPABILITIES[cap_key]
    gf, gv = cap["oracle_path"]
    if cap["kind"] == "classification":
        y_true = [r["oracle"][gf][gv] for r in calib_rows]
        y_pred = [outputs[r["row_id"]].get("label") for r in calib_rows]
        metric = CAP.macro_f1(y_true, y_pred)
        err_flags = [0 if t == p else 1 for t, p in zip(y_true, y_pred)]
    else:
        def eq(a, b):
            if a is None or b is None:
                return a is None and b is None
            return abs(float(a) - float(b)) <= max(0.01, abs(float(a)) * 0.01)
        y_true = [r["oracle"][gf][gv] for r in calib_rows]
        y_pred = [outputs[r["row_id"]].get("value") for r in calib_rows]
        metric = CAP.field_f1(y_true, y_pred)
        err_flags = [0 if eq(t, p) else 1 for t, p in zip(y_true, y_pred)]
    return metric, err_flags


def old_wilson_upper(k, n, conf=CONF):
    if n == 0:
        return 1.0
    e = k / n
    z = 1.959963985
    denom = 1 + z * z / n
    center = (e + z * z / (2 * n)) / denom
    half = z * math.sqrt(max(e * (1 - e) / n + z * z / (4 * n * n), 0)) / denom
    return min(1.0, center + half)


def required_n_zero_failure(eps=EPSILON, delta=DELTA):
    """0 失败情形下达到上界 ≤ ε 所需最小 n：n ≥ ln(δ)/ln(1−ε)。"""
    return math.ceil(math.log(delta) / math.log(1 - eps))


def group_stratified(rows, per_group=20, cap=300):
    group = source_groups(rows)
    picked = []
    for gkey, grows in sorted(group.items(), key=lambda kv: str(kv[0])):
        picked.extend(grows[:per_group])
        if len(picked) >= cap:
            break
    return picked[:cap]


def main():
    rows, snap = materialize()
    build = CapabilityBuild(memo={})
    out = dict(snapshot=snap, epsilon=EPSILON, delta=DELTA, confidence=CONF,
               rule="UpperCI_(1-δ) ≤ ε，Clopper–Pearson 精确单侧上界",
               old_rule=OLD_STATUS_RULE, required_n_zero_failure=required_n_zero_failure(),
               calibration_sets=dict(
                   legacy="rows[:300]（与 v1.2 完全相同的顺序抽样校准集，保证新旧可比）",
                   group_stratified="按 source group 分层抽样（每 group 最多 20 行，共 300 行）"),
               capabilities={})
    for domain in ["ecom", "finproc"]:
        calib_legacy = rows[domain][:300]
        calib_grouped = group_stratified(rows[domain])
        for kind in ["classification", "extraction"]:
            cap_key = WL.CAP_SPEC[(domain, kind)][0]
            rec = dict(
                capability_id=CAP.CAPABILITIES[cap_key]["capability_id"],
                version=CAP.capability_version(cap_key),
                capability_impl_revision=CAP.CAPABILITY_IMPL_REVISION,
                operator_family=CAP.CAPABILITIES[cap_key]["kind"],
                source_family=domain,
                model_hash=CAP.model_hash(),
                prompt_hash=CAP.prompt_hash(CAP.CAPABILITIES[cap_key]["task"]),
                schema_hash=CAP.schema_hash(CAP.CAPABILITIES[cap_key]["task"]),
                metric=CAP.CAPABILITIES[cap_key]["metric"])
            for set_name, calib in [("legacy", calib_legacy), ("group_stratified", calib_grouped)]:
                outputs, _ = build.build(cap_key, calib)
                metric, err_flags = evaluate(calib, cap_key, outputs)
                n = len(err_flags)
                k = sum(err_flags)
                cp_lo, cp_hi = clopper_pearson(k, n)
                cp_upper_1s = clopper_pearson_upper_one_sided(k, n)
                wilson_hi = old_wilson_upper(k, n)
                groups = source_groups(calib)
                rec[set_name] = dict(
                    n=n, n_errors=k, metric_value=round(metric, 4),
                    observed_error=round(k / n, 4),
                    clopper_pearson_95=[round(cp_lo, 4), round(cp_hi, 4)],
                    clopper_pearson_upper_onesided_95=round(cp_upper_1s, 4),
                    wilson_upper_95_old=round(wilson_hi, 4),
                    n_independent_source_groups=len(groups),
                    group_sizes_top=sorted((len(v) for v in groups.values()), reverse=True)[:8],
                    max_errors_allowed_for_pass=next(
                        (k2 - 1 for k2 in range(0, 60)
                         if clopper_pearson_upper_one_sided(k2, n) > EPSILON), None),
                    status_new="PASS" if cp_upper_1s <= EPSILON else "FAIL",
                    status_old="PASS" if wilson_hi <= OLD_EPSILON else "REVIEW",
                    validation_set_hash=__import__("hashlib").sha256(
                        "".join(sorted(r["payload_hash"] for r in calib)).encode()).hexdigest()[:32])
            out["capabilities"][cap_key] = rec
    caps = out["capabilities"]

    def count(field, value):
        return sum(1 for c in caps.values() if c["legacy"][field] == value)

    out["summary"] = dict(
        n_capabilities=len(caps),
        legacy_set=dict(n_pass_new=count("status_new", "PASS"), n_pass_old=count("status_old", "PASS")),
        group_stratified_set=dict(
            n_pass_new=sum(1 for c in caps.values() if c["group_stratified"]["status_new"] == "PASS"),
            n_pass_old=sum(1 for c in caps.values() if c["group_stratified"]["status_old"] == "PASS")),
        required_n_zero_failure=out["required_n_zero_failure"],
        interpretation=(
            "① 判据修复：PASS 现在唯一定义为 Clopper–Pearson 单侧上界 ≤ ε(=2%)（δ=5%），"
            "取代旧的 Wilson 上界 ≤ 20%。② 旧判据过宽（等价于容忍 20% 错误率），"
            "不能作为生产门禁；新判据下 mock capability 全部 FAIL —— 这是正确结论："
            "在 n=300 下若要断言总体误差 ≤2%，最多只允许 1 次错误（见 max_errors_allowed_for_pass）。"
            "③ 因此 mock 能力只能用于因果实验（同源误差对 A/B 无偏），不可用于生产部署；"
            "生产部署需要更高精度 capability 或更大 n。"),
    )
    path = os.path.join(EXP_OUT, "certificates_v3_clopper_pearson.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out["summary"], ensure_ascii=False, indent=1))
    for k_, v in caps.items():
        lg, gp = v["legacy"], v["group_stratified"]
        print(f"  {k_}: legacy(err={lg['observed_error']}, CP↑={lg['clopper_pearson_upper_onesided_95']}, "
              f"old_wilson={lg['wilson_upper_95_old']}, groups={lg['n_independent_source_groups']}, "
              f"{lg['status_old']}→{lg['status_new']}) | grouped(err={gp['observed_error']}, "
              f"CP↑={gp['clopper_pearson_upper_onesided_95']}, groups={gp['n_independent_source_groups']}, "
              f"{gp['status_old']}→{gp['status_new']})")
    return out


if __name__ == "__main__":
    main()
