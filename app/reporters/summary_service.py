"""当日汇总（架构 §5.1 输出层）。

**三口径并列**：文本声明总额 / 明细求和 / 账号表对应列求和。
三者**不合并为单一数字**（Spec F-7 / AC-04）—— 合并就等于替用户做了口径裁决。
"""

from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal

from app.domain.enums import BizType
from app.domain.models import DailySummary, ParseResult, SummaryBlock
from app.parsers.normalizer import format_money
from app.repositories.memory_store import MemoryStore

ZERO = Decimal("0.00")


def requests_for(store: MemoryStore, target: date_cls, biz_type=None) -> list[ParseResult]:
    """当日**生效**的解析结果（同批次重复解析只保留最新一条，AC-08）。

    唯一取数入口：`build_summary` 与 `build_report` 都走这里，
    因此批次级幂等只需在此处收敛，不会出现「汇总不放大、汇报仍放大」的割裂。
    """
    out = [r for r in store.active_requests() if r.request_date == target]
    if biz_type is not None:
        wanted = biz_type.value if hasattr(biz_type, "value") else str(biz_type)
        out = [r for r in out if r.biz_type.value == wanted]
    return sorted(out, key=lambda r: r.request_id)


def _block(biz: BizType, results: list[ParseResult]) -> SummaryBlock:
    if not results:
        label = "抖加" if biz is BizType.DOUJIA else "垫付"
        return SummaryBlock(
            biz_type=biz,
            total_amount=0.0,
            entry_count=0,
            note=f"当日无{label}申请解析记录",
        )

    items_sum = ZERO
    declared = ZERO
    sheet_sum: Decimal | None = None
    declared_count = 0
    item_count = 0
    entry_count = 0
    for result in results:
        items_sum += Decimal(result.cross_check.line_items_sum)
        declared += Decimal(result.cross_check.declared_total_amount)
        declared_count += result.cross_check.declared_count or 0
        item_count += result.cross_check.split_count_sum or 0
        entry_count += result.cross_check.line_items_len
        if result.cross_check.sheet_column_sum is not None:
            value = Decimal(result.cross_check.sheet_column_sum)
            sheet_sum = value if sheet_sum is None else sheet_sum + value

    consistent = declared == items_sum and (declared_count == item_count or declared_count == 0)
    label = "抖加" if biz is BizType.DOUJIA else "垫付"
    scope = "文本声明额 / 明细求和" + (" / 表内该列累计" if sheet_sum is not None else "")
    note = (
        f"来源：{label}申请文本 + 测试副本；三口径并列（{scope}），"
        + ("各口径一致" if consistent else "存在口径不一致，禁止自动调和")
    )
    return SummaryBlock(
        biz_type=biz,
        total_amount=float(items_sum),
        entry_count=entry_count,
        declared_total_amount=float(declared),
        line_items_sum=float(items_sum),
        sheet_column_sum=float(sheet_sum) if sheet_sum is not None else None,
        declared_count=declared_count or None,
        item_count=item_count or None,
        consistent=consistent,
        note=note,
    )


def build_summary(store: MemoryStore, target: date_cls, biz_type=None) -> DailySummary:
    results = requests_for(store, target, biz_type)
    wanted = [BizType.DOUJIA, BizType.ADVANCE]
    if biz_type is not None:
        value = biz_type.value if hasattr(biz_type, "value") else str(biz_type)
        wanted = [b for b in wanted if b.value == value]
    blocks = [_block(biz, [r for r in results if r.biz_type is biz]) for biz in wanted]
    return DailySummary(date=target, blocks=blocks)


def money(value: float | Decimal | None) -> str:
    """统一的金额展示（保 2 位，带千分位）。"""
    if value is None:
        return "—"
    return f"¥{format_money(Decimal(str(value)))}"
