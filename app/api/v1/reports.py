"""负责人汇报端点。"""

from __future__ import annotations

from fastapi import APIRouter

from app.domain.models import ApiResponse, DailyReportInput
from app.orchestrator import pipeline

router = APIRouter(tags=["reports"])


@router.post("/reports/daily", response_model=ApiResponse, status_code=201)
def create_daily_report(payload: DailyReportInput) -> ApiResponse:
    """生成面向负责人的简短汇报（结论 + 关键数字 + 需决策项）。"""
    report = pipeline.create_daily_report(payload.date, payload.include_unresolved)
    return ApiResponse(code=0, data=report.model_dump(mode="json"))


@router.get("/reports/daily/{report_id}", response_model=ApiResponse)
def get_daily_report(report_id: str) -> ApiResponse:
    report = pipeline.get_daily_report(report_id)
    return ApiResponse(code=0, data=report.model_dump(mode="json"))
