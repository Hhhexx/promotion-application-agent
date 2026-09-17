"""接口级回归：非法日期必须被「标记」，而不是让服务 500。

对应缺陷（已修复）：`app/parsers/normalizer.py` 的 `date()` 构造曾让非法月日
（如 `13/45/99`）抛裸 `ValueError`，`POST /api/v1/requests/parse` 以 500 结束。
修复后，用户实际感受到的应是「被标记 → 转人工确认」，而不是「服务挂了」：
  HTTP 200 + `DATE_UNRESOLVABLE`（P0，blocking）+ `NEEDS_REVIEW`，
  且闸门照常拦下写表（409，零写入）。
"""

from __future__ import annotations

import pytest

from support import make_advance_text, sha256

#: 垫付文本，预计打款日期写了一个不存在的月日。
INVALID_DATE_TEXT = make_advance_text(
    [("初秋", 300)], total=300, declared_count=1, expected_pay_date="13/45/99"
)


@pytest.fixture
def parsed(client, table_id) -> dict:
    response = client.post(
        "/api/v1/requests/parse",
        json={"raw_text": INVALID_DATE_TEXT, "table_id": table_id},
    )
    assert response.status_code == 200, (
        f"应为 200（标记待确认），实际 {response.status_code}：{response.text[:200]}"
    )
    return response.json()["data"]


class TestUnresolvableDateIsMarkedNotCrashed:
    def test_parse_still_succeeds(self, parsed):
        # 关键：畸形日期是「数据问题」，不是「服务故障」——不得 5xx
        assert parsed["request_id"]
        assert parsed["biz_type"] == "advance"

    def test_date_unresolvable_anomaly_is_well_formed(self, parsed):
        hits = [a for a in parsed["anomalies"] if a["code"] == "DATE_UNRESOLVABLE"]
        assert len(hits) == 1
        anomaly = hits[0]
        assert anomaly["severity"] == "P0"
        assert anomaly["blocking"] is True
        assert anomaly["target_field"] == "预计打款日期"
        assert anomaly["text_value"] == "13/45/99"
        assert anomaly["rule_id"] == "cross.date_unresolvable"
        assert anomaly["exc_id"] == "EXC-02"
        assert anomaly["action_required"]

    def test_date_is_left_unresolved_not_guessed(self, parsed):
        summary = parsed["summary"]
        assert summary["expected_pay_date"] is None
        assert summary["expected_pay_date_raw"] == "13/45/99"
        assert summary["expected_pay_date_inferred"] is False

    def test_batch_goes_to_needs_review(self, parsed):
        assert parsed["aggregate_state"] == "NEEDS_REVIEW"

    def test_commit_is_blocked_with_zero_write(self, client, parsed, table_id):
        copy_path = client.get(f"/api/v1/account-tables/{table_id}").json()["data"]["copy_path"]
        before = sha256(copy_path)
        response = client.post(
            f"/api/v1/requests/{parsed['request_id']}/commit", json={"table_id": table_id}
        )
        assert response.status_code == 409
        assert response.json()["code"] != 0
        # 恰好这一条阻断项进入 pending 清单（其他异常均为 P1/P2）
        assert len(response.json()["data"]["pending"]) == 1
        assert sha256(copy_path) == before
