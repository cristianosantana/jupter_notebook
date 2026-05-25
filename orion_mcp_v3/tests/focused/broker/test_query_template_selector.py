from __future__ import annotations

from collections.abc import Sequence

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES, QueryExpander
from orion_mcp_v3.broker.query_capability_catalog import build_query_capability_catalog
from orion_mcp_v3.broker.query_template_selector import QuerySelectionValidator, QueryTemplateSelector
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST
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


async def test_selector_regression_vendedor_question_selects_vendedor_template() -> None:
    selected = await _select_fake(
        question="quais vendedores se destacaram em março?",
        response_template="performance_vendedor",
        measure="vendas",
        dimension="vendedor",
    )

    assert selected is not None
    assert selected.template_slug == "performance_vendedor"


async def test_selector_regression_concessionaria_question_selects_concessionaria_template() -> None:
    selected = await _select_fake(
        question="cruze faturamento das concessionárias de janeiro a março",
        response_template="performance_concessionaria",
        measure="vendas",
        dimension="concessionaria",
    )

    assert selected is not None
    assert selected.template_slug == "performance_concessionaria"


async def test_selector_regression_pagamento_question_selects_formas_pagamento() -> None:
    selected = await _select_fake(
        question="qual forma de pagamento domina?",
        response_template="formas_pagamento",
        measure="total",
        dimension="periodo",
    )

    assert selected is not None
    assert selected.template_slug == "formas_pagamento"


def test_selector_regression_invalid_template_falls_back_to_registry_match() -> None:
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    invalid = QuerySelectionValidator(catalog).validate(
        QuerySelectionContract(
            template_slug="template_inexistente",
            measure="total",
            dimension="forma_pagamento",
            operation="ranking_desc",
            confidence=0.95,
            reason="Template fora do catálogo.",
        )
    )
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        metrics=("total",),
        entities=("forma_pagamento",),
    )

    plans = QueryExpander(registry=ANALYTICS_TEMPLATES).expand(
        cp,
        ANALYTICS_ALLOWLIST,
        query_text="qual forma de pagamento domina?",
    )

    assert invalid.accepted is False
    assert plans
    assert plans[0].intent_slug == "template.formas_pagamento"
    assert plans[0].hints["semantic_reason"] == "registry_match"


async def _select_fake(
    *,
    question: str,
    response_template: str,
    measure: str,
    dimension: str,
) -> QuerySelectionContract | None:
    provider = FakeSelectorProvider(
        f"""
        {{
          "template_slug": "{response_template}",
          "measure": "{measure}",
          "dimension": "{dimension}",
          "operation": "ranking_desc",
          "confidence": 0.91,
          "reason": "seleção semântica fake"
        }}
        """
    )
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    selected = await QueryTemplateSelector(provider).select(
        question,
        cognitive_plan=CognitivePlan(intent_type=IntentType.ANALYTICAL, needs_analytics=True),
        capabilities=catalog,
    )
    if selected is None:
        return None
    validation = QuerySelectionValidator(catalog).validate(selected)
    return validation.contract if validation.accepted else None
