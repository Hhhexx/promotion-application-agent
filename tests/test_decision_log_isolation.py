"""裁决日志跨会话隔离回归（F-12 审计留痕）。

**被钉住的缺陷（P1）**：`requests.export_decisions` 用 `read_entries()` **读落盘
JSONL**（append-only，从不清理）再按 `request_id` 过滤；而 `request_id` 里的自增序号
`next_seq('req')` 在进程重启后归零 → **新会话的 request 会撞上上一会话的同名
request_id**，把历史陈旧记录混进本次导出（实测：本会话 2 条 → 导出 5 行）。

导出应取**当前会话口径**（内存态），JSONL 落盘用于长期审计、不应回流到接口。
本文件以「预置陈旧记录」模拟上一会话残留，断言导出**不含陈旧记录、含本会话记录**，
并锁定 CSV 表头 11 列顺序（对外契约）。
"""

from __future__ import annotations

import csv
import io

import pytest

from app.repositories import decision_repo
from support import anomaly_by_code

#: CSV 导出锁定契约（顺序即列序，不得随意增删/换位）。
LOCKED_CSV_FIELDS = [
    "ts",
    "request_id",
    "anomaly_id",
    "rule_id",
    "code",
    "severity",
    "action",
    "original_value",
    "final_value",
    "operator",
    "reason",
]

#: 模拟上一会话遗留、且 request_id 与本会话撞号的陈旧记录。
STALE_ANOMALY_ID = "anm_prev_session_01"


def _seed_stale_entry(request_id: str) -> None:
    """把一条陈旧记录写进落盘日志（模拟上一会话残留）。"""
    decision_repo.append_entry(
        {
            "ts": "2000-01-01T00:00:00+00:00",
            "request_id": request_id,
            "anomaly_id": STALE_ANOMALY_ID,
            "rule_id": "cross.count",
            "code": "COUNT_MISMATCH",
            "severity": "P0",
            "action": "accept",
            "original_value": "5",
            "final_value": None,
            "operator": "prev-session",
            "reason": "line:1|上一会话遗留（不应出现在本会话导出中）",
        }
    )


@pytest.fixture
def resolved_request(client, table_id, advance_text) -> tuple[str, str]:
    """跑一条真实裁决，返回 (request_id, 本会话发生的 anomaly_id)。"""
    parsed = client.post(
        "/api/v1/requests/parse", json={"raw_text": advance_text, "table_id": table_id}
    ).json()["data"]
    request_id = parsed["request_id"]

    # 先预置陈旧记录，制造「同 request_id 撞号」场景。
    _seed_stale_entry(request_id)

    anomaly = anomaly_by_code(parsed, "COUNT_MISMATCH")
    response = client.post(
        f"/api/v1/requests/{request_id}/resolutions",
        json={
            "anomaly_id": anomaly["anomaly_id"],
            "decision": "accept",
            "operator": "qa",
            "note": "以明细为准",
        },
    )
    assert response.status_code == 200, response.text
    return request_id, anomaly["anomaly_id"]


class TestDecisionLogSessionIsolation:
    def test_json_export_excludes_previous_session_entries(self, client, resolved_request):
        request_id, live_anomaly_id = resolved_request

        response = client.get(
            f"/api/v1/requests/{request_id}/decisions", params={"format": "json"}
        )
        assert response.status_code == 200, response.text
        entries = response.json()

        anomaly_ids = {e["anomaly_id"] for e in entries}
        assert STALE_ANOMALY_ID not in anomaly_ids, f"陈旧记录回流：{anomaly_ids}"
        assert live_anomaly_id in anomaly_ids, f"本会话记录缺失：{anomaly_ids}"
        assert all(e["request_id"] == request_id for e in entries)

    def test_csv_export_excludes_previous_session_entries(self, client, resolved_request):
        request_id, live_anomaly_id = resolved_request

        response = client.get(
            f"/api/v1/requests/{request_id}/decisions", params={"format": "csv"}
        )
        assert response.status_code == 200, response.text
        text = response.text

        assert STALE_ANOMALY_ID not in text, "陈旧记录混进 CSV 导出"
        assert live_anomaly_id in text, "本会话记录未出现在 CSV 导出"

    def test_csv_header_is_locked_eleven_columns(self, client, resolved_request):
        request_id, _ = resolved_request
        response = client.get(
            f"/api/v1/requests/{request_id}/decisions", params={"format": "csv"}
        )
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == LOCKED_CSV_FIELDS, f"CSV 表头契约被破坏：{rows[0]}"

    def test_stale_entry_does_not_leak_across_request_ids(self, client, resolved_request):
        """另一 request_id 的陈旧记录同样不应串进本 request 的导出。"""
        request_id, _ = resolved_request
        decision_repo.append_entry(
            {
                "ts": "2000-01-01T00:00:00+00:00",
                "request_id": "req_19990101_doujia_01",
                "anomaly_id": "anm_other_request_01",
                "rule_id": "cross.count",
                "code": "COUNT_MISMATCH",
                "severity": "P0",
                "action": "accept",
                "original_value": "1",
                "final_value": None,
                "operator": "prev-session",
                "reason": "其它 request",
            }
        )
        response = client.get(
            f"/api/v1/requests/{request_id}/decisions", params={"format": "json"}
        )
        anomaly_ids = {e["anomaly_id"] for e in response.json()}
        assert "anm_other_request_01" not in anomaly_ids
