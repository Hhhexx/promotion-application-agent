"""申请端点：解析、异常清单、人工裁决、提交写表、审计导出。"""

from __future__ import annotations

from fastapi import APIRouter, Body, Query
from fastapi.responses import PlainTextResponse

from app.core.logging import log_event
from app.domain.models import ApiResponse, ParseRequestInput, ResolutionInput
from app.orchestrator import pipeline
from app.repositories.decision_repo import export_csv

router = APIRouter(tags=["requests"])


@router.post("/requests/parse", response_model=ApiResponse)
def parse_request(payload: ParseRequestInput) -> ApiResponse:
    """解析申请文本并返回解析结果与分级异常清单（LLM 旁路可选，无密钥不降级）。"""
    result = pipeline.parse_into_request(
        raw_text=payload.raw_text,
        biz_type_hint=payload.biz_type_hint,
        table_id=payload.table_id,
        enable_llm=payload.enable_llm,
    )
    return ApiResponse(code=0, data=result.model_dump(mode="json"), message="解析完成")


@router.get("/requests/{request_id}", response_model=ApiResponse)
def get_request(request_id: str) -> ApiResponse:
    """获取解析结果、异常清单与闸门状态。"""
    result = pipeline.get_request(request_id)
    return ApiResponse(code=0, data=result.model_dump(mode="json"))


@router.post("/requests/{request_id}/resolutions", response_model=ApiResponse)
def resolve_anomaly(request_id: str, payload: ResolutionInput) -> ApiResponse:
    """人工裁决一条异常，并**重跑校验**更新状态（仍是失败则保持 NEEDS_REVIEW）。"""
    outcome = pipeline.resolve_anomaly(request_id, payload)
    log_event("resolution_api", request_id=request_id, anomaly_id=payload.anomaly_id)
    return ApiResponse(code=0, data=outcome.model_dump(mode="json"), message="裁决已记录")


@router.post("/requests/{request_id}/commit", response_model=ApiResponse)
def commit_request(request_id: str, payload: dict = Body(...)) -> ApiResponse:
    """写入测试副本。存在未裁决 P0 时返回 409 且不发生任何写入。"""
    result = pipeline.get_request(request_id)
    table_id = payload.get("table_id") or result.table_id or pipeline.default_table_id()
    outcome = pipeline.commit_request(request_id, table_id)
    return ApiResponse(code=0, data=outcome.model_dump(mode="json"), message="写入完成")


@router.get("/requests/{request_id}/decisions", response_class=PlainTextResponse)
def export_decisions(request_id: str, fmt: str = Query(default="json", alias="format")) -> PlainTextResponse:
    """裁决日志导出（append-only；F-12 审计留痕）。

    口径：**当前会话**内该申请的裁决记录（内存态主数据，ADR-003）。
    不回读落盘 JSONL —— 后者用于长期审计留存，但 `request_id` 跨会话撞号会让
    陈旧记录回流到接口（见 `tests/test_decision_log_isolation.py`）。
    """
    entries = pipeline.list_decisions(request_id)
    if fmt == "csv":
        return PlainTextResponse(
            export_csv(entries),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{request_id}-decisions.csv"'},
        )
    import json

    return PlainTextResponse(json.dumps(entries, ensure_ascii=False, indent=2), media_type="application/json")
