"""异常工厂与表级体检规则（架构 §4）。

`AnomalyFactory` 保证「25 个异常码 → Anomaly」的构造口径唯一：定档级别、
是否阻断、PRD 编号一律从 `app.domain.enums` 取，禁止在规则里硬写。

表级体检规则（`table.*`）与批次无关，每次校验都会重跑一次，全部为 P1/P2 不阻断，
不参与写表闸门判定。
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.domain.enums import AnomalyCode, Severity, exc_id_of, is_blocking, severity_of
from app.domain.models import Anomaly, SourceSpan
from app.parsers.normalizer import format_money, to_decimal
from app.repositories.xlsx_repository import SheetRow

#: 异常码 → 规则 ID。界面按 `table.` 前缀把体检项与批次项分区展示。
RULE_ID_BY_CODE: dict[AnomalyCode, str] = {
    AnomalyCode.TOTAL_MISMATCH: "cross.total",
    AnomalyCode.COUNT_MISMATCH: "cross.count",
    AnomalyCode.MERGED_COUNT_MISMATCH: "cross.merged_count",
    AnomalyCode.DATE_ORDER_INVALID: "cross.date_order",
    AnomalyCode.DATE_UNRESOLVABLE: "cross.date_unresolvable",
    AnomalyCode.PAYER_INCONSISTENT: "cross.payer",
    AnomalyCode.DUPLICATE_WITHIN_REQUEST: "req.duplicate",
    AnomalyCode.FIELD_MISSING: "req.field_missing",
    AnomalyCode.UNPARSED_LINE: "req.unparsed_line",
    AnomalyCode.MATCH_AMBIGUOUS: "match.ambiguous",
    AnomalyCode.MATCH_NOT_FOUND: "match.not_found",
    AnomalyCode.DOUYIN_ID_EMPTY: "match.douyin_id_empty",
    AnomalyCode.CROSS_SOURCE_TOTAL_MISMATCH: "xsrc.total",
    AnomalyCode.CROSS_SOURCE_SCOPE_MISMATCH: "xsrc.scope",
    AnomalyCode.CROSS_SOURCE_FIELD_CONFLICT: "xsrc.field_conflict",
    AnomalyCode.TARGET_CELL_NONEMPTY: "write.target_nonempty",
    AnomalyCode.LLM_RULE_CONFLICT: "llm.rule_conflict",
    AnomalyCode.SPLIT_NOT_RETAINED: "req.split_not_retained",
    AnomalyCode.TABLE_EMPTY_ROW_SKIPPED: "table.empty_row",
    AnomalyCode.DATE_FORMAT_INCONSISTENT: "table.date_format",
    AnomalyCode.UNACCEPTED_WITH_AMOUNT: "table.unaccepted_amount",
    AnomalyCode.DOUJIA_EXCEEDS_QUOTE: "table.doujia_exceeds_quote",
    AnomalyCode.NICKNAME_DIRTY: "table.nickname_dirty",
    AnomalyCode.REMARK_EMPTY: "table.remark_empty",
    AnomalyCode.STATUS_FIELD_INCONSISTENT: "table.status_inconsistent",
}

#: 昵称中的非业务装饰字符。**不自动清洗**，只提示人工核对。
DIRTY_NICKNAME_RE = re.compile(r"[@#$%^&*+=\[\]{}|\\/<>~`\u3000]")


class AnomalyFactory:
    """按序生成 `anm_xx` 编号的异常构造器。"""

    def __init__(self, prefix: str = "anm") -> None:
        self.prefix = prefix
        self._n = 0

    def make(
        self,
        code: AnomalyCode,
        message: str,
        *,
        severity: Severity | None = None,
        blocking: bool | None = None,
        rule_id: str | None = None,
        line_no: int | None = None,
        target_field: str | None = None,
        suggestion: str | None = None,
        account_ref: str | None = None,
        text_value: str | None = None,
        sheet_value: str | None = None,
        source_span: SourceSpan | None = None,
        impact_amount: Decimal | None = None,
        action_required: str | None = None,
        evidence_note: str | None = None,
        sheet_row_ref: str | None = None,
    ) -> Anomaly:
        self._n += 1
        return Anomaly(
            anomaly_id=f"{self.prefix}_{self._n:02d}",
            rule_id=rule_id or RULE_ID_BY_CODE.get(code, code.value.lower()),
            exc_id=exc_id_of(code),
            code=code,
            severity=severity or severity_of(code),
            blocking=is_blocking(code) if blocking is None else blocking,
            message=message,
            line_no=line_no,
            target_field=target_field,
            suggestion=suggestion,
            account_ref=account_ref,
            text_value=text_value,
            sheet_value=sheet_value,
            source_span=source_span,
            impact_amount=float(impact_amount) if impact_amount is not None else None,
            action_required=action_required,
            evidence_note=evidence_note,
            sheet_row_ref=sheet_row_ref,
        )


def _money(raw: object) -> Decimal | None:
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    try:
        return to_decimal(text)
    except Exception:
        return None


def table_health_anomalies(
    factory: AnomalyFactory,
    rows: list[SheetRow],
    empty_row_refs: list[str],
    date_styles: dict[str, int],
    highlighted_empty_remarks: list[str],
) -> list[Anomaly]:
    """账号表体检：与本次申请无关的台账卫生问题，全部 P1/P2、不阻断写表。"""
    out: list[Anomaly] = []

    for row_ref in empty_row_refs:
        out.append(
            factory.make(
                AnomalyCode.TABLE_EMPTY_ROW_SKIPPED,
                f"账号表第 {row_ref} 行为整行空行（含主键昵称与抖音号均为空），已跳过不参与匹配",
                sheet_row_ref=row_ref,
                action_required="需运营确认该行是待补录账号还是应删除的残留行",
                evidence_note="空行不会被删除，也不会被当作匹配目标；系统不猜测其归属",
            )
        )

    if len({k for k in date_styles if k not in ("empty", "unknown")}) > 1:
        detail = "、".join(f"{k}×{v}" for k, v in sorted(date_styles.items()))
        out.append(
            factory.make(
                AnomalyCode.DATE_FORMAT_INCONSISTENT,
                f"台账日期列存在多种书写风格（{detail}），其中无年份写法无法唯一确定年份",
                target_field="date_columns",
                action_required="需运营给出年份归属口径；在此之前系统不推断日期列的年份",
                evidence_note="无年份写法（如 4.9 / 4.10）按批次日期锚定只能得到推断值，必须标 inferred 并待确认",
            )
        )

    for row in rows:
        out.extend(_row_level_anomalies(factory, row))

    for row_ref in highlighted_empty_remarks:
        out.append(
            factory.make(
                AnomalyCode.REMARK_EMPTY,
                f"账号表第 {row_ref} 行「备注」单元格被底色高亮标记，但内容为空",
                sheet_row_ref=row_ref,
                target_field="remark",
                action_required="需运营补充该行备注原文，或清除高亮标记",
                evidence_note="高亮通常意味着此处本应有内容；系统不代为填写",
            )
        )
    return out


def _row_level_anomalies(factory: AnomalyFactory, row: SheetRow) -> list[Anomaly]:
    """逐行体检。"""
    out: list[Anomaly] = []
    name = row.text("douyin_nickname") or f"第 {row.row_ref} 行"
    quote = _money(row.values.get("quote_price"))
    doujia = _money(row.values.get("doujia_amount"))
    accepted = row.text("accepted")
    is_paid = row.text("is_paid")
    payer = row.text("payer")
    pay_date = row.text("pay_date")
    doujia_payer = row.text("doujia_payer")
    review = row.text("review_result")

    if accepted == "否" and ((quote is not None and quote > 0) or (doujia is not None and doujia > 0)):
        amount = (quote or Decimal("0")) + (doujia or Decimal("0"))
        out.append(
            factory.make(
                AnomalyCode.UNACCEPTED_WITH_AMOUNT,
                f"「{name}」是否接单为「否」，却已登记金额 {format_money(amount)} 元",
                account_ref=name,
                sheet_row_ref=row.row_ref,
                target_field="accepted",
                sheet_value=accepted,
                impact_amount=amount,
                action_required="需运营确认该博主是否已接单，或该金额是否为误录",
            )
        )

    if doujia is not None and quote is not None and doujia > quote:
        out.append(
            factory.make(
                AnomalyCode.DOUJIA_EXCEEDS_QUOTE,
                f"「{name}」抖加 {format_money(doujia)} 元高于合作报价 {format_money(quote)} 元",
                account_ref=name,
                sheet_row_ref=row.row_ref,
                target_field="doujia_amount",
                text_value=format_money(quote),
                sheet_value=format_money(doujia),
                impact_amount=doujia - quote,
                action_required="需运营复核抖加投放金额是否填写有误",
            )
        )

    if DIRTY_NICKNAME_RE.search(name):
        out.append(
            factory.make(
                AnomalyCode.NICKNAME_DIRTY,
                f"账号表昵称「{name}」含非业务装饰字符",
                account_ref=name,
                sheet_row_ref=row.row_ref,
                target_field="douyin_nickname",
                sheet_value=name,
                suggestion=DIRTY_NICKNAME_RE.sub("", name),
                action_required="需确认该昵称是否为原始昵称；系统不做自动清洗（去装饰属猜测）",
            )
        )

    if is_paid == "是" and not payer:
        out.append(
            factory.make(
                AnomalyCode.STATUS_FIELD_INCONSISTENT,
                f"「{name}」是否打款为「是」，但打款人为空",
                rule_id="table.status_payment",
                severity=Severity.P1,
                account_ref=name,
                sheet_row_ref=row.row_ref,
                target_field="payer",
                text_value="是否打款=是",
                sheet_value="（空）",
                action_required="需财务确认实际打款人（系统不填默认值）",
            )
        )
    if is_paid == "是" and not pay_date:
        out.append(
            factory.make(
                AnomalyCode.STATUS_FIELD_INCONSISTENT,
                f"「{name}」是否打款为「是」，但打款日期为空",
                rule_id="table.status_payment",
                severity=Severity.P1,
                account_ref=name,
                sheet_row_ref=row.row_ref,
                target_field="pay_date",
                text_value="是否打款=是",
                sheet_value="（空）",
                action_required="需财务确认实际打款日期（系统不填默认值）",
            )
        )
    if doujia is not None and doujia > 0 and not doujia_payer:
        out.append(
            factory.make(
                AnomalyCode.STATUS_FIELD_INCONSISTENT,
                f"「{name}」已登记抖加 {format_money(doujia)} 元，但抖加支付人为空",
                rule_id="table.status_payment",
                severity=Severity.P1,
                account_ref=name,
                sheet_row_ref=row.row_ref,
                target_field="doujia_payer",
                sheet_value="（空）",
                action_required="需运营确认抖加支付人",
            )
        )
    if accepted == "否" and review:
        out.append(
            factory.make(
                AnomalyCode.STATUS_FIELD_INCONSISTENT,
                f"「{name}」是否接单为「否」，但审核结果为「{review}」",
                rule_id="table.status_accepted_review",
                severity=Severity.P2,
                account_ref=name,
                sheet_row_ref=row.row_ref,
                target_field="review_result",
                sheet_value=review,
                action_required="需运营确认接单与审核状态的先后口径",
            )
        )
    return out
