# -*- coding: utf-8 -*-
"""模型后端探测：验证 GLM 双 key 与免费兜底是否可用、模型 id 是否正确、token 计量是否返回。

不打印任何明文密钥（仅打印掩码与 hash 前缀）。
"""
import json
import sys
import time
import urllib.error
import urllib.request

import credentials as _cred

GLM_KEYS = list(_cred.GLM_KEYS)
GLM_BASE = _cred.GLM_BASE_URL
GLM_MODEL = _cred.GLM_MODEL

FALLBACK = dict(provider=_cred.FREE_FALLBACK_CONFIG["provider"],
                api_key=_cred.FREE_FALLBACK_CONFIG["api_key"],
                base_url=_cred.FREE_FALLBACK_CONFIG["base_url"],
                model=_cred.FREE_FALLBACK_CONFIG["model"])


def mask(k):
    """凭据显示名（不泄露任何密钥字符）。"""
    return _cred.label(k or "")


def call(base, key, model, n_max=8):
    body = json.dumps({"model": model, "temperature": 0,
                       "messages": [{"role": "user", "content": "只回答一个字符：OK"}],
                       "max_tokens": n_max}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            d = json.loads(r.read().decode())
        return dict(ok=True, ms=round((time.time() - t0) * 1000),
                    text=d["choices"][0]["message"]["content"][:40],
                    usage=d.get("usage"), model=d.get("model"))
    except urllib.error.HTTPError as e:
        return dict(ok=False, status=e.code, body=e.read().decode()[:300], ms=round((time.time() - t0) * 1000))
    except Exception as e:  # noqa: BLE001
        return dict(ok=False, error=repr(e)[:200], ms=round((time.time() - t0) * 1000))


if __name__ == "__main__":
    out = {"glm_base": GLM_BASE, "glm_model": GLM_MODEL}
    for i, k in enumerate(GLM_KEYS):
        out[f"glm_key{i}"] = dict(masked=mask(k), result=call(GLM_BASE, k, GLM_MODEL))
    out["fallback"] = dict(masked=mask(FALLBACK["api_key"]), provider=FALLBACK["provider"],
                           model=FALLBACK["model"],
                           result=call(FALLBACK["base_url"], FALLBACK["api_key"], FALLBACK["model"], 16))
    print(json.dumps(out, ensure_ascii=False, indent=1))
