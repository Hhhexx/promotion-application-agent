"""账号表列定义与回填权限（架构 §3）。

13 个业务列 + 6 个下划线前缀溯源列。每一列的回填权限在此**唯一声明**，
仓储层写单元格前一律查表，禁止散落在业务逻辑里。

权限语义（架构 §3.2 / §3.4 / Spec §6.4）：
  NEVER           禁止自动写/改（文本无此信息，写入即属"猜"）
  FILL_IF_EMPTY   可回填；已有非空值则不覆盖（改报 TARGET_CELL_NONEMPTY P1）
  AFTER_DECISION  必须存在人工裁决记录（accept/override）才可写
  SYSTEM          系统审计字段（备注、溯源列）
"""

from __future__ import annotations

from enum import Enum


class WritePolicy(str, Enum):
    NEVER = "never"
    FILL_IF_EMPTY = "fill_if_empty"
    AFTER_DECISION = "after_decision"
    SYSTEM = "system"


#: (中文表头, 英文键, 回填权限)
SHEET_COLUMNS: list[tuple[str, str, WritePolicy]] = [
    ("类型", "type", WritePolicy.NEVER),
    ("抖音昵称", "douyin_nickname", WritePolicy.NEVER),
    ("抖音号", "douyin_id", WritePolicy.NEVER),
    ("报价", "quote_price", WritePolicy.NEVER),
    ("抖加", "doujia_amount", WritePolicy.FILL_IF_EMPTY),
    ("抖加支付人", "doujia_payer", WritePolicy.FILL_IF_EMPTY),
    ("是否打款", "is_paid", WritePolicy.AFTER_DECISION),
    ("打款人", "payer", WritePolicy.AFTER_DECISION),
    ("打款日期", "pay_date", WritePolicy.AFTER_DECISION),
    ("发布日期", "publish_date", WritePolicy.NEVER),
    ("是否接单", "accepted", WritePolicy.NEVER),
    ("审核结果", "review_result", WritePolicy.NEVER),
    ("备注", "remark", WritePolicy.SYSTEM),
]

#: 溯源列（下划线前缀标识系统列，与业务 13 列并存、不污染业务字段）。
TRACE_COLUMNS: list[str] = [
    "_batch_id",
    "_request_id",
    "_rule_id",
    "_confirmed_by",
    "_confirmed_at",
    "_dedup_key",
]

#: 写入台账工作表名（副本自带，用于跨重启的幂等判重）。
LEDGER_SHEET = "_写入台账"
LEDGER_HEADERS: list[str] = ["dedup_key", "batch_id", "request_id", "row_ref", "written_at"]

CN_BY_KEY: dict[str, str] = {key: cn for cn, key, _ in SHEET_COLUMNS}
KEY_BY_CN: dict[str, str] = {cn: key for cn, key, _ in SHEET_COLUMNS}
POLICY_BY_KEY: dict[str, WritePolicy] = {key: policy for _, key, policy in SHEET_COLUMNS}

#: 只读列 —— 任何写入路径命中即抛错（架构 §3.3「抖加金额 ≠ 报价」的落地机制）。
READ_ONLY_KEYS: frozenset[str] = frozenset(
    key for _, key, policy in SHEET_COLUMNS if policy is WritePolicy.NEVER
)

#: 「人工确认后才可写」三列。
DECISION_REQUIRED_KEYS: frozenset[str] = frozenset(
    key for _, key, policy in SHEET_COLUMNS if policy is WritePolicy.AFTER_DECISION
)

#: 需要做非空检测的列（可回填 + 需裁决两类）。写前发现已有非空且值不同 → 不覆盖。
GUARDED_KEYS: frozenset[str] = READ_ONLY_KEYS | DECISION_REQUIRED_KEYS | frozenset(
    key for _, key, policy in SHEET_COLUMNS if policy is WritePolicy.FILL_IF_EMPTY
)


def assert_writable(field_key: str) -> None:
    """写前权限断言：命中只读列直接抛错。"""
    from app.domain.errors import ReadOnlyFieldError

    if field_key in READ_ONLY_KEYS:
        raise ReadOnlyFieldError(
            f"「{CN_BY_KEY.get(field_key, field_key)}」列只读，任何写入路径都被禁止",
            detail="架构 §3.3：抖加金额 ≠ 报价；文本亦不提供类型/抖音号/发布日期/接单/审核信息",
        )
