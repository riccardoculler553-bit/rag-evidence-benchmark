# -*- coding: utf-8 -*-
"""v1.2 实验全局配置：固定项、成本模型、阈值、随机种子。

所有"固定项"（§3.1）在此集中定义，harness 会对其做 hash 与一致性校验。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # rag-evidence-benchmark/
EXP = os.path.join(ROOT, "exp")
EXP_DATA = os.path.join(EXP, "dataset")
EXP_OUT = os.path.join(EXP, "runs")

SEED = 20260919
BOOTSTRAP_N = 10000
PERMUTATION_N = 10000

# ---- 实验规模（§7：N=10,000 固定；§22：queries ≥200/domain） ----
N_ROWS_PER_DOMAIN = 10_000
SWEEP = [1, 5, 10, 25, 50, 75, 100]
QUERIES_PER_SWEEP_POINT = 40        # 40 × 7 = 280 paired queries/domain
NATURAL_QUERIES_PER_DOMAIN = 20     # 额外自然谓词查询（realism check）
SPLIT = {"build": 0.60, "dev": 0.20, "blind": 0.20}

DOMAINS = ["ecom", "finproc"]

# ---- batch（§5：主实验强制 batch_size=1）----
BATCH_SIZE = 1

# ---- 成本模型（可替换的 pricing_version；全部为"逻辑调用"计费）----
PRICING = dict(
    pricing_version="mock-2026.09",
    input_per_1k=0.0020,        # 元 / 1K input tokens
    output_per_1k=0.0060,       # 元 / 1K output tokens
    per_call_overhead=0.00002,  # 元 / 次 LLM 调用
    retrieval_per_row=0.0000005,
    validation_per_row=0.0000008,
    synthesis_input_per_1k=0.0020,
    synthesis_output_per_1k=0.0060,
)

# ---- 模拟服务延迟（mock 模型的 service-time 模型；仅用于延迟可比性，报告中明确标注）----
LATENCY = dict(
    ms_per_input_token=0.15,
    ms_per_output_token=0.60,
    ms_per_call_overhead=2.0,
    ms_per_row_scan=0.0008,
    ms_per_row_validation=0.0015,
)

# ---- 模型（§3.1 固定项）----
MODEL_ID = "deterministic-mock-semantic"
MODEL_REVISION = "mock-det-v1"
TEMPERATURE = 0.0
DECODING = "greedy"
TOKENIZER = "char4-bpe-proxy"

# ---- 质量契约 / non-inferiority（§23）----
QUALITY_METRIC = "task_specific"     # Filter→P/R, Extract→Field F1, TopK→Recall@K/NDCG, Classification→Macro-F1
EPSILON_Q = 0.01                     # 质量 non-inferiority 容差（绝对）
NON_INFERIORITY_CONF = 0.95

THRESHOLDS = dict(
    W1_semantic_work_reduction=0.50,
    W1_cost_per_correct_reduction=0.20,
    W1_p95_degradation=0.10,
    W2_semantic_work_reduction=0.25,
    W2_cost_per_correct_reduction=0.10,
    W3_cost_ratio_limit=1.10,
    validation_share_total=0.10,
    validation_share_saving=0.25,
    # 用户指令中的预注册成功条件（W1 目标 50%/30%）
    W1_semantic_work_reduction_min=0.30,
)

# ---- Validation 协议（§15/§16/§17）----
VALIDATION = dict(
    mode="V1_CACHED_CERTIFICATE",   # V0 structural + V1 cached certificate
    sequential_sampling=[30, 60, 120, 240, 300],
    epsilon=0.02,
    delta=0.05,
    certificate_ttl_queries=10_000,
)

# ---- 缓存策略（§10：function caching 开/关分别报告）----
CACHE_POLICY = dict(
    physical_memoization=True,   # 物理复用（保证运行时间可控，输出等价）
    cost_accounting="logical",   # 成本按逻辑调用计费，不做物理去重抵扣
)

CONCURRENCY = 1
HARDWARE_NOTE = "python-3.13.12 / win32 / single-process / deterministic-mock-model"
