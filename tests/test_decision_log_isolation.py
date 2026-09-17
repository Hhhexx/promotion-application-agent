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
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.orchestrator import pipeline
from app.repositories import decision_repo
from app.repositories.memory_store import STORE
from support import anomaly_by_code

REPO_ROOT = Path(__file__).resolve().parents[1]

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


# --------------------------------------------------------------------------- #
# 对抗性验证：隔离不能修过头 / 落盘档案不能改坏 / 过滤必须精确匹配
# --------------------------------------------------------------------------- #
def _parse(client, table_id: str, raw_text: str) -> dict:
    response = client.post(
        "/api/v1/requests/parse", json={"raw_text": raw_text, "table_id": table_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _export_json(client, request_id: str) -> list:
    response = client.get(
        f"/api/v1/requests/{request_id}/decisions", params={"format": "json"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _resolve(client, request_id: str, anomaly_id: str):
    return client.post(
        f"/api/v1/requests/{request_id}/resolutions",
        json={"anomaly_id": anomaly_id, "decision": "accept", "operator": "qa", "note": "对抗验证"},
    )


class TestIsolationIsNotOverzealous:
    """方向 2/3：隔离不能把本会话记录也滤掉，也不能缓存截断。"""

    def test_all_session_decisions_remain_visible(self, client, table_id, advance_text):
        parsed = _parse(client, table_id, advance_text)
        request_id = parsed["request_id"]
        _seed_stale_entry(request_id)  # 制造同名陈旧记录

        live_ids = []
        for code in ("COUNT_MISMATCH", "DATE_ORDER_INVALID"):
            anomaly = anomaly_by_code(parsed, code)
            assert _resolve(client, request_id, anomaly["anomaly_id"]).status_code == 200
            live_ids.append(anomaly["anomaly_id"])

        seen = {e["anomaly_id"] for e in _export_json(client, request_id)}
        assert set(live_ids) <= seen, f"本会话裁决被误过滤：seen={seen} want>={live_ids}"
        assert STALE_ANOMALY_ID not in seen, f"陈旧记录又回流：{seen}"

    def test_export_grows_as_decisions_appended(self, client, table_id, advance_text):
        parsed = _parse(client, table_id, advance_text)
        request_id = parsed["request_id"]

        first = anomaly_by_code(parsed, "COUNT_MISMATCH")["anomaly_id"]
        assert _resolve(client, request_id, first).status_code == 200
        n_first = len(_export_json(client, request_id))

        second = anomaly_by_code(parsed, "DATE_ORDER_INVALID")["anomaly_id"]
        assert _resolve(client, request_id, second).status_code == 200
        n_second = len(_export_json(client, request_id))

        assert n_second == n_first + 1, f"导出未随裁决增长（疑似缓存截断）：{n_first} -> {n_second}"

    def test_prefix_similar_request_ids_do_not_leak(self, client, table_id):
        """方向 6：过滤是精确匹配而非前缀匹配（..._01 vs ..._01_c15 / ..._01x）。"""
        STORE.decision_log.extend(
            [
                {"request_id": "req_x_01", "anomaly_id": "am_exact"},
                {"request_id": "req_x_01_c15", "anomaly_id": "am_prefix"},
                {"request_id": "req_x_01x", "anomaly_id": "am_suffix"},
            ]
        )
        got = pipeline.list_decisions("req_x_01")
        assert [e["anomaly_id"] for e in got] == ["am_exact"], got


_SESSION_SCRIPT = '''
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

text = Path(sys.argv[1]).read_text(encoding="utf-8")
with TestClient(app) as c:
    tid = c.post("/api/v1/account-tables").json()["data"]["table_id"]
    parsed = c.post("/api/v1/requests/parse",
                    json={"raw_text": text, "table_id": tid}).json()["data"]
    rid = parsed["request_id"]
    for code in ("COUNT_MISMATCH", "DATE_ORDER_INVALID"):
        a = next(x for x in parsed["anomalies"] if x["code"] == code)
        r = c.post(f"/api/v1/requests/{rid}/resolutions",
                   json={"anomaly_id": a["anomaly_id"], "decision": "accept", "operator": "qa"})
        assert r.status_code == 200, r.text
print("RID=" + rid)
'''


class TestDiskArchiveAcrossSessions:
    """方向 5：落盘 JSONL 仍是 append-only 全量档案（带 session_id），不被隔离修复改坏。"""

    def test_jsonl_is_append_only_full_archive_with_session_id(self, workdir, advance_text):
        sample = workdir / "advance.txt"
        sample.write_text(advance_text, encoding="utf-8")
        runner = workdir / "session_runner.py"
        runner.write_text(_SESSION_SCRIPT, encoding="utf-8")
        data_dir = workdir / "session-data"
        env = {**os.environ, "MST_DATA_DIR": str(data_dir), "PYTHONPATH": str(REPO_ROOT)}

        request_ids = []
        for _ in range(2):  # 两个独立进程 = 两个会话
            result = subprocess.run(
                [sys.executable, str(runner), str(sample)],
                cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
            )
            assert result.returncode == 0, result.stderr
            rid_lines = [ln for ln in result.stdout.splitlines() if ln.startswith("RID=")]
            assert rid_lines, f"子进程未输出 request_id：{result.stdout!r}\n{result.stderr!r}"
            request_ids.append(rid_lines[-1][len("RID="):])

        log_path = data_dir / "decisions" / "decisions.jsonl"
        records = [
            json.loads(ln)
            for ln in log_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]

        assert len(records) >= 4, f"落盘档案条数不足（append-only 被破坏）：{len(records)}"
        session_ids = {r.get("session_id") for r in records}
        assert None not in session_ids, f"落盘记录缺 session_id：{session_ids}"
        assert len(session_ids) >= 2, f"两会话 session_id 未区分：{session_ids}"

        assert request_ids[0] == request_ids[1], f"两会话未撞号，测试前提不成立：{request_ids}"
        same_rid = [r for r in records if r["request_id"] == request_ids[0]]
        assert len(same_rid) >= 4, f"同名 request_id 的跨会话记录被丢弃：{len(same_rid)}"
