"""当日汇总端点。"""

from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, Query

from app.domain.enums import BizType
from app.domain.models import ApiResponse
from app.orchestrator import pipeline

router = APIRouter(tags=["summary"])


@router.get("/summary", response_model=ApiResponse)
def get_daily_summary(
    date: date_cls = Query(...),
    biz_type: BizType | None = Query(default=None),
) -> ApiResponse:
    """当日抖加 / 垫付汇总，**三口径并列**不合并。"""
    summary = pipeline.daily_summary(date, biz_type)
    return ApiResponse(code=0, data=summary.model_dump(mode="json"))
