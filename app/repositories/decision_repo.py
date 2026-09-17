"""裁决日志仓储：append-only JSONL，可导出 CSV。

「撤销」= 追加一条反向记录，**不物理删除**（架构 §3.2 可追溯性要求）。
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from app.core.config import DECISION_LOG, ensure_dirs
from app.core.logging import log_event

CSV_FIELDS = [
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


def append_entry(entry: dict, path: Path | None = None) -> None:
    """追加一条裁决记录到 JSONL。"""
    ensure_dirs()
    target = path or DECISION_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log_event("decision_appended", **{k: entry.get(k) for k in ("request_id", "anomaly_id", "action")})


def read_entries(path: Path | None = None) -> list[dict]:
    target = path or DECISION_LOG
    if not target.exists():
        return []
    out: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def export_csv(entries: list[dict] | None = None, path: Path | None = None) -> str:
    """导出裁决日志为 CSV 文本（界面「下载裁决日志」出口）。"""
    rows = entries if entries is not None else read_entries(path)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})
    return buffer.getvalue()
