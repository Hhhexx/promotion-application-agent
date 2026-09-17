"""跨层数据契约（pydantic 模型）。

冻结自 `docs/openapi.yaml` 与 `docs/02-架构设计.md` §2 / §3。
**所有跨层数据一律用本文件的模型传递，禁止裸 dict 跨层**（架构 §5.2 硬规则 5）。

金额字段说明：模型对外声明为 `float`（与 OpenAPI 的 `number/double` 对齐），
但**全部求和与比较在 `Decimal` 中完成**，仅在序列化边界转 float。
见 Spec §10「金额约束：统一 Decimal 保 2 位，禁止 float」——该约束约束的是运算，
不是线格式。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AnomalyCode,
    BizType,
    Decision,
    ItemState,
    MatchLevel,
    Severity,
)

# --------------------------------------------------------------------------- #
# 基础结构
# --------------------------------------------------------------------------- #


class SourceSpan(BaseModel):
    """原文起止偏移（字符下标，左闭右开）。界面据此高亮冲突 token。"""

    start: int
    end: int


class MatchCandidate(BaseModel):
    """一个候选表行。`score` 只用于排序，**不得**用于自动采纳（架构 §2.7）。"""

    row_ref: str
    douyin_nickname: str = ""
    douyin_id: str | None = None
    score: float = 0.0


class MatchResult(BaseModel):
    """匹配结论。仅 EXACT_ID / EXACT_NAME 可作自动回填目标。"""

    level: MatchLevel
    matched_row_ref: str | None = None
    candidates: list[MatchCandidate] = Field(default_factory=list)
    note: str = ""


class Resolution(BaseModel):
    """人工裁决记录（append-only 日志的一行）。"""

    decision: Decision
    operator: str
    resolved_at: datetime
    note: str | None = None
    original_value: str | None = None
    final_value: str | None = None


class Anomaly(BaseModel):
    """异常证据对象 —— 校验层与界面层之间的**唯一接口**。

    基础字段对齐 `docs/openapi.yaml#/components/schemas/Anomaly`；
    `rule_id / account_ref / text_value / sheet_value / source_span /
    impact_amount / action_required` 为 Spec §6.1 `ViolationRecord` 证据契约字段
    （界面证据面板据此渲染，缺字段时降级显示「证据不完整」）。
    """

    model_config = ConfigDict(use_enum_values=True)

    anomaly_id: str
    rule_id: str
    exc_id: str | None = None
    code: AnomalyCode
    severity: Severity
    blocking: bool
    message: str
    line_no: int | None = None
    target_field: str | None = None
    suggestion: str | None = None
    resolved: bool = False
    resolution: Resolution | None = None
    # --- 证据契约（Spec §6.1）---
    account_ref: str | None = None
    text_value: str | None = None
    sheet_value: str | None = None
    source_span: SourceSpan | None = None
    impact_amount: float | None = None
    action_required: str | None = None
    evidence_note: str | None = None
    sheet_row_ref: str | None = None

    @property
    def is_open_p0(self) -> bool:
        """未裁决且阻断 —— 闸门的判定依据。"""
        return self.blocking and not self.resolved


# --------------------------------------------------------------------------- #
# 解析产物
# --------------------------------------------------------------------------- #


class LineItem(BaseModel):
    """行级申请条目（架构 §2.2）。"""

    line_no: int
    biz_type: BizType
    blogger_name_raw: str
    blogger_name_norm: str
    song_name: str | None = None
    amount: float
    amount_exact: str = Field(default="", description="Decimal 字符串原值，避免浮点回读误差")
    split_count: int | None = None
    payer: str
    request_date: date
    source_span: SourceSpan
    dedup_key: str
    match_result: MatchResult | None = None
    state: ItemState = ItemState.PARSED


class ClaimSummary(BaseModel):
    """表级汇总声明（架构 §2.3）。与明细行分列建模才能做交叉校验。"""

    biz_type: BizType
    declared_total_amount: float
    declared_total_exact: str = ""
    declared_date: date
    declared_count: int | None = None
    declared_merged_count: int | None = None
    payer: str
    expected_pay_date: date | None = None
    expected_pay_date_inferred: bool = False
    expected_pay_date_raw: str | None = None


class CrossCheck(BaseModel):
    """交叉校验明细（架构 §2.5）。三口径并列，**不合并为单一数字**。"""

    line_items_sum: float
    declared_total_amount: float
    split_count_sum: int | None = None
    declared_count: int | None = None
    line_items_len: int
    declared_merged_count: int | None = None
    expected_pay_date: date | None = None
    declared_date: date
    sheet_column_sum: float | None = Field(
        default=None, description="账号表对应列求和（抖加批次＝「抖加」列）"
    )
    sheet_column_sum_exact: str | None = None


class ParseResult(BaseModel):
    """解析 + 校验的完整产物（架构 §2.4）。"""

    request_id: str
    batch_id: str
    biz_type: BizType
    request_date: date
    summary: ClaimSummary
    line_items: list[LineItem]
    cross_check: CrossCheck
    anomalies: list[Anomaly]
    aggregate_state: ItemState
    llm_used: bool = False
    # 解析/校验所依据的账号表 ID。裁决重跑校验必须回到同一张表，
    # 否则会出现「按 A 表判定的异常、用 B 表复核」的错配。
    table_id: str | None = None


# --------------------------------------------------------------------------- #
# 账号表
# --------------------------------------------------------------------------- #


class AccountTableMeta(BaseModel):
    table_id: str
    filename: str
    row_count: int
    is_test_copy: bool = True
    source_path: str | None = None
    copy_path: str | None = None


class AccountTableDetail(AccountTableMeta):
    columns: list[str]
    rows: list[dict] = Field(default_factory=list)
    empty_row_refs: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 入参 / 出参
# --------------------------------------------------------------------------- #


class ParseRequestInput(BaseModel):
    raw_text: str
    biz_type_hint: BizType | None = None
    table_id: str | None = None
    enable_llm: bool = False


class ResolutionInput(BaseModel):
    anomaly_id: str
    decision: Decision
    override_value: str | None = None
    operator: str
    note: str | None = None


class ResolutionResult(BaseModel):
    anomaly_id: str
    item_state: ItemState
    still_blocking: bool
    remaining_p0_count: int = 0
    revalidated: bool = True


class CommitInput(BaseModel):
    table_id: str
    confirm_token: str | None = None


class WrittenEntry(BaseModel):
    dedup_key: str
    row_ref: str
    fields_written: dict = Field(default_factory=dict)


class SkippedEntry(BaseModel):
    dedup_key: str
    reason: str


class CommitResult(BaseModel):
    written_count: int
    skipped_count: int
    written: list[WrittenEntry] = Field(default_factory=list)
    skipped: list[SkippedEntry] = Field(default_factory=list)


class SummaryBlock(BaseModel):
    """当日汇总的一个口径块。三口径并列展示（Spec §6 / F-7）。"""

    biz_type: BizType
    total_amount: float
    entry_count: int
    declared_total_amount: float | None = None
    line_items_sum: float | None = None
    sheet_column_sum: float | None = None
    declared_count: int | None = None
    item_count: int | None = None
    consistent: bool | None = None
    note: str = ""


class DailySummary(BaseModel):
    date: date
    blocks: list[SummaryBlock]


class DailyReportInput(BaseModel):
    date: date
    include_unresolved: bool = True


class AnomalyBrief(BaseModel):
    code: str
    severity: Severity
    message: str
    exc_id: str | None = None


class DecisionItem(BaseModel):
    """汇报卡「需决策项」一行。"""

    severity: Severity
    headline: str
    need_from: str


class DailyReport(BaseModel):
    report_id: str
    date: date
    headline: str = ""
    doujia_total: float
    advance_total: float
    confirmed_amount: float = 0.0
    pending_amount: float = 0.0
    anomaly_count: int
    pending_review_count: int
    anomalies_summary: list[AnomalyBrief] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    overflow_count: int = 0
    generated_at: datetime | None = None
    markdown: str = ""


class ApiResponse(BaseModel):
    """统一响应信封：`code=0` 成功，非 0 为错误码。"""

    code: int = 0
    data: object | None = None
    message: str = ""
