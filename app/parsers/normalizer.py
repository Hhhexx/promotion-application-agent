"""归一化工具（架构 §2.6 / §2.7）。

全程确定性、可单测。**明确禁止**语义猜测类"归一化"：去昵称装饰后缀、
去 `@@` 前缀、同义昵称合并、繁简转换 —— 这些属于猜（架构 §2.6 第 7 条）。
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.config import MONEY_EXP
from app.domain.errors import UnresolvableError

_ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS = re.compile(r"\s+")

ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
SLASH_YMD_RE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")
SLASH_YMD_DASH_RE = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$")
SLASH_YYMD_RE = re.compile(r"^(\d{2})/(\d{1,2})/(\d{1,2})$")
DOTTED_MD_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})$")


def normalize_text(value: str) -> str:
    """NFKC → 去零宽/控制字符 → 折叠空白 → 去首尾。"""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = _ZERO_WIDTH.sub("", s)
    s = _CONTROL.sub("", s)
    return _WS.sub(" ", s).strip()


def normalize_name(value: str) -> str:
    """昵称归一：在 `normalize_text` 基础上仅追加 ASCII 段小写。

    CJK 段保持不变 —— 不做拼音、不做简繁、不去装饰后缀。
    """
    s = normalize_text(value)
    return "".join(ch.lower() if ch.isascii() else ch for ch in s)


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    """把金额文本转成 `Decimal` 并量化到 2 位。`¥`、千分位、空格一律剥离。"""
    if isinstance(value, Decimal):
        return value.quantize(Decimal(MONEY_EXP))
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(Decimal(MONEY_EXP))
    s = normalize_text(value).replace("¥", "").replace("￥", "").replace(",", "").replace(" ", "")
    if not s:
        raise InvalidOperation("空金额")
    return Decimal(s).quantize(Decimal(MONEY_EXP))


def format_money(value: Decimal) -> str:
    """金额的稳定字符串形式（去重键与审计字段使用）。"""
    return f"{value.quantize(Decimal(MONEY_EXP)):.2f}"


def _complete_two_digit_year(yy: int, anchor_year: int) -> int:
    """两位数年份补全：取距 `anchor_year` 最近的世纪（确定性，无猜测成分）。

    `26` + anchor 2026 → 2026（差 0）而非 1926（差 100）。
    """
    candidates = (yy + 2000, yy + 1900)
    return min(candidates, key=lambda y: (abs(y - anchor_year), y))


def classify_date_format(raw: str) -> str:
    """判定日期书写风格，供 `DATE_FORMAT_INCONSISTENT` 使用。"""
    s = normalize_text(raw)
    if not s:
        return "empty"
    if ISO_RE.match(s):
        return "iso"
    if SLASH_YMD_RE.match(s):
        return "slash_ymd"
    if SLASH_YMD_DASH_RE.match(s):
        return "dotted_ymd"
    if SLASH_YYMD_RE.match(s):
        return "slash_yymd"
    if DOTTED_MD_RE.match(s):
        return "dotted_md"
    return "unknown"


def normalize_date(raw: str, anchor_year: int) -> tuple[date, bool]:
    """归一日期为 `date`，返回 `(值, 是否为推断)`。

    * `inferred=False`：原文已含四位年份，值可直接采信。
    * `inferred=True`：两位年份补全或无年份按批次锚定 —— 调用方**必须**置为待确认
      （Spec §10 日期约束）。

    无法唯一确定时抛 `UnresolvableError`，绝不静默取值。

    注意：**所有** `date(...)` 构造都必须收敛为 `UnresolvableError`。
    形如 `13/45/99`、`2026/13/01` 的非法月日会让 `date()` 抛裸 `ValueError`，
    若任其冒泡，解析端点会以 500 结束 —— 那是「服务崩了」而不是「数据有问题」，
    既误导调用方，也违背第 5 条「不猜测、标记人工确认」的产品要求。
    """
    s = normalize_text(raw)
    for pattern in (ISO_RE, SLASH_YMD_RE, SLASH_YMD_DASH_RE):
        m = pattern.match(s)
        if m:
            y, mo, d = (int(g) for g in m.groups())
            try:
                return date(y, mo, d), False
            except ValueError as exc:  # 例如 2026/13/01
                raise UnresolvableError(f"日期无法归一：{raw}") from exc
    m = SLASH_YYMD_RE.match(s)
    if m:
        yy, mo, d = (int(g) for g in m.groups())
        try:
            return date(_complete_two_digit_year(yy, anchor_year), mo, d), True
        except ValueError as exc:  # 例如 13/45/99
            raise UnresolvableError(f"日期无法归一：{raw}") from exc
    m = DOTTED_MD_RE.match(s)
    if m:
        mo, d = (int(g) for g in m.groups())
        try:
            return date(anchor_year, mo, d), True
        except ValueError as exc:  # 例如 4.31
            raise UnresolvableError(f"日期无法归一：{raw}") from exc
    raise UnresolvableError(f"日期无法归一：{raw}")


def monetary_key(value: Decimal) -> str:
    """去重键里的金额段（保 2 位，禁用 float 表示）。"""
    return format_money(value)


def build_dedup_key(
    biz_type: str, request_date: date, name_norm: str, amount: Decimal, payer_norm: str
) -> str:
    """记录级去重键（架构 §2.6）。"""
    return f"{biz_type}|{request_date.isoformat()}|{name_norm}|{monetary_key(amount)}|{payer_norm}"


def build_batch_id(biz_type: str, request_date: date) -> str:
    """批次级幂等键（架构 §2.6）。"""
    return f"{biz_type}|{request_date.isoformat()}"
