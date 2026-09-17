"""负责人汇报卡（架构 §5.1 输出层 / 设计 §2.5 压缩原则）。

只保留四类信息：一行结论、3~4 个关键数字、≤3 条需决策项、元信息。
**去掉**逐条明细、解析过程、技术字段名、系统内部状态。
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.enums import ItemState, Severity, ev
from app.domain.models import AnomalyBrief, DailyReport, DecisionItem
from app.repositories.memory_store import MemoryStore
from app.reporters.summary_service import build_summary, money, requests_for

MAX_DECISIONS = 3
SEVERITY_ORDER = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2}
LAMP = {Severity.P0: "红灯", Severity.P1: "黄灯", Severity.P2: "提示"}


def _pending_anomalies(results) -> list:
    out = []
    for result in results:
        for anomaly in result.anomalies:
            if anomaly.resolved:
                continue
            if str(anomaly.rule_id).startswith("table."):
                continue
            out.append((result, anomaly))
    out.sort(
        key=lambda pair: (
            SEVERITY_ORDER.get(pair[1].severity, 9),
            -(pair[1].impact_amount or 0.0),
        )
    )
    return out


def build_report(
    store: MemoryStore, target: date_cls, include_unresolved: bool = True
) -> DailyReport:
    summary = build_summary(store, target)
    results = requests_for(store, target)
    by_biz = {b.biz_type.value: b for b in summary.blocks}
    doujia = by_biz.get("doujia")
    advance = by_biz.get("advance")

    confirmed = Decimal("0.00")
    pending = Decimal("0.00")
    for result in results:
        for item in result.line_items:
            amount = Decimal(item.amount_exact or f"{item.amount:.2f}")
            if item.state in (ItemState.NEEDS_REVIEW, ItemState.BLOCKED):
                pending += amount
            else:
                confirmed += amount

    pairs = _pending_anomalies(results) if include_unresolved else []
    blocking = [(r, a) for r, a in pairs if a.blocking]
    warn = [(r, a) for r, a in pairs if not a.blocking]

    headline = _headline(doujia, advance, blocking, warn)
    decisions = [
        DecisionItem(
            severity=anomaly.severity,
            headline=f"{LAMP.get(anomaly.severity, '提示')} · {anomaly.message}",
            need_from=anomaly.action_required or "需业务方确认",
        )
        for _result, anomaly in pairs[:MAX_DECISIONS]
    ]

    report = DailyReport(
        report_id=f"rep_{target.strftime('%Y%m%d')}_{store.next_seq('report'):02d}",
        date=target,
        headline=headline,
        doujia_total=doujia.total_amount if doujia else 0.0,
        advance_total=advance.total_amount if advance else 0.0,
        confirmed_amount=float(confirmed),
        pending_amount=float(pending),
        anomaly_count=len(pairs),
        pending_review_count=len(blocking),
        anomalies_summary=[
            AnomalyBrief(
                code=ev(anomaly.code),
                severity=anomaly.severity,
                message=anomaly.message,
                exc_id=anomaly.exc_id,
            )
            for _result, anomaly in pairs
        ],
        decisions=decisions,
        overflow_count=max(0, len(pairs) - MAX_DECISIONS),
        generated_at=datetime.now(timezone.utc),
        markdown="",
    )
    report.markdown = _to_markdown(report, doujia, advance)
    return report


def _headline(doujia, advance, blocking, warn) -> str:
    parts: list[str] = []
    if doujia and doujia.entry_count:
        parts.append(f"抖加 {money(doujia.total_amount)}")
    if advance and advance.entry_count:
        parts.append(f"垫付 {money(advance.total_amount)}")
    if not parts:
        return "当日无申请记录，无需入账动作。"
    scope = "、".join(parts)
    if blocking:
        return f"{scope}；存在 {len(blocking)} 项阻断待人工确认，未入账。"
    if warn:
        return f"{scope}；无阻断项，{len(warn)} 项口径待确认（不阻断入账）。"
    return f"{scope}；校验全部通过，可入账。"


def _to_markdown(report: DailyReport, doujia, advance) -> str:
    lines = [f"【当日汇报 · {report.date.isoformat()}】", f"结论：{report.headline}", ""]
    lines.append("关键数字")
    if doujia and doujia.entry_count:
        lines.append(f"- 抖加合计 {money(doujia.total_amount)}（{doujia.entry_count} 笔）")
    if advance and advance.entry_count:
        lines.append(f"- 垫付合计 {money(advance.total_amount)}（{advance.entry_count} 笔）")
    lines.append(f"- 已确认金额 {money(report.confirmed_amount)} / 待确认金额 {money(report.pending_amount)}")
    lines.append(f"- 未裁决阻断项 {report.pending_review_count}；口径待确认项 {report.anomaly_count}")
    if report.decisions:
        lines.append("")
        lines.append("需决策")
        for idx, item in enumerate(report.decisions, start=1):
            lines.append(f"{idx}. {item.headline} · {item.need_from}")
        if report.overflow_count:
            lines.append(f"（另有 {report.overflow_count} 项，见工作台）")
    lines.append("")
    stamp = report.generated_at.astimezone().strftime("%Y-%m-%d %H:%M") if report.generated_at else ""
    lines.append(f"数据来源：账号表测试副本（未触碰原表）；生成时间 {stamp}")
    return "\n".join(lines)
