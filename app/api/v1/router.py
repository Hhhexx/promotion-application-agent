"""v1 路由汇总（入口层只装配）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import accounts, reports, requests, summary

router = APIRouter(prefix="/api/v1")
router.include_router(accounts.router)
router.include_router(requests.router)
router.include_router(summary.router)
router.include_router(reports.router)
