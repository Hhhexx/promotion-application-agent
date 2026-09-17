"""LLM 旁路单测（架构 §5.4 / Spec AC-11）。

不变量：**无密钥即 no-op，主流程零降级**；且 LLM 与规则结论分歧时升级人工，
绝不「取其一」。这条链路平时不跑（无密钥），所以必须靠注入假适配器来验证。
"""

from __future__ import annotations

from app.core.config import llm_enabled
from app.domain.enums import AnomalyCode
from app.llm import llm_adapter
from app.llm.llm_adapter import LLMAdapter
from app.parsers.base import parse_request
from app.validators.engine import validate


class _FakeAdapter(LLMAdapter):
    """把 `name` 映射为某个规范化昵称的假适配器。"""

    name = "fake"
    available = True

    def __init__(self, mapping):
        self._mapping = mapping

    def suggest_entity(self, name: str) -> str | None:
        return self._mapping(name)


class TestNoKeyDegradation:
    def test_env_has_no_key(self):
        assert llm_enabled() is False

    def test_default_adapter_is_unavailable(self):
        assert llm_adapter.get_adapter().available is False
        assert llm_adapter.get_adapter().suggest_entity("初秋") is None

    def test_enable_llm_without_key_is_safe(self, client, table_id, doujia_text):
        response = client.post(
            "/api/v1/requests/parse",
            json={"raw_text": doujia_text, "table_id": table_id, "enable_llm": True},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["llm_used"] is False
        assert not [a for a in data["anomalies"] if a["code"] == "LLM_RULE_CONFLICT"]

    def test_no_llm_anomalies_without_key(self, source_snapshot, doujia_text):
        result = validate(parse_request(doujia_text), source_snapshot, "req_noop")
        assert result.llm_used is False
        assert not [a for a in result.anomalies if a.code == "LLM_RULE_CONFLICT"]


class TestInjectedAdapter:
    def test_identity_adapter_reports_llm_used_without_conflict(self, source_snapshot, doujia_text):
        llm_adapter.set_adapter(_FakeAdapter(lambda name: name))
        result = validate(parse_request(doujia_text), source_snapshot, "req_llm_ok")
        assert result.llm_used is True
        # 模型与规则一致 → 不产生冲突异常
        assert not [a for a in result.anomalies if a.code == "LLM_RULE_CONFLICT"]
        assert result.aggregate_state == "READY"

    def test_diverging_adapter_raises_blocking_conflict(self, source_snapshot, doujia_text):
        # 模型把所有人都归一到「艳红」，与规则判定的其他行不一致
        llm_adapter.set_adapter(_FakeAdapter(lambda name: "艳红"))
        result = validate(parse_request(doujia_text), source_snapshot, "req_llm_bad")
        assert result.llm_used is True
        conflicts = [a for a in result.anomalies if a.code == AnomalyCode.LLM_RULE_CONFLICT]
        assert conflicts
        assert all(a.blocking is True and a.severity == "P0" for a in conflicts)
        assert "艳红" in {a.text_value for a in conflicts}
        assert result.aggregate_state == "NEEDS_REVIEW"

    def test_ambiguity_is_not_resolved_just_because_model_agrees(self, source_snapshot):
        # 规则判为歧义时，模型侧即使给出同样的名字也不能自动放行 —— 仍须人工指定目标行。
        text = (
            "【垫付统计】今日已垫付：¥500（2026-09-03）\n\n明细如下：\n"
            "申请为【达人：葵花夫妇】垫付 ¥500（歌曲《你是我的仰望》）\n\n"
            "今日共 1 笔垫付申请。\n打款人：林老师\n"
        )
        llm_adapter.set_adapter(_FakeAdapter(lambda name: name))
        result = validate(parse_request(text), source_snapshot, "req_amb")
        assert result.aggregate_state == "NEEDS_REVIEW"
        assert [a for a in result.anomalies if a.code == AnomalyCode.MATCH_AMBIGUOUS]
        # 回归：两侧同判「无法确定目标行」= 结论一致，不该再报一条目标行写 `?` 的冲突噪声
        assert not [a for a in result.anomalies if a.code == AnomalyCode.LLM_RULE_CONFLICT]

    def test_ambiguous_item_still_conflicts_when_model_picks_a_concrete_row(self, source_snapshot):
        # 反向控制：规则判歧义、模型却指向某个具体行 —— 这才是真分歧，必须升级人工。
        text = (
            "【垫付统计】今日已垫付：¥500（2026-09-03）\n\n明细如下：\n"
            "申请为【达人：葵花夫妇】垫付 ¥500（歌曲《你是我的仰望》）\n\n"
            "今日共 1 笔垫付申请。\n打款人：林老师\n"
        )
        llm_adapter.set_adapter(_FakeAdapter(lambda name: "初秋"))
        result = validate(parse_request(text), source_snapshot, "req_amb_conflict")
        conflicts = [a for a in result.anomalies if a.code == AnomalyCode.LLM_RULE_CONFLICT]
        assert conflicts
        assert all(a.blocking is True and a.severity == "P0" for a in conflicts)
        assert "初秋" in {a.text_value for a in conflicts}
