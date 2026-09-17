"""代码行数门禁（README「单文件 ≤ 300 代码行」的机械复核器）。

**口径（严格、可机械复核）**：一行算「代码行」当且仅当它
  - 去掉首尾空白后非空，且
  - 不以 `#` 开头（即不是纯注释行）。
**docstring 计入** —— 它是可执行语句（模块/函数体第一个表达式），严格讲不是注释。
这与 `grep -v '^\\s*$' f | grep -v '^\\s*#' f | wc -l` 完全一致。

扫描范围：app/ tools/ tests/ web/（跳过 __pycache__ / node_modules / .git 等）。
任一文件超限 → 退出码 1。

用法：
  <venv>/python.exe tools/check_lines.py            # 扫描仓库根
  <venv>/python.exe tools/check_lines.py <目录>      # 扫描指定目录
退出码 0 = 全部达标；1 = 存在超限文件。
"""

from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 300
ROOTS = ("app", "tools", "tests", "web")
CODE_EXTS = frozenset({".py", ".js", ".mjs", ".css", ".html", ".htm"})
SKIP_DIRS = frozenset({"__pycache__", "node_modules", ".git", ".pytest_cache", ".venv", ".mypy_cache"})


def count_code_lines(path: Path) -> int:
    """按上文口径统计单个文件的代码行数。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    total = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        total += 1
    return total


def iter_files(base: Path):
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix not in CODE_EXTS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def scan(repo: Path) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for name in ROOTS:
        base = repo / name
        if not base.exists():
            continue
        for path in iter_files(base):
            rows.append((count_code_lines(path), str(path.relative_to(repo))))
    rows.sort(key=lambda row: (-row[0], row[1]))
    return rows


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    repo = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[1]
    rows = scan(repo)

    print(f"代码行数门禁：上限 {LIMIT} 行/文件（口径：非空且非纯注释行，docstring 计入）")
    print(f"扫描根：{repo}")
    for count, rel in rows:
        mark = "   <<< 超限" if count > LIMIT else ""
        print(f"{count:5d}  {rel}{mark}")

    over = [(count, rel) for count, rel in rows if count > LIMIT]
    print("=" * 60)
    print(f"文件总数 {len(rows)}；超限 {len(over)} 个")
    if over:
        for count, rel in over:
            print(f"  [超限] {rel}: {count} > {LIMIT}")
        return 1
    print("全部达标。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
