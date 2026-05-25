from __future__ import annotations

from collections.abc import Sequence

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES
from orion_mcp_v3.broker.query_capability_catalog import build_query_capability_catalog
from orion_mcp_v3.broker.query_template_selector import QuerySelectionValidator, QueryTemplateSelector
from orion_mcp_v3.contracts.query_selection import QuerySelectionContract
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.protocols.llm import ChatMessage, LLMResponse, LLMResponseMeta


class FakeSelectorProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0
        self.last_messages: Sequence[ChatMessage] = ()

    async def generate(self, prompt: str, **kwargs):  # type: ignore[no-untyped-def]
        return LLMResponse(text=self.text, meta=LLMResponseMeta(model="fake"))

    async def chat(self, messages: Sequence[ChatMessage], **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.last_messages = messages
        return LLMResponse(text=self.text, meta=LLMResponseMeta(model="fake"))

    async def stream(self, messages: Sequence[ChatMessage], **kwargs):  # type: ignore[no-untyped-def]
        yield ""


async def test_query_template_selector_returns_contract_from_json() -> None:
    provider = FakeSelectorProvider(
        """
        {
          "template_slug": "performance_vendedor",
          "measure": "vendas",
          "dimension": "vendedor",
          "operation": "ranking_desc",
          "confidence": 0.93,
          "reason": "A pergunta pede vendedores em destaque."
        }
        """
    )
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    plan = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        metrics=("vendas",),
        entities=("vendedor",),
    )

    selected = await QueryTemplateSelector(provider).select(
        "quais vendedores se destacaram em março?",
        cognitive_plan=plan,
        capabilities=catalog,
    )

    assert provider.calls == 1
    assert selected is not None
    assert selected.template_slug == "performance_vendedor"
    assert selected.dimension == "vendedor"
    assert "query_cards" in provider.last_messages[-1].content


async def test_query_template_selector_rejects_non_json() -> None:
    provider = FakeSelectorProvider("use performance_vendedor")
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)

    selected = await QueryTemplateSelector(provider).select(
        "quais vendedores se destacaram?",
        cognitive_plan=CognitivePlan(intent_type=IntentType.ANALYTICAL, needs_analytics=True),
        capabilities=catalog,
    )

    assert selected is None


def test_query_selection_validator_accepts_supported_selection() -> None:
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    result = QuerySelectionValidator(catalog).validate(
        QuerySelectionContract(
            template_slug="performance_vendedor",
            measure="valor vendido",
            dimension="vendedores",
            operation="ranking_desc",
            confidence=0.9,
            reason="Pergunta pede vendedores.",
        )
    )

    assert result.accepted is True
    assert result.contract is not None
    assert result.contract.measure == "vendas"
    assert result.contract.dimension == "vendedor"


def test_query_selection_validator_rejects_wrong_dimension_for_template() -> None:
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    result = QuerySelectionValidator(catalog).validate(
        QuerySelectionContract(
            template_slug="formas_pagamento",
            measure="total",
            dimension="vendedor",
            operation="ranking_desc",
            confidence=0.9,
            reason="Dimensão incompatível.",
        )
    )

    assert result.accepted is False
    assert result.rejected_reason == "unsupported_dimension"
