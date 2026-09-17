"""LLM 可选旁路适配器（架构 §5.4）。

**无密钥即 no-op，主流程零降级**：`available=False` 时管线直接跳过 AP-1/AP-2，
全部 P0 校验与写表流程不受影响（Spec AC-11）。

适配器可被替换（测试注入 fake），这是"规则与模型结论分歧时升级人工"
这条链路的可测试入口。
"""

from __future__ import annotations

import json
import os

from app.core.config import LLM_BASE_URL_ENV, LLM_API_KEY_ENV, LLM_MODEL_ENV, llm_enabled
from app.core.logging import log_event
from app.llm.prompts import ENTITY_SYSTEM_PROMPT, entity_user_prompt


class LLMAdapter:
    """基底：默认不可用。`suggest_entity` 返回 None 表示"无意建议"。"""

    name = "noop"
    available = False

    def suggest_entity(self, name: str) -> str | None:  # noqa: ARG002
        return None


class OpenAICompatAdapter(LLMAdapter):
    """兼容 OpenAI 协议的服务。仅用于实体归一建议，不做任何字段推断。"""

    name = "openai-compatible"
    available = True

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def suggest_entity(self, name: str) -> str | None:
        import httpx

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": ENTITY_SYSTEM_PROMPT},
                        {"role": "user", "content": entity_user_prompt(name)},
                    ],
                },
                timeout=10.0,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            canonical = json.loads(content).get("canonical")
            log_event("llm_suggest", name=name, canonical=canonical, model=self.model)
            return canonical or None
        except Exception as exc:  # 旁路失败绝不影响主流程
            log_event("llm_unavailable", reason=str(exc)[:200])
            return None


_ADAPTER: LLMAdapter = LLMAdapter()


def get_adapter() -> LLMAdapter:
    return _ADAPTER


def set_adapter(adapter: LLMAdapter) -> None:
    """替换适配器（测试注入 / 运行时切换）。"""
    global _ADAPTER
    _ADAPTER = adapter


def reset_adapter() -> None:
    """按环境变量重建适配器；无密钥即 no-op。"""
    global _ADAPTER
    if not llm_enabled():
        _ADAPTER = LLMAdapter()
        return
    _ADAPTER = OpenAICompatAdapter(
        api_key=os.environ[LLM_API_KEY_ENV],
        base_url=os.environ.get(LLM_BASE_URL_ENV, "https://api.openai.com/v1"),
        model=os.environ.get(LLM_MODEL_ENV, "gpt-4o-mini"),
    )
