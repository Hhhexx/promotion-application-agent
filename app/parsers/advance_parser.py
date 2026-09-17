"""垫付申请文本解析（架构 §2.2 / §2.3 垫付列）。

模板形态：
    【垫付统计】今日已垫付：¥2250（2026-09-03）
    申请为【达人：初秋】垫付 ¥950（歌曲《你是我的仰望》）
    今日共 7 笔垫付申请。
    打款人：林老师
    预计打款日期：26/08/31
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.domain.errors import UnresolvableError
from app.parsers.base import ParsedRequest, RawItem
from app.parsers.normalizer import normalize_date, normalize_text, to_decimal

TOTAL_RE = re.compile(r"今日已垫付[:：]\s*¥?\s*([\d,]+(?:\.\d+)?)")
COUNT_RE = re.compile(r"今日共\s*(\d+)\s*笔")
PAYER_RE = re.compile(r"^打款人[:：]\s*(.+)$", re.MULTILINE)
EXPECTED_PAY_DATE_RE = re.compile(r"预计打款日期[:：]\s*([0-9./\-]+)")

LINE_RE = re.compile(
    r"申请为\s*【\s*达人[:：]\s*(?P<name>[^】]+?)\s*】\s*"
    r"垫付\s*¥?\s*(?P<amount>[\d,]+(?:\.\d+)?)"
    r"(?:\s*[（(]\s*歌曲\s*[《<](?P<song>[^》>]+)[》>]\s*[）)])?"
)


def fill_summary(text: str, parsed: ParsedRequest) -> None:
    """抽取表级汇总声明；`预计打款日期` 缺年份时按批次日期锚定并标推断。"""
    if (m := TOTAL_RE.search(text)) is not None:
        parsed.declared_total = to_decimal(m.group(1))
    else:
        parsed.missing_fields.append("声明总额（今日已垫付）")

    if (m := COUNT_RE.search(text)) is not None:
        parsed.declared_count = int(m.group(1))

    if (m := PAYER_RE.search(text)) is not None:
        parsed.payer_raw = normalize_text(m.group(1))
    else:
        parsed.missing_fields.append("打款人")

    if (m := EXPECTED_PAY_DATE_RE.search(text)) is not None:
        raw = m.group(1)
        parsed.expected_pay_date_raw = raw
        try:
            value, inferred = normalize_date(raw, anchor_year=parsed.declared_date.year)
            parsed.expected_pay_date = value
            parsed.expected_pay_date_inferred = inferred
        except UnresolvableError:
            parsed.date_issues.append(("预计打款日期", raw))


def parse_line(line: str) -> RawItem | None:
    """解析单条明细行；无法识别返回 None（由调用方升级为 `UNPARSED_LINE`）。"""
    m = LINE_RE.search(line)
    if m is None:
        return None
    try:
        amount: Decimal = to_decimal(m.group("amount"))
    except Exception:
        return None
    song = m.group("song")
    return RawItem(
        line_no=0,
        name_raw=normalize_text(m.group("name")),
        song_name=normalize_text(song) if song else None,
        amount=amount,
        split_count=None,  # 垫付无「分 N 笔」概念
        span=None,  # type: ignore[arg-type] 由 base 回填
    )


def anchor_year_for(raw: str, declared: date) -> int:
    """供测试与调试：暴露锚定规则（距声明年份最近的世纪）。"""
    return declared.year
