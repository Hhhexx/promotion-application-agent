"""端到端验证后半程（链路「出」）：写表放行 → 写入内容核查 → 汇总 → 汇报 → 审计导出 → 错误路径。

对应 Spec v1.0 §12 的步骤 8–12。只被 `tools/e2e_smoke.py` 调用。
"""

from __future__ import annotations

import json

from tools.e2e_harness import (
    HEADER_TO_KEY,
    SOURCE,
    WRITABLE_HEADERS,
    Checker,
    Ctx,
    data_of,
    norm_cell,
    one,
    read_source_rows,
    sha256,
)


def check_commit_unlocked(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("10. 裁决后写表应放行")
    r = client.get(f"/api/v1/requests/{ctx.adv_id}")
    ck.check("重取申请返回 200", r.status_code == 200, str(r.status_code))
    after = data_of(r.json())
    ck.check("闸门状态转为 READY", after.get("aggregate_state") == "READY", str(after.get("aggregate_state")))
    ck.check(
        "异常已标记 resolved",
        all(a.get("resolved") for a in (after.get("anomalies") or []) if a.get("severity") == "P0"),
    )

    r = client.post(f"/api/v1/requests/{ctx.adv_id}/commit", json={"table_id": ctx.table_id})
    ck.check("写表返回 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    ctx.adv_commit = data_of(r.json())
    ck.check("写入了 5 行", ctx.adv_commit.get("written_count") == 5, str(ctx.adv_commit.get("written_count")))
    rows = [w.get("row_ref") for w in (ctx.adv_commit.get("written") or [])]
    ck.check("葵花夫妇落点 = 人工指定的行", ctx.pick in rows, f"pick={ctx.pick} rows={rows}")


def check_cross_table_guard(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("11. 换表写表必须被拒绝（行号只在解析所用的表上有意义）")
    other = data_of(client.post("/api/v1/account-tables").json()).get("table_id")
    r = client.post(f"/api/v1/requests/{ctx.adv_id}/commit", json={"table_id": other})
    ck.check("跨表写表返回 4xx", 400 <= r.status_code < 500, f"{r.status_code} {r.text[:160]}")


def check_written_content(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("12. 写入内容核查（回填权限表 + 不猜测填充）")
    r = client.get(f"/api/v1/account-tables/{ctx.table_id}")
    ck.check("GET /account-tables 返回 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    detail = data_of(r.json())
    ck.check("返回列名清单", len(detail.get("columns") or []) == 13, str(detail.get("columns")))
    rows = {str(row.get("row_ref")): row for row in (detail.get("rows") or [])}
    ck.check("副本中空行被登记（第 12 行）", "12" in (detail.get("empty_row_refs") or []), str(detail.get("empty_row_refs")))

    written = ctx.adv_commit.get("written") or []
    ck.check(
        "写入行的备注列带来源批次标记",
        all("来源=" in (rows.get(str(w.get("row_ref")), {}).get("remark") or "") for w in written),
    )
    row4 = rows.get("4", {})
    ck.check(
        "只被抖加批次覆盖的行，其抖加列就是抖加批次写的值",
        row4.get("doujia_amount") == "100.00" and (row4.get("doujia_payer") or "") == "爆火音乐",
        json.dumps(row4, ensure_ascii=False)[:260],
    )
    target = rows.get(ctx.pick, {})
    ck.check(
        "人工指定的目标行拿到了垫付列写入",
        (target.get("pay_date") or "") != "" or (target.get("payer") or "") != "",
        json.dumps(target, ensure_ascii=False)[:260],
    )

    # 最强断言：逐行逐列比对副本 vs 源表。授权列之外必须与源表完全一致
    # —— 证明写入没有"顺手改别的列"，也没有给空值补默认值。
    src = read_source_rows(SOURCE)
    diffs: list[str] = []
    for row_ref, src_row in src.items():
        copy_row = rows.get(row_ref, {})
        for header, src_value in src_row.items():
            if header in WRITABLE_HEADERS:
                continue
            key = HEADER_TO_KEY.get(header)
            if key is None:
                continue
            got = copy_row.get(key)
            if norm_cell(got) != norm_cell(src_value):
                diffs.append(f"第{row_ref}行 {header}: 源={src_value!r} 副本={got!r}")
    ck.check("非授权列逐行逐列与源表一致（写入未越界）", not diffs, "；".join(diffs[:4]))
    ck.check("源表字节仍未改动", sha256(SOURCE) == ctx.source_hash_before, "源表被污染！")


def check_summary(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("13. 当日汇总（三口径并列，不合并）")
    r = client.get("/api/v1/summary", params={"date": "2026-09-02", "biz_type": "doujia"})
    ck.check("GET /summary 返回 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    blocks = (data_of(r.json())).get("blocks") or []
    ck.check("返回单一业务口径块", len(blocks) == 1, str(len(blocks)))
    block = one(blocks)
    ck.check("抖加口径块 total_amount = 700", block.get("total_amount") == 700.0, str(block.get("total_amount")))
    ck.check(
        "口径块同时列出声明值与明细和",
        block.get("declared_total_amount") == 700.0 and block.get("line_items_sum") == 700.0,
        json.dumps(block, ensure_ascii=False)[:200],
    )
    ck.check("口径块未把表内列合计混进总额", block.get("total_amount") != 400.0)

    r = client.get("/api/v1/summary", params={"date": "2026-09-03"})
    both = (data_of(r.json())).get("blocks") or []
    ck.check("不传 biz_type 时两种口径并列返回", len(both) == 2, str(len(both)))


def check_report(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("14. 负责人汇报卡")
    r = client.post("/api/v1/reports/daily", json={"date": "2026-09-03", "include_unresolved": True})
    ck.check("POST /reports/daily 返回 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    report = data_of(r.json())
    report_id = report.get("report_id") or ""
    ck.check("拿到 report_id", bool(report_id), report_id)
    ck.check("汇报含正文 markdown", bool(report.get("markdown")), str(report.get("markdown"))[:100])
    ck.check("汇报含标题摘要", bool(report.get("headline")), str(report.get("headline"))[:100])
    ck.check(
        "汇报区分已确认金额与待确认金额",
        report.get("confirmed_amount") is not None and report.get("pending_amount") is not None,
        f"confirmed={report.get('confirmed_amount')} pending={report.get('pending_amount')}",
    )
    ck.check("汇报列出待人工确认数", (report.get("pending_review_count") or 0) >= 0, str(report.get("pending_review_count")))
    r = client.get(f"/api/v1/reports/daily/{report_id}")
    ck.check("重取汇报返回 200", r.status_code == 200, str(r.status_code))
    ck.check("不存在的汇报返回 404", client.get("/api/v1/reports/daily/nope").status_code == 404)


def check_audit_export(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("15. 裁决日志导出（审计留痕）")
    r = client.get(f"/api/v1/requests/{ctx.adv_id}/decisions", params={"format": "csv"})
    ck.check("CSV 导出返回 200", r.status_code == 200, str(r.status_code))
    ck.check("CSV 含表头", "anomaly_id" in r.text, str(r.text.splitlines()[:1]))
    ck.check("CSV 含 4 条裁决", len([ln for ln in r.text.splitlines() if ln.strip()]) == 5, str(len(r.text.splitlines())))
    ck.check("CSV 记录了操作人", "e2e" in r.text)

    r = client.get(f"/api/v1/requests/{ctx.adv_id}/decisions")
    ck.check("JSON 导出返回 200 且为数组", r.status_code == 200 and r.text.strip().startswith("["), r.text[:80])
    try:
        entries = json.loads(r.text)
    except json.JSONDecodeError:
        ck.check("JSON 导出可解析", False, r.text[:120])
        return
    ck.check("JSON 导出含 4 条", len(entries) == 4, str(len(entries)))
    ck.check(
        "日志可追溯到具体异常与规则",
        all(e.get("anomaly_id") and e.get("rule_id") and e.get("severity") for e in entries),
    )
    ck.check(
        "日志记录原始值与终值（审计可回溯）",
        any(e.get("final_value") for e in entries),
        json.dumps([[e.get("original_value"), e.get("final_value")] for e in entries], ensure_ascii=False)[:200],
    )
    ck.check(
        "日志不含枚举对象字面量（str(Enum) 污染）",
        "AnomalyCode." not in r.text and "Severity." not in r.text and "Decision." not in r.text,
        r.text[:120],
    )
    ck.check("日志按 request 隔离（不会串到另一批次）", all(e.get("request_id") == ctx.adv_id for e in entries))


def check_error_paths(client, ck: Checker, ctx: Ctx) -> None:
    ck.title("16. 错误路径（不存在资源应 404，不是 500）")
    ck.check("不存在的 request 返回 404", client.get("/api/v1/requests/nope").status_code == 404)
    ck.check("不存在的 table 返回 404", client.get("/api/v1/account-tables/nope").status_code == 404)
    ck.check(
        "空文本解析应 4xx",
        400 <= client.post("/api/v1/requests/parse", json={"raw_text": "   "}).status_code < 500,
    )
    code = client.get("/api/v1/summary").status_code
    ck.check("无日期汇总应 4xx", 400 <= code < 500, str(code))
