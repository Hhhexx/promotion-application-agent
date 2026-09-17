"""抖加申请文本解析（架构 §2.2 / §2.3 抖加列）。

模板形态：
    【抖加金额统计】今日已支付：¥700（2026-09-02）
    歌名：《你是我的仰望》- 博主名：初秋 - 金额：¥300（分 3 笔）
    今日共 7 笔支付申请，合并同博主后为 4 笔。
    抖加支付人：爆火音乐
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.parsers.base import ParsedRequest, RawItem
from app.parsers.normalizer import normalize_text, to_decimal

TOTAL_RE = re.compile(r"今日已支付[:：]\s*¥?\s*([\d,]+(?:\.\d+)?)")
COUNT_RE = re.compile(r"今日共\s*(\d+)\s*笔")
MERGED_RE = re.compile(r"合并同博主后为\s*(\d+)\s*笔")
PAYER_RE = re.compile(r"抖加支付人[:：]\s*(.+)")

#: 顺序固定：歌名 → 博主名 → 金额 → 可选分笔数。任一段缺失即视为无法识别。
LINE_RE = re.compile(
    r"歌名[:：]\s*[《<](?P<song>[^》>]+)[》>]\s*[-－—]\s*"
    r"博主名[:：]\s*(?P<name>.+?)\s*[-－—]\s*"
    r"金额[:：]\s*¥?\s*(?P<amount>[\d,]+(?:\.\d+)?)"
    r"(?:\s*[（(]\s*分\s*(?P<split>\d+)\s*笔\s*[）)])?"
)


def fill_summary(text: str, parsed: ParsedRequest) -> None:
    """抽取表级汇总声明。缺失的字段记入 `missing_fields`，不填默认值。"""
    if (m := TOTAL_RE.search(text)) is not None:
        parsed.declared_total = to_decimal(m.group(1))
    else:
        parsed.missing_fields.append("声明总额（今日已支付）")

    if (m := COUNT_RE.search(text)) is not None:
        parsed.declared_count = int(m.group(1))
    if (m := MERGED_RE.search(text)) is not None:
        parsed.declared_merged_count = int(m.group(1))
    if (m := PAYER_RE.search(text)) is not None:
        parsed.payer_raw = normalize_text(m.group(1))
    else:
        parsed.missing_fields.append("抖加支付人")


def parse_line(line: str) -> RawItem | None:
    """解析单条明细行；无法识别返回 None（由调用方升级为 `UNPARSED_LINE`）。"""
    m = LINE_RE.search(line)
    if m is None:
        return None
    try:
        amount: Decimal = to_decimal(m.group("amount"))
    except Exception:  # 金额不可解析视为该行未识别
        return None
    split_raw = m.group("split")
    return RawItem(
        line_no=0,
        name_raw=normalize_text(m.group("name")),
        song_name=normalize_text(m.group("song")) or None,
        amount=amount,
        split_count=int(split_raw) if split_raw else 1,
        span=None,  # type: ignore[arg-type] 由 base 回填
    )
