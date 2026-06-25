#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据脱敏主脚本（不可逆）。
对文本/文件中的 PII（身份证、手机号、银行卡、邮箱、IP 等）做掩码/哈希/删除替换。

用法:
    python mask.py --input input.txt --output masked.txt
    python mask.py --input input.txt --mode hash
    cat input.txt | python mask.py > masked.txt
    python mask.py --input input.csv --mode mask --keep-name

说明:
    - 不可逆脱敏，不生成还原映射表。
    - 处理前请自行备份原始数据。
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

# ---------- 识别规则（正则） ----------
# 顺序：先匹配长格式，避免被短格式截断
PATTERNS = [
    ("id_card", re.compile(r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]")),
    ("bank_card", re.compile(r"\b[1-9]\d{14,18}\b")),
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

# ---------- 脱敏函数 ----------
def mask_value(value, kind, mode):
    """按字段类型与模式做不可逆脱敏。"""
    if mode == "redact":
        return "[REDACTED]"
    if mode == "hash":
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    # mode == "mask"（默认）
    if kind == "id_card":
        return value[:6] + "*" * (len(value) - 10) + value[-4:]
    if kind == "phone":
        return value[:3] + "****" + value[-4:]
    if kind == "bank_card":
        return "*" * (len(value) - 4) + value[-4:]
    if kind == "email":
        name, _, domain = value.partition("@")
        head = name[0] if name else ""
        return head + "***@" + domain
    if kind == "ip":
        return value.rsplit(".", 1)[0] + ".*"
    # 兜底：保留首末各 1 字符
    return value[0] + "*" * (len(value) - 2) + value[-1] if len(value) > 2 else "*" * len(value)


def mask_text(text, mode="mask"):
    """对整段文本做全量脱敏，返回脱敏后文本与命中统计。"""
    hits = {}
    # 用占位符替换避免不同类型重叠匹配互相破坏
    placeholders = []
    for kind, pat in PATTERNS:
        def _sub(m, k=kind):
            tok = f"\x00{len(placeholders)}\x00"
            placeholders.append(mask_value(m.group(0), k, mode))
            hits[k] = hits.get(k, 0) + 1
            return tok
        text = pat.sub(_sub, text)
    # 回填占位符
    for i, val in enumerate(placeholders):
        text = text.replace(f"\x00{i}\x00", val, 1)
    return text, hits


def main():
    ap = argparse.ArgumentParser(description="不可逆 PII 脱敏工具")
    ap.add_argument("--input", "-i", help="输入文件路径；缺省则读 stdin")
    ap.add_argument("--output", "-o", help="输出文件路径；缺省则写 stdout")
    ap.add_argument("--mode", "-m", choices=["mask", "hash", "redact"], default="mask",
                    help="脱敏模式：mask=掩码(默认) hash=SHA-256 redact=删除")
    args = ap.parse_args()

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    masked, hits = mask_text(text, args.mode)

    if args.output:
        Path(args.output).write_text(masked, encoding="utf-8")
    else:
        sys.stdout.write(masked)

    # 统计写到 stderr，不污染输出流
    summary = ", ".join(f"{k}={v}" for k, v in hits.items()) or "未命中"
    print(f"[mask] 命中: {summary}", file=sys.stderr)


if __name__ == "__main__":
    main()
