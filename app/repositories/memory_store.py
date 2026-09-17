"""内存态存储（架构 §5.5 演示态：内存为主 + 裁决日志落 JSONL）。

**不引入数据库**（ADR-003）。主数据在内存，产物落文件。
所有写入只作用于测试副本；源表路径仅作只读引用保存。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.domain.models import (
    AccountTableMeta,
    CommitResult,
    DailyReport,
    ParseResult,
    Resolution,
)


@dataclass
class TableRecord:
    """一张已登记账号表的运行期句柄。"""

    meta: AccountTableMeta
    source_path: str
    copy_path: str
    is_test_copy: bool = True


@dataclass
class MemoryStore:
    """进程内主数据存储。测试可调用 `reset()` 获得干净状态。"""

    tables: dict[str, TableRecord] = field(default_factory=dict)
    requests: dict[str, ParseResult] = field(default_factory=dict)
    #: 批次级幂等索引：`batch_id -> 当前生效的 request_id`（Spec §6.2 双键设计）。
    #: `batch_id` 是确定性的（`biz_type|日期`），因此同一批次重复提交只会指向最新一次解析。
    requests_by_batch: dict[str, str] = field(default_factory=dict)
    #: 被后续解析取代的 request_id。旧条目**保留在 `requests` 里可查**（审计/深链接不 404），
    #: 但不得参与汇总与汇报（AC-08：重复提交不产生重复行）。
    superseded_request_ids: set[str] = field(default_factory=set)
    reports: dict[str, DailyReport] = field(default_factory=dict)
    commits: dict[str, CommitResult] = field(default_factory=dict)
    decisions: dict[str, Resolution] = field(default_factory=dict)
    decision_log: list[dict] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    #: 本次进程会话标识。落盘 JSONL 的每条记录都会带上它（**仅供长期审计分档**，
    #: 不进入对外 CSV 的锁定列）。`request_id` 的自增序号跨会话会撞号，凭它可以区分
    #: 「同名 request_id」到底属于哪一次会话。
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    # ------------------------------------------------------------- 表
    def put_table(self, record: TableRecord) -> None:
        self.tables[record.meta.table_id] = record

    def get_table(self, table_id: str) -> TableRecord | None:
        return self.tables.get(table_id)

    def default_table(self) -> TableRecord | None:
        if not self.tables:
            return None
        return next(iter(self.tables.values()))

    # --------------------------------------------------------- 请求
    def put_request(self, result: ParseResult) -> str | None:
        """写入一次解析结果，并按 `batch_id` 做**批次级幂等**。

        同一批次（`biz_type|日期`）被重复解析时，旧条目被标记为「已取代」：
        索引改指向新 `request_id`，旧条目仍保留在 `requests` 中可查（不 404），
        但 `superseded_request_ids` 会让它退出汇总 / 汇报（AC-08）。

        返回被取代的旧 `request_id`（无则 `None`），供上层留痕。
        """
        previous_id = self.requests_by_batch.get(result.batch_id)
        superseded: str | None = None
        if previous_id is not None and previous_id != result.request_id:
            superseded = previous_id
            self.superseded_request_ids.add(previous_id)
            # 旧条目上的裁决已过期：按前缀清除，避免影响 `line_has_decision` 的前置判断。
            self._drop_decisions(previous_id)
        self.requests[result.request_id] = result
        self.requests_by_batch[result.batch_id] = result.request_id
        return superseded

    def get_request(self, request_id: str) -> ParseResult | None:
        return self.requests.get(request_id)

    def is_superseded(self, request_id: str) -> bool:
        """该条目是否已被同批次的后续解析取代（取代后不得进入汇总）。"""
        return request_id in self.superseded_request_ids

    def active_requests(self) -> list[ParseResult]:
        """当前生效（未被取代）的全部解析结果。"""
        return [r for r in self.requests.values() if not self.is_superseded(r.request_id)]

    def _drop_decisions(self, request_id: str) -> None:
        prefix = f"{request_id}:"
        for key in [k for k in self.decisions if k.startswith(prefix)]:
            self.decisions.pop(key, None)

    # --------------------------------------------------------- 裁决
    def put_decision(self, request_id: str, anomaly_id: str, resolution: Resolution) -> None:
        self.decisions[f"{request_id}:{anomaly_id}"] = resolution

    def get_decision(self, request_id: str, anomaly_id: str) -> Resolution | None:
        return self.decisions.get(f"{request_id}:{anomaly_id}")

    def line_has_decision(self, request_id: str, line_no: int) -> bool:
        """该条目是否已有 accept/override 记录 —— `AFTER_DECISION` 列的写入前置条件。"""
        prefix = f"{request_id}:"
        for key, res in self.decisions.items():
            if not key.startswith(prefix) or res.decision not in ("accept", "override"):
                continue
            if res.note and res.note.startswith(f"line:{line_no}|"):
                return True
        return False

    def append_log(self, entry: dict) -> None:
        self.decision_log.append(entry)

    # --------------------------------------------------------- 汇报
    def put_report(self, report: DailyReport) -> None:
        self.reports[report.report_id] = report

    def get_report(self, report_id: str) -> DailyReport | None:
        return self.reports.get(report_id)

    # --------------------------------------------------------- 序号
    def next_seq(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def reset(self) -> None:
        self.tables.clear()
        self.requests.clear()
        self.requests_by_batch.clear()
        self.superseded_request_ids.clear()
        self.reports.clear()
        self.commits.clear()
        self.decisions.clear()
        self.decision_log.clear()
        self.counters.clear()
        # 新会话换新标识：旧落盘记录据此与新会话区分（不改写历史 JSONL）。
        self.session_id = uuid.uuid4().hex


#: 进程级单例（演示态；测试通过 fixture 调用 `reset()`）。
STORE = MemoryStore()
