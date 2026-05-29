from __future__ import annotations

from collections.abc import Sequence

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES
from orion_mcp_v3.broker.query_capability_catalog import build_query_capability_catalog
from orion_mcp_v3.contracts.answer_presentation import AnswerPresentationContract
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.query_selection import QuerySelectionContract
from orion_mcp_v3.protocols.llm import ChatMessage, LLMResponse, LLMResponseMeta
from orion_mcp_v3.runtime.answer_presentation_interpreter import (
    AnswerPresentationInterpreter,
    AnswerPresentationValidator,
)


class FakePresentationProvider:
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


async def test_answer_presentation_interpreter_returns_contract_from_json() -> None:
    provider = FakePresentationProvider(
        """
        {
          "result_scope": {"mode": "all", "limit": null},
          "sort": {"field": "vendas", "direction": "desc"},
          "confidence": 0.93,
          "reason": "Usuário pediu todos ordenados do maior para o menor."
        }
        """
    )
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    query_selection = QuerySelectionContract(
        template_slug="itens_vendidos",
        measure="vendas",
        dimension="item",
        operation="ranking_desc",
        confidence=0.9,
    )

    contract = await AnswerPresentationInterpreter(provider).interpret(
        "total vendido no periodo, ordenar do maior para o menor, inclua todos",
        cognitive_plan=CognitivePlan(intent_type=IntentType.ANALYTICAL, needs_analytics=True),
        query_selection=query_selection,
        capabilities=catalog,
    )

    assert provider.calls == 1
    assert contract is not None
    assert contract.result_scope == {"mode": "all", "limit": None}
    assert contract.sort == {"field": "vendas", "direction": "desc"}
    assert "selected_query_card" in provider.last_messages[-1].content


def test_answer_presentation_validator_normalizes_sort_alias() -> None:
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    result = AnswerPresentationValidator(catalog).validate(
        AnswerPresentationContract(
            result_scope={"mode": "all", "limit": None},
            sort={"field": "valor vendido", "direction": "desc"},
            confidence=0.9,
            reason="Pedido pede todos os itens ordenados por venda.",
        ),
        query_selection=QuerySelectionContract(
            template_slug="itens_vendidos",
            measure="vendas",
            dimension="item",
            operation="ranking_desc",
            confidence=0.9,
        ),
    )

    assert result.accepted is True
    assert result.contract is not None
    assert result.contract.result_scope == {"mode": "all", "limit": None}
    assert result.contract.sort == {"field": "vendas", "direction": "desc"}
