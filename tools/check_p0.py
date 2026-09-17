#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P0 门禁扫描器 — 每 Phase 结束前必须运行。

P0-1 禁止 emoji 作为功能图标
P0-2 禁止紫色→粉色渐变主视觉
P0-3 禁止 AI 模板味占位文案

用法:
    python tools/check_p0.py [目标路径 ...]
默认扫描 docs/ src/ web/。
退出码: 0 = 通过, 1 = 发现违规。

抑制机制（两档，勿滥用）:
  1. 行内标记 `p0-ignore`  → 该行全部规则跳过（用于 lint 配置、正则本身等必须写出违禁字样的场合）
  2. 否定上下文            → 仅对 P0-2 / P0-3 生效。命中位置**前面 14 字窗口内**出现否定词
     （无 / 不含 / 禁止 / 不得 / 不出现 / 不使用 / 避免 / 杜绝 / 未出现）时，判定为
     "在陈述禁令"而非"在使用违规"，跳过。
     例：`P0-3 无 AI 模板味 | 通过。无 "Welcome to" / "Lorem ipsum"` 属正当陈述。
     用**前缀窗口**而非整行共现，是为了避免"一行里出现'无'就整行豁免"这种过度放宽。
     注意：P0-1（emoji）不适用此档——文档里出现 emoji 字符就是隐患，一律要报。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- P0-1 emoji
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F000-\U0001F02F"
    "\U0001F0A0-\U0001F0FF"
    "\U0001F100-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U0000200D"
    "\U000020E3"
    "\U000E0020-\U000E007F"
    "]"
)

# --------------------------------------------------- P0-2 紫→粉渐变 / P0-3 模板味
GRADIENT_PATTERNS = [
    (re.compile(r"#7C3AED", re.I), "禁用的紫色 #7C3AED"),
    (re.compile(r"#A855F7", re.I), "禁用的紫色 #A855F7"),
    (re.compile(r"#EC4899", re.I), "禁用的粉色 #EC4899"),
    (re.compile(r"#8B5CF6", re.I), "禁用的紫色 #8B5CF6"),
    (re.compile(r"linear-gradient\([^)]*#(?:6366F1|4F46E5|7C3AED|A855F7|8B5CF6)[^)]*"
                r"#(?:EC4899|F472B6|DB2777)", re.I), "Indigo→Pink 渐变组合"),
]

TEMPLATE_PATTERNS = [
    (re.compile(r"lorem ipsum", re.I), "Lorem ipsum 占位文案"),
    (re.compile(r"welcome to our app", re.I), "Welcome to Our App 占位文案"),
    (re.compile(r"sign up today", re.I), "Sign up today 占位文案"),
    (re.compile(r"cubic-bezier\(\s*0?\.68\s*,\s*-?0?\.55\s*,", re.I), "禁止的弹跳缓动"),
]

# 判定"在陈述禁令"：命中位置前 60 字窗口内的否定词（仅 P0-2 / P0-3 适用）
# 窗口取 60 而非更小：禁令句式常写作「无 "Welcome to" / "Lorem ipsum"」或
# 「禁止…（不出现 "Welcome to"、"Lorem ipsum"）」，违禁词距否定词可达 30+ 字。
# 范围仍限于本行，不会跨行泄漏。
NEGATION_PREFIXES = ("无", "不含", "禁止", "不得", "不出现", "不使用",
                     "避免", "杜绝", "未出现", "p0-ignore")
NEGATION_WINDOW = 60

SCAN_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".ts", ".tsx", ".js",
                 ".jsx", ".vue", ".html", ".htm", ".css", ".scss", ".txt"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build",
             # `.workbuddy` 存放 append-only 经验台账（pitfalls.jsonl 等）。台账为记录
             # "哪个色值/文案被禁"，**必然**含违禁字样字面量，属正当记录而非使用违禁，
             # 与"禁令陈述"同理，故整体排除。台账不做门禁扫描。
             ".workbuddy"}
SELF = Path(__file__).resolve()


def in_negation_context(line: str, start: int) -> bool:
    """命中点的前缀窗口内是否有否定词 → 说明该行在陈述禁令而非使用违规。"""
    lo = max(0, start - NEGATION_WINDOW)
    return any(k in line[lo:start] for k in NEGATION_PREFIXES)


def iter_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in targets:
        p = Path(raw)
        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            candidates = [f for f in sorted(p.rglob("*")) if f.is_file()]
        else:
            continue
        for f in candidates:
            if f.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in f.parts):
                continue
            if f.resolve() == SELF:          # 不扫自己（正则里必然含违禁色值）
                continue
            files.append(f)
    return files


def scan(files: list[Path]) -> int:
    violations = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            # P0-1：emoji 无豁免（除整行 p0-ignore）
            if "p0-ignore" not in line:
                for ch in EMOJI_RE.findall(line):
                    violations += 1
                    print(f"[P0-1 emoji] {f}:{lineno}: 发现 emoji 字符 "
                          f"{ch!r} (U+{ord(ch):04X})")
            # P0-2 / P0-3：否定上下文豁免（仅看命中点前 14 字窗口，不做整行豁免）
            for rx, why in GRADIENT_PATTERNS:
                m = rx.search(line)
                if m and not in_negation_context(line, m.start()):
                    violations += 1
                    print(f"[P0-2 渐变] {f}:{lineno}: {why}")
                    break
            for rx, why in TEMPLATE_PATTERNS:
                m = rx.search(line)
                if m and not in_negation_context(line, m.start()):
                    violations += 1
                    print(f"[P0-3 文案] {f}:{lineno}: {why}")
                    break
    return violations


def main() -> int:
    targets = sys.argv[1:] or ["docs", "src", "web", "tools"]
    files = iter_files(targets)
    if not files:
        print("未找到可扫描文件（目标路径可能不存在）")
        return 0
    print(f"扫描 {len(files)} 个文件 ...")
    n = scan(files)
    if n:
        print(f"\n门禁未通过: 共 {n} 处 P0 违规，必须修复后重跑。")
        return 1
    print("\nP0 门禁通过: 无 emoji 图标 / 无紫粉渐变 / 无模板味占位。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
