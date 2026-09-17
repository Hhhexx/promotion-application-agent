"""人工确认闸门测试（架构 §4.2 / §4.3）。

闸门不变量：**任何写表之前必须无未裁决 P0**。本文件的重点是那条曾经出过 bug
的路径：歧义匹配被 `override` 钉死目标行后，重跑字段校验暴露的新 P0 必须
**由新异常单独承载阻断**，而被 override 的那条异常必须标记为已裁决 —— 否则
「解完新异常后旧异常仍然 pending」+「重复 override 不断产出同名新异常」会
把操作员锁进死循环。
"""

from __future__ import annotations

import pytest

from support import anomaly_by_code, approve_advance, p0_of, sha256


@pytest.fixture
def adv(client, table_id, advance_text) -> dict:
    response = client.post(
        "/api/v1/requests/parse", json={"raw_text": advance_text, "table_id": table_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _resolve(client, request_id: str, payload: dict) -> tuple[int, dict]:
    response = client.post(f"/api/v1/requests/{request_id}/resolutions", json=payload)
    return response.status_code, response.json()


class TestGateInvariants:
    def test_batch_with_open_p0_is_needs_review(self, adv):
        assert adv["aggregate_state"] == "NEEDS_REVIEW"
        assert len(p0_of(adv)) == 3
        assert all(a["blocking"] for a in p0_of(adv))
        assert all(a["anomaly_id"] for a in p0_of(adv))
        assert {a["code"] for a in p0_of(adv)} == {
            "MATCH_AMBIGUOUS",
            "COUNT_MISMATCH",
            "DATE_ORDER_INVALID",
        }

    def test_commit_blocked_with_409_and_no_write(self, client, adv, table_id):
        copy_path = client.get(f"/api/v1/account-tables/{table_id}").json()["data"]["copy_path"]
        before = sha256(copy_path)
        response = client.post(
            f"/api/v1/requests/{adv['request_id']}/commit", json={"table_id": table_id}
        )
        assert response.status_code == 409
        body = response.json()
        assert body["code"] != 0
        assert len(body["data"]["pending"]) == 3
        assert sha256(copy_path) == before  # 抛错前不打开工作簿 → 零写入


class TestRejectedDecisions:
    def test_ambiguous_cannot_be_accepted(self, client, adv):
        status, body = _resolve(
            client,
            adv["request_id"],
            {
                "anomaly_id": anomaly_by_code(adv, "MATCH_AMBIGUOUS")["anomaly_id"],
                "decision": "accept",
                "operator": "qa",
            },
        )
        assert status == 409
        assert body["code"] == 1003
        assert body["data"]["pending"] == [anomaly_by_code(adv, "MATCH_AMBIGUOUS")["anomaly_id"]]

    def test_override_without_value_is_rejected(self, client, adv):
        status, body = _resolve(
            client,
            adv["request_id"],
            {
                "anomaly_id": anomaly_by_code(adv, "MATCH_AMBIGUOUS")["anomaly_id"],
                "decision": "override",
                "operator": "qa",
            },
        )
        assert status == 400
        assert body["code"] == 1001

    def test_override_with_blank_value_is_rejected(self, client, adv):
        status, _ = _resolve(
            client,
            adv["request_id"],
            {
                "anomaly_id": anomaly_by_code(adv, "MATCH_AMBIGUOUS")["anomaly_id"],
                "decision": "override",
                "override_value": "   ",
                "operator": "qa",
            },
        )
        assert status == 400

    def test_override_to_unknown_row_is_rejected(self, client, adv):
        status, _ = _resolve(
            client,
            adv["request_id"],
            {
                "anomaly_id": anomaly_by_code(adv, "MATCH_AMBIGUOUS")["anomaly_id"],
                "decision": "override",
                "override_value": "99999",
                "operator": "qa",
            },
        )
        assert 400 <= status < 500

    def test_unknown_anomaly_id_is_404(self, client, adv):
        status, body = _resolve(
            client,
            adv["request_id"],
            {"anomaly_id": "anm_not_exist", "decision": "accept", "operator": "qa"},
        )
        assert status == 404
        assert body["code"] == 1002


class TestAmbiguityOverrideRegression:
    """回归：override 钉死目标行后，被 override 的异常必须 resolved，新 P0 单独承载。"""

    def _resolve_count_and_date(self, client, adv) -> str:
        request_id = adv["request_id"]
        for code, note in (("COUNT_MISMATCH", "以明细为准"), ("DATE_ORDER_INVALID", "确认为录入笔误")):
            status, _ = _resolve(
                client,
                request_id,
                {
                    "anomaly_id": anomaly_by_code(adv, code)["anomaly_id"],
                    "decision": "accept",
                    "operator": "qa",
                    "note": note,
                },
            )
            assert status == 200
        return request_id

    def test_override_pins_target_and_isolates_new_blocker(self, client, adv):
        request_id = self._resolve_count_and_date(client, adv)
        ambiguous = anomaly_by_code(adv, "MATCH_AMBIGUOUS")
        # 解析顺序是确定的：歧义异常是流水线上的第一条
        assert ambiguous["anomaly_id"] == "anm_01"

        candidates = next(
            i for i in adv["line_items"] if i["match_result"]["level"] == "AMBIGUOUS"
        )["match_result"]["candidates"]
        assert sorted(c["row_ref"] for c in candidates) == ["7", "9"]
        pick = str(candidates[0]["row_ref"])

        status, body = _resolve(
            client,
            request_id,
            {
                "anomaly_id": ambiguous["anomaly_id"],
                "decision": "override",
                "override_value": pick,
                "operator": "qa",
                "note": f"人工核对后指定第 {pick} 行",
            },
        )
        assert status == 200
        outcome = body["data"]
        assert outcome["revalidated"] is True
        assert outcome["remaining_p0_count"] == 1
        assert outcome["still_blocking"] is True

        after = client.get(f"/api/v1/requests/{request_id}").json()["data"]
        anm01 = next(a for a in after["anomalies"] if a["anomaly_id"] == "anm_01")
        # 被 override 的那条异常必须已裁决，不能继续挂着 pending
        assert anm01["resolved"] is True
        assert anm01["resolution"]["decision"] == "override"
        assert anm01["resolution"]["final_value"] == pick

        conflicts = [a for a in after["anomalies"] if a["code"] == "CROSS_SOURCE_FIELD_CONFLICT"]
        assert len(conflicts) == 1
        conflict = conflicts[0]
        assert conflict["blocking"] is True
        assert conflict["severity"] == "P0"
        assert conflict["text_value"] == "林老师"
        assert conflict["sheet_value"] == "木木老师"
        assert conflict["sheet_row_ref"] == pick
        assert conflict["resolved"] is False  # 新异常单独承载阻断
        assert conflict["anomaly_id"] != ambiguous["anomaly_id"]
        assert after["aggregate_state"] == "NEEDS_REVIEW"

    def test_repeated_override_does_not_emit_duplicate_conflict(self, client, adv):
        request_id = self._resolve_count_and_date(client, adv)
        ambiguous = anomaly_by_code(adv, "MATCH_AMBIGUOUS")
        pick = str(
            next(i for i in adv["line_items"] if i["match_result"]["level"] == "AMBIGUOUS")[
                "match_result"
            ]["candidates"][0]["row_ref"]
        )
        for _ in range(2):
            status, _ = _resolve(
                client,
                request_id,
                {
                    "anomaly_id": ambiguous["anomaly_id"],
                    "decision": "override",
                    "override_value": pick,
                    "operator": "qa",
                },
            )
            assert status == 200

        after = client.get(f"/api/v1/requests/{request_id}").json()["data"]
        conflicts = [a for a in after["anomalies"] if a["code"] == "CROSS_SOURCE_FIELD_CONFLICT"]
        # 幂等：重复 override 不会不断产出同名新异常
        assert len(conflicts) == 1
        assert len([a for a in after["anomalies"] if a["severity"] == "P0" and not a["resolved"]]) == 1

    def test_gate_converges_to_ready_after_all_p0_resolved(self, client, adv):
        request_id, _ = approve_advance(client, adv)
        final = client.get(f"/api/v1/requests/{request_id}").json()["data"]
        assert final["aggregate_state"] == "READY"
        assert all(a["resolved"] for a in final["anomalies"] if a["severity"] == "P0")


class TestIgnoreDecision:
    def test_ignore_puts_batch_into_blocked_and_still_forbids_write(self, client, adv, table_id):
        request_id = adv["request_id"]
        status, body = _resolve(
            client,
            request_id,
            {
                "anomaly_id": anomaly_by_code(adv, "COUNT_MISMATCH")["anomaly_id"],
                "decision": "ignore",
                "operator": "qa",
                "note": "退回发起人补充缺失笔数",
            },
        )
        assert status == 200
        assert body["data"]["item_state"] == "BLOCKED"

        after = client.get(f"/api/v1/requests/{request_id}").json()["data"]
        assert after["aggregate_state"] == "BLOCKED"
        assert all(item["state"] == "BLOCKED" for item in after["line_items"])

        commit = client.post(f"/api/v1/requests/{request_id}/commit", json={"table_id": table_id})
        assert commit.status_code == 409
