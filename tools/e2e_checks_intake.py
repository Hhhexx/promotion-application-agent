"""端到端验证前半程（链路「进」）：健康检查 → 登记表 → 解析 → 校验证据 → 闸门拦截 → 裁决收敛。

对应 Spec v1.0 §12 的步骤 3–9。只被 `tools/e2e_smoke.py` 调用。
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.e2e_harness import (
    ADVANCE,
    DOUJIA,
    SOURCE,
    Checker,
    Ctx,
    anomalies_of,
    by_code,
    data_of,
    one,
    p0_of,
    sha256,
)


def check_health(client, ck: Checker) -> None:
    ck.title("1. 健康检查")
    r = client.get("/health")
    ck.check("GET /health 返回 200", r.status_code == 200, str(r.status_code))
    ck.check("健康体 status=ok", (r.json() or {}).get("status") == "ok")

    r = client.get("/")
    ck.check("GET / 返回前端页面", r.status_code == 200 and "<html" in r.text.lower(), str(r.status_code))
    r = client.get("/docs")
    ck.check("GET /docs 返回接口文档", r.status_code == 200, str(r.status_code))


def check_register_table(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("2. 登记账号表（服务端复制副本，源表只读）")
    r = client.post("/api/v1/account-tables")
    ck.check("POST /account-tables 返回 201", r.status_code == 201, str(r.status_code))
    meta = data_of(r.json())
    ctx.table_id = meta.get("table_id") or ""
    ck.check("拿到 table_id", bool(ctx.table_id), ctx.table_id)
    ctx.copy_path = Path(meta.get("copy_path") or "")
    ck.check("副本文件已落盘", ctx.copy_path.exists(), str(ctx.copy_path))
    ck.check("副本 ≠ 源表路径", ctx.copy_path.resolve() != SOURCE.resolve())
    ck.check("副本被标记 is_test_copy", meta.get("is_test_copy") is True)
    ck.check("源表字节未被改动", sha256(SOURCE) == ctx.source_hash_before)


def check_doujia_parse(client, ck: Checker, ctx: Ctx) -> dict:
    ck.title("3. 解析抖加申请（期望 0 个 P0）")
    r = client.post(
        "/api/v1/requests/parse",
        json={"raw_text": DOUJIA.read_text(encoding="utf-8"), "table_id": ctx.table_id},
    )
    ck.check("POST /requests/parse 返回 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    payload = r.json()
    d = data_of(payload)
    ctx.dj_id = d.get("request_id") or ""
    ck.check("拿到 request_id", bool(ctx.dj_id), ctx.dj_id)
    ck.check("request_id 含业务与日期", "20260902" in ctx.dj_id and "doujia" in ctx.dj_id, ctx.dj_id)
    ck.check("抖加 P0 数量为 0", len(p0_of(payload)) == 0, json.dumps(p0_of(payload), ensure_ascii=False)[:200])

    summary = d.get("summary") or {}
    cross = d.get("cross_check") or {}
    ck.check("声明总额 700.00", summary.get("declared_total_exact") == "700.00", str(summary.get("declared_total_exact")))
    ck.check("明细行金额之和 = 700", cross.get("line_items_sum") == 700.0, str(cross.get("line_items_sum")))
    ck.check("合并同博主后 4 行明细", len(d.get("line_items") or []) == 4, str(len(d.get("line_items") or [])))
    ck.check(
        "拆笔数之和 7 与声明笔数一致",
        cross.get("split_count_sum") == cross.get("declared_count"),
        json.dumps(cross, ensure_ascii=False)[:160],
    )
    mismatch = by_code(payload, "CROSS_SOURCE_TOTAL_MISMATCH")
    ck.check(
        "跨源口径不一致降级为 P1（不阻断）",
        len(mismatch) >= 1 and all(a.get("severity") == "P1" and not a.get("blocking") for a in mismatch),
        f"{len(mismatch)} 条",
    )
    ck.check("表内抖加列合计 400（第三口径可见）", cross.get("sheet_column_sum") == 400.0, str(cross.get("sheet_column_sum")))
    ck.check("汇总口径明确不合并为一个数字", cross.get("line_items_sum") != cross.get("sheet_column_sum"))
    ck.check("批次状态为 READY", d.get("aggregate_state") == "READY", str(d.get("aggregate_state")))
    return d


def check_doujia_commit(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("4. 抖加批次写表（无 P0 应直接放行）")
    r = client.post(f"/api/v1/requests/{ctx.dj_id}/commit", json={"table_id": ctx.table_id})
    ck.check("写表返回 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    commit = data_of(r.json())
    ck.check("写入 4 行", commit.get("written_count") == 4, str(commit.get("written_count")))
    ck.check("跳过 0 行", commit.get("skipped_count") == 0, str(commit.get("skipped_count")))
    rows = [w.get("row_ref") for w in (commit.get("written") or [])]
    ck.check("落点行号为 2/3/4/5", sorted(rows) == ["2", "3", "4", "5"], str(rows))
    fields = one(commit.get("written") or [{}]).get("fields_written") or {}
    ck.check("写了抖加金额列", "doujia_amount" in fields, str(list(fields)))
    ck.check("写了抖加支付人列", "doujia_payer" in fields, str(list(fields)))
    ck.check("备注列写明来源批次", "来源=" in (fields.get("remark") or ""), str(fields.get("remark"))[:80])
    ck.check("报价列未被改写（只读）", "quote_price" not in fields, str(list(fields)))


def check_idempotent_replay(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("5. 幂等重放（同批次再写应全部 SKIPPED 且不改表）")
    before = sha256(ctx.copy_path)
    r = client.post(f"/api/v1/requests/{ctx.dj_id}/commit", json={"table_id": ctx.table_id})
    replay = data_of(r.json())
    ck.check("重放返回 200", r.status_code == 200, str(r.status_code))
    ck.check("重放写入 0 行", replay.get("written_count") == 0, str(replay.get("written_count")))
    ck.check("重放跳过 4 行", replay.get("skipped_count") == 4, str(replay.get("skipped_count")))
    ck.check(
        "跳过原因为 SKIPPED_ALREADY_WRITTEN",
        all(s.get("reason") == "SKIPPED_ALREADY_WRITTEN" for s in (replay.get("skipped") or [])),
        json.dumps(replay.get("skipped"), ensure_ascii=False)[:200],
    )
    ck.check("重放未改动副本字节", sha256(ctx.copy_path) == before)


def check_advance_parse(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("6. 解析垫付申请（期望 3 个 P0）")
    r = client.post(
        "/api/v1/requests/parse",
        json={"raw_text": ADVANCE.read_text(encoding="utf-8"), "table_id": ctx.table_id},
    )
    ck.check("POST /requests/parse 返回 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    payload = r.json()
    ctx.adv_data = data_of(payload)
    ctx.adv_id = ctx.adv_data.get("request_id") or ""
    p0s = p0_of(payload)
    ck.check("垫付 P0 数量为 3", len(p0s) == 3, f"实际 {len(p0s)}: {[a.get('code') for a in p0s]}")
    for code in ("COUNT_MISMATCH", "DATE_ORDER_INVALID", "MATCH_AMBIGUOUS"):
        ck.check(f"命中 P0 异常码 {code}", len(by_code(payload, code)) == 1, str(len(by_code(payload, code))))
    ck.check("P0 均标记 blocking", all(a.get("blocking") for a in p0s))
    ck.check("所有 P0 带 anomaly_id", all(a.get("anomaly_id") for a in p0s))
    ck.check("闸门状态为 NEEDS_REVIEW", ctx.adv_data.get("aggregate_state") == "NEEDS_REVIEW", str(ctx.adv_data.get("aggregate_state")))
    summary = ctx.adv_data.get("summary") or {}
    ck.check("声明垫付总额 2250.00", summary.get("declared_total_exact") == "2250.00", str(summary.get("declared_total_exact")))

    ck.title("6.1 异常必须给出可核查的证据与动作，而不是一句「有问题」")
    for anomaly in p0s:
        ck.check(
            f"{anomaly.get('code')} 带 evidence/action/suggestion",
            bool(anomaly.get("message"))
            and bool(anomaly.get("action_required") or anomaly.get("suggestion"))
            and bool(anomaly.get("rule_id"))
            and bool(anomaly.get("exc_id")),
            f"rule={anomaly.get('rule_id')} exc={anomaly.get('exc_id')}",
        )
    ck.check(
        "全部异常都带 PRD 编号（便于对照产品文档）",
        all(a.get("exc_id") for a in anomalies_of(payload)),
        str([a.get("exc_id") for a in anomalies_of(payload)]),
    )
    ck.check(
        "异常分级覆盖 P0/P1/P2 三档",
        {a.get("severity") for a in anomalies_of(payload)} == {"P0", "P1", "P2"},
        str(sorted({a.get("severity") for a in anomalies_of(payload)})),
    )
    ck.check(
        "台账里已有的问题（空行/日期格式/昵称脏/未接单）被标记为 P1/P2 不阻断",
        all(
            a.get("severity") in ("P1", "P2")
            for a in anomalies_of(payload)
            if a.get("code")
            in (
                "TABLE_EMPTY_ROW_SKIPPED",
                "DATE_FORMAT_INCONSISTENT",
                "NICKNAME_DIRTY",
                "DOUJIA_EXCEEDS_QUOTE",
                "UNACCEPTED_WITH_AMOUNT",
            )
        ),
    )


def check_gate_blocks(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("7. 未裁决时写表必须被 409 拦截（且零写入）")
    before = sha256(ctx.copy_path)
    r = client.post(f"/api/v1/requests/{ctx.adv_id}/commit", json={"table_id": ctx.table_id})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    ck.check("写表返回 409", r.status_code == 409, f"{r.status_code} {r.text[:200]}")
    ck.check("响应体 code 非 0", body.get("code") != 0, str(body.get("code")))
    ck.check(
        "响应体回传 pending 异常 id",
        len((body.get("data") or {}).get("pending") or []) == 3,
        json.dumps(body.get("data"), ensure_ascii=False)[:160],
    )
    ck.check("拦截时副本字节未变动", sha256(ctx.copy_path) == before)


def check_bad_resolutions(client, ck: Checker, ctx: Ctx) -> dict:
    ck.title("8. 错误裁决动作必须被拒绝（歧义不能用「确认无误」放行）")
    ambiguous = one(by_code(ctx.adv_data, "MATCH_AMBIGUOUS"))
    base = f"/api/v1/requests/{ctx.adv_id}/resolutions"
    r = client.post(base, json={"anomaly_id": ambiguous.get("anomaly_id"), "decision": "accept", "operator": "e2e"})
    ck.check("歧义 + accept 返回 409", r.status_code == 409, f"{r.status_code} {r.text[:160]}")
    r = client.post(base, json={"anomaly_id": ambiguous.get("anomaly_id"), "decision": "override", "operator": "e2e"})
    ck.check("override 缺修正值返回 4xx", 400 <= r.status_code < 500, f"{r.status_code} {r.text[:160]}")
    r = client.post(base, json={"anomaly_id": "anm_not_exist", "decision": "accept", "operator": "e2e"})
    ck.check("不存在的异常 id 返回 404", r.status_code == 404, str(r.status_code))
    return ambiguous


def check_resolution_convergence(client, ck: Checker, ctx: Ctx, ambiguous: dict) -> None:
    ck.title("9. 逐条人工裁决，闸门应逐步收敛")
    base = f"/api/v1/requests/{ctx.adv_id}/resolutions"
    r = client.post(
        base,
        json={
            "anomaly_id": one(by_code(ctx.adv_data, "COUNT_MISMATCH")).get("anomaly_id"),
            "decision": "accept",
            "operator": "e2e",
            "note": "已与发起人核对，以明细 5 条为准",
        },
    )
    ck.check("COUNT_MISMATCH 裁决返回 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        left = (data_of(r.json())).get("remaining_p0_count")
        ck.check("裁决后仍剩 2 个 P0", left == 2, str(left))

    r = client.post(
        base,
        json={
            "anomaly_id": one(by_code(ctx.adv_data, "DATE_ORDER_INVALID")).get("anomaly_id"),
            "decision": "accept",
            "operator": "e2e",
            "note": "确认打款日期栏为录入笔误",
        },
    )
    ck.check("DATE_ORDER_INVALID 裁决返回 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        left = (data_of(r.json())).get("remaining_p0_count")
        ck.check("裁决后仍剩 1 个 P0", left == 1, str(left))

    # 9.3 匹配歧义（葵花夫妇命中 2 行）→ 候选行取自条目的 match_result，而非刮异常文本
    item = next(
        (i for i in (ctx.adv_data.get("line_items") or []) if (i.get("match_result") or {}).get("level") == "AMBIGUOUS"),
        None,
    )
    ck.check("找到 AMBIGUOUS 明细行", item is not None)
    candidates = ((item or {}).get("match_result") or {}).get("candidates") or []
    ck.check("候选行 >= 2", len(candidates) >= 2, str([c.get("row_ref") for c in candidates]))
    ctx.pick = str(one(candidates).get("row_ref"))

    r = client.post(
        base,
        json={
            "anomaly_id": ambiguous.get("anomaly_id"),
            "decision": "override",
            "override_value": ctx.pick,
            "operator": "e2e",
            "note": f"人工核对后指定第 {ctx.pick} 行",
        },
    )
    ck.check("MATCH_AMBIGUOUS override 返回 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        outcome = data_of(r.json())
        ck.check("重跑校验已执行", outcome.get("revalidated") is True)
        left = outcome.get("remaining_p0_count") or 0
        ck.check(
            "钉死目标行后暴露出新的 P0（信息不丢失）",
            left == 1,
            f"remaining={left} still_blocking={outcome.get('still_blocking')}",
        )
    r = client.post(
        base,
        json={"anomaly_id": ambiguous.get("anomaly_id"), "decision": "override", "override_value": "99999", "operator": "e2e"},
    )
    ck.check("指定不存在的行号被拒绝", 400 <= r.status_code < 500, str(r.status_code))

    ck.title("9.4 把重跑暴露出的字段冲突也裁掉（否则应一直卡在 NEEDS_REVIEW）")
    r = client.get(f"/api/v1/requests/{ctx.adv_id}")
    surfaced = [a for a in ((data_of(r.json())).get("anomalies") or []) if a.get("severity") == "P0" and not a.get("resolved")]
    ck.check("暴露出的 P0 恰好 1 条", len(surfaced) == 1, json.dumps([a.get("code") for a in surfaced], ensure_ascii=False))
    conflict = one(surfaced)
    ck.check(
        "冲突异常写明「文本值 vs 台账值」两侧取值",
        bool(conflict.get("text_value")) and bool(conflict.get("sheet_value")),
        f"{conflict.get('text_value')} vs {conflict.get('sheet_value')}",
    )
    r = client.post(
        base,
        json={
            "anomaly_id": conflict.get("anomaly_id"),
            "decision": "accept",
            "operator": "e2e",
            "note": "台账第 7 行已有打款记录，以台账为准，本批次不改写",
        },
    )
    ck.check("冲突裁决返回 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    if r.status_code == 200:
        left = (data_of(r.json())).get("remaining_p0_count") or 0
        ck.check("剩余 P0 归零", left == 0, str(left))
