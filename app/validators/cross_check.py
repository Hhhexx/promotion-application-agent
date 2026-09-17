"""交叉校验（架构 §2.5）—— 「不猜测」的核心判定。

同源校验（文本内部自相矛盾）与跨源校验（文本 vs 账号表）都收敛到本文件。
跨源判定的因果边界见架构 §4.5：**无法验证的等式不构成正确性缺陷**，
故 `CROSS_SOURCE_TOTAL_MISMATCH` 定档 P1 不阻断。
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import AnomalyCode
from app.domain.models import Anomaly, CrossCheck, LineItem
from app.parsers.base import ParsedRequest, amount_of
from app.parsers.normalizer import build_dedup_key, format_money, normalize_name, to_decimal
from app.validators.anomaly_rules import AnomalyFactory
from app.validators.matcher import SheetIndex
from app.validators.scope_rules import emit_scope_mismatch, sheet_column_sum

ZERO = Decimal("0.00")

#: 文本可声明的字段 → 账号表对应列（用于 CROSS_SOURCE_FIELD_CONFLICT）。
TEXT_FIELD_TO_SHEET: dict[str, dict[str, str]] = {
    "doujia": {"doujia_amount": "抖加", "doujia_payer": "抖加支付人"},
    "advance": {"payer": "打款人"},
}


def _declared_total(parsed: ParsedRequest) -> Decimal:
    return parsed.declared_total if parsed.declared_total is not None else ZERO


def _same_source_checks(
    factory: AnomalyFactory, parsed: ParsedRequest, items: list[LineItem]
) -> tuple[Decimal, list[Anomaly]]:
    """文本内部一致性：总额、笔数、合并笔数、日期倒挂、支付人口径。"""
    out: list[Anomaly] = []
    items_sum = sum((amount_of(i) for i in items), ZERO)

    if parsed.declared_total is not None and items_sum != parsed.declared_total:
        diff = parsed.declared_total - items_sum
        out.append(
            factory.make(
                AnomalyCode.TOTAL_MISMATCH,
                f"明细金额求和 {format_money(items_sum)} 元 ≠ 文本声明总额 "
                f"{format_money(parsed.declared_total)} 元",
                text_value=format_money(parsed.declared_total),
                sheet_value=format_money(items_sum),
                impact_amount=diff,
                action_required="需运营确认以哪个口径入账（系统不取其一）",
            )
        )

    split_sum = sum((i.split_count or 1) for i in items)
    if parsed.declared_count is not None and split_sum != parsed.declared_count:
        out.append(
            factory.make(
                AnomalyCode.COUNT_MISMATCH,
                f"文本声明「今日共 {parsed.declared_count} 笔」，明细折算后为 {split_sum} 笔，"
                f"缺口 {parsed.declared_count - split_sum} 笔",
                text_value=str(parsed.declared_count),
                sheet_value=str(split_sum),
                action_required="需运营确认缺失笔数的性质（数据丢失 / 已合并 / 已撤回）",
                evidence_note="金额求和与声明总额一致，仅笔数口径不自洽 —— 说明漏检点不在金额比对",
            )
        )

    if parsed.declared_merged_count is not None and len(items) != parsed.declared_merged_count:
        out.append(
            factory.make(
                AnomalyCode.MERGED_COUNT_MISMATCH,
                f"文本声明合并同博主后 {parsed.declared_merged_count} 笔，实际明细 {len(items)} 行",
                text_value=str(parsed.declared_merged_count),
                sheet_value=str(len(items)),
                action_required="需运营确认合并口径",
            )
        )

    if parsed.expected_pay_date is not None and parsed.expected_pay_date < parsed.declared_date:
        days = (parsed.declared_date - parsed.expected_pay_date).days
        out.append(
            factory.make(
                AnomalyCode.DATE_ORDER_INVALID,
                f"预计打款日期 {parsed.expected_pay_date.isoformat()} 早于申请日期 "
                f"{parsed.declared_date.isoformat()}，倒挂 {days} 天",
                target_field="expected_pay_date",
                text_value=parsed.expected_pay_date_raw or parsed.expected_pay_date.isoformat(),
                sheet_value=parsed.declared_date.isoformat(),
                action_required="需运营确认该日期是否为跨年写法或历史数据误填",
                evidence_note="日期疑似跨年或沿用了上一批次数据，系统不按最近年份静默改写",
            )
        )

    payers = {normalize_name(i.payer) for i in items if i.payer}
    if len(payers) > 1:
        out.append(
            factory.make(
                AnomalyCode.PAYER_INCONSISTENT,
                f"明细行之间的支付人口径不一致：{'、'.join(sorted(payers))}",
                text_value="、".join(sorted(payers)),
                action_required="需运营确认本批次支付人",
            )
        )

    seen: dict[str, LineItem] = {}
    for item in items:
        if item.dedup_key in seen:
            first = seen[item.dedup_key]
            out.append(
                factory.make(
                    AnomalyCode.DUPLICATE_WITHIN_REQUEST,
                    f"第 {item.line_no} 行与第 {first.line_no} 行为同一笔申请（去重键相同）",
                    line_no=item.line_no,
                    account_ref=item.blogger_name_raw,
                    text_value=item.dedup_key,
                    source_span=item.source_span,
                    action_required="需运营确认是否为重复提交",
                )
            )
        else:
            seen[item.dedup_key] = item

    split_items = [i for i in items if (i.split_count or 1) > 1]
    if split_items:
        detail = "、".join(f"{i.blogger_name_raw} 分 {i.split_count} 笔" for i in split_items)
        out.append(
            factory.make(
                AnomalyCode.SPLIT_NOT_RETAINED,
                f"文本含分笔申请但未提供分笔子明细（{detail}），无法按笔追溯",
                action_required="如需按笔对账，需运营补充分笔明细",
                evidence_note="系统不把合并金额拆成若干笔（拆分数额属猜测）",
            )
        )
    return items_sum, out


def _cross_source_checks(
    factory: AnomalyFactory,
    parsed: ParsedRequest,
    items: list[LineItem],
    index: SheetIndex,
    items_sum: Decimal,
) -> tuple[Decimal | None, list[Anomaly]]:
    """文本 vs 账号表。返回 (表内对应列求和, 异常列表)。"""
    out: list[Anomaly] = []
    biz = parsed.biz_type.value
    sheet_sum: Decimal | None = None

    if biz == "doujia":
        sheet_sum, sheet_owners = sheet_column_sum(index.rows, "doujia_amount")
        text_owners = [i.blogger_name_raw for i in items]
        if parsed.declared_total is not None and sheet_sum != parsed.declared_total:
            diff = abs(parsed.declared_total - sheet_sum)
            out.append(
                factory.make(
                    AnomalyCode.CROSS_SOURCE_TOTAL_MISMATCH,
                    f"文本声明抖加 {format_money(parsed.declared_total)} 元，"
                    f"账号表「抖加」列累计 {format_money(sheet_sum)} 元",
                    target_field="doujia_amount",
                    text_value=format_money(parsed.declared_total),
                    sheet_value=format_money(sheet_sum),
                    impact_amount=diff,
                    action_required="需运营确认两者口径（按批次还是累计）；系统禁止自动调和",
                    evidence_note="账号表「抖加」列无批次/日期维度，该等式无法验证，故定档 P1 不阻断",
                )
            )
        emit_scope_mismatch(
            factory, out, "博主集合", text_owners, sheet_owners, "xsrc.scope", "doujia_amount"
        )
        sheet_payers = sorted({r.text("doujia_payer") for r in index.rows if r.text("doujia_payer")})
        if parsed.payer_raw and sheet_payers and parsed.payer_raw not in sheet_payers:
            emit_scope_mismatch(
                factory,
                out,
                "抖加支付人口径",
                [parsed.payer_raw],
                sheet_payers,
                "xsrc.scope_payer",
                "doujia_payer",
            )
    else:
        paid_rows = [r for r in index.rows if r.text("payer")]
        sheet_owners = [r.text("douyin_nickname") for r in paid_rows if r.text("douyin_nickname")]
        emit_scope_mismatch(
            factory,
            out,
            "博主集合（对比台账已登记打款人的行）",
            [i.blogger_name_raw for i in items],
            sheet_owners,
            "xsrc.scope",
            "payer",
        )
        sheet_payers = sorted({r.text("payer") for r in paid_rows})
        if parsed.payer_raw and sheet_payers and parsed.payer_raw not in sheet_payers:
            emit_scope_mismatch(
                factory,
                out,
                "打款人口径",
                [parsed.payer_raw],
                sheet_payers,
                "xsrc.scope_payer",
                "payer",
            )

    out.extend(_field_conflicts(factory, parsed.biz_type.value, parsed.payer_raw, items, index))
    return sheet_sum, out


def _field_conflicts(
    factory: AnomalyFactory,
    biz_type: str,
    batch_payer: str | None,
    items: list[LineItem],
    index: SheetIndex,
) -> list[Anomaly]:
    """`CROSS_SOURCE_FIELD_CONFLICT`（P0）。

    适用前提（本次实现明确固化，架构 §2.5 的必然推论）：**目标行必须唯一**。
    匹配为 `AMBIGUOUS` / `NO_MATCH` 时不存在可比对的表内行，此时不作字段冲突判定，
    相关观察写入歧义异常的 `evidence_note`，信息不丢失。
    """
    out: list[Anomaly] = []
    mapping = TEXT_FIELD_TO_SHEET.get(biz_type, {})
    for item in items:
        match = item.match_result
        if match is None or match.matched_row_ref is None:
            continue
        row = index.row_by_ref(match.matched_row_ref)
        if row is None:
            continue
        for sheet_key, label in mapping.items():
            sheet_text = row.text(sheet_key)
            if not sheet_text:
                continue
            text_value = _text_field_value(item, sheet_key, batch_payer)
            if not text_value:
                continue
            if normalize_name(sheet_text) != normalize_name(text_value):
                out.append(
                    factory.make(
                        AnomalyCode.CROSS_SOURCE_FIELD_CONFLICT,
                        f"「{item.blogger_name_raw}」的{label}：文本为「{text_value}」，"
                        f"台账第 {row.row_ref} 行为「{sheet_text}」",
                        line_no=item.line_no,
                        account_ref=item.blogger_name_raw,
                        sheet_row_ref=row.row_ref,
                        target_field=sheet_key,
                        text_value=text_value,
                        sheet_value=sheet_text,
                        source_span=item.source_span,
                        action_required=f"需运营确认{label}以哪一侧为准；系统不覆盖已有值",
                    )
                )
    return out


def _text_field_value(item: LineItem, sheet_key: str, batch_payer: str | None) -> str | None:
    if sheet_key == "doujia_amount":
        return item.amount_exact or f"{item.amount:.2f}"
    if sheet_key == "doujia_payer":
        return batch_payer
    if sheet_key == "payer":
        return item.payer
    return None


def run_cross_checks(
    factory: AnomalyFactory,
    parsed: ParsedRequest,
    items: list[LineItem],
    index: SheetIndex,
) -> tuple[CrossCheck, list[Anomaly]]:
    """执行同源 + 跨源全部校验，返回 `CrossCheck` 与异常清单。"""
    items_sum, same_src = _same_source_checks(factory, parsed, items)
    sheet_sum, cross_src = _cross_source_checks(factory, parsed, items, index, items_sum)

    split_sum = sum((i.split_count or 1) for i in items)
    check = CrossCheck(
        line_items_sum=float(items_sum),
        declared_total_amount=float(_declared_total(parsed)),
        split_count_sum=split_sum,
        declared_count=parsed.declared_count,
        line_items_len=len(items),
        declared_merged_count=parsed.declared_merged_count,
        expected_pay_date=parsed.expected_pay_date,
        declared_date=parsed.declared_date,
        sheet_column_sum=float(sheet_sum) if sheet_sum is not None else None,
        sheet_column_sum_exact=format_money(sheet_sum) if sheet_sum is not None else None,
    )
    return check, same_src + cross_src


def dedup_key_for(item: LineItem) -> str:
    """重算去重键（供回读校验比对）。"""
    return build_dedup_key(
        item.biz_type.value if hasattr(item.biz_type, "value") else str(item.biz_type),
        item.request_date,
        item.blogger_name_norm,
        to_decimal(item.amount_exact or item.amount),
        normalize_name(item.payer),
    )
