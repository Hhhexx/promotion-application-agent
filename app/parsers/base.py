"""解析层公共骨架（架构 §2.2 / §2.3）。

职责：识别文本类型、抽取表级汇总声明、驱动类型特化的明细行解析器。
**解析层不碰 Excel、不做业务校验**（架构 §5.2 硬规则 2）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.enums import BizType
from app.domain.errors import ValidationError
from app.domain.models import SourceSpan
from app.parsers.normalizer import (
    build_batch_id,
    build_dedup_key,
    normalize_date,
    normalize_name,
    normalize_text,
    to_decimal,
)

HEADER_DOUJIA_RE = re.compile(r"【\s*抖加金额统计\s*】")
HEADER_ADVANCE_RE = re.compile(r"【\s*垫付统计\s*】")
DETAIL_MARKER_RE = re.compile(r"明细如下")
TERMINATOR_RE = re.compile(r"^(今日共|抖加支付人|打款人[:：]|预计打款日期[:：]|【)")
DECLARED_DATE_RE = re.compile(r"[（(]\s*(\d{4}-\d{1,2}-\d{1,2})\s*[）)]")


@dataclass
class RawItem:
    """解析出的明细行原始值（尚未匹配表、尚未定状态）。"""

    line_no: int
    name_raw: str
    song_name: str | None
    amount: Decimal
    split_count: int | None
    span: SourceSpan


@dataclass
class ParsedRequest:
    """解析产物中间态。`missing_fields` / `date_issues` 由校验层转成异常。"""

    biz_type: BizType
    source_text: str
    declared_date: date
    items: list[RawItem] = field(default_factory=list)
    unparsed_lines: list[tuple[int, str, SourceSpan]] = field(default_factory=list)
    declared_total: Decimal | None = None
    declared_count: int | None = None
    declared_merged_count: int | None = None
    payer_raw: str | None = None
    expected_pay_date: date | None = None
    expected_pay_date_inferred: bool = False
    expected_pay_date_raw: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    date_issues: list[tuple[str, str]] = field(default_factory=list)

    @property
    def payer_norm(self) -> str:
        return normalize_name(self.payer_raw or "")

    @property
    def batch_id(self) -> str:
        return build_batch_id(self.biz_type.value, self.declared_date)

    def dedup_key_of(self, item: RawItem) -> str:
        return build_dedup_key(
            self.biz_type.value,
            self.declared_date,
            normalize_name(item.name_raw),
            item.amount,
            self.payer_norm,
        )


def detect_biz_type(text: str, hint: BizType | None = None) -> BizType:
    """按文档头判定申请类型；识别不出时**拒绝解析**而不是猜。"""
    if HEADER_DOUJIA_RE.search(text):
        return BizType.DOUJIA
    if HEADER_ADVANCE_RE.search(text):
        return BizType.ADVANCE
    if hint is not None:
        return hint
    raise ValidationError("未识别到有效申请条目，请检查文本类型（需含【抖加金额统计】或【垫付统计】）")


def _line_spans(text: str) -> list[tuple[int, str, SourceSpan]]:
    """把原文切成 (物理行号, 行内容, 偏移) —— 偏移用于界面高亮冲突 token。"""
    out: list[tuple[int, str, SourceSpan]] = []
    cursor = 0
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        start = text.find(raw_line, cursor) if raw_line else cursor
        if start < 0:
            start = cursor
        end = start + len(raw_line)
        out.append((idx, raw_line, SourceSpan(start=start, end=end)))
        cursor = end + 1
    return out


def _detail_lines(text: str) -> tuple[list[tuple[int, str, SourceSpan]], bool]:
    """截取「明细如下」之后的明细行，遇终止行停止。"""
    lines = _line_spans(text)
    start_at: int | None = None
    for pos, (_no, line, _span) in enumerate(lines):
        if DETAIL_MARKER_RE.search(line):
            start_at = pos + 1
            break
    if start_at is None:
        return [], False
    picked: list[tuple[int, str, SourceSpan]] = []
    for no, line, span in lines[start_at:]:
        stripped = normalize_text(line)
        if not stripped:
            continue
        if TERMINATOR_RE.match(stripped):
            break
        picked.append((no, line, span))
    return picked, True


def parse_request(text: str, hint: BizType | None = None) -> ParsedRequest:
    """解析申请文本 → `ParsedRequest`。

    失败**不得静默跳过**（Spec §10 输入约束）：无法识别的明细行记为
    `unparsed_lines`，由校验层升级为 `UNPARSED_LINE`（P0）。
    """
    if not text or not text.strip():
        raise ValidationError("申请文本为空")
    biz_type = detect_biz_type(text, hint)

    # 延迟导入：类型特化解析器在模块级反向依赖本模块，置于顶层会形成循环导入。
    from app.parsers import advance_parser, doujia_parser

    m = DECLARED_DATE_RE.search(text)
    if not m:
        raise ValidationError("未识别到申请日期，无法建立批次（系统不猜测日期）")
    declared_date, _ = normalize_date(m.group(1), anchor_year=date.today().year)

    parsed = ParsedRequest(biz_type=biz_type, source_text=text, declared_date=declared_date)
    parser = doujia_parser if biz_type is BizType.DOUJIA else advance_parser
    parser.fill_summary(text, parsed)

    detail_lines, marker_found = _detail_lines(text)
    if not marker_found or not detail_lines:
        raise ValidationError("未识别到有效申请条目，请检查文本类型与「明细如下：」段落")

    for line_no, line, span in detail_lines:
        raw = parser.parse_line(normalize_text(line))
        if raw is None:
            parsed.unparsed_lines.append((line_no, line.strip(), span))
            continue
        raw.line_no = line_no
        raw.span = span
        parsed.items.append(raw)

    if not parsed.items:
        raise ValidationError("未识别到有效申请条目，全部明细行解析失败")
    return parsed


def build_line_items(parsed: ParsedRequest):
    """把 `RawItem` 提升为 `LineItem`（含 dedup_key；匹配结果由校验层补）。"""
    from app.domain.models import LineItem  # 局部导入避免环

    payer = parsed.payer_raw or ""
    items: list[LineItem] = []
    for raw in parsed.items:
        items.append(
            LineItem(
                line_no=raw.line_no,
                biz_type=parsed.biz_type,
                blogger_name_raw=raw.name_raw,
                blogger_name_norm=normalize_name(raw.name_raw),
                song_name=raw.song_name,
                amount=float(raw.amount),
                amount_exact=f"{raw.amount:.2f}",
                split_count=raw.split_count,
                payer=payer,
                request_date=parsed.declared_date,
                source_span=raw.span,
                dedup_key=parsed.dedup_key_of(raw),
            )
        )
    return items


def amount_of(item) -> Decimal:
    """从 `LineItem` 取回精确金额（Decimal），供校验与汇总使用。"""
    return to_decimal(item.amount_exact or item.amount)
