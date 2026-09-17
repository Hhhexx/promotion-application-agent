"""FastAPI 装配（入口层：只注册路由、挂载静态、映射错误码，零业务逻辑）。

启动时登记仓库自带的测试用账号表（源表只读，服务端复制副本后再写）。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as v1_router
from app.core.config import WEB_DIR, ensure_dirs
from app.core.logging import log_event
from app.domain.errors import DomainError, GateBlockedError, ValidationError
from app.domain.models import ApiResponse
from app.llm.llm_adapter import reset_adapter
from app.orchestrator import pipeline

logger = logging.getLogger("mst.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动：确保证目录存在、按环境变量重建 LLM 适配器、登记默认测试表。"""
    ensure_dirs()
    reset_adapter()
    try:
        meta = pipeline.register_table()
        log_event("startup_table", table_id=meta.table_id, rows=meta.row_count)
    except DomainError as exc:  # 缺表不阻断启动，界面会提示
        log_event("startup_table_skipped", reason=exc.message)
    yield


app = FastAPI(
    title="推广申请处理台 API",
    version="1.0.0",
    description=(
        "把群里的自然语言《抖加申请总结》《垫付申请总结》转成可核查、可追溯的台账数据；"
        "对任何不确定项零猜测，一律标记并转人工确认。"
        "统一响应格式 { code, data, message }，code=0 表示成功。"
    ),
    lifespan=lifespan,
)


def _error_response(exc: DomainError) -> JSONResponse:
    data = {"pending": exc.pending} if isinstance(exc, GateBlockedError) else None
    return JSONResponse(
        status_code=exc.http_status,
        content=ApiResponse(code=exc.code, data=data, message=exc.message).model_dump(),
    )


@app.exception_handler(DomainError)
async def handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
    log_event("domain_error", code=exc.code, status=exc.http_status, message=exc.message)
    return _error_response(exc)


@app.exception_handler(RequestValidationError)
async def handle_request_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(ValidationError("请求参数校验失败", detail=str(exc.errors()[:3])))


app.include_router(v1_router)

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok", "service": "推广申请处理台", "version": app.version}
