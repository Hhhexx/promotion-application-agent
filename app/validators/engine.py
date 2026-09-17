"""校验引擎：解析产物 + 账号表快照 → `ParseResult`（架构 §4.2）。

确定性链路：parse → match → same-source check → cross-source check → table health。
不含任何"取其一 / 填默认值"的分支 —— 不确定即升级人工。
"""

from __future__ import annotations

from app.domain.enums import AnomalyCode, ItemState, MatchLevel
from app.domain.models import Anomaly, ParseResult
from app.llm.llm_adapter import get_adapter
from app.parsers.base import ParsedRequest, build_line_items
from app.parsers.normalizer import normalize_name
from app.repositories.xlsx_repository import TableSnapshot
from app.validators.anomaly_rules import AnomalyFactory, table_health_anomalies
from app.validators.cross_check import run_cross_checks
from app.validators.matcher import SheetIndex

ITEM_LEVEL_MATCH_CODES = (
    AnomalyCode.MATCH_AMBIGUOUS,
    AnomalyCode.MATCH_NOT_FOUND,
    AnomalyCode.DOUYIN_ID_EMPTY,
)


def _match_anomalies(
    factory: AnomalyFactory, items, index: SheetIndex
) -> list[Anomaly]:
    """逐条匹配；非 EXACT_* 一律升级人工（架构 §2.7 禁止兜底猜测）。"""
    out: list[Anomaly] = []
    for item in items:
        result = index.match(item.blogger_name_raw)
        item.match_result = result

        if result.level is MatchLevel.AMBIGUOUS:
            rows = [index.row_by_ref(c.row_ref) for c in result.candidates]
            detail = "；".join(
                f"第 {r.row_ref} 行 抖音号={r.text('douyin_id') or '（空）'} "
                f"是否打款={r.text('is_paid') or '（空）'} 打款人={r.text('payer') or '（空）'} "
                f"打款日期={r.text('pay_date') or '（空）'}"
                for r in rows
                if r is not None
            )
            out.append(
                factory.make(
                    AnomalyCode.MATCH_AMBIGUOUS,
                    f"「{item.blogger_name_raw}」在账号表命中 {len(result.candidates)} 行，"
                    f"无法自动判定写入目标",
                    line_no=item.line_no,
                    account_ref=item.blogger_name_raw,
                    source_span=item.source_span,
                    suggestion="请人工指定目标行；系统不会自行挑选第一行",
                    action_required="需运营指定目标行（或说明该博主是否需要新建行）",
                    evidence_note=(
                        f"候选行明细 —— {detail}。"
                        "因目标行未确定，系统不对候选行做字段冲突判定（避免误判为 P0 冲突）；"
                        "若某候选行的字段值与文本不同，该差异同样需要人工确认。"
                    ),
                )
            )
        elif result.level in (MatchLevel.NO_MATCH, MatchLevel.WEAK_FUZZY):
            candidates = "、".join(
                f"{c.douyin_nickname}({c.row_ref}, {c.score})" for c in result.candidates
            )
            out.append(
                factory.make(
                    AnomalyCode.MATCH_NOT_FOUND,
                    f"「{item.blogger_name_raw}」在账号表中"
                    + ("无精确命中，仅有模糊候选" if result.candidates else "无任何命中"),
                    line_no=item.line_no,
                    account_ref=item.blogger_name_raw,
                    source_span=item.source_span,
                    suggestion=f"候选：{candidates}" if candidates else None,
                    action_required="需运营确认该账号在台账中的位置；系统禁止自动新建行",
                    evidence_note=(
                        "模糊候选仅作提示，不参与自动采纳（架构 §2.7 WEAK_FUZZY）"
                        if result.candidates
                        else None
                    ),
                )
            )
        elif result.matched_row_ref:
            row = index.row_by_ref(result.matched_row_ref)
            if row is not None and not row.text("douyin_id"):
                out.append(
                    factory.make(
                        AnomalyCode.DOUYIN_ID_EMPTY,
                        f"「{item.blogger_name_raw}」对应账号表第 {row.row_ref} 行抖音号为空，"
                        f"本次匹配仅依赖昵称",
                        line_no=item.line_no,
                        account_ref=item.blogger_name_raw,
                        sheet_row_ref=row.row_ref,
                        target_field="douyin_id",
                        action_required="建议运营补齐抖音号，以降低同名歧义风险",
                    )
                )
    return out


