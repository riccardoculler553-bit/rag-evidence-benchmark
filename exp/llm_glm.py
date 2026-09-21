# -*- coding: utf-8 -*-
"""GLM-4.5-Air 双 key 客户端（v2）：keep-alive 连接池 + 令牌桶限流 + 正确的 429 处理 + 免费兜底。

关键修正（相对 v1）：
  1. 传输层改用线程本地 keep-alive HTTPSConnection：p50 延迟从 ~1.7s 降到 ~0.45s（实测）
  2. HTTP 429（错误码 1302「已达到速率限制」）不再被当作"额度耗尽"→ 改为令牌桶限流 + 指数退避重试，
     只有 401/403/余额不足 才触发 key 切换（v1 曾因 429 误切到兜底模型，污染了后半程实验）
  3. 每次调用记录实际后端（glm_key0 / glm_key1 / free_fallback），供报告区分数据来源
  4. 事件日志：RATE_LIMIT_BACKOFF / KEY_SWITCH / FALLBACK_ENABLED / FALLBACK_FAILED
"""
import http.client
import json
import os
import random
import ssl
import threading
import time

from config import EXP_OUT

# ========== 凭据：来自环境变量或本地私有文件（见 credentials.py）==========
# 仓库内不含任何明文密钥；缺少凭据时真实模型实验会显式报错，
# 而 mock / Tier 1 实验不受影响。
import credentials as _cred                                     # noqa: E402

GLM_KEYS = list(_cred.GLM_KEYS)
GLM_BASE_URL = _cred.GLM_BASE_URL
GLM_BASE = GLM_BASE_URL                 # 兼容旧调用方（probe_rate.py）
GLM_HOST = _cred.GLM_HOST
GLM_PATH = _cred.GLM_PATH
GLM_MODEL = _cred.GLM_MODEL

FREE_FALLBACK_CONFIG = dict(_cred.FREE_FALLBACK_CONFIG)

GLM_PRICING = dict(input_per_m=0.8, output_short_per_m=2.0, output_long_per_m=6.0,
                   cache_hit_per_m=0.16, output_short_limit=200, version="bigmodel-2026.09")
FALLBACK_PRICING = dict(input_per_m=0.35, output_per_m=0.35, cache_hit_per_m=0.0,
                        version="siliconflow-public-approx")
MAX_TOKENS_DEFAULT = 64

RATE_LIMIT_CODES = {1302, 429}          # 速率限制 → 退避重试，不切 key
QUOTA_CODES = {1113, 1112}              # 余额/额度不足 → 切 key
AUTH_CODES = {1000, 1001, 401, 403}


def mask(k: str) -> str:
    """凭据显示名 —— **不泄露任何密钥字符**。

    修复：旧实现 `f"{k[:6]}…{k[-4:]}"` 会把 6 位前缀 + 4 位后缀写进
    日志与报告（`key_usage.json` / `analysis_bundle.json` / 报告正文），
    属于部分泄露。现改为稳定标签：glm_key0 / glm_key1 / free_fallback。
    """
    return _cred.label(k or "")


class RateLimiter:
    """令牌桶：限制全局 QPS。"""

    def __init__(self, qps):
        self.qps = max(0.1, qps)
        self.tokens = float(self.qps)
        self.last = time.time()
        self.lock = threading.Lock()

    def acquire(self):
        while True:
            with self.lock:
                now = time.time()
                self.tokens = min(self.qps, self.tokens + (now - self.last) * self.qps)
                self.last = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                need = (1.0 - self.tokens) / self.qps
            time.sleep(min(need, 0.25))


class FallbackFailed(RuntimeError):
    pass


