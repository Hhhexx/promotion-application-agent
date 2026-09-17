"""账号表匹配器单测（架构 §2.7）。

核心不变量：**非 EXACT_* 一律升级人工，禁止任何兜底猜测**。
模糊候选（WEAK_FUZZY）只作提示，永不作为可写目标；
同名多行（AMBIGUOUS）不按「第一行 / 最高分」自动选。
"""

from __future__ import annotations

from app.domain.enums import MatchLevel
from app.parsers.base import parse_request
from app.repositories.xlsx_repository import SheetRow
from app.validators.engine import validate
from app.validators.matcher import SheetIndex
from support import make_advance_text, make_doujia_text


def _index() -> SheetIndex:
    rows = [
        SheetRow("2", {"douyin_nickname": "初秋", "douyin_id": "34579726153"}),
        SheetRow("3", {"douyin_nickname": "艳红", "douyin_id": "47657512581"}),
        SheetRow("7", {"douyin_nickname": "葵花夫妇", "douyin_id": "LBXXnvzhuang"}),
        SheetRow("9", {"douyin_nickname": "葵花夫妇", "douyin_id": None}),
        SheetRow("10", {"douyin_nickname": "@@陈三", "douyin_id": "chensan35195"}),
    ]
    return SheetIndex(rows)


class TestMatchLevels:
    def test_exact_name_unique_hit(self):
        result = _index().match("初秋")
        assert result.level is MatchLevel.EXACT_NAME
        assert result.matched_row_ref == "2"

    def test_exact_id_wins_by_unique_id(self):
        result = _index().match("初秋", douyin_id="34579726153")
        assert result.level is MatchLevel.EXACT_ID
        assert result.matched_row_ref == "2"

    def test_ambiguous_name_lists_all_candidates(self):
        result = _index().match("葵花夫妇")
        assert result.level is MatchLevel.AMBIGUOUS
        assert result.matched_row_ref is None
        assert sorted(c.row_ref for c in result.candidates) == ["7", "9"]

    def test_no_match_returns_no_candidates(self):
        result = _index().match("完全无关的名字")
        assert result.level is MatchLevel.NO_MATCH
        assert result.matched_row_ref is None
        assert result.candidates == []

    def test_weak_fuzzy_is_never_an_auto_target(self):
        result = _index().match("葵花夫妇X")
        assert result.level is MatchLevel.WEAK_FUZZY
        # 候选仅作提示：不得给出可写目标
        assert result.matched_row_ref is None
        assert {c.row_ref for c in result.candidates} == {"7", "9"}
        assert all(c.score >= 0.6 for c in result.candidates)

    def test_decoration_in_table_name_is_not_stripped(self):
        # @@陈三 在台账里就是原名，系统不清洗装饰字符（去装饰属猜测）
        result = _index().match("@@陈三")
        assert result.level is MatchLevel.EXACT_NAME
        assert result.matched_row_ref == "10"

    def test_trailing_whitespace_does_not_break_exact_match(self):
        assert _index().match("@@陈三  ").matched_row_ref == "10"


class TestNoFuzzyFallbackInEngine:
    """模糊 / 歧义都必须在引擎里升级为人工阻断，而不是自动挑一行写入。"""

    def test_weak_fuzzy_becomes_blocking_match_not_found(self, source_snapshot):
        text = make_doujia_text([("初秋X", 300, None)], total=300)
        result = validate(parse_request(text), source_snapshot, "req_fuzzy")
        hits = [a for a in result.anomalies if a.code == "MATCH_NOT_FOUND"]
        assert len(hits) == 1
        assert hits[0].blocking is True
        assert hits[0].severity == "P0"
        assert hits[0].rule_id == "match.not_found"
        # 模糊候选只是提示，不构成任何写入目标
        assert result.line_items[0].match_result.matched_row_ref is None

    def test_ambiguous_becomes_blocking_and_skips_field_conflict(self, source_snapshot):
        # 葵花夫妇命中第 7、9 行；第 7 行打款人=木木老师 ≠ 文本 林老师。
        # 目标行未定，不得越级判成 P0 字段冲突（否则等于替人挑了行）。
        text = make_advance_text([("葵花夫妇", 500)], total=500, declared_count=1)
        result = validate(parse_request(text), source_snapshot, "req_amb")
        codes = {a.code for a in result.anomalies}
        assert "MATCH_AMBIGUOUS" in codes
        assert "CROSS_SOURCE_FIELD_CONFLICT" not in codes
        ambiguous = next(a for a in result.anomalies if a.code == "MATCH_AMBIGUOUS")
        assert ambiguous.blocking is True
        # 候选行信息写进证据，信息不丢失
        assert "第 7 行" in (ambiguous.evidence_note or "")
        assert "第 9 行" in (ambiguous.evidence_note or "")
