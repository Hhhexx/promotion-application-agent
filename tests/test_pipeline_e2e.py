"""端到端测试（Spec v1.0 §12）：用 TestClient 把核心用户旅程跑成回归门禁。

对应用户旅程：登记账号表 → 解析抖加（无 P0）→ 写表 → 幂等重放 →
解析垫付（3 个 P0）→ 409 拦截 → 逐条裁决 → 写表 → 换表被拒 → 源表零污染。

这是「可运行演示」升级为「可回归验证」的关键文件：任何一处契约退化都会红。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from support import approve_advance, p0_of, sha256


@pytest.fixture
def journey(client, table_id, doujia_text, advance_text, source_table) -> dict:
    """跑完整条链路，返回各步骤产物供断言复用。"""
    source_hash = sha256(source_table)
    meta = client.get(f"/api/v1/account-tables/{table_id}").json()["data"]
    copy_path = meta["copy_path"]

    def parse(text: str) -> dict:
        response = client.post(
            "/api/v1/requests/parse", json={"raw_text": text, "table_id": table_id}
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def commit(request_id: str, **payload) -> tuple[int, dict]:
        response = client.post(
            f"/api/v1/requests/{request_id}/commit", json={"table_id": table_id, **payload}
        )
        return response.status_code, response.json()

    doujia = parse(doujia_text)
    _, doujia_body = commit(doujia["request_id"])
    doujia_commit = doujia_body["data"]
    hash_after_first_commit = sha256(copy_path)

    _, doujia_replay_body = commit(doujia["request_id"])
    doujia_replay = doujia_replay_body["data"]
    replay_copy_hash_unchanged = sha256(copy_path) == hash_after_first_commit

    advance = parse(advance_text)
    hash_before_block = sha256(copy_path)
    blocked_status, blocked_body = commit(advance["request_id"])
    blocked_copy_hash_unchanged = sha256(copy_path) == hash_before_block

    advance_id, pick = approve_advance(client, advance)
    ready = client.get(f"/api/v1/requests/{advance_id}").json()["data"]
    _, advance_body = commit(advance_id)
    advance_commit = advance_body["data"]

    return {
        "source_hash": source_hash,
        "source_table": source_table,
        "copy_path": copy_path,
        "replay_copy_hash_unchanged": replay_copy_hash_unchanged,
        "blocked_copy_hash_unchanged": blocked_copy_hash_unchanged,
        "meta": meta,
        "doujia": doujia,
        "doujia_commit": doujia_commit,
        "doujia_replay": doujia_replay,
        "advance": advance,
        "blocked_status": blocked_status,
        "blocked_body": blocked_body,
        "advance_id": advance_id,
        "pick": pick,
        "ready": ready,
        "advance_commit": advance_commit,
    }


class TestHealthAndTable:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_table_is_registered_as_copy(self, journey, source_table):
        meta = journey["meta"]
        assert meta["is_test_copy"] is True
        assert meta["copy_path"] != str(source_table)
        assert Path(meta["copy_path"]).exists()
        assert meta["source_path"] == str(source_table)

    def test_trace_columns_do_not_replace_business_columns(self, journey):
        assert len(journey["meta"]["columns"]) == 13


class TestDoujiaJourney:
    def test_parse_is_clean(self, journey):
        doujia = journey["doujia"]
        assert p0_of(doujia) == []
        assert doujia["aggregate_state"] == "READY"
        assert doujia["summary"]["declared_total_exact"] == "700.00"
        assert len(doujia["line_items"]) == 4
        assert doujia["cross_check"]["line_items_sum"] == 700.0
        assert doujia["cross_check"]["sheet_column_sum"] == 400.0
        assert doujia["cross_check"]["split_count_sum"] == 7

    def test_cross_source_mismatch_is_visible_but_not_blocking(self, journey):
        mismatch = [
            a
            for a in journey["doujia"]["anomalies"]
            if a["code"] == "CROSS_SOURCE_TOTAL_MISMATCH"
        ]
        assert mismatch and all(a["severity"] == "P1" and not a["blocking"] for a in mismatch)

    def test_commit_writes_four_rows(self, journey):
        outcome = journey["doujia_commit"]
        assert outcome["written_count"] == 4
        assert outcome["skipped_count"] == 0
        assert sorted(w["row_ref"] for w in outcome["written"]) == ["2", "3", "4", "5"]
        fields = outcome["written"][0]["fields_written"]
        assert "doujia_amount" in fields
        assert "doujia_payer" in fields
        assert "quote_price" not in fields  # 只读列不得被写入
        assert "来源=" in fields["remark"]

    def test_replay_is_idempotent(self, journey):
        replay = journey["doujia_replay"]
        assert replay["written_count"] == 0
        assert replay["skipped_count"] == 4
        assert all(s["reason"] == "SKIPPED_ALREADY_WRITTEN" for s in replay["skipped"])
        assert journey["replay_copy_hash_unchanged"] is True

    def test_replay_marks_items_skipped_already_written(self, journey, client):
        final = client.get(f"/api/v1/requests/{journey['doujia']['request_id']}").json()["data"]
        assert all(i["state"] == "SKIPPED_ALREADY_WRITTEN" for i in final["line_items"])


class TestAdvanceJourney:
    def test_parse_exposes_three_p0(self, journey):
        advance = journey["advance"]
        assert advance["aggregate_state"] == "NEEDS_REVIEW"
        assert len(p0_of(advance)) == 3
        assert {a["code"] for a in p0_of(advance)} == {
            "MATCH_AMBIGUOUS",
            "COUNT_MISMATCH",
            "DATE_ORDER_INVALID",
        }
        assert advance["summary"]["declared_total_exact"] == "2250.00"
        assert advance["summary"]["expected_pay_date_inferred"] is True
        assert advance["summary"]["expected_pay_date_raw"] == "26/08/31"

    def test_commit_is_blocked_with_pending_list(self, journey):
        assert journey["blocked_status"] == 409
        assert journey["blocked_body"]["code"] != 0
        pending = journey["blocked_body"]["data"]["pending"]
        assert len(pending) == 3
        assert set(pending) <= {a["anomaly_id"] for a in journey["advance"]["anomalies"]}
        assert journey["blocked_copy_hash_unchanged"] is True

    def test_after_resolutions_gate_is_ready(self, journey):
        assert journey["ready"]["aggregate_state"] == "READY"
        assert all(a["resolved"] for a in journey["ready"]["anomalies"] if a["severity"] == "P0")

    def test_commit_writes_five_rows_including_pinned_target(self, journey):
        outcome = journey["advance_commit"]
        assert outcome["written_count"] == 5
        assert journey["pick"] in [w["row_ref"] for w in outcome["written"]]

    def test_advance_writes_only_after_decision_columns(self, journey):
        for entry in journey["advance_commit"]["written"]:
            fields = entry["fields_written"]
            assert set(fields) <= {"payer", "pay_date", "remark"}
            assert "quote_price" not in fields
            assert "douyin_id" not in fields


class TestContractGuards:
    def test_committing_against_another_table_is_rejected(self, client, journey):
        other = client.post("/api/v1/account-tables").json()["data"]["table_id"]
        response = client.post(
            f"/api/v1/requests/{journey['advance_id']}/commit", json={"table_id": other}
        )
        assert 400 <= response.status_code < 500

    def test_source_table_is_byte_identical(self, journey):
        assert sha256(journey["source_table"]) == journey["source_hash"]

    def test_copy_carries_provenance_remark(self, client, journey):
        detail = client.get(f"/api/v1/account-tables/{journey['meta']['table_id']}").json()["data"]
        rows = {str(r["row_ref"]): r for r in detail["rows"]}
        for entry in journey["advance_commit"]["written"]:
            assert "来源=" in (rows[entry["row_ref"]]["remark"] or "")
        assert "12" in detail["empty_row_refs"]

    def test_error_paths_are_domain_errors(self, client):
        assert client.get("/api/v1/requests/nope").status_code == 404
        assert client.get("/api/v1/account-tables/nope").status_code == 404
        assert client.post("/api/v1/requests/parse", json={"raw_text": "   "}).status_code == 400
        assert client.get("/api/v1/summary").status_code == 400
