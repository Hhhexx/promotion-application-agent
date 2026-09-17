"""测试夹具自身的护栏：**测试运行不得写入仓库内的 data/**。

背景：`data/test-copies/`、`data/uploads/`、`data/decisions/` 是运行期产物。
若测试把副本 / 裁决日志写进仓库，会造成「测试互相污染 + 仓库被弄脏 + 结果不可重复」。

**接缝契约（与后端约定）**：唯一接缝是 `config.*`。任何模块都不得再持有
`from app.core.config import X` 的 import 期副本，使用点一律读 `config.X`。
因此 `tests/conftest.py::clean_state` 只 patch 三处 `config.*` 即可重定向全部落盘。

本文件给出两类护栏：
  1. **结构性**：写盘接缝（`config.*`）都指向仓库 `data/` 之外（快速、廉价）；
  2. **功能型（关键）**：只 patch `config` 的前提下**真的落一次盘**，断言文件落在
     临时目录、且仓库 `data/` 无任何新增。
     结构性检查只验「名字在不在」，重构一搬家就失效/误报；功能型检查抓的是**行为**：
     只要有任何模块把接缝搬走（继续持有 import 期副本），副本 / 日志会落到仓库 `data/`，
     本用例立刻变红。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core import config
from app.orchestrator import pipeline
from app.repositories import decision_repo

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_DATA = (REPO_ROOT / "data").resolve()

#: 唯一的写盘接缝：所有运行期落盘都必须经由这三处 `config` 属性。
WRITE_TARGETS = {
    "config.TEST_COPY_DIR": lambda: config.TEST_COPY_DIR,
    "config.UPLOAD_DIR": lambda: config.UPLOAD_DIR,
    "config.DECISION_LOG": lambda: config.DECISION_LOG,
}


def _is_outside_repo_data(path) -> bool:
    resolved = Path(path).resolve()
    if resolved == REPO_DATA:
        return False
    # 必须是仓库 data/ 之外（既不是它本身，也不是它的子孙）
    return REPO_DATA not in resolved.parents


def _repo_data_files() -> set[str]:
    """仓库 data/ 下全部文件（相对路径），用于比对「有无新增」。"""
    if not REPO_DATA.exists():
        return set()
    return {str(p.relative_to(REPO_DATA)) for p in REPO_DATA.rglob("*") if p.is_file()}


def test_all_write_seams_are_redirected_outside_repo_data():
    leaked = {
        name: str(getter())
        for name, getter in WRITE_TARGETS.items()
        if not _is_outside_repo_data(getter())
    }
    assert not leaked, f"以下写盘接缝仍指向仓库 data/，测试会污染仓库：{leaked}"


def test_source_table_is_still_the_repo_copy():
    # 源表是仓库内只读夹具，**刻意不被重定向** —— 它必须保持可读且存在
    assert config.DEFAULT_SOURCE_TABLE == REPO_ROOT / "data" / "你是我的仰望-推广账号表.xlsx"
    assert config.DEFAULT_SOURCE_TABLE.exists()
    assert _is_outside_repo_data(config.TEST_COPY_DIR), "源表目录与产物目录不应混为一谈"


def test_real_write_lands_in_temp_dir_and_repo_data_untouched(source_table):
    """功能型守卫：只 patch config 的前提下，真的落一次盘（两条真实写入路径）。

    - 登记账号表 → 复制测试副本落盘（走 `TEST_COPY_DIR`）
    - 追加裁决日志 → JSONL 落盘（走 `DECISION_LOG`）

    若任何模块把接缝搬走（仍持有 import 期副本），上述文件会落到仓库 `data/`，
    本用例立刻红 —— 这是上面两条「结构性」检查抓不到的行为退化。

    注意：`pipeline` / `decision_repo` 在**模块顶部**导入（即 config 被 patch 之前），
    这样才真正检验「import 之后再 patch config」这一现实场景；否则模块若在 patch 之后
    才首次导入，会碰巧拿到已 patch 的值，形成假绿（import 顺序敏感）。
    """
    before = _repo_data_files()
    source_hash_before = hashlib.sha256(source_table.read_bytes()).hexdigest()

    meta = pipeline.register_table(source_path=source_table)
    copy_path = Path(meta.copy_path)
    assert copy_path.exists(), "登记后测试副本未落盘"
    assert _is_outside_repo_data(copy_path), f"测试副本落到仓库 data/ 了：{copy_path}"
    assert Path(config.TEST_COPY_DIR).resolve() in copy_path.resolve().parents, (
        f"副本未落在被 patch 的 config.TEST_COPY_DIR 下：{copy_path} vs {config.TEST_COPY_DIR}"
    )
    # 源表只读：登记副本不得改动源表字节
    assert hashlib.sha256(source_table.read_bytes()).hexdigest() == source_hash_before, (
        "登记测试副本改动了源表字节"
    )

    decision_repo.append_entry(
        {"request_id": "req_probe", "anomaly_id": "am_probe", "action": "accept"}
    )
    assert Path(config.DECISION_LOG).exists(), "裁决日志未落盘"
    assert _is_outside_repo_data(config.DECISION_LOG), f"裁决日志落到仓库 data/ 了：{config.DECISION_LOG}"

    after = _repo_data_files()
    assert after == before, f"仓库 data/ 出现了新增文件：{sorted(after - before)}"
