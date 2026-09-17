"""领域枚举与异常码定档表。

代码侧唯一枚举源，冻结自 `docs/02-架构设计.md` §2.1 / §4.1 / §4.4 与
`docs/Spec-v1.0.md` 附录 A。`EXC_ID_MAP` 是 `EXC-xx`（产品编号）与异常码
（代码侧）之间的唯一映射，供 Spec / OpenAPI / 测试三处统一引用。

定档口径见 `docs/02-架构设计.md` §4.5：P0 仅限「正确性缺陷 / 需求未满足 /
契约安全与数据完整性破坏」三类，其余一律 P1 / P2。
"""

from __future__ import annotations

from enum import Enum


class BizType(str, Enum):
    """申请类型。"""

    DOUJIA = "doujia"
    ADVANCE = "advance"


class Severity(str, Enum):
    """严重级别。P0 阻断写表，P1 警告，P2 提示。"""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class Decision(str, Enum):
    """人工裁决动作。"""

    ACCEPT = "accept"
    OVERRIDE = "override"
    IGNORE = "ignore"


class ItemState(str, Enum):
    """条目状态机（架构 §4.3）。"""

    PARSED = "PARSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    RESOLVED = "RESOLVED"
    READY = "READY"
    WRITTEN = "WRITTEN"
    SKIPPED_ALREADY_WRITTEN = "SKIPPED_ALREADY_WRITTEN"
    BLOCKED = "BLOCKED"


class MatchLevel(str, Enum):
    """账号表匹配置信级别（架构 §2.7）。非 EXACT_* 一律升级人工。"""

    EXACT_ID = "EXACT_ID"
    EXACT_NAME = "EXACT_NAME"
    AMBIGUOUS = "AMBIGUOUS"
    NO_MATCH = "NO_MATCH"
    WEAK_FUZZY = "WEAK_FUZZY"


class AnomalyCode(str, Enum):
    """25 个异常码（架构 §4.1）。"""

    # P0 —— 阻断
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    COUNT_MISMATCH = "COUNT_MISMATCH"
    FIELD_MISSING = "FIELD_MISSING"
    UNPARSED_LINE = "UNPARSED_LINE"
    DATE_ORDER_INVALID = "DATE_ORDER_INVALID"
    DATE_UNRESOLVABLE = "DATE_UNRESOLVABLE"
    DUPLICATE_WITHIN_REQUEST = "DUPLICATE_WITHIN_REQUEST"
    MATCH_AMBIGUOUS = "MATCH_AMBIGUOUS"
    MATCH_NOT_FOUND = "MATCH_NOT_FOUND"
    LLM_RULE_CONFLICT = "LLM_RULE_CONFLICT"
    CROSS_SOURCE_FIELD_CONFLICT = "CROSS_SOURCE_FIELD_CONFLICT"
    # P1 —— 警告
    TABLE_EMPTY_ROW_SKIPPED = "TABLE_EMPTY_ROW_SKIPPED"
    MERGED_COUNT_MISMATCH = "MERGED_COUNT_MISMATCH"
    PAYER_INCONSISTENT = "PAYER_INCONSISTENT"
    TARGET_CELL_NONEMPTY = "TARGET_CELL_NONEMPTY"
    DATE_FORMAT_INCONSISTENT = "DATE_FORMAT_INCONSISTENT"
    DOUYIN_ID_EMPTY = "DOUYIN_ID_EMPTY"
    CROSS_SOURCE_TOTAL_MISMATCH = "CROSS_SOURCE_TOTAL_MISMATCH"
    CROSS_SOURCE_SCOPE_MISMATCH = "CROSS_SOURCE_SCOPE_MISMATCH"
    STATUS_FIELD_INCONSISTENT = "STATUS_FIELD_INCONSISTENT"
    UNACCEPTED_WITH_AMOUNT = "UNACCEPTED_WITH_AMOUNT"
    # P2 —— 提示
    DOUJIA_EXCEEDS_QUOTE = "DOUJIA_EXCEEDS_QUOTE"
    NICKNAME_DIRTY = "NICKNAME_DIRTY"
    SPLIT_NOT_RETAINED = "SPLIT_NOT_RETAINED"
    REMARK_EMPTY = "REMARK_EMPTY"


