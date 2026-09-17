"""账号表读取服务（架构 §3.2）：取快照、取明细、定位登记记录。

只读侧；登记/复制副本仍在 `pipeline`（按职责就近，也与文件规模拆分一起决定）。

**运行期路径一律调用期取值**：任何模块都不得在 import 期绑定 `config.TEST_COPY_DIR`
等可重定向项，使用点必须写 `config.X`。这样 `tests/conftest.py` 只覆盖 `config.*`
三处即可重定向**全部**落盘（契约见 conftest 注释；行为护栏见
`tests/test_isolation_guard.py::test_real_write_lands_in_temp_dir_and_repo_data_untouched`）。
本模块只读已登记的 `copy_path`，不直接拼运行期路径。
"""

from __future__ import annotations

from app.domain.errors import NotFoundError
from app.domain.models import AccountTableDetail
from app.repositories.memory_store import STORE, MemoryStore, TableRecord
from app.repositories.xlsx_repository import TableSnapshot, XlsxRepository


def _store() -> MemoryStore:
    return STORE


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def require_table(table_id: str) -> TableRecord:
    record = _store().get_table(table_id)
    if record is None:
        raise NotFoundError(f"账号表 {table_id} 未登记")
    return record


def table_detail(table_id: str) -> AccountTableDetail:
    record = require_table(table_id)
    repo = XlsxRepository(record.copy_path)
    snapshot = repo.snapshot()
    meta = record.meta
    return AccountTableDetail(
        **meta.model_dump(),
        columns=snapshot.columns,
        rows=[
            {"row_ref": r.row_ref, **{k: _jsonable(v) for k, v in r.values.items()}}
            for r in snapshot.rows
        ],
        empty_row_refs=snapshot.empty_row_refs,
    )


def table_snapshot(table_id: str | None = None) -> TableSnapshot:
    """读取账号表快照（用于裁决时重跑字段冲突校验）。未指定则用当前默认表。"""
    store = _store()
    record = require_table(table_id) if table_id else store.default_table()
    if record is None:
        raise NotFoundError("尚未登记账号表")
    return XlsxRepository(record.copy_path).snapshot()


def default_table_id() -> str:
    """当前默认账号表 id（未登记时返回空串）。入口层据此给写表端点兜底。"""
    record = _store().default_table()
    return record.meta.table_id if record else ""


__all__ = [
    "require_table",
    "table_detail",
    "table_snapshot",
    "default_table_id",
]
