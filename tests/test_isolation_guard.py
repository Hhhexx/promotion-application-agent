"""测试夹具自身的护栏：**测试运行不得写入仓库内的 data/**。

背景：`data/test-copies/`、`data/uploads/`、`data/decisions/` 是运行期产物。
若测试把副本/裁决日志写进仓库，会造成「测试互相污染 + 仓库被弄脏 + 结果不可重复」。
本文件把「产物路径必须落在仓库之外」固化成不变量：任何一次重构把路径改回 `data/`，
这里立刻变红。

（`tests/conftest.py::clean_state` 通过 monkeypatch 覆盖下列模块属性；
生产侧另有 `MST_DATA_DIR` 环境变量做整体重定向，见 `app/core/config.py`。）
"""

from __future__ import annotations

from pathlib import Path

from app.core import config
from app.orchestrator import pipeline
from app.repositories import decision_repo

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_DATA = (REPO_ROOT / "data").resolve()

#: 所有可能被测试触发的写盘目标（模块属性 + 配置）：必须与仓库 data/ 无关。
WRITE_TARGETS = {
    "config.TEST_COPY_DIR": lambda: config.TEST_COPY_DIR,
    "config.UPLOAD_DIR": lambda: config.UPLOAD_DIR,
    "config.DECISION_LOG": lambda: config.DECISION_LOG,
    "pipeline.TEST_COPY_DIR": lambda: pipeline.TEST_COPY_DIR,
    "pipeline.UPLOAD_DIR": lambda: pipeline.UPLOAD_DIR,
    "decision_repo.DECISION_LOG": lambda: decision_repo.DECISION_LOG,
}


def _is_outside_repo_data(path) -> bool:
    resolved = Path(path).resolve()
    if resolved == REPO_DATA:
        return False
    # 必须是仓库 data/ 之外（既不是它本身，也不是它的子孙）
    return REPO_DATA not in resolved.parents


def test_all_write_targets_are_redirected_outside_repo_data():
    leaked = {
        name: str(getter())
        for name, getter in WRITE_TARGETS.items()
        if not _is_outside_repo_data(getter())
    }
    assert not leaked, f"以下写盘目标仍指向仓库 data/，测试会污染仓库：{leaked}"


def test_source_table_is_still_the_repo_copy():
    # 源表是仓库内只读夹具，**刻意不被重定向** —— 它必须保持可读且存在
    assert config.DEFAULT_SOURCE_TABLE == REPO_ROOT / "data" / "你是我的仰望-推广账号表.xlsx"
    assert config.DEFAULT_SOURCE_TABLE.exists()
    assert _is_outside_repo_data(config.TEST_COPY_DIR), "源表目录与产物目录不应混为一谈"