#: 异常码 → (定档级别, 是否阻断写表)。
#: 注：`STATUS_FIELD_INCONSISTENT` 有两个实例（支付状态不自洽 P1 / 接单审核矛盾 P2），
#: 级别由 `Anomaly.severity` 承载、不固化在 code 上 —— 见 Spec 附录 A 说明。
CODE_SEVERITY: dict[AnomalyCode, tuple[Severity, bool]] = {
    AnomalyCode.TOTAL_MISMATCH: (Severity.P0, True),
    AnomalyCode.COUNT_MISMATCH: (Severity.P0, True),
    AnomalyCode.FIELD_MISSING: (Severity.P0, True),
    AnomalyCode.UNPARSED_LINE: (Severity.P0, True),
    AnomalyCode.DATE_ORDER_INVALID: (Severity.P0, True),
    AnomalyCode.DATE_UNRESOLVABLE: (Severity.P0, True),
    AnomalyCode.DUPLICATE_WITHIN_REQUEST: (Severity.P0, True),
    AnomalyCode.MATCH_AMBIGUOUS: (Severity.P0, True),
    AnomalyCode.MATCH_NOT_FOUND: (Severity.P0, True),
    AnomalyCode.LLM_RULE_CONFLICT: (Severity.P0, True),
    AnomalyCode.CROSS_SOURCE_FIELD_CONFLICT: (Severity.P0, True),
    AnomalyCode.MERGED_COUNT_MISMATCH: (Severity.P1, False),
    AnomalyCode.PAYER_INCONSISTENT: (Severity.P1, False),
    AnomalyCode.TARGET_CELL_NONEMPTY: (Severity.P1, False),
    AnomalyCode.DATE_FORMAT_INCONSISTENT: (Severity.P1, False),
    AnomalyCode.DOUYIN_ID_EMPTY: (Severity.P1, False),
    AnomalyCode.CROSS_SOURCE_TOTAL_MISMATCH: (Severity.P1, False),
    AnomalyCode.CROSS_SOURCE_SCOPE_MISMATCH: (Severity.P1, False),
    AnomalyCode.STATUS_FIELD_INCONSISTENT: (Severity.P1, False),
    AnomalyCode.UNACCEPTED_WITH_AMOUNT: (Severity.P1, False),
    AnomalyCode.TABLE_EMPTY_ROW_SKIPPED: (Severity.P1, False),
    AnomalyCode.DOUJIA_EXCEEDS_QUOTE: (Severity.P2, False),
    AnomalyCode.NICKNAME_DIRTY: (Severity.P2, False),
    AnomalyCode.SPLIT_NOT_RETAINED: (Severity.P2, False),
    AnomalyCode.REMARK_EMPTY: (Severity.P2, False),
}

#: 异常码 → PRD 产品编号。多对一允许，故值为元组；展示取首个。
EXC_ID_MAP: dict[AnomalyCode, tuple[str, ...]] = {
    AnomalyCode.COUNT_MISMATCH: ("EXC-01",),
    AnomalyCode.DATE_ORDER_INVALID: ("EXC-02",),
    AnomalyCode.DATE_UNRESOLVABLE: ("EXC-02",),
    AnomalyCode.TOTAL_MISMATCH: ("EXC-03",),
    AnomalyCode.CROSS_SOURCE_TOTAL_MISMATCH: ("EXC-03",),
    AnomalyCode.DUPLICATE_WITHIN_REQUEST: ("EXC-04",),
    AnomalyCode.MATCH_AMBIGUOUS: ("EXC-04", "EXC-06"),
    AnomalyCode.MATCH_NOT_FOUND: ("EXC-06",),
    AnomalyCode.CROSS_SOURCE_FIELD_CONFLICT: ("EXC-05",),
    AnomalyCode.STATUS_FIELD_INCONSISTENT: ("EXC-07", "EXC-13"),
    AnomalyCode.TABLE_EMPTY_ROW_SKIPPED: ("EXC-08",),
    AnomalyCode.UNACCEPTED_WITH_AMOUNT: ("EXC-09",),
    AnomalyCode.DATE_FORMAT_INCONSISTENT: ("EXC-10",),
    AnomalyCode.CROSS_SOURCE_SCOPE_MISMATCH: ("EXC-11",),
    AnomalyCode.DOUJIA_EXCEEDS_QUOTE: ("EXC-12",),
    AnomalyCode.REMARK_EMPTY: ("EXC-14",),
    AnomalyCode.NICKNAME_DIRTY: ("EXC-15",),
    AnomalyCode.SPLIT_NOT_RETAINED: ("EXC-16",),
}
#: 无 EXC 对应项的架构侧新增码（Spec 附录 A）：FIELD_MISSING / UNPARSED_LINE /
#: MERGED_COUNT_MISMATCH / PAYER_INCONSISTENT / TARGET_CELL_NONEMPTY /
#: LLM_RULE_CONFLICT / DOUYIN_ID_EMPTY / STATUS_FIELD_INCONSISTENT（与 EXC-13 共用）。


def severity_of(code: AnomalyCode) -> Severity:
    """取异常码的定档级别。"""
    return CODE_SEVERITY[code][0]


def is_blocking(code: AnomalyCode) -> bool:
    """取异常码是否阻断写表。"""
    return CODE_SEVERITY[code][1]


def exc_id_of(code: AnomalyCode) -> str | None:
    """取异常码对应的 PRD 编号（展示用首个）。"""
    ids = EXC_ID_MAP.get(code)
    return ids[0] if ids else None


def ev(value: object) -> str:
    """取枚举的**值**字符串。

    注意：Python 3.11+ 中 `str(SomeStrEnum.MEMBER)` 返回 `'SomeStrEnum.MEMBER'`，
    直接 `str()` 会污染日志与 JSONL，故统一走本函数。
    """
    return value.value if isinstance(value, Enum) else str(value)
