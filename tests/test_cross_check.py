"""交叉校验单测（架构 §2.5 / §4.5）。

本文件锁死「跨源差异的定档口径」这条最容易退化的规则：
  * 同源自相矛盾（总额 / 笔数）→ P0 阻断；
  * 跨源总额差异（表内列无批次维度，等式无法验证）→ **P1 不阻断**；
  * 跨源字段取值冲突（目标行唯一、可比对）→ P0 阻断。
错误地把 P1 升格成 P0 会阻塞全部业务；错误地把 P0 降格成 P1 会放行错账。
"""

from __future__ import annotations

from app.parsers.base import parse_request
from app.validators.engine import validate
from support import make_advance_text, make_doujia_text, make_snapshot


class TestSameSource:
    def test_count_mismatch_is_blocking_p0(self, source_snapshot):
        # 声明 5 笔，明细实际只有 2 笔
        text = make_doujia_text(
            [("初秋", 100, None), ("艳红", 100, None)], total=200, declared_count=5
        )
        result = validate(parse_request(text), source_snapshot, "req_count")
        hits = [a for a in result.anomalies if a.code == "COUNT_MISMATCH"]
        assert len(hits) == 1
        assert hits[0].severity == "P0"
        assert hits[0].blocking is True
        assert hits[0].rule_id == "cross.count"
        assert hits[0].text_value == "5"
        assert hits[0].sheet_value == "2"

    def test_consistent_count_produces_no_count_mismatch(self, source_snapshot):
        text = make_doujia_text(
            [("初秋", 100, None), ("艳红", 100, None)], total=200, declared_count=2
        )
        result = validate(parse_request(text), source_snapshot, "req_ok")
        assert not [a for a in result.anomalies if a.code == "COUNT_MISMATCH"]

    def test_total_mismatch_is_blocking_p0(self, source_snapshot):
        # 声明 700，明细求和 200
        text = make_doujia_text(
            [("初秋", 100, None), ("艳红", 100, None)], total=700, declared_count=2
        )
        result = validate(parse_request(text), source_snapshot, "req_total")
        hits = [a for a in result.anomalies if a.code == "TOTAL_MISMATCH"]
        assert len(hits) == 1
        assert hits[0].blocking is True
        assert hits[0].rule_id == "cross.total"
        assert hits[0].impact_amount == 500.0


class TestCrossSource:
    def test_real_doujia_sample_downgrades_total_mismatch_to_p1(self, doujia_text, source_snapshot):
        result = validate(parse_request(doujia_text), source_snapshot, "req_cross")
        hits = [a for a in result.anomalies if a.code == "CROSS_SOURCE_TOTAL_MISMATCH"]
        assert len(hits) == 1
        anomaly = hits[0]
        assert anomaly.severity == "P1"
        assert anomaly.blocking is False
        assert anomaly.rule_id == "xsrc.total"
        assert anomaly.text_value == "700.00"
        assert anomaly.sheet_value == "400.00"
        assert anomaly.evidence_note and "无法验证" in anomaly.evidence_note

    def test_three_figures_are_reported_side_by_side_not_merged(self, doujia_text, source_snapshot):
        result = validate(parse_request(doujia_text), source_snapshot, "req_three")
        check = result.cross_check
        assert check.line_items_sum == 700.0
        assert check.declared_total_amount == 700.0
        assert check.sheet_column_sum == 400.0
        assert check.sheet_column_sum_exact == "400.00"
        # 三口径并列：绝不把表内列合计混进总额
        assert check.line_items_sum != check.sheet_column_sum

    def test_doujia_batch_has_zero_p0(self, doujia_text, source_snapshot):
        result = validate(parse_request(doujia_text), source_snapshot, "req_zero")
        assert [a for a in result.anomalies if a.severity == "P0"] == []
        assert result.aggregate_state == "READY"

    def test_scope_mismatch_is_p1_not_p0(self, doujia_text, source_snapshot):
        result = validate(parse_request(doujia_text), source_snapshot, "req_scope")
        scope = [a for a in result.anomalies if a.code == "CROSS_SOURCE_SCOPE_MISMATCH"]
        assert scope
        assert all(a.severity == "P1" and not a.blocking for a in scope)

    def test_field_conflict_on_unique_target_is_blocking_p0(self, source_snapshot):
        # 唐山第一女泵工 唯一命中台账第 4 行，该行打款人=木木老师，文本=林老师
        text = make_advance_text([("唐山第一女泵工", 950)], total=950, declared_count=1, payer="林老师")
        result = validate(parse_request(text), source_snapshot, "req_conflict")
        hits = [a for a in result.anomalies if a.code == "CROSS_SOURCE_FIELD_CONFLICT"]
        assert len(hits) == 1
        anomaly = hits[0]
        assert anomaly.severity == "P0"
        assert anomaly.blocking is True
        assert anomaly.rule_id == "xsrc.field_conflict"
        assert anomaly.text_value == "林老师"
        assert anomaly.sheet_value == "木木老师"
        assert anomaly.sheet_row_ref == "4"
        assert anomaly.target_field == "payer"

    def test_no_field_conflict_when_target_row_is_undetermined(self, source_snapshot):
        # 葵花夫妇 命中第 7、9 行 → 目标行未定 → 不做字段冲突判定
        text = make_advance_text([("葵花夫妇", 500)], total=500, declared_count=1)
        result = validate(parse_request(text), source_snapshot, "req_amb")
        assert not [a for a in result.anomalies if a.code == "CROSS_SOURCE_FIELD_CONFLICT"]


class TestDeterminism:
    def test_same_input_yields_same_anomaly_ids(self, doujia_text, source_snapshot):
        first = validate(parse_request(doujia_text), source_snapshot, "req_a")
        second = validate(parse_request(doujia_text), source_snapshot, "req_b")
        assert [a.anomaly_id for a in first.anomalies] == [a.anomaly_id for a in second.anomalies]
        assert [a.code for a in first.anomalies] == [a.code for a in second.anomalies]

    def test_factory_emits_sequential_ids(self):
        from app.domain.enums import AnomalyCode
        from app.validators.anomaly_rules import AnomalyFactory

        factory = AnomalyFactory()
        assert factory.make(AnomalyCode.REMARK_EMPTY, "a").anomaly_id == "anm_01"
        assert factory.make(AnomalyCode.REMARK_EMPTY, "b").anomaly_id == "anm_02"

    def test_snapshot_helper_is_hermetic(self):
        # make_snapshot 造出的空快照不引入任何表级体检项
        result = validate(
            parse_request(make_doujia_text([("初秋", 100, None)], total=100, declared_count=1)),
            make_snapshot([]),
            "req_empty",
        )
        assert not [a for a in result.anomalies if a.rule_id.startswith("table.")]
