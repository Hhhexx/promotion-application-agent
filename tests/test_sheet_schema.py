"""回填权限表单测（架构 §3.2 / §3.3 / Spec §6.4）。

回填权限是「不猜测」落到写表层的最后一道闸门。这里锁死两条：
  * 只读列（如「报价」）任何写入路径都抛 `ReadOnlyFieldError`；
  * 可回填列遇已有非空值时不覆盖，转为可核查的冲突（供上层报 TARGET_CELL_NONEMPTY）。
"""

from __future__ import annotations

import pytest

from app.domain.errors import ReadOnlyFieldError
from app.repositories.sheet_schema import (
    CN_BY_KEY,
    DECISION_REQUIRED_KEYS,
    GUARDED_KEYS,
    KEY_BY_CN,
    READ_ONLY_KEYS,
    TRACE_COLUMNS,
    WritePolicy,
    assert_writable,
)
from app.repositories.xlsx_repository import XlsxRepository, copy_test_copy, policy_of


class TestSchemaDeclarations:
    def test_quote_price_is_read_only(self):
        assert "quote_price" in READ_ONLY_KEYS
        assert policy_of("quote_price") is WritePolicy.NEVER
        with pytest.raises(ReadOnlyFieldError):
            assert_writable("quote_price")

    def test_read_only_set_covers_never_columns(self):
        assert READ_ONLY_KEYS == frozenset(
            {"type", "douyin_nickname", "douyin_id", "quote_price", "publish_date", "accepted", "review_result"}
        )

    def test_decision_required_columns(self):
        assert DECISION_REQUIRED_KEYS == frozenset({"is_paid", "payer", "pay_date"})

    def test_fillable_columns_are_writable(self):
        for key in ("doujia_amount", "doujia_payer"):
            assert key not in READ_ONLY_KEYS
            assert_writable(key)  # 不抛异常

    def test_guarded_superset(self):
        assert READ_ONLY_KEYS <= GUARDED_KEYS
        assert DECISION_REQUIRED_KEYS <= GUARDED_KEYS

    def test_cn_key_mapping_is_bijective(self):
        assert CN_BY_KEY["quote_price"] == "报价"
        assert KEY_BY_CN["报价"] == "quote_price"
        assert len(CN_BY_KEY) == len(KEY_BY_CN) == 13

    def test_error_carries_http_status_for_entry_layer(self):
        try:
            assert_writable("quote_price")
        except ReadOnlyFieldError as exc:
            assert exc.http_status == 400
            assert exc.code == 1004
        else:  # pragma: no cover
            pytest.fail("只读列未抛错")


class TestRepositoryWriteGuards:
    @pytest.fixture
    def repo(self, source_table, workdir) -> XlsxRepository:
        copy_path = copy_test_copy(source_table, workdir / "copy.xlsx")
        return XlsxRepository(copy_path)

    def test_writing_read_only_column_raises(self, repo):
        with pytest.raises(ReadOnlyFieldError):
            repo.write_row("2", {"quote_price": "999"}, {})

    def test_fill_if_empty_writes_into_empty_cell(self, repo):
        written, blocked = repo.write_row("2", {"doujia_amount": "300.00"}, {"_batch_id": "b1"})
        assert written["doujia_amount"] == "300.00"
        assert blocked == []
        assert repo.ws.cell(row=2, column=repo.header["doujia_amount"]).value == "300.00"

    def test_existing_nonempty_value_is_not_overwritten(self, repo):
        # 第 6 行「抖加」已有 100
        written, blocked = repo.write_row("6", {"doujia_amount": "999.00"}, {})
        assert "doujia_amount" not in written
        assert blocked == [("doujia_amount", "100")]
        assert repo.ws.cell(row=6, column=repo.header["doujia_amount"]).value == 100

    def test_remark_is_appended_with_source_trace(self, repo):
        written, _ = repo.write_row("2", {"doujia_amount": "1.00"}, {}, remark="来源=doujia|2026-09-02；x")
        assert "来源=doujia|2026-09-02" in written["remark"]

    def test_trace_columns_are_added_after_business_columns(self, repo):
        repo.write_row("2", {"doujia_amount": "1.00"}, {"_batch_id": "b1", "_dedup_key": "k"})
        for name in TRACE_COLUMNS:
            assert name in repo.header
        assert repo.header["_batch_id"] > repo.header["remark"]
