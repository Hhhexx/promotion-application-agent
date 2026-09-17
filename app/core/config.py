"""运行配置。

演示态不引入配置中心；所有可调项集中在此，便于审计。
"""

from __future__ import annotations

import os
from pathlib import Path

#: 仓库根目录（本文件位于 app/core/config.py）。
ROOT_DIR = Path(__file__).resolve().parents[2]

#: 运行期可写产物的根目录。默认 `data/`；设 `MST_DATA_DIR` 可整体重定向。
#: 用途：自动化验证可以把产物丢进临时目录，做到**用完即弃、不需要删除任何已有文件**
#: —— 递归删除容易被运行环境的 safe-delete 守卫拦截（守卫无法区分"脚本清理自己的
#: 输出"和"误删用户数据"），改路径比硬删文件更可靠。
DATA_DIR = Path(os.environ.get("MST_DATA_DIR") or (ROOT_DIR / "data"))

#: 仓储内自带的账号表源文件（只读，永不修改）。
#: **刻意不受 `MST_DATA_DIR` 影响** —— 它是仓库内的只读夹具，不是运行期产物。
DEFAULT_SOURCE_TABLE = ROOT_DIR / "data" / "你是我的仰望-推广账号表.xlsx"

#: 测试副本输出目录。
TEST_COPY_DIR = DATA_DIR / "test-copies"

#: 上传暂存目录。
UPLOAD_DIR = DATA_DIR / "uploads"

#: 裁决日志（append-only JSONL）。
DECISION_LOG = DATA_DIR / "decisions" / "decisions.jsonl"

#: 前端静态资源目录。
WEB_DIR = ROOT_DIR / "web"

#: 金额量化精度（保 2 位，禁止 float 参与运算）。
MONEY_EXP = "0.01"

#: LLM 旁路开关：无密钥时自动降级为 no-op，主流程不受影响（架构 §5.4）。
LLM_API_KEY_ENV = "LLM_API_KEY"
LLM_BASE_URL_ENV = "LLM_BASE_URL"
LLM_MODEL_ENV = "LLM_MODEL"


def llm_enabled() -> bool:
    """环境变量存在密钥时才认为 LLM 旁路可用。"""
    return bool(os.environ.get(LLM_API_KEY_ENV))


def ensure_dirs() -> None:
    """确保运行期需要的目录存在。"""
    TEST_COPY_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DECISION_LOG.parent.mkdir(parents=True, exist_ok=True)
