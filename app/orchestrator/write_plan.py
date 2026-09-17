"""写表规划：把「已确认条目」翻译成「允许回填的单元格」。

**回填权限的唯一来源**（架构 §4.4 / PRD 回填权限表）：文本未声明的字段一律不写。
从 `pipeline` 拆出，保持单一职责，也让编排层只关注编排。
"""

from __future__ import annotations

#: `AFTER_DECISION` 列的允许取值来源 —— 文本未声明的字段一律不写。
ADVANCE_PENDING_NOTE = "是否打款=未写入（文本仅声明垫付申请与预计打款日期，系统不推断已打款）"


def has_batch_decision(result) -> bool:
    """`AFTER_DECISION` 列的写入前置条件之一：本批次存在 accept/override 裁决，或初始无 P0。"""
    if any(a.resolution is not None and a.resolution.decision in ("accept", "override") for a in result.anomalies):
        return True
    return not any(a.blocking for a in result.anomalies)


def confirmed_by(result, line_no: int | None) -> str:
    """回填单元格的 `_confirmed_by` 溯源值。"""
    for anomaly in result.anomalies:
        if anomaly.resolution is None or anomaly.line_no != line_no:
            continue
        return anomaly.resolution.operator
    for anomaly in result.anomalies:
        if anomaly.resolution is not None and anomaly.resolution.decision in ("accept", "override"):
            return anomaly.resolution.operator
    return "（本批次初始校验通过）"


def plan_writes(result, item, has_decision: bool) -> tuple[dict, str]:
    """按回填权限表规划写入内容。**不写任何文本未声明的字段。**"""
    biz = item.biz_type.value if hasattr(item.biz_type, "value") else str(item.biz_type)
    writes: dict[str, object] = {}
    notes: list[str] = []
    if biz == "doujia":
        writes["doujia_amount"] = item.amount_exact or f"{item.amount:.2f}"
        writes["doujia_payer"] = item.payer
        notes.append(f"抖加金额与支付人来自 {result.batch_id}")
    else:
        if not has_decision:
            return {}, "无人工裁决记录，跳过「人工确认后才可写」列"
        writes["payer"] = item.payer
        if result.summary.expected_pay_date is not None:
            writes["pay_date"] = result.summary.expected_pay_date.isoformat()
            notes.append(f"打款日期取文本「预计打款日期」{result.summary.expected_pay_date_raw}")
        notes.append(ADVANCE_PENDING_NOTE)
    return writes, "；".join(notes)


__all__ = ["ADVANCE_PENDING_NOTE", "has_batch_decision", "confirmed_by", "plan_writes"]
