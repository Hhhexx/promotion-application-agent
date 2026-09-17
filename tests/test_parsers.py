"""解析层单测（架构 §2.2 / §2.3）。

覆盖：
  * 业务类型识别（无 hint 必须靠文档头；识别不出必须抛错，不猜）；
  * 表级汇总声明抽取（总额 / 笔数 / 合并笔数 / 支付人 / 预计打款日期）；
  * 明细行解析（拆笔数 7 = 3+2+1+1、金额 Decimal 保 2 位、source_span）；
  * 无法识别的明细行必须进 `unparsed_lines`（升级为 UNPARSED_LINE），不静默跳过。
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.enums import BizType
from app.domain.errors import ValidationError
from app.parsers.base import build_line_items, detect_biz_type, parse_request
from support import make_advance_text, make_doujia_text


class TestBizTypeDetection:
    def test_doujia_header(self, doujia_text):
        assert detect_biz_type(doujia_text) is BizType.DOUJIA

    def test_advance_header(self, advance_text):
        assert detect_biz_type(advance_text) is BizType.ADVANCE

    def test_hint_used_when_no_header(self):
        assert detect_biz_type("随便一段话，没有文档头", BizType.ADVANCE) is BizType.ADVANCE

    def test_header_wins_over_hint(self):
        text = make_doujia_text([("初秋", 100, None)], total=100)
        assert detect_biz_type(text, BizType.ADVANCE) is BizType.DOUJIA

    def test_unknown_type_without_hint_is_rejected(self):
        # 识别不出就拒绝解析 —— 猜类型会让后续校验全部错位
        with pytest.raises(ValidationError):
            detect_biz_type("既没有抖加头也没有垫付头")


class TestParseGuards:
    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            parse_request("")

    def test_whitespace_only_text_rejected(self):
        with pytest.raises(ValidationError):
            parse_request("   \n\t ")

    def test_missing_date_rejected(self):
        text = "【抖加金额统计】今日已支付：¥100\n\n明细如下：\n歌名：《X》- 博主名：初秋 - 金额：¥100\n"
        with pytest.raises(ValidationError):
            parse_request(text)

    def test_missing_detail_marker_rejected(self):
        text = "【抖加金额统计】今日已支付：¥100（2026-09-02）\n\n抖加支付人：爆火音乐\n"
        with pytest.raises(ValidationError):
            parse_request(text)

    def test_all_lines_unparsable_rejected(self):
        text = (
            "【抖加金额统计】今日已支付：¥100（2026-09-02）\n\n明细如下：\n"
            "这一行不是任何模板能识别的格式\n\n抖加支付人：爆火音乐\n"
        )
        with pytest.raises(ValidationError):
            parse_request(text)


class TestDoujiaParse:
    def test_summary_declaration(self, doujia_text):
        parsed = parse_request(doujia_text)
        assert parsed.biz_type is BizType.DOUJIA
        assert parsed.declared_date == date(2026, 9, 2)
        assert parsed.declared_total == 700
        assert parsed.declared_count == 7
        assert parsed.declared_merged_count == 4
        assert parsed.payer_raw == "爆火音乐"
        assert parsed.missing_fields == []

    def test_items_and_split_counts(self, doujia_text):
        parsed = parse_request(doujia_text)
        assert [i.name_raw for i in parsed.items] == ["初秋", "艳红", "唐山第一女泵工", "戎大姨"]
        assert [i.split_count for i in parsed.items] == [3, 2, 1, 1]
        # 拆笔数之和 7 = 3 + 2 + 1 + 1
        assert sum(i.split_count for i in parsed.items) == 7

    def test_amounts_are_decimal_quantized(self, doujia_text):
        items = build_line_items(parse_request(doujia_text))
        assert [i.amount_exact for i in items] == ["300.00", "200.00", "100.00", "100.00"]
        assert all(i.song_name == "你是我的仰望" for i in items)

    def test_line_items_carry_dedup_key_and_span(self, doujia_text):
        items = build_line_items(parse_request(doujia_text))
        assert items[0].dedup_key == "doujia|2026-09-02|初秋|300.00|爆火音乐"
        assert items[0].source_span.end > items[0].source_span.start
        assert items[0].line_no == 4  # 「明细如下：」在第 3 行，首条明细在第 4 行

    def test_missing_payer_is_recorded_not_defaulted(self):
        text = make_doujia_text([("初秋", 100, None)], total=100)
        text = text.replace("抖加支付人：爆火音乐", "")
        parsed = parse_request(text)
        assert parsed.payer_raw is None
        assert "抖加支付人" in parsed.missing_fields


class TestAdvanceParse:
    def test_summary_declaration(self, advance_text):
        parsed = parse_request(advance_text)
        assert parsed.biz_type is BizType.ADVANCE
        assert parsed.declared_date == date(2026, 9, 3)
        assert parsed.declared_total == 2250
        assert parsed.declared_count == 7
        assert parsed.payer_raw == "林老师"
        assert parsed.missing_fields == []

    def test_expected_pay_date_is_inferred_from_two_digit_year(self, advance_text):
        parsed = parse_request(advance_text)
        assert parsed.expected_pay_date_raw == "26/08/31"
        assert parsed.expected_pay_date == date(2026, 8, 31)
        assert parsed.expected_pay_date_inferred is True

    def test_advance_has_no_split_concept(self, advance_text):
        parsed = parse_request(advance_text)
        assert [i.name_raw for i in parsed.items] == ["初秋", "艳红", "戎大姨", "高高", "葵花夫妇"]
        assert all(i.split_count is None for i in parsed.items)

    def test_advance_amounts_exact(self, advance_text):
        items = build_line_items(parse_request(advance_text))
        assert [i.amount_exact for i in items] == ["950.00", "300.00", "300.00", "200.00", "500.00"]
        assert sum(float(i.amount_exact) for i in items) == 2250.0

    def test_unresolvable_expected_pay_date_becomes_date_issue(self):
        text = make_advance_text(
            [("初秋", 300)], total=300, declared_count=1, expected_pay_date="4.31"
        )
        parsed = parse_request(text)
        assert parsed.expected_pay_date is None
        assert parsed.date_issues == [("预计打款日期", "4.31")]


class TestUnparsedLines:
    def test_unrecognized_detail_line_is_kept_not_skipped(self):
        text = (
            "【抖加金额统计】今日已支付：¥300（2026-09-02）\n\n明细如下：\n"
            "歌名：《你是我的仰望》- 博主名：初秋 - 金额：¥300（分 3 笔）\n"
            "这一行完全不是明细格式\n\n今日共 3 笔支付申请，合并同博主后为 1 笔。\n"
            "抖加支付人：爆火音乐\n"
        )
        parsed = parse_request(text)
        assert len(parsed.items) == 1
        assert len(parsed.unparsed_lines) == 1
        line_no, raw, span = parsed.unparsed_lines[0]
        assert line_no == 5
        assert raw == "这一行完全不是明细格式"
        assert span.end > span.start
