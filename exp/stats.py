# -*- coding: utf-8 -*-
"""配对统计：paired bootstrap 95% CI、paired permutation、Wilcoxon signed-rank（§26）。"""
import math
import random

from config import BOOTSTRAP_N, PERMUTATION_N, SEED


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def percentile(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def paired_bootstrap_ci(diffs, n=BOOTSTRAP_N, alpha=0.05, seed=SEED):
    """对配对差值做 bootstrap，返回 (mean, lo, hi)。"""
    if not diffs:
        return 0.0, 0.0, 0.0
    rnd = random.Random(seed)
    k = len(diffs)
    means = []
    for _ in range(n):
        s = 0.0
        for _ in range(k):
            s += diffs[rnd.randrange(k)]
        means.append(s / k)
    means.sort()
    lo = means[int(alpha / 2 * n)]
    hi = means[min(n - 1, int((1 - alpha / 2) * n))]
    return mean(diffs), lo, hi


def paired_permutation_p(diffs, n=PERMUTATION_N, seed=SEED):
    """符号翻转置换检验（two-sided）。"""
    if not diffs:
        return 1.0
    obs = abs(mean(diffs))
    rnd = random.Random(seed)
    cnt = 0
    k = len(diffs)
    for _ in range(n):
        s = 0.0
        for d in diffs:
            s += d if rnd.random() < 0.5 else -d
        if abs(s / k) >= obs - 1e-15:
            cnt += 1
    return (cnt + 1) / (n + 1)


def wilcoxon_signed_rank_p(diffs):
    """Wilcoxon 符号秩检验（正态近似 + 平局校正）。"""
    d = [x for x in diffs if abs(x) > 1e-12]
    if not d:
        return 1.0
    ranks = {}
    order = sorted(range(len(d)), key=lambda i: abs(d[i]))
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abs(abs(d[order[j + 1]]) - abs(d[order[i]])) < 1e-12:
            j += 1
        avg = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_plus = sum(ranks[i] for i in range(len(d)) if d[i] > 0)
    w_minus = sum(ranks[i] for i in range(len(d)) if d[i] < 0)
    n = len(d)
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0:
        return 1.0
    z = (min(w_plus, w_minus) - mu) / sigma          # 双侧检验统计量（W = min(W+,W-)）
    p_one_sided = 0.5 * math.erfc(abs(z) / math.sqrt(2))
    return max(0.0, min(1.0, 2 * p_one_sided))


def summarize_paired(a_vals, b_vals, transform=None):
    """A/B 配对指标聚合：mean/P50/P95 + bootstrap CI + permutation p + wilcoxon p。"""
    pairs = [(a, b) for a, b in zip(a_vals, b_vals)]
    if not pairs:
        return {}
    if transform:
        diffs = [transform(a, b) for a, b in pairs]
        a_t = [transform(a, b) for a, b in pairs]
        b_t = [0.0 for _ in pairs]
    else:
        diffs = [a - b for a, b in pairs]
        a_t, b_t = a_vals, b_vals
    m, lo, hi = paired_bootstrap_ci(diffs)
    return dict(
        n=len(pairs), mean_diff=round(m, 6), ci95=[round(lo, 6), round(hi, 6)],
        p_permutation=round(paired_permutation_p(diffs), 5),
        p_wilcoxon=round(wilcoxon_signed_rank_p(diffs), 5),
        mean_a=round(mean(a_t), 6), mean_b=round(mean(b_t), 6),
        p50_a=round(percentile(a_t, 50), 6), p95_a=round(percentile(a_t, 95), 6),
        p50_b=round(percentile(b_t, 50), 6), p95_b=round(percentile(b_t, 95), 6),
    )
