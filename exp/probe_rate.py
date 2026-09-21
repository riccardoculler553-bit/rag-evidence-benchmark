# -*- coding: utf-8 -*-
"""GLM 速率限制探测：找出不触发 429 的安全并发/QPS，并测量单次延迟与连接复用收益。"""
import concurrent.futures as cf
import http.client
import json
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from llm_glm import GLM_KEYS, GLM_BASE, GLM_MODEL

HOST = "open.bigmodel.cn"
PATH = "/api/paas/v4/chat/completions"
PROMPT = ("你是企业制度条款分类器。只输出 JSON。\n可选标签：条款 | 例外 | 脚注 | 附录\n"
          "<payload>\nTRV-001-v3 第1.1条：普通员工在北京的住宿标准为 300 元。本条自 2026-01-01 起施行。\n</payload>\n"
          "输出格式：{\"label\": \"...\"}")


def call_keepalive(conn, key):
    body = json.dumps({"model": GLM_MODEL, "temperature": 0,
                       "messages": [{"role": "user", "content": PROMPT}],
                       "max_tokens": 64, "thinking": {"type": "disabled"}})
    t0 = time.time()
    try:
        conn.request("POST", PATH, body=body,
                     headers={"Content-Type": "application/json",
                              "Authorization": f"Bearer {key}"})
        r = conn.getresponse()
        data = json.loads(r.read().decode())
        if r.status != 200:
            return dict(ok=False, status=r.status, ms=(time.time() - t0) * 1000,
                        err=json.dumps(data, ensure_ascii=False)[:160])
        return dict(ok=True, ms=(time.time() - t0) * 1000, usage=data.get("usage"))
    except Exception as e:  # noqa: BLE001
        return dict(ok=False, status=-1, ms=(time.time() - t0) * 1000, err=repr(e)[:160])


def worker(n_calls, results, key, conns, idx):
    conn = conns[idx]
    for _ in range(n_calls):
        r = call_keepalive(conn, key)
        results.append(r)


def bench(concurrency, calls_per_thread, key):
    conns = []
    for _ in range(concurrency):
        c = http.client.HTTPSConnection(HOST, timeout=60,
                                        context=ssl.create_default_context())
        conns.append(c)
    results = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(worker, calls_per_thread, results, key, conns, i)
                for i in range(concurrency)]
        for f in futs:
            f.result()
    wall = time.time() - t0
    ok = [r for r in results if r["ok"]]
    err429 = [r for r in results if not r["ok"] and r.get("status") == 429]
    other = [r for r in results if not r["ok"] and r.get("status") != 429]
    lat = sorted(r["ms"] for r in ok)
    return dict(concurrency=concurrency, calls=len(results), ok=len(ok),
                n429=len(err429), other_err=len(other),
                wall_s=round(wall, 2), throughput_qps=round(len(ok) / wall, 2),
                p50_ms=round(lat[len(lat) // 2], 1) if lat else None,
                p95_ms=round(lat[int(len(lat) * 0.95) - 1], 1) if lat else None,
                sample_err=(other[0]["err"] if other else (err429[0]["err"] if err429 else None)))


if __name__ == "__main__":
    key = GLM_KEYS[0]
    out = {}
    print("== 单次顺序延迟（keep-alive）==")
    seq = bench(1, 5, key)
    out["sequential"] = seq
    print(json.dumps(seq, ensure_ascii=False))
    for conc in [2, 4, 6, 8, 12]:
        r = bench(conc, 4, key)
        out[f"conc{conc}"] = r
        print(json.dumps(r, ensure_ascii=False))
        if r["n429"] > 0:
            print(f"  -> concurrency {conc} 触发 429，安全上限更低")
            break
    with open("exp/runs/rate_probe.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
