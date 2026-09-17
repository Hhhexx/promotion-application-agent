"""领域错误类型。

入口层据此映射 HTTP 状态码；业务层只抛领域错误，不感知 HTTP。
"""

from __future__ import annotations


class DomainError(Exception):
    """领域错误基类。`code` 为业务错误码（非 0）。"""

    code: int = 1000
    http_status: int = 400

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class ValidationError(DomainError):
    """入参不合法（如未提供文本、文本无法识别类型）。"""

    code = 1001
    http_status = 400


class NotFoundError(DomainError):
    """资源不存在（request_id / table_id / report_id 未命中）。"""

    code = 1002
    http_status = 404


class GateBlockedError(DomainError):
    """人工确认闸门拦下写表：存在未裁决 P0。

    对应架构 §4.3 闸门不变量 —— 该错误抛出时**不发生任何写入**。
    """

    code = 1003
    http_status = 409

    def __init__(self, message: str, *, pending: list[str] | None = None) -> None:
        super().__init__(message)
        self.pending = pending or []


class ReadOnlyFieldError(DomainError):
    """试图写入只读列（如「报价」）。架构 §3.3 硬约束。"""

    code = 1004
    http_status = 400


class UnresolvableError(DomainError):
    """日期等字段无法唯一归一，禁止静默取值（Spec §10 日期约束）。"""

    code = 1005
    http_status = 400
