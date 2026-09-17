"""账号表端点（入口层：只做参数绑定与响应封装，零业务逻辑）。"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.domain.models import ApiResponse
from app.orchestrator import pipeline

router = APIRouter(tags=["accounts"])


@router.post("/account-tables", response_model=ApiResponse, status_code=201)
def upload_account_table(file: UploadFile | None = File(default=None)) -> ApiResponse:
    """上传账号表测试副本；未提供文件时登记仓库自带的测试表。

    服务端一律**复制**一份再写，源表与生产表均不被修改。
    落盘与复制由编排层完成，本层只做参数绑定与响应封装。
    """
    if file is None:
        meta = pipeline.register_table()
        return ApiResponse(code=0, data=meta.model_dump(), message="已登记仓库自带测试表")

    meta = pipeline.register_uploaded_table(file.filename, file.file.read())
    return ApiResponse(code=0, data=meta.model_dump(), message="已生成测试副本")


@router.get("/account-tables/{table_id}", response_model=ApiResponse)
def get_account_table(table_id: str) -> ApiResponse:
    """读取副本内容与元信息（含溯源列与空行引用）。"""
    detail = pipeline.table_detail(table_id)
    return ApiResponse(code=0, data=detail.model_dump(mode="json"))
