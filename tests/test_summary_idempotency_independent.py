"""批次级幂等 —— QA **独立回归**（与实现方 `test_summary_idempotency.py` 并存）。

分层原则（team-lead 指令）：实现方测试 + 独立方测试两层，独立验证不依赖实现者自证。
本文件由 QA 独立编写，只断言 Spec §6.2 双键 / AC-08 的**对外可观测契约**，
不绑定任何具体实现（无论后端用「同 batch_id 覆盖旧 request」还是「汇总侧按 batch_id
去重」，都应满足）。除复现 QA 原始用例，另补实现方那份**缺失**的
「同日不同 biz_type 各自独立」，以及三条组合角度。

被钉住的 P0 缺陷：同一份文本重复解析时，`request_id` 因序号自增而每次不同，
旧实现让每次解析都作为独立记录进入当日汇总 → 金额 / 明细数 / 声明数随解析次数
线性放大（3 次 → ¥700×3）。
"""

from __future__ import annotations

from support import make_advance_text, make_doujia_text

DOUJIA_DATE = "2026-09-02"
ADVANCE_DATE = "2026-09-03"


def _parse(client, table_id: str, raw_text: str) -> dict:
    response = client.post(
        "/api/v1/requests/parse", json={"raw_text": raw_text, "table_id": table_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _summary(client, date_str: str) -> dict:
    response = client.get("/api/v1/summary", params={"date": date_str})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _biz(summary_data: dict, biz: str) -> dict:
    """取当日汇总中指定业务口径块（不存在则断言失败）。"""
    for block in summary_data["blocks"]:
        if block["biz_type"] == biz:
            return block
    raise AssertionError(f"汇总中无 {biz} 口径块：{summary_data['blocks']}")


class TestRepeatedParseStaysStable:
    def test_doujia_amount_count_declared_stable(self, client, table_id, doujia_text):
        """同一抖加文本重复解析：金额 / 明细数 / 声明数三口径必须纹丝不动。"""
        _parse(client, table_id, doujia_text)
        base = _biz(_summary(client, DOUJIA_DATE), "doujia")

        _parse(client, table_id, doujia_text)
        _parse(client, table_id, doujia_text)
        after = _biz(_summary(client, DOUJIA_DATE), "doujia")

        assert after["total_amount"] == base["total_amount"] == 700.0
        assert after["entry_count"] == base["entry_count"] == 4
        assert after["declared_count"] == base["declared_count"] == 7
        assert after["item_count"] == base["item_count"] == 7

    def test_advance_amount_count_stable(self, client, table_id, advance_text):
        """垫付同理：真值 5 笔明细合计 ¥2,250，重复解析不得放大。"""
        _parse(client, table_id, advance_text)
        base = _biz(_summary(client, ADVANCE_DATE), "advance")

        _parse(client, table_id, advance_text)
        _parse(client, table_id, advance_text)
        after = _biz(_summary(client, ADVANCE_DATE), "advance")

        assert after == base
        assert after["total_amount"] == 2250.0
        assert after["entry_count"] == 5


class TestBatchesStayIndependent:
    def test_distinct_dates_accumulate_separately(
        self, client, table_id, doujia_text, advance_text
    ):
        """不同日期 → 各自独立累计，不得过度去重压成一条。"""
        for _ in range(3):
            _parse(client, table_id, doujia_text)
            _parse(client, table_id, advance_text)

        day_dj = _summary(client, DOUJIA_DATE)
        day_adv = _summary(client, ADVANCE_DATE)

        assert _biz(day_dj, "doujia")["total_amount"] == 700.0
        assert _biz(day_dj, "advance")["entry_count"] == 0
        assert _biz(day_adv, "advance")["total_amount"] == 2250.0
        assert _biz(day_adv, "doujia")["entry_count"] == 0

    def test_same_day_two_biz_types_are_independent(self, client, table_id):
        """同日抖加与垫付是两个批次：各自去重、互不污染金额/明细数/声明数。

        这是实现方 `test_summary_idempotency.py` 未覆盖的一条。
        """
        day = "2026-09-05"
        doujia = make_doujia_text(
            [("初秋", 300, None)], total=300, declared_count=1, date_str=day
        )
        advance = make_advance_text(
            [("初秋", 950)], total=950, declared_count=1, date_str=day
        )
        for _ in range(2):
            _parse(client, table_id, doujia)
            _parse(client, table_id, advance)

        summary = _summary(client, day)
        blk_dj = _biz(summary, "doujia")
        blk_adv = _biz(summary, "advance")

        assert blk_dj["total_amount"] == 300.0
        assert blk_dj["entry_count"] == 1
        assert blk_dj["declared_count"] == 1
        assert blk_adv["total_amount"] == 950.0
        assert blk_adv["entry_count"] == 1
        assert blk_adv["declared_count"] == 1

    def test_interleaved_orders_dedup_per_batch_key(
        self, client, table_id, doujia_text, advance_text
    ):
        """交错提交：去重键必须是 (biz_type, 日期)，不能只按日期也不能按提交顺序。"""
        for _ in range(3):
            _parse(client, table_id, advance_text)
            _parse(client, table_id, doujia_text)
            _parse(client, table_id, doujia_text)

        assert _biz(_summary(client, DOUJIA_DATE), "doujia")["total_amount"] == 700.0
        assert _biz(_summary(client, ADVANCE_DATE), "advance")["total_amount"] == 2250.0


class TestSupersededAndReport:
    def test_superseded_old_request_id_still_reachable(self, client, table_id, doujia_text):
        """批次去重不得把历史 request_id 变成 404（审计 / 深链接可回溯）。"""
        first = _parse(client, table_id, doujia_text)
        _parse(client, table_id, doujia_text)
        _parse(client, table_id, doujia_text)

        response = client.get(f"/api/v1/requests/{first['request_id']}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["request_id"] == first["request_id"]
        assert data["batch_id"] == first["batch_id"]

    def test_report_amount_matches_summary(self, client, table_id, doujia_text):
        """汇报卡与汇总同源：不能出现「汇总修了、汇报没修」的错配。"""
        for _ in range(3):
            _parse(client, table_id, doujia_text)

        block = _biz(_summary(client, DOUJIA_DATE), "doujia")
        response = client.post("/api/v1/reports/daily", json={"date": DOUJIA_DATE})
        assert response.status_code == 201, response.text
        report = response.json()["data"]

        assert report["doujia_total"] == block["total_amount"] == 700.0
        assert "2,100" not in report["headline"]


class TestCombinationAngles:
    def test_repeat_parse_then_commit_writes_one_batch_only(self, client, table_id, doujia_text):
        """组合角度：解析 3 次后再写表，落行数必须等于「单次解析」结果（4 行），不是 12。"""
        latest = None
        for _ in range(3):
            latest = _parse(client, table_id, doujia_text)

        response = client.post(
            f"/api/v1/requests/{latest['request_id']}/commit", json={"table_id": table_id}
        )
        assert response.status_code == 200, response.text
        outcome = response.json()["data"]

        assert outcome["written_count"] == 4, f"重复解析后落行数异常：{outcome['written_count']}"
        assert outcome["skipped_count"] == 0
        assert sorted(w["row_ref"] for w in outcome["written"]) == ["2", "3", "4", "5"]

    def test_summary_biz_type_filter_matches_unfiltered_block(self, client, table_id, doujia_text):
        """查询参数 `biz_type` 过滤后的口径块，必须与不传参数时的同名块一致。"""
        for _ in range(3):
            _parse(client, table_id, doujia_text)

        unfiltered = _biz(_summary(client, DOUJIA_DATE), "doujia")
        response = client.get(
            "/api/v1/summary", params={"date": DOUJIA_DATE, "biz_type": "doujia"}
        )
        assert response.status_code == 200, response.text
        blocks = response.json()["data"]["blocks"]
        assert len(blocks) == 1, blocks

        assert blocks[0]["total_amount"] == unfiltered["total_amount"] == 700.0
        assert blocks[0]["entry_count"] == unfiltered["entry_count"] == 4
        assert blocks[0]["declared_count"] == unfiltered["declared_count"] == 7
