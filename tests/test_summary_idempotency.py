"""批次级幂等回归（Spec §6.2 双键设计 / AC-08）。

背景（P0 缺陷）：同一份申请文本被重复解析时，`request_id` 因序号自增而每次不同，
旧实现让每次解析都作为独立记录进入当日汇总，导致金额 / 明细数 / 声明数随解析次数
线性放大（解析 3 次 → ¥700×3）。修复采用**批次级幂等键** `batch_id = biz_type|日期`：
同批次只保留最新一条生效记录参与汇总，旧条目仍可查但不入账。

覆盖：
  1. 同批次抖加重复解析 → 汇总金额 / 明细数 / 声明数不变
  2. 同批次垫付重复解析 → 汇总金额 / 明细数不变
  3. 汇报卡（build_report 路径）与汇总同源，同样不放大
  4. 不同日期（不同 batch_id）→ 各自独立累计，**不过度去重**
  5. 被取代的旧 request_id 仍可通过 GET 取到（200，审计 / 深链接不 404）
"""

from __future__ import annotations

import pytest

from support import make_doujia_text, sha256

DOUJIA_DATE = "2026-09-02"
ADVANCE_DATE = "2026-09-03"
DOUJIA_TOTAL = 700.0
ADVANCE_TOTAL = 2250.0


def _parse(client, table_id: str, raw_text: str) -> dict:
    response = client.post(
        "/api/v1/requests/parse", json={"raw_text": raw_text, "table_id": table_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _block(client, date_str: str, biz: str) -> dict:
    response = client.get("/api/v1/summary", params={"date": date_str, "biz_type": biz})
    assert response.status_code == 200, response.text
    blocks = response.json()["data"]["blocks"]
    assert len(blocks) == 1, blocks
    return blocks[0]


class TestRepeatedParseDoesNotInflateSummary:
    def test_doujia_summary_is_stable_across_parses(self, client, table_id, doujia_text):
        first = _parse(client, table_id, doujia_text)
        first_block = _block(client, DOUJIA_DATE, "doujia")

        # 再解析两次（同批次）：request_id 必然不同，但汇总必须纹丝不动。
        second = _parse(client, table_id, doujia_text)
        third = _parse(client, table_id, doujia_text)
        assert len({first["request_id"], second["request_id"], third["request_id"]}) == 3
        assert {first["batch_id"], second["batch_id"], third["batch_id"]} == {"doujia|" + DOUJIA_DATE}

        after_block = _block(client, DOUJIA_DATE, "doujia")
        assert after_block == first_block
        assert after_block["total_amount"] == DOUJIA_TOTAL
        assert after_block["line_items_sum"] == DOUJIA_TOTAL
        assert after_block["declared_total_amount"] == DOUJIA_TOTAL
        assert after_block["entry_count"] == 4
        assert after_block["declared_count"] == 7
        assert after_block["item_count"] == 7

    def test_advance_summary_is_stable_across_parses(self, client, table_id, advance_text):
        _parse(client, table_id, advance_text)
        first_block = _block(client, ADVANCE_DATE, "advance")

        _parse(client, table_id, advance_text)
        _parse(client, table_id, advance_text)
        after_block = _block(client, ADVANCE_DATE, "advance")

        assert after_block == first_block
        assert after_block["total_amount"] == ADVANCE_TOTAL
        assert after_block["line_items_sum"] == ADVANCE_TOTAL
        assert after_block["entry_count"] == 5

    def test_report_path_shares_dedup_with_summary(self, client, table_id, doujia_text):
        for _ in range(3):
            _parse(client, table_id, doujia_text)

        response = client.post("/api/v1/reports/daily", json={"date": DOUJIA_DATE})
        assert response.status_code == 201, response.text
        report = response.json()["data"]

        assert report["doujia_total"] == DOUJIA_TOTAL
        # 已确认 + 待确认 是「明细逐笔求和」，同样不得随解析次数放大。
        assert pytest.approx(report["confirmed_amount"] + report["pending_amount"], abs=0.01) == DOUJIA_TOTAL


class TestDifferentBatchesStayIndependent:
    def test_distinct_dates_accumulate_separately(self, client, table_id):
        # 同一天重复两次（应去重），另一天同样重复两次（应各自独立保留）。
        day_a = make_doujia_text(
            [("初秋", 300, 3), ("艳红", 200, 2)], total=500, declared_count=5, declared_merged=2,
            date_str="2026-09-10",
        )
        day_b = make_doujia_text(
            [("高高", 100, None), ("葵花夫妇", 150, None)], total=250, declared_count=2, declared_merged=2,
            date_str="2026-09-11",
        )
        for _ in range(2):
            _parse(client, table_id, day_a)
            _parse(client, table_id, day_b)

        block_a = _block(client, "2026-09-10", "doujia")
        block_b = _block(client, "2026-09-11", "doujia")

        # 各日期独立：金额分别是 500 / 250，而不是 1000 / 500（过度去重也不允许）。
        assert block_a["total_amount"] == 500.0
        assert block_a["entry_count"] == 2
        assert block_b["total_amount"] == 250.0
        assert block_b["entry_count"] == 2


class TestSupersededRequestRemainsRetrievable:
    def test_old_request_id_still_returns_200(self, client, table_id, advance_text):
        old = _parse(client, table_id, advance_text)
        new = _parse(client, table_id, advance_text)
        assert old["request_id"] != new["request_id"]

        response = client.get(f"/api/v1/requests/{old['request_id']}")
        assert response.status_code == 200, response.text
        assert response.json()["data"]["request_id"] == old["request_id"]

    def test_superseded_request_excluded_from_summary(self, client, table_id, advance_text):
        old = _parse(client, table_id, advance_text)
        new = _parse(client, table_id, advance_text)

        # 生效条目是新解析的（旧条目被取代），但汇总只算一份。
        current = _block(client, ADVANCE_DATE, "advance")
        assert current["entry_count"] == 5
        assert current["total_amount"] == ADVANCE_TOTAL
        assert old["request_id"] != new["request_id"]


class TestSupersedeKeepsWriteIdempotent:
    """批次被取代后，写表仍必须靠 dedup_key 台账幂等 —— 不得二次落行。"""

    def test_reparse_then_commit_skips_already_written(self, client, table_id, doujia_text):
        copy_path = client.get(f"/api/v1/account-tables/{table_id}").json()["data"]["copy_path"]

        first = _parse(client, table_id, doujia_text)
        outcome = client.post(
            f"/api/v1/requests/{first['request_id']}/commit", json={"table_id": table_id}
        ).json()["data"]
        assert outcome["written_count"] == 4
        hash_after_write = sha256(copy_path)

        # 同批次重解析 → 取代旧条目；再写表：全部命中台账，零写入。
        second = _parse(client, table_id, doujia_text)
        assert second["request_id"] != first["request_id"]
        replay = client.post(
            f"/api/v1/requests/{second['request_id']}/commit", json={"table_id": table_id}
        ).json()["data"]

        assert replay["written_count"] == 0
        assert replay["skipped_count"] == 4
        assert {s["reason"] for s in replay["skipped"]} == {"SKIPPED_ALREADY_WRITTEN"}
        assert sha256(copy_path) == hash_after_write
