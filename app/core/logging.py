"""结构化日志。

演示态输出单行 JSON，便于人工核对"每一步可复现、可解释"（架构 §5.3）。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_LOGGER_NAME = "mst"


def _configure() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_event(event: str, **fields: Any) -> None:
    """记录一条结构化事件。`event` 是稳定的机器可读键。"""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event,
    }
    payload.update(fields)
    _configure().info(json.dumps(payload, ensure_ascii=False, default=str))