class GLMClient:
    """线程安全；keep-alive；限流；正确区分限流与额度耗尽。"""

    def __init__(self, max_tokens=MAX_TOKENS_DEFAULT, log_path=None, keys=None,
                 enable_fallback=True, max_qps=25.0, max_retries=8, timeout=60):
        self.keys = list(keys or GLM_KEYS)
        self.key_idx = 0
        self.glm_exhausted = [False] * len(self.keys)
        self.using_fallback = False
        self.fallback_disabled = not enable_fallback
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.limiter = RateLimiter(max_qps)
        self.lock = threading.Lock()
        self.local = threading.local()          # 线程本地 keep-alive 连接
        self.log_path = log_path or os.path.join(EXP_OUT, "key_switch_log.jsonl")
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self.usage = {f"glm_key{i}": dict(eq=mask(k), calls=0, prompt_tokens=0,
                                          completion_tokens=0, cached_tokens=0,
                                          cost=0.0, errors=0, rate_limits=0,
                                          latency_ms_sum=0.0)
                      for i, k in enumerate(self.keys)}
        self.usage["free_fallback"] = dict(eq=mask(FREE_FALLBACK_CONFIG["api_key"]),
                                           calls=0, prompt_tokens=0, completion_tokens=0,
                                           cached_tokens=0, cost=0.0, errors=0, rate_limits=0,
                                           latency_ms_sum=0.0,
                                           provider=FREE_FALLBACK_CONFIG["provider"],
                                           model=FREE_FALLBACK_CONFIG["model"])
        self.switches = 0
        self.rate_limit_events = 0
        self.fallback_failures = 0
        self.total_tokens = 0
        self._log("CLIENT_INIT", "startup", "-", f"glm_key0",
                  f"max_qps={max_qps}, keys={len(self.keys)}, keepalive=on")

    # ---------------------------------------------------------------- 连接
    def _conn(self, host):
        c = getattr(self.local, "conn", None)
        cur_host = getattr(self.local, "host", None)
        if c is None or cur_host != host:
            if c is not None:
                try:
                    c.close()
                except Exception:  # noqa: BLE001
                    pass
            c = http.client.HTTPSConnection(host, timeout=self.timeout,
                                            context=ssl.create_default_context())
            self.local.conn = c
            self.local.host = host
        return c

    def _drop_conn(self):
        c = getattr(self.local, "conn", None)
        if c is not None:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
            self.local.conn = None

    # ---------------------------------------------------------------- 日志
    def _log(self, event, reason, frm, to, detail=""):
        rec = dict(ts=time.strftime("%Y-%m-%dT%H:%M:%S"), event=event, reason=reason,
                   from_=frm, to=to, detail=detail,
                   usage_snapshot={k: dict(calls=v["calls"], pt=v["prompt_tokens"],
                                           ct=v["completion_tokens"],
                                           cost=round(v["cost"], 6),
                                           rate_limits=v["rate_limits"])
                                   for k, v in self.usage.items()},
                   cumulative_total_tokens=self.total_tokens)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---------------------------------------------------------------- key 轮换
    def _current_name(self):
        return "free_fallback" if self.using_fallback else f"glm_key{self.key_idx}"

    def _rotate_for_quota(self, reason, detail=""):
        with self.lock:
            self.switches += 1
            frm = self._current_name()
            if not self.using_fallback:
                self.glm_exhausted[self.key_idx] = True
                nxt = next((j for j in range(len(self.keys)) if not self.glm_exhausted[j]), None)
                if nxt is not None:
                    self.key_idx = nxt
                    self._log("KEY_SWITCH", reason, frm, f"glm_key{nxt}", detail)
                    return
                if self.fallback_disabled:
                    self._log("NO_BACKEND", reason, frm, "none", "fallback disabled")
                    raise FallbackFailed("all glm keys exhausted; fallback disabled")
                self.using_fallback = True
                self._log("FALLBACK_ENABLED", reason, frm, "free_fallback", detail)
                return
            self.fallback_failures += 1
            self._log("FALLBACK_FAILED", reason, "free_fallback", "none", detail)
            raise FallbackFailed(reason)

    # ---------------------------------------------------------------- 调用
    def complete(self, prompt, task="generic"):
        """返回 (text, prompt_tokens, completion_tokens, meta)；彻底不可用时抛 FallbackFailed。"""
        attempt = 0
        while True:
            name = self._current_name()
            if name == "free_fallback":
                cfg = FREE_FALLBACK_CONFIG
                host, path, key, model = (cfg["host"], cfg["path"], cfg["api_key"], cfg["model"])
                extra = None
            else:
                host, path, key, model = GLM_HOST, GLM_PATH, self.keys[self.key_idx], GLM_MODEL
                extra = {"thinking": {"type": "disabled"}}
            self.limiter.acquire()
            t0 = time.time()
            status, payload = self._send(host, path, key, model, prompt, extra)
            dt = (time.time() - t0) * 1000

            if status == 200:
                msg = payload["choices"][0]["message"]
                text = (msg.get("content") or "").strip()
                u = payload.get("usage") or {}
                pt = int(u.get("prompt_tokens", 0))
                ct = int(u.get("completion_tokens", 0))
                cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
                with self.lock:
                    v = self.usage[name]
                    v["calls"] += 1
                    v["prompt_tokens"] += pt
                    v["completion_tokens"] += ct
                    v["cached_tokens"] += cached
                    v["cost"] += self._cost(name, pt, ct, cached)
                    v["latency_ms_sum"] += dt
                    self.total_tokens += pt + ct
                return text, pt, ct, dict(backend=name, model=payload.get("model", model),
                                          cached_tokens=cached, latency_ms=round(dt, 1))

            # ---- 错误分支 ----
            code = None
            msg = ""
            if isinstance(payload, dict):
                err = payload.get("error") or {}
                code = err.get("code")
                msg = err.get("message", "")
            with self.lock:
                self.usage[name]["errors"] += 1

            is_rate = status == 429 or code in RATE_LIMIT_CODES
            is_quota = (code in QUOTA_CODES) or any(
                s in str(msg) for s in ["余额", "欠费", "额度不足", "quota", "insufficient"])
            is_auth = status in (401, 403) or code in AUTH_CODES

            if is_auth or is_quota:
                self._rotate_for_quota(f"HTTP_{status}_CODE_{code}", str(payload)[:200])
                attempt = 0
                continue

            if is_rate:
                with self.lock:
                    self.rate_limit_events += 1
                    self.usage[name]["rate_limits"] += 1
                attempt += 1
                delay = min(20.0, 0.5 * (2 ** min(attempt, 5))) * (0.7 + random.random() * 0.6)
                self._log("RATE_LIMIT_BACKOFF", f"code={code}", name, name,
                          f"attempt={attempt}, sleep={delay:.2f}s, msg={msg[:80]}")
                if attempt >= self.max_retries:
                    self._log("RATE_LIMIT_EXHAUSTED", f"attempts={attempt}", name, name, msg[:120])
                    attempt = 0
                    time.sleep(delay)
                else:
                    time.sleep(delay)
                continue

            # 其他错误：退避重试，连续 3 次失败则尝试下一个 key
            self._drop_conn()
            attempt += 1
            if attempt >= 3:
                attempt = 0
                self._rotate_for_quota(f"CONSECUTIVE_FAILURES_status{status}", str(payload)[:160])
                continue
            time.sleep(0.4 * attempt)

    def _send(self, host, path, key, model, prompt, extra):
        body = {"model": model, "temperature": 0, "top_p": 1,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.max_tokens}
        if extra:
            body.update(extra)
        data = json.dumps(body)
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                   "Connection": "keep-alive"}
        for retry_conn in range(2):
            try:
                conn = self._conn(host)
                conn.request("POST", path, body=data, headers=headers)
                resp = conn.getresponse()
                raw = resp.read().decode()
                return resp.status, json.loads(raw)
            except Exception as e:  # noqa: BLE001
                self._drop_conn()
                if retry_conn == 1:
                    return -1, {"error": {"code": "TRANSPORT", "message": repr(e)[:200]}}
        return -1, {"error": {"code": "TRANSPORT", "message": "unreachable"}}

    # ---------------------------------------------------------------- 计价
    @staticmethod
    def _cost(name, pt, ct, cached):
        if name == "free_fallback":
            p = FALLBACK_PRICING
            return (pt / 1e6) * p["input_per_m"] + (ct / 1e6) * p["output_per_m"]
        p = GLM_PRICING
        fresh = max(0, pt - cached)
        rate = p["output_short_per_m"] if ct <= p["output_short_limit"] else p["output_long_per_m"]
        return ((fresh / 1e6) * p["input_per_m"] + (cached / 1e6) * p["cache_hit_per_m"]
                + (ct / 1e6) * rate)

    def summary(self):
        with self.lock:
            return dict(using_fallback=self.using_fallback, switches=self.switches,
                        rate_limit_events=self.rate_limit_events,
                        fallback_failures=self.fallback_failures,
                        total_tokens=self.total_tokens,
                        per_backend={k: dict(v) for k, v in self.usage.items()},
                        total_cost_yuan=round(sum(v["cost"] for v in self.usage.values()), 6),
                        pricing=dict(glm=GLM_PRICING, fallback=FALLBACK_PRICING))

    def persist(self, path=None):
        path = path or os.path.join(EXP_OUT, "key_usage.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.summary(), f, ensure_ascii=False, indent=1)
        return path
