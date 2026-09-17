"""归一化层单测（架构 §2.6 / Spec §10）。

锁定三条不可退让的约束：
  * 文本归一化是确定性的（NFKC + 去零宽/控制字符 + 折叠空白），**不做语义猜测**；
  * 金额一律 `Decimal` 保 2 位，`amount_exact` 是去重与审计的唯一来源；
  * 日期无法唯一确定时必须抛错，两位年份补全是确定性的（取最近世纪）。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import pytest

from app.domain.errors import UnresolvableError
from app.parsers.normalizer import (
    build_batch_id,
    build_dedup_key,
    classify_date_format,
    format_money,
    monetary_key,
    normalize_date,
    normalize_name,
    normalize_text,
    to_decimal,
)


class TestTextNormalization:
    def test_nfkc_folds_fullwidth_to_halfwidth(self):
        assert normalize_text("　Ａ　Ｂ　１２３　") == "A B 123"

    def test_strips_zero_width_and_control_chars(self):
        # 零宽空格 / 零宽连接符 / BOM 一律剔除，避免同名不同键
        assert normalize_text("y\u200bou\ufeff") == "you"
        assert normalize_text("抖加\x07金额") == "抖加金额"

    def test_collapses_whitespace_and_strips(self):
        assert normalize_text("  抖加\t金额 \n") == "抖加 金额"

    def test_idempotent(self):
        once = normalize_text(" Ａ\u200b  Ｂ ")
        assert normalize_text(once) == once

    def test_name_normalization_only_lowercases_ascii(self):
        # CJK 段保持原样：不做拼音、不做简繁、不去装饰后缀
        assert normalize_name("ＡbＣ") == "abc"
        assert normalize_name("葵花夫妇") == "葵花夫妇"
        assert normalize_name("@@陈三") == "@@陈三"


class TestMoney:
    def test_strips_currency_and_thousand_separator(self):
        assert to_decimal("¥1,234.5") == Decimal("1234.50")
        assert to_decimal("￥2,250") == Decimal("2250.00")

    def test_quantized_to_two_decimals(self):
        value = to_decimal("700")
        assert value == Decimal("700.00")
        assert value.as_tuple().exponent == -2

    def test_int_and_float_inputs(self):
        assert to_decimal(700) == Decimal("700.00")
        assert format_money(to_decimal(700)) == "700.00"

    def test_float_input_goes_through_str_no_binary_noise(self):
        # 0.1 + 0.2 的二进制误差不得进入台账
        assert to_decimal(0.1 + 0.2) == Decimal("0.30")

    def test_empty_amount_is_rejected(self):
        with pytest.raises(InvalidOperation):
            to_decimal("   ")

    def test_monetary_key_is_stable_two_decimal_string(self):
        assert monetary_key(Decimal("300")) == "300.00"
        assert monetary_key(to_decimal("¥1,234.5")) == "1234.50"


class TestDate:
    def test_two_digit_year_completes_to_nearest_century(self):
        value, inferred = normalize_date("26/08/31", anchor_year=2026)
        assert value == date(2026, 8, 31)
        assert inferred is True

    def test_two_digit_year_anchored_to_1900(self):
        value, inferred = normalize_date("26/08/31", anchor_year=1900)
        assert value == date(1926, 8, 31)
        assert inferred is True

    def test_four_digit_year_is_not_inferred(self):
        value, inferred = normalize_date("2026/8/21", anchor_year=2026)
        assert value == date(2026, 8, 21)
        assert inferred is False

    def test_iso_date_is_not_inferred(self):
        value, inferred = normalize_date("2026-09-03", anchor_year=2026)
        assert value == date(2026, 9, 3)
        assert inferred is False

    def test_yearless_dotted_date_is_inferred_and_anchored(self):
        value, inferred = normalize_date("4.9", anchor_year=2026)
        assert value == date(2026, 4, 9)
        assert inferred is True

    def test_yearless_impossible_date_is_unresolvable_not_guessed(self):
        # 4.31 不存在：必须抛领域错误，绝不静默取近似值
        with pytest.raises(UnresolvableError):
            normalize_date("4.31", anchor_year=2026)

    def test_unparseable_date_is_unresolvable(self):
        with pytest.raises(UnresolvableError):
            normalize_date("上周三", anchor_year=2026)

    def test_two_digit_year_with_impossible_month_or_day_is_unresolvable(self):
        # 回归：两位年份写法下的非法月日（原缺陷：抛裸 ValueError → 接口 500）
        with pytest.raises(UnresolvableError) as excinfo:
            normalize_date("13/45/99", anchor_year=2026)
        # UnresolvableError 不是 ValueError 的子类；断言这一条即证明
        # 抛出的不是裸 ValueError（「数据有问题」而非「服务崩了」）。
        assert not isinstance(excinfo.value, ValueError)

    @pytest.mark.parametrize(
        ("raw", "branch"),
        [
            ("13/45/99", "slash_yymd"),  # 两位年份 + 非法月日
            ("2026/13/01", "slash_ymd"),  # 四位年份斜杠
            ("2026-13-01", "iso"),  # 四位年份短横
            ("2026.13.01", "dotted_ymd"),  # 四位年份点号
            ("4.31", "dotted_md"),  # 无年份点号（修复前已正确的防回归基线）
        ],
    )
    def test_impossible_month_or_day_is_never_a_bare_value_error(self, raw, branch):
        """四条 date() 构造路径（+ 既已正确的点号路径）都必须收敛为领域错误。"""
        assert classify_date_format(raw) == branch  # 确认确实走到了预期分支
        with pytest.raises(UnresolvableError) as excinfo:
            normalize_date(raw, anchor_year=2026)
        assert not isinstance(excinfo.value, ValueError)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-09-03", "iso"),
            ("2026/8/21", "slash_ymd"),
            ("26/08/31", "slash_yymd"),
            ("2026.8.21", "dotted_ymd"),
            ("4.9", "dotted_md"),
            ("", "empty"),
            ("明天", "unknown"),
        ],
    )
    def test_classify_date_format(self, raw, expected):
        assert classify_date_format(raw) == expected


class TestKeys:
    def test_dedup_key_is_deterministic(self):
        first = build_dedup_key("advance", date(2026, 9, 3), "初秋", Decimal("950.00"), "林老师")
        second = build_dedup_key("advance", date(2026, 9, 3), "初秋", Decimal("950.00"), "林老师")
        assert first == second == "advance|2026-09-03|初秋|950.00|林老师"

    def test_dedup_key_uses_two_decimal_money(self):
        assert build_dedup_key("doujia", date(2026, 9, 2), "初秋", Decimal("300"), "爆火音乐") == (
            "doujia|2026-09-02|初秋|300.00|爆火音乐"
        )

    def test_dedup_key_changes_on_amount_or_payer(self):
        base = build_dedup_key("advance", date(2026, 9, 3), "初秋", Decimal("950.00"), "林老师")
        assert base != build_dedup_key("advance", date(2026, 9, 3), "初秋", Decimal("900.00"), "林老师")
        assert base != build_dedup_key("advance", date(2026, 9, 3), "初秋", Decimal("950.00"), "木木老师")

    def test_batch_id(self):
        assert build_batch_id("doujia", date(2026, 9, 2)) == "doujia|2026-09-02"