def _llm_checks(factory: AnomalyFactory, items, index: SheetIndex) -> tuple[list[Anomaly], bool]:
    """LLM 旁路：**与规则不一致即升级人工，不取其一**（架构 §5.4）。"""
    adapter = get_adapter()
    if not adapter.available:
        return [], False
    out: list[Anomaly] = []
    for item in items:
        suggestion = adapter.suggest_entity(item.blogger_name_raw)
        if suggestion is None:
            continue
        llm_match = index.match(suggestion)
        rule_level = item.match_result.level if item.match_result else None
        agrees = (
            llm_match.level in (MatchLevel.EXACT_ID, MatchLevel.EXACT_NAME)
            and rule_level in (MatchLevel.EXACT_ID, MatchLevel.EXACT_NAME)
            and llm_match.matched_row_ref == item.match_result.matched_row_ref
        )
        if agrees or llm_match.level is MatchLevel.NO_MATCH:
            continue
        # 两侧都判「无法确定目标行」（同为 AMBIGUOUS）→ 结论其实一致，不构成分歧。
        # 歧义本身已由 match.ambiguous（P0）记录在案，此处再报一次只是噪声，
        # 还会产出一条目标行写 `?` 的空洞异常，干扰操作员的裁决队列。
        if llm_match.level is MatchLevel.AMBIGUOUS and rule_level is MatchLevel.AMBIGUOUS:
            continue
        out.append(
            factory.make(
                AnomalyCode.LLM_RULE_CONFLICT,
                f"LLM 对「{item.blogger_name_raw}」的建议（{suggestion} → 第 "
                f"{llm_match.matched_row_ref or '?'} 行）与规则判定（{rule_level}）不一致",
                line_no=item.line_no,
                account_ref=item.blogger_name_raw,
                text_value=suggestion,
                sheet_value=str(item.match_result.matched_row_ref or ""),
                source_span=item.source_span,
                action_required="需人工裁定以哪一侧为准；系统不采信任何一侧",
                evidence_note="规则与模型结论分歧时升级人工，避免二选一掩盖真实分歧",
            )
        )
    return out, True


def validate(
    parsed: ParsedRequest,
    snapshot: TableSnapshot,
    request_id: str,
) -> ParseResult:
    """执行完整校验并产出 `ParseResult`。"""
    factory = AnomalyFactory()
    items = build_line_items(parsed)
    index = SheetIndex(snapshot.rows)
    anomalies: list[Anomaly] = []

    anomalies.extend(_match_anomalies(factory, items, index))

    for field in parsed.missing_fields:
        anomalies.append(
            factory.make(
                AnomalyCode.FIELD_MISSING,
                f"文本中未识别到必填字段：{field}",
                target_field=field,
                action_required=f"需运营补充{field}；系统保持该字段为空并标记，不填默认值",
            )
        )
    for field, raw in parsed.date_issues:
        anomalies.append(
            factory.make(
                AnomalyCode.DATE_UNRESOLVABLE,
                f"{field}「{raw}」无法唯一归一为具体日期",
                target_field=field,
                text_value=raw,
                action_required=f"需运营给出{field}的完整日期（含年份）",
            )
        )
    for line_no, raw, span in parsed.unparsed_lines:
        anomalies.append(
            factory.make(
                AnomalyCode.UNPARSED_LINE,
                f"第 {line_no} 行无法被任何模板规则解析，已保留原文待人工补录",
                line_no=line_no,
                text_value=raw.strip(),
                source_span=span,
                action_required="需运营确认该行内容或补齐格式；系统不静默跳过",
            )
        )

    check, cross_anomalies = run_cross_checks(factory, parsed, items, index)
    anomalies.extend(cross_anomalies)

    llm_anomalies, llm_used = _llm_checks(factory, items, index)
    anomalies.extend(llm_anomalies)

    anomalies.extend(
        table_health_anomalies(
            factory,
            snapshot.rows,
            snapshot.empty_row_refs,
            snapshot.date_styles,
            snapshot.highlighted_empty_remarks,
        )
    )

    blocking_open = [a for a in anomalies if a.blocking]
    state = ItemState.NEEDS_REVIEW if blocking_open else ItemState.READY
    for item in items:
        item.state = state

    if parsed.declared_total is None:
        check.declared_total_amount = float(check.line_items_sum)

    return ParseResult(
        request_id=request_id,
        batch_id=parsed.batch_id,
        biz_type=parsed.biz_type,
        request_date=parsed.declared_date,
        summary=_summary_model(parsed, check),
        line_items=items,
        cross_check=check,
        anomalies=anomalies,
        aggregate_state=state,
        llm_used=llm_used,
    )


def _summary_model(parsed: ParsedRequest, check):
    from app.domain.models import ClaimSummary

    return ClaimSummary(
        biz_type=parsed.biz_type,
        declared_total_amount=float(parsed.declared_total or 0),
        declared_total_exact=f"{parsed.declared_total or 0:.2f}",
        declared_date=parsed.declared_date,
        declared_count=parsed.declared_count,
        declared_merged_count=parsed.declared_merged_count,
        payer=parsed.payer_raw or "",
        expected_pay_date=parsed.expected_pay_date,
        expected_pay_date_inferred=parsed.expected_pay_date_inferred,
        expected_pay_date_raw=parsed.expected_pay_date_raw,
    )


def open_p0(anomalies: list[Anomaly]) -> list[Anomaly]:
    """未裁决的阻断项 —— 写表闸门的唯一判据。"""
    return [a for a in anomalies if a.blocking and not a.resolved]


def name_matches(a: str, b: str) -> bool:
    return normalize_name(a) == normalize_name(b)
