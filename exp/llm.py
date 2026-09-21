# -*- coding: utf-8 -*-
"""模型适配层（§3.1 固定项：model_id / model_revision / temperature / decoding / tokenizer）。

默认后端：deterministic-mock-semantic（可复现、零外部依赖、greedy 解码）。
可切换到 OpenAI 兼容后端（环境变量），prompt / schema / 输出解析完全不变。

重要（写入实验报告的边界条件）：mock 后端的行为由固定词表 + 规则实现，
其"语义能力"是脚本化的；因此本实验的因果结论只对
「同一 capability implementation + 同一 model revision」内部的 Build Position 成立，
跨模型的外部有效性需要以同一 prompt/schema 重跑真实模型（见 run_manifest.model_swappable）。
"""
import hashlib
import json
import re

from config import MODEL_ID, MODEL_REVISION, TEMPERATURE, DECODING, TOKENIZER

# ---------------------------------------------------------------- tokenizer 代理
def count_tokens(text: str) -> int:
    """char4-bpe-proxy：确定性代理分词器（记录在 run_manifest.tokenizer）。"""
    if not text:
        return 0
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


class MockSemanticModel:
    """deterministic-mock-semantic / mock-det-v1

    行为定义（即 capability implementation 的语义假设，全部可审计）：
      * classification：关键词表 + 固定优先级 tie-break；多信号共现时按优先级取首个命中。
      * extraction：取"第一个紧邻『元/万元』的数字"；不做单位归一（万元场景会失败）。
    上述两类"失败模式"在数据集的不同子集上分布均匀，因此 survivor 子集上的质量
    与全集质量可比（这正是 Build Position 因果隔离所需要的）。
    """

    revision = MODEL_REVISION
    model_id = MODEL_ID

    # ---- classification 关键词优先级表 ----
    # cap-impl-v1.0→v1.1：修正"发货"过宽命中（address_change 被误判为物流）
    # cap-impl-v1.2：把"退款"提到"物流"之前（客户主诉求优先，符合业务语义；
    #                同时消除"退款工单里提到物流曾延误"造成的系统性误判）
    ISSUE_RULES = [
        ("refund_request", ["申请退款", "退款"]),
        ("logistics_delay", ["物流", "未更新轨迹", "延误", "发货超时"]),
        ("product_quality", ["换货", "无法充电", "音质", "外壳划痕", "连接不稳定", "屏幕闪烁"]),
        ("address_change", ["修改收货地址", "收货地址"]),
        ("other", ["咨询", "开票", "保修"]),
    ]
    CLAUSE_RULES = [
        ("例外", ["例外", "上浮"]),
        ("脚注", ["注：", "脚注"]),
        ("附录", ["附录"]),
        ("条款", ["条：", "标准为", "标准 "]),
    ]

    def complete(self, prompt: str, task: str = "generic"):
        """返回 (completion_text, tokens_in, tokens_out)。greedy、确定性。"""
        payload = self._extract_payload(prompt)
        if task == "issue_classification":
            out = self._classify(payload, self.ISSUE_RULES,
                                 default="other")
        elif task == "clause_classification":
            out = self._classify(payload, self.CLAUSE_RULES, default="条款")
        elif task == "amount_extraction":
            out = self._extract_amount(payload)
        else:
            out = ""
        completion = json.dumps(out, ensure_ascii=False)
        return completion, count_tokens(prompt), count_tokens(completion)

    # ---- 内部 ----
    @staticmethod
    def _extract_payload(prompt: str) -> str:
        m = re.search(r"<payload>\n(.*?)\n</payload>", prompt, re.S)
        return m.group(1) if m else prompt

    @staticmethod
    def _classify(payload, rules, default):
        for label, kws in rules:
            for kw in kws:
                if kw in payload:
                    return {"label": label}
        return {"label": default}

    @staticmethod
    def _extract_amount(payload):
        """取第一个紧邻"元/万元"的数字；不做单位归一（真实但保守的实现）。"""
        m = re.search(r"(\d+(?:\.\d+)?)\s*(万元|元)", payload)
        if not m:
            return {"value": None, "raw": None}
        val = float(m.group(1))
        return {"value": val, "raw": m.group(1), "unit": m.group(2)}


class OpenAICompatibleModel:
    """可选真实模型后端（同一 prompt/schema）。默认不启用。"""

    revision = "openai-compatible"

    def __init__(self, base_url, api_key, model):
        self.base_url, self.api_key, self.model = base_url, api_key, model
        self.model_id = model

    def complete(self, prompt: str, task: str = "generic"):
        import urllib.request
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps({"model": self.model, "temperature": TEMPERATURE,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, usage.get("prompt_tokens", count_tokens(prompt)), \
            usage.get("completion_tokens", count_tokens(text))


def get_model():
    import os
    if os.environ.get("RAGX_MODEL_BACKEND") == "openai":
        return OpenAICompatibleModel(os.environ["OPENAI_BASE_URL"],
                                     os.environ["OPENAI_API_KEY"],
                                     os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    return MockSemanticModel()


def model_hash():
    h = hashlib.sha256()
    for name in ["MockSemanticModel", MockSemanticModel.ISSUE_RULES, MockSemanticModel.CLAUSE_RULES]:
        h.update(repr(name).encode())
    h.update(MODEL_REVISION.encode())
    h.update(TOKENIZER.encode())
    h.update(f"{TEMPERATURE}|{DECODING}".encode())
    return h.hexdigest()[:16]
