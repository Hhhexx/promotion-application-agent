"""编排层：parse → validate → (review) → commit → summary → report（架构 §5.1）。

入口层只调用本层；本层不感知 HTTP。所有跨层数据都用 `app/domain/models.py` 的模型。
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

from app.core.config import (
    DEFAULT_SOURCE_TABLE,
    TEST_COPY_DIR,
    UPLOAD_DIR,
    ensure_dirs,
)
from app.core.logging import log_event
from app.domain.enums import AnomalyCode, ItemState
from app.domain.errors import (
    DomainError,
    GateBlockedError,
    NotFoundError,
    ValidationError,
)
from app.domain.models import (
    AccountTableDetail,
    AccountTableMeta,
    CommitResult,
    DailyReport,
    DailySummary,
    ParseResult,
    ResolutionInput,
    ResolutionResult,
    SkippedEntry,
    WrittenEntry,
)
from app.llm.llm_adapter import reset_adapter
from app.parsers.base import parse_request
from app.repositories.memory_store import STORE, MemoryStore, TableRecord
from app.repositories.xlsx_repository import (
    TableSnapshot,
    XlsxRepository,
    copy_test_copy,
    utc_now_iso,
)
from app.reporters.report_builder import build_report
from app.reporters.summary_service import build_summary
from app.validators.anomaly_rules import AnomalyFactory
from app.validators.engine import validate
from app.orchestrator import review_gate
from app.orchestrator.review_gate import apply_item_states, open_blockers
from app.orchestrator.write_plan import confirmed_by, has_batch_decision, plan_writes


def _store() -> MemoryStore:
    return STORE


# --------------------------------------------------------------------------- #
# 账号表
# --------------------------------------------------------------------------- #
def register_table(
    source_path: str | Path | None = None,
    filename: str | None = None,
) -> AccountTableMeta:
    """登记账号表：**复制为测试副本**，源表只读（架构 §3.2）。"""
    ensure_dirs()
    store = _store()
    source = Path(source_path) if source_path else DEFAULT_SOURCE_TABLE
    if not source.exists():
        raise ValidationError(f"账号表源文件不存在：{source}")
    table_id = f"tbl_copy_{store.next_seq('table'):02d}"
    copy_path = TEST_COPY_DIR / f"{table_id}__{source.stem}（测试副本）.xlsx"
    copy_test_copy(source, copy_path)
    repo = XlsxRepository(copy_path)
    snapshot = repo.snapshot()
    meta = AccountTableMeta(
        table_id=table_id,
        filename=filename or copy_path.name,
        row_count=len(snapshot.rows),
        is_test_copy=True,
        source_path=str(source),
        copy_path=str(copy_path),
    )
    store.put_table(TableRecord(meta=meta, source_path=str(source), copy_path=str(copy_path)))
    log_event("table_registered", table_id=table_id, rows=len(snapshot.rows), source=str(source))
    return meta


def register_uploaded_table(filename: str | None, payload: bytes) -> AccountTableMeta:
    """把上传的 xlsx 落到暂存目录后登记副本。

    入口层只负责把文件名与字节流转交过来；**落盘属于本层职责**
    （路由不直接碰文件系统，见代码组织规范 §1）。
    """
    ensure_dirs()
    stem = Path(filename or "uploaded.xlsx").stem or "uploaded"
    staged = UPLOAD_DIR / f"{stem}.xlsx"
    staged.write_bytes(payload)
    return register_table(source_path=staged, filename=filename)


def table_detail(table_id: str) -> AccountTableDetail:
    record = _require_table(table_id)
    repo = XlsxRepository(record.copy_path)
    snapshot = repo.snapshot()
    meta = record.meta
    return AccountTableDetail(
        **meta.model_dump(),
        columns=snapshot.columns,
        rows=[{"row_ref": r.row_ref, **{k: _jsonable(v) for k, v in r.values.items()}} for r in snapshot.rows],
        empty_row_refs=snapshot.empty_row_refs,
    )


def table_snapshot(table_id: str | None = None) -> TableSnapshot:
    """读取账号表快照（用于裁决时重跑字段冲突校验）。未指定则用当前默认表。"""
    store = _store()
    record = _require_table(table_id) if table_id else store.default_table()
    if record is None:
        raise NotFoundError("尚未登记账号表")
    return XlsxRepository(record.copy_path).snapshot()


def _require_table(table_id: str):
    record = _store().get_table(table_id)
    if record is None:
        raise NotFoundError(f"账号表 {table_id} 未登记")
    return record


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def parse_into_request(
    raw_text: str,
    biz_type_hint=None,
    table_id: str | None = None,
    enable_llm: bool = False,
) -> ParseResult:
    """解析 + 校验。存在 P0 时批次进入 NEEDS_REVIEW 并禁止写表。"""
    store = _store()
    record = _require_table(table_id) if table_id else store.default_table()
    if record is None:
        record = _auto_register_default()
    if enable_llm:
        reset_adapter()
    parsed = parse_request(raw_text, biz_type_hint)
    request_id = f"req_{parsed.declared_date.strftime('%Y%m%d')}_{parsed.biz_type.value}_{store.next_seq('req'):02d}"
    snapshot = XlsxRepository(record.copy_path).snapshot()
    result = validate(parsed, snapshot, request_id)
    result.table_id = record.meta.table_id
    apply_item_states(result)
    superseded = store.put_request(result)
    if superseded is not None:
        # 批次级幂等留痕：同批次重复解析，旧条目退出汇总（AC-08）。
        log_event(
            "request_superseded",
            batch_id=result.batch_id,
            superseded_request_id=superseded,
            active_request_id=request_id,
        )
    log_event(
        "request_parsed",
        request_id=request_id,
        biz=parsed.biz_type.value,
        items=len(result.line_items),
        p0=len(open_blockers(result)),
        anomalies=len(result.anomalies),
    )
    return result


def _auto_register_default() -> TableRecord:
    """未显式上传时自动登记仓库自带的测试用账号表。"""
    if not DEFAULT_SOURCE_TABLE.exists():
        raise NotFoundError("尚未登记账号表，且仓库内无默认测试表")
    register_table()
    record = _store().default_table()
    assert record is not None
    return record


def get_request(request_id: str) -> ParseResult:
    result = _store().get_request(request_id)
    if result is None:
        raise NotFoundError(f"请求 {request_id} 不存在")
    return result


def default_table_id() -> str:
    """当前默认账号表 id（未登记时返回空串）。入口层据此给写表端点兜底。"""
    record = _store().default_table()
    return record.meta.table_id if record else ""


def resolve_anomaly(request_id: str, payload: ResolutionInput) -> ResolutionResult:
    """记录一条人工裁决并**重跑校验**。

    重跑必须回到**该申请解析时所用的那张表**（`result.table_id`）：
    否则会出现「按 A 表判定的异常、用 B 表复核」的错配。
    入口层不直接接触 `review_gate` 与内存态存储（代码组织规范 §1）。
    """
    result = get_request(request_id)
    return review_gate.apply_resolution(result, _store(), payload, table_snapshot(result.table_id))


# --------------------------------------------------------------------------- #
# 写表
# --------------------------------------------------------------------------- #
def commit_request(request_id: str, table_id: str) -> CommitResult:
    """把已确认条目写入测试副本（幂等）。

    **闸门不变量**：存在未裁决 P0 或被打回项时抛 `GateBlockedError`，
    调用方映射 HTTP 409，且本函数在抛错前**不打开工作簿**——不发生任何写入。
    """
    store = _store()
    result = get_request(request_id)
    record = _require_table(table_id)
    # 行号（row_ref）只在「解析时所用的那张表」上有意义。
    # 若允许换表写表，就会把 A 表的行号写到 B 表的同名行上——契约破坏。
    if result.table_id and result.table_id != table_id:
        raise ValidationError(
            f"申请 {request_id} 是依据账号表 {result.table_id} 校验的，"
            f"不能用 {table_id} 写表；请重新解析或改用同一张表"
        )

    apply_item_states(result)
    blocked = open_blockers(result)
    if result.aggregate_state is not ItemState.READY:
        reason = "存在未裁决阻断项" if blocked else "存在被打回重提的阻断项"
        raise GateBlockedError(
            f"{reason}，禁止写入测试副本",
            pending=[a.anomaly_id for a in blocked],
        )

    has_decision = has_batch_decision(result)
    repo = XlsxRepository(record.copy_path)
    ledger = repo.ledger_keys()
    written: list[WrittenEntry] = []
    skipped: list[SkippedEntry] = []
    ledger_entries: list[dict] = []
    now = utc_now_iso()

    for item in result.line_items:
        if item.state is not ItemState.READY:
            skipped.append(SkippedEntry(dedup_key=item.dedup_key, reason="NOT_READY"))
            continue
        if item.dedup_key in ledger:
            item.state = ItemState.SKIPPED_ALREADY_WRITTEN
            skipped.append(SkippedEntry(dedup_key=item.dedup_key, reason="SKIPPED_ALREADY_WRITTEN"))
            continue
        writes, note = plan_writes(result, item, has_decision)
        row_ref = item.match_result.matched_row_ref if item.match_result else None
        if row_ref is None:
            skipped.append(SkippedEntry(dedup_key=item.dedup_key, reason="NOT_READY"))
            continue
        trace = {
            "_batch_id": result.batch_id,
            "_request_id": result.request_id,
            "_rule_id": "write.plan",
            "_confirmed_by": confirmed_by(result, item.line_no),
            "_confirmed_at": now,
            "_dedup_key": item.dedup_key,
        }
        remark = f"来源={result.batch_id}；request_id={result.request_id}；{note}"
        cells, blocked_cells = repo.write_row(row_ref, writes, trace, remark=remark)
        if blocked_cells:
            factory = AnomalyFactory(prefix=f"anmW{item.line_no}")
            for key, existing in blocked_cells:
                result.anomalies.append(
                    factory.make(
                        AnomalyCode.TARGET_CELL_NONEMPTY,
                        f"「{item.blogger_name_raw}」第 {row_ref} 行目标单元格已有值「{existing}」，未覆盖",
                        line_no=item.line_no,
                        account_ref=item.blogger_name_raw,
                        sheet_row_ref=row_ref,
                        target_field=key,
                        sheet_value=existing,
                        action_required="需运营确认以哪一侧为准；系统不覆盖已有值",
                    )
                )
        if cells or not writes:
            item.state = ItemState.WRITTEN
            written.append(
                WrittenEntry(dedup_key=item.dedup_key, row_ref=row_ref, fields_written=cells)
            )
            ledger_entries.append(
                {
                    "dedup_key": item.dedup_key,
                    "batch_id": result.batch_id,
                    "request_id": result.request_id,
                    "row_ref": row_ref,
                    "written_at": now,
                }
            )

    if ledger_entries:
        repo.append_ledger(ledger_entries)
        repo.save()
    outcome = CommitResult(
        written_count=len(written), skipped_count=len(skipped), written=written, skipped=skipped
    )
    store.commits[request_id] = outcome
    log_event(
        "commit_done",
        request_id=request_id,
        written=len(written),
        skipped=len(skipped),
        copy=record.copy_path,
    )
    return outcome


# --------------------------------------------------------------------------- #
# 汇总与汇报
# --------------------------------------------------------------------------- #
def daily_summary(date: date_cls, biz_type=None) -> DailySummary:
    return build_summary(_store(), date, biz_type)


def create_daily_report(date: date_cls, include_unresolved: bool = True) -> DailyReport:
    store = _store()
    report = build_report(store, date, include_unresolved=include_unresolved)
    store.put_report(report)
    return report


def get_daily_report(report_id: str) -> DailyReport:
    report = _store().get_report(report_id)
    if report is None:
        raise NotFoundError(f"汇报 {report_id} 不存在")
    return report


# --------------------------------------------------------------------------- #
# 裁决日志（对外导出）
# --------------------------------------------------------------------------- #
def list_decisions(request_id: str) -> list[dict]:
    """该申请在**当前会话**内产生的裁决记录（F-12 审计导出）。

    取内存态主数据（ADR-003：内存为主 + JSONL 落盘做长留存），而非回读落盘 JSONL：
    `request_id` 的自增序号在进程重启后归零，回读会把上一会话的同名 `request_id`
    陈旧记录混进本次导出（实测本会话 2 条 → 导出 5 行）。落盘 JSONL 仍完整保留，
    供长期审计，只是**不回流到接口**。
    """
    return [e for e in _store().decision_log if e.get("request_id") == request_id]


__all__ = [
    "register_table",
    "register_uploaded_table",
    "table_detail",
    "table_snapshot",
    "default_table_id",
    "parse_into_request",
    "get_request",
    "resolve_anomaly",
    "commit_request",
    "daily_summary",
    "create_daily_report",
    "get_daily_report",
    "list_decisions",
    "DomainError",
]
