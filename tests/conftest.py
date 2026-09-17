"""pytest 公共夹具。

关键设计：
1. **干净起点、零删除**：`app.repositories.memory_store.STORE` 是模块级单例；
   `data/test-copies/` 与 `data/decisions/` 会在测试间累积。这里不删除仓库内任何文件，
   而是把「副本目录 / 裁决日志路径」重定向到**本次会话的临时目录**再逐测试分目录，
   因此测试天然互不干扰、可重复运行。
   （不用 `rmtree` 是刻意为之：运行环境的 safe-delete 守卫会拦截大批量删除。）
2. **无密钥 LLM**：默认清掉 `LLM_API_KEY`，让旁路稳定走 no-op（可被单测覆盖替换）。
3. **`sys.path`**：`conftest` 在收集阶段就把仓库根与 tests 目录加入 `sys.path`，
   使 `import app` / `import support` 在 `pytest` 与 `python -m pytest` 下都成立。
"""

from __future__ import annotations

import itertools
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for _p in (str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core import config  # noqa: E402
from app.llm import llm_adapter  # noqa: E402
from app.orchestrator import pipeline  # noqa: E402
from app.repositories import decision_repo  # noqa: E402
from app.repositories.memory_store import STORE  # noqa: E402
from app.repositories.xlsx_repository import XlsxRepository  # noqa: E402

SOURCE_TABLE = ROOT / "data" / "你是我的仰望-推广账号表.xlsx"
SAMPLES_DIR = ROOT / "data" / "samples"
DOUJIA_SAMPLE = SAMPLES_DIR / "抖加申请-2026-09-02.txt"
ADVANCE_SAMPLE = SAMPLES_DIR / "垫付申请-2026-09-03.txt"

_case_seq = itertools.count(1)


@pytest.fixture(scope="session")
def artifact_root() -> Path:
    """本次测试会话专属的临时根目录（进程退出后由系统回收，测试内不删除）。"""
    return Path(tempfile.mkdtemp(prefix="mst-pytest-artifacts-"))


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, artifact_root):
    """每个测试都回到干净起点：重置内存态、隔离磁盘产物、关闭 LLM 旁路。"""
    monkeypatch.delenv(config.LLM_API_KEY_ENV, raising=False)
    monkeypatch.delenv(config.LLM_BASE_URL_ENV, raising=False)
    monkeypatch.delenv(config.LLM_MODEL_ENV, raising=False)

    workdir = artifact_root / f"case-{next(_case_seq):04d}"
    copies = workdir / "test-copies"
    uploads = workdir / "uploads"
    decisions = workdir / "decisions" / "decisions.jsonl"
    for path in (copies, uploads, decisions.parent):
        path.mkdir(parents=True, exist_ok=True)

    # 把「写盘产物」重定向到临时目录：源表与仓库 data/ 全程只读。
    # 生产代码另提供 `MST_DATA_DIR` 环境变量做整体重定向（见 app/core/config.py），
    # 但那是**会话级**的（DATA_DIR 在 import 时求值）；这里逐测试再分目录并直接
    # 覆盖模块属性，取的是**每例隔离**，与 import 顺序无关。
    monkeypatch.setattr(config, "TEST_COPY_DIR", copies)
    monkeypatch.setattr(config, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(config, "DECISION_LOG", decisions)
    monkeypatch.setattr(pipeline, "TEST_COPY_DIR", copies)
    monkeypatch.setattr(pipeline, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(decision_repo, "DECISION_LOG", decisions)

    STORE.reset()
    llm_adapter.reset_adapter()
    yield
    STORE.reset()
    llm_adapter.reset_adapter()


@pytest.fixture
def workdir(artifact_root) -> Path:
    """供测试自建临时文件的目录（不删）。"""
    path = artifact_root / f"scratch-{next(_case_seq):04d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def source_table() -> Path:
    return SOURCE_TABLE


@pytest.fixture
def source_snapshot():
    """只读读取仓库自带账号表的快照（供校验层单测使用，不产生任何写入）。"""
    return XlsxRepository(SOURCE_TABLE).snapshot()


@pytest.fixture
def doujia_text() -> str:
    return DOUJIA_SAMPLE.read_text(encoding="utf-8")


@pytest.fixture
def advance_text() -> str:
    return ADVANCE_SAMPLE.read_text(encoding="utf-8")


@pytest.fixture
def client(clean_state):
    """触发 lifespan 的 TestClient（服务端会登记一份仓库自带表的测试副本）。"""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def table_id(client) -> str:
    """显式登记一张账号表副本，返回其 table_id。"""
    response = client.post("/api/v1/account-tables")
    assert response.status_code == 201, response.text
    return response.json()["data"]["table_id"]
