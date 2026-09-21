# -*- coding: utf-8 -*-
"""凭据加载器（可安全提交）。

优先级：
  1. 环境变量
       GLM_KEY_0 / GLM_KEY_1        —— 主模型（glm-4.5-air）双 key
       FREE_FALLBACK_API_KEY        —— 免费兜底 key（可空）
  2. 本地文件 exp/_local_credentials.py（**已在 .gitignore 中**，仅本机存在）

设计约束：
  - 本模块**不得**包含任何明文密钥，否则无法提交到版本库。
  - 缺少凭据时**不报错**：mock / Tier 1 实验不需要真实模型，
    调用方应先检查 `available()`，仅真实模型实验才需要 key。
  - 兜底模型默认关闭，必须显式提供 key 才启用（避免静默混入非主模型，
    违反 v1.3 §17「fallback 不得进入正式因果统计」）。
"""
from __future__ import annotations

import os

try:                                    # 本机私有文件（不入库）
    from _local_credentials import (    # type: ignore
        LOCAL_FREE_FALLBACK_KEY,
        LOCAL_GLM_KEYS,
    )
except Exception:                       # noqa: BLE001
    LOCAL_GLM_KEYS = []
    LOCAL_FREE_FALLBACK_KEY = ""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or "").strip()


def _load_glm_keys() -> list[str]:
    env_keys = [k for k in (_env("GLM_KEY_0"), _env("GLM_KEY_1")) if k]
    if env_keys:
        return env_keys
    return [k for k in LOCAL_GLM_KEYS if k]


GLM_KEYS: list[str] = _load_glm_keys()
FREE_FALLBACK_KEY: str = _env("FREE_FALLBACK_API_KEY") or LOCAL_FREE_FALLBACK_KEY

# ---- 端点 / 模型（非机密，可入库）----
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
GLM_HOST = "open.bigmodel.cn"
GLM_PATH = "/api/paas/v4/chat/completions"
GLM_MODEL = "glm-4.5-air"

FREE_FALLBACK_CONFIG = {
    "provider": "siliconflow",
    "api_key": FREE_FALLBACK_KEY,
    "base_url": "https://api.siliconflow.cn/v1",
    "host": "api.siliconflow.cn",
    "path": "/v1/chat/completions",
    "model": "Qwen/Qwen2.5-7B-Instruct",
    # 只有拿到 key 才启用；否则显式关闭，避免请求到空 key 造成静默失败
    "enabled": bool(FREE_FALLBACK_KEY),
}


def available() -> bool:
    """主模型是否可用（真实模型实验的前置条件）。"""
    return bool(GLM_KEYS)


def fallback_available() -> bool:
    return bool(FREE_FALLBACK_CONFIG["api_key"])


def label(key: str) -> str:
    """给凭据一个**稳定且不可逆**的显示名。

    早期版本用 `k[:6]…k[-4:]`（前缀+后缀掩码），会把密钥的 6 位前缀与 4 位后缀
    写进日志/报告，属于部分泄露。此处改为固定标签，日志里只保留槽位信息。
    """
    if not key:
        return "none"
    if key in GLM_KEYS:
        return f"glm_key{GLM_KEYS.index(key)}"
    if key == FREE_FALLBACK_CONFIG["api_key"]:
        return "free_fallback"
    return "unknown_key"
