"""人工确认闸门与状态流转（架构 §4.2 / §4.3）。

闸门不变量：**任何 WRITTEN 之前必须经过 READY；任何 READY 必须无未裁决 P0。**

三个裁决动作与产品语义的对应（Spec §7 裁决动作栏 / openapi `ResolutionInput`）：
  accept   确认无误 —— 人工核实后认定该异常不成立，放行
  override 修正为某值 —— 人工给出正确值（歧义匹配必须走此路并指定目标行）
  ignore   打回重提 —— 退回发起人补充；该批次/条目**不得写表**
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.enums import AnomalyCode, Decision, ItemState, ev
from app.domain.errors import GateBlockedError, NotFoundError, ValidationError
from app.domain.models import Anomaly, ParseResult, Resolution, ResolutionInput, ResolutionResult
from app.repositories import decision_repo
from app.repositories.memory_store import MemoryStore
from app.repositories.xlsx_repository import TableSnapshot
from app.validators.cross_check import _field_conflicts
from app.validators.matcher import SheetIndex


def open_blockers(result: ParseResult) -> list[Anomaly]:
    return [a for a in result.anomalies if a.blocking and not a.resolved]


def _ignored_blockers(result: ParseResult) -> list[Anomaly]:
    return [
        a
        for a in result.anomalies
        if a.blocking
        and a.resolved
        and a.resolution is not None
        and a.resolution.decision == Decision.IGNORE
    ]


def find_anomaly(result: ParseResult, anomaly_id: str) -> Anomaly:
    for anomaly in result.anomalies:
        if anomaly.anomaly_id == anomaly_id:
            return anomaly
    raise NotFoundError(f"异常 {anomaly_id} 不存在")


def aggregate_state(result: ParseResult) -> ItemState:
    """由异常裁决状态推导批次状态。"""
    if _ignored_blockers(result):
        return ItemState.BLOCKED
    if open_blockers(result):
        return ItemState.NEEDS_REVIEW
    return ItemState.READY


def apply_item_states(result: ParseResult) -> ItemState:
    """把批次状态落到每条条目上（条目级阻断优先）。"""
    batch_state = aggregate_state(result)
    blocked_lines = {a.line_no for a in _ignored_blockers(result) if a.line_no is not None}
    review_lines = {a.line_no for a in open_blockers(result) if a.line_no is not None}
    for item in result.line_items:
        if batch_state is ItemState.BLOCKED or item.line_no in blocked_lines:
            item.state = ItemState.BLOCKED
        elif batch_state is ItemState.NEEDS_REVIEW or item.line_no in review_lines:
            item.state = ItemState.NEEDS_REVIEW
        else:
            item.state = ItemState.READY
    result.aggregate_state = batch_state
    return batch_state


def _pin_ambiguous_target(
    result: ParseResult, anomaly: Anomaly, target: str, snapshot: TableSnapshot
) -> bool:
    """歧义匹配的 `override`：把目标行钉死，并**重跑该条的字段冲突校验**。

    返回 True 表示重跑后仍存在新的 P0（此时保持 NEEDS_REVIEW）。
    """
    index = SheetIndex(snapshot.rows)
    row = index.row_by_ref(target)
    if row is None:
        raise ValidationError(f"指定的目标行 {target} 不存在于账号表")
    item = next((i for i in result.line_items if i.line_no == anomaly.line_no), None)
    if item is None:
        return False
    from app.domain.enums import MatchLevel
    from app.domain.models import MatchCandidate, MatchResult

    item.match_result = MatchResult(
        level=MatchLevel.EXACT_NAME,
        matched_row_ref=target,
        candidates=[
            MatchCandidate(
                row_ref=target,
                douyin_nickname=row.text("douyin_nickname"),
                douyin_id=row.text("douyin_id") or None,
                score=1.0,
            )
        ],
        note=f"人工指定目标行 {target}",
    )
    from app.validators.anomaly_rules import AnomalyFactory

    factory = AnomalyFactory(prefix=f"anm_r{anomaly.line_no}")
    fresh = _field_conflicts(factory, ev(item.biz_type), item.payer or None, [item], index)
    if fresh:
        # 幂等：同一条目上已经登记过的同类冲突不再重复落条
        existing = {
            (a.code, a.line_no, a.target_field) for a in result.anomalies if a.rule_id == "xsrc.field_conflict"
        }
        appended = False
        for new in fresh:
            if (new.code, new.line_no, new.target_field) in existing:
                continue
            new.anomaly_id = f"{anomaly.anomaly_id}_c{len(result.anomalies)}"
            result.anomalies.append(new)
            appended = True
        return appended
    return False


def apply_resolution(
    result: ParseResult,
    store: MemoryStore,
    payload: ResolutionInput,
    snapshot: TableSnapshot,
) -> ResolutionResult:
    """记录人工裁决、写 append-only 日志、重跑校验并更新状态。"""
    anomaly = find_anomaly(result, payload.anomaly_id)
    code = AnomalyCode(anomaly.code)

    if code is AnomalyCode.MATCH_AMBIGUOUS and payload.decision is Decision.ACCEPT:
        raise GateBlockedError(
            "歧义匹配不能用「确认无误」放行：必须指定目标行（修正为某值）或打回重提",
            pending=[anomaly.anomaly_id],
        )
    if payload.decision is Decision.OVERRIDE and not (payload.override_value or "").strip():
        raise ValidationError("「修正为某值」必须提供修正值")

    still_blocking = False
    if code is AnomalyCode.MATCH_AMBIGUOUS and payload.decision is Decision.OVERRIDE:
        # 「歧义」这一条已经被人工钉死目标行 → 本条判定完成。
        # 重跑时若暴露**新的**冲突，那是另一条独立异常（自带 anomaly_id），
        # 由它去阻断；不得把本条继续挂成未裁决 —— 否则操作员解完新异常后
        # 本条仍然 pending，且重复 override 会不断产出同名新异常，形成死循环。
        still_blocking = _pin_ambiguous_target(result, anomaly, payload.override_value.strip(), snapshot)
    anomaly.resolved = True

    resolution = Resolution(
        decision=payload.decision,
        operator=payload.operator,
        resolved_at=datetime.now(timezone.utc),
        note=payload.note,
        original_value=anomaly.sheet_value or anomaly.text_value,
        final_value=payload.override_value,
    )
    anomaly.resolution = resolution
    store.put_decision(result.request_id, anomaly.anomaly_id, resolution)

    entry = {
        "ts": resolution.resolved_at.isoformat(),
        "request_id": result.request_id,
        "anomaly_id": anomaly.anomaly_id,
        "rule_id": anomaly.rule_id,
        "code": ev(anomaly.code),
        "severity": ev(anomaly.severity),
        "action": ev(payload.decision),
        "original_value": resolution.original_value,
        "final_value": resolution.final_value,
        "operator": payload.operator,
        "reason": payload.note or "",
        "line_no": anomaly.line_no,
    }
    if anomaly.line_no is not None:
        entry["reason"] = f"line:{anomaly.line_no}|{entry['reason']}"
    store.append_log(entry)
    # 落盘 JSONL 额外带 session_id：request_id 的自增序号跨会话撞号时，
    # 审计侧可据此区分同名记录归属（只落盘，不进对外 CSV 的锁定列）。
    decision_repo.append_entry({**entry, "session_id": store.session_id})

    state = apply_item_states(result)
    return ResolutionResult(
        anomaly_id=anomaly.anomaly_id,
        item_state=state,
        still_blocking=still_blocking or bool(open_blockers(result)),
        remaining_p0_count=len(open_blockers(result)),
        revalidated=True,
    )
