# -*- coding: utf-8 -*-
"""提交前守卫：确保仓库内不出现明文 / 半脱敏凭据。

本脚本**不含任何密钥字面量**（避免守则本身成为泄露源），只做形态匹配：

  1. GLM 形态：32 位 hex + '.' + 8 位以上字母数字
  2. 通用 sk- token：sk- 后接 16 位以上字母数字
  3. 旧掩码形态：<6 位十六进制>…<4 位字母数字>  —— 历史 `mask()` 的产物
  4. 常见赋值形态：api_key = "..." / token = "..."（非空、非占位符）

用法：
    python check_no_secrets.py            # 扫描全仓（退出码 1 表示发现问题）
    python check_no_secrets.py --staged   # 仅扫描 git 暂存区内容

CI / pre-commit 建议接入。
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

TEXT_EXT = {".json", ".jsonl", ".md", ".csv", ".txt", ".py", ".yaml", ".yml",
            ".toml", ".ini", ".cfg", ".sh"}

# 允许出现明文凭据的文件（必须同时被 .gitignore 忽略）
ALLOWLIST = {"_local_credentials.py"}

RULES = [
    ("GLM_KEY_FORM", re.compile(r"\b[0-9a-f]{32}\.[A-Za-z0-9]{8,}\b")),
    ("SK_TOKEN", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("MASKED_GLM", re.compile(r"\b[0-9a-f]{6}\u2026[A-Za-z0-9]{4}\b")),
    ("MASKED_SK", re.compile(r"\bsk-[A-Za-z0-9]{3}\u2026[A-Za-z0-9]{4}\b")),
    ("HARDCODED_ASSIGN",
     re.compile(r"""(?:api_key|apikey|access_token|secret)\s*[:=]\s*["']"""
                r"""(?!\s*["'])(?!<)(?!\$)(?!os\.environ)(?!_env)(?!LOCAL_)(?!__)"""
                r"""(?!none|None|你的|在这里|your_|REDACTED|\[)["']?[^"'\s]{12,}["']""")),
]

PLACEHOLDER_OK = re.compile(r"(REDACTED|your_|YOUR_|在这里|example|placeholder|xxx+)", re.I)


def scan_text(s: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for name, rx in RULES:
        for m in rx.finditer(s):
            frag = m.group(0)
            if PLACEHOLDER_OK.search(frag):
                continue
            hits.append((name, frag[:24] + ("…" if len(frag) > 24 else "")))
    return hits


def iter_files():
    for base, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".venv", "node_modules")]
        for fn in files:
            if fn in ALLOWLIST:
                continue
            if os.path.splitext(fn)[1].lower() in TEXT_EXT:
                yield os.path.join(base, fn)


def iter_staged():
    out = subprocess.run(["git", "diff", "--cached", "--name-only"],
                         cwd=HERE, capture_output=True, text=True).stdout.split()
    for rel in out:
        if os.path.splitext(rel)[1].lower() in TEXT_EXT and os.path.basename(rel) not in ALLOWLIST:
            p = os.path.join(HERE, rel)
            if os.path.exists(p):
                yield p


def main() -> int:
    staged = "--staged" in sys.argv
    files = list(iter_staged() if staged else iter_files())
    bad = 0
    for p in files:
        try:
            s = io.open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        hits = scan_text(s)
        if hits:
            bad += 1
            print(f"  !! {os.path.relpath(p, HERE)}")
            for name, frag in hits[:5]:
                print(f"       [{name}] {frag}")
    print(f"\n扫描 {len(files)} 个文件（{'暂存区' if staged else '全仓'}）："
          f"{'发现 ' + str(bad) + ' 个可疑文件' if bad else '未发现凭据痕迹'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
