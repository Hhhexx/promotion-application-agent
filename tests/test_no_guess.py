"""「不猜测」原则的落地测试。

系统对任何不确定项都不许填默认值 / 不许顺手改别的列。本文件用**逐行逐列的文件级对比**
把这条原则变成可回归的证据：除本批次授权可写的列之外，副本必须与源表完全一致；
源表本来就空的格子（如「马马马叔」的打款人、葵花夫妇第 9 行的抖音号）写入后仍然为空。
"""

from __future__ import annotations

import pytest

from support import (
    HEADER_TO_KEY,
    WRITABLE_HEADERS,
    approve_advance,
    normalize_cell,
    read_sheet_rows,
    sha256,
)


@pytest.fixture
def written(client, table_id, doujia_text, advance_text, source_table) -> dict:
    """跑完抖加 + 垫付两条写入链路，返回源表 / 副本的逐行快照。"""
    source_hash_before = sha256(source_table)

    def parse(text: str) -> dict:
        response = client.post(
            "/api/v1/requests/parse", json={"raw_text": text, "table_id": table_id}
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    doujia = parse(doujia_text)
    client.post(f"/api/v1/requests/{doujia['request_id']}/commit", json={"table_id": table_id})

    advance = parse(advance_text)
    advance_id, pick = approve_advance(client, advance)
    commit = client.post(
        f"/api/v1/requests/{advance_id}/commit", json={"table_id": table_id}
    )
    assert commit.status_code == 200, commit.text

    detail = client.get(f"/api/v1/account-tables/{table_id}").json()["data"]
    return {
        "source_table": source_table,
        "source_hash_before": source_hash_before,
        "copy_path": detail["copy_path"],
        "detail": detail,
        "source_rows": read_sheet_rows(source_table),
        "copy_rows": read_sheet_rows(detail["copy_path"]),
        "pick": pick,
        "advance_written": commit.json()["data"]["written"],
    }


class TestEmptyCellsAreNotFilled:
    def test_mamashu_payer_stays_empty(self, written):
        # 源表第 17 行「是否打款=是」但「打款人」为空 —— 系统不填默认值
        row = written["copy_rows"]["17"]
        assert normalize_cell(row["打款人"]) == ""
        assert normalize_cell(row["打款日期"]) == ""
        assert row["是否打款"] == "是"

    def test_ambiguous_second_row_is_untouched(self, written):
        # 葵花夫妇第 9 行：抖音号 / 打款人 / 打款日期原本为空；目标行被钉到第 7 行后，
        # 第 9 行不得被顺手写入任何内容
        row = written["copy_rows"]["9"]
        assert normalize_cell(row["抖音号"]) == ""
        assert normalize_cell(row["打款人"]) == ""
        assert normalize_cell(row["打款日期"]) == ""
        assert written["pick"] == "7"

    def test_pinned_row_receives_the_write(self, written):
        row = written["copy_rows"][written["pick"]]
        # 打款日期为空 → 被写入；打款人已有「木木老师」→ 不覆盖（这正是「不猜测 / 不覆盖」）
        assert normalize_cell(row["打款日期"]) == "2026-08-31"
        assert normalize_cell(row["打款人"]) == "木木老师"

    def test_read_only_columns_are_not_derived_from_anything(self, written):
        # 「报价」不得被抖加金额或垫付金额污染
        assert normalize_cell(written["copy_rows"]["2"]["报价"]) == normalize_cell(
            written["source_rows"]["2"]["报价"]
        )
        assert normalize_cell(written["copy_rows"]["7"]["报价"]) == normalize_cell(
            written["source_rows"]["7"]["报价"]
        )


class TestNoOutOfScopeWrites:
    def test_non_writable_columns_are_byte_identical_row_by_row(self, written):
        source_rows = written["source_rows"]
        copy_rows = written["copy_rows"]
        diffs: list[str] = []
        for row_ref, source_row in source_rows.items():
            copy_row = copy_rows.get(row_ref, {})
            for header, source_value in source_row.items():
                if header in WRITABLE_HEADERS:
                    continue
                if header not in HEADER_TO_KEY:
                    continue
                got = copy_row.get(header)
                if normalize_cell(got) != normalize_cell(source_value):
                    diffs.append(f"第{row_ref}行 {header}: 源={source_value!r} 副本={got!r}")
        assert not diffs, "；".join(diffs[:6])

    def test_source_table_is_never_modified(self, written):
        assert sha256(written["source_table"]) == written["source_hash_before"]
        # 副本与源表是不同文件，写入只落在副本
        assert written["copy_path"] != str(written["source_table"])

    def test_empty_row_is_registered_not_deleted(self, written):
        detail = written["detail"]
        assert detail["empty_row_refs"] == ["12"]
        # 空行不参与匹配，故不出现在行清单里
        assert "12" not in {str(r["row_ref"]) for r in detail["rows"]}
        # 文件里那一行仍然存在且为空
        assert normalize_cell(written["copy_rows"].get("12", {}).get("抖音昵称")) == ""

    def test_provenance_trace_is_recorded_for_written_rows(self, written):
        rows = {str(r["row_ref"]): r for r in written["detail"]["rows"]}
        for entry in written["advance_written"]:
            remark = rows[entry["row_ref"]]["remark"] or ""
            assert "来源=" in remark
            assert "request_id=" in remark
