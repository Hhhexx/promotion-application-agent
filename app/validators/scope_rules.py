"""跨源「范围 / 口径」族规则（架构 §2.5 / §4.5）。

与 `cross_check` 里「同一字段两侧取值冲突」（P0）不同，本模块只处理**覆盖范围**
层面的不一致：文本与账号表列出的博主集合 / 支付人集合不同，只能定档 P1——
**范围不同不等于同一字段取值冲突**，不得升格为 P0。

拆出本模块是为了让「字段冲突判定」与「范围差异判定」各自单一职责、
文件规模可控（代码组织规范 §1）。
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import AnomalyCode, Severity
from app.domain.models import Anomaly
from app.repositories.xlsx_repository import SheetRow
from app.validators.anomaly_rules import AnomalyFactory, _money

ZERO = Decimal("0.00")


def sheet_column_sum(rows: list[SheetRow], key: str) -> tuple[Decimal, list[str]]:
    """账号表某列的累计值与贡献该值的博主名（第三口径；不参与总额合并）。"""
    total = ZERO
    owners: list[str] = []
    for row in rows:
        value = _money(row.values.get(key))
        if value is None or value == 0:
            continue
        total += value
        name = row.text("douyin_nickname")
        if name:
            owners.append(name)
    return total, owners


def emit_scope_mismatch(
    factory: AnomalyFactory,
    out: list[Anomaly],
    label: str,
    text_values: list[str],
    sheet_values: list[str],
    rule_id: str,
    field: str,
) -> None:
    """两级集合差异 → P1。**不同博主/不同行的差异不得升格为 P0 字段冲突。**"""
    if set(text_values) == set(sheet_values):
        return
    only_text = sorted(set(text_values) - set(sheet_values))
    only_sheet = sorted(set(sheet_values) - set(text_values))
    parts = []
    if only_text:
        parts.append(f"仅文本有：{'、'.join(only_text)}")
    if only_sheet:
        parts.append(f"仅台账有：{'、'.join(only_sheet)}")
    out.append(
        factory.make(
            AnomalyCode.CROSS_SOURCE_SCOPE_MISMATCH,
            f"文本与账号表的{label}不一致（{'；'.join(parts)}）",
            rule_id=rule_id,
            severity=Severity.P1,
            target_field=field,
            text_value="、".join(text_values),
            sheet_value="、".join(sheet_values),
            action_required="需运营确认台账与文本的覆盖范围口径",
            evidence_note="两侧范围不同不等于同一字段取值冲突，故不升格为 P0",
        )
    )


__all__ = ["sheet_column_sum", "emit_scope_mismatch"]
