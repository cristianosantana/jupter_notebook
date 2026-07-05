"""Testes E2E do workspace pipeline (5D)."""

from __future__ import annotations

import pytest

from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider, LLMStreamChunk
from orion_mcp_v3.public_chat.application.workspace_pipeline import build_remissive_workspace
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.analytical_narrator import AnalyticalNarrator
from orion_mcp_v3.public_chat.infrastructure.memory_resolver import MemoryResolver
from orion_mcp_v3.public_chat.tests.phase4.fixtures import load_maio_contract_fixture, march_hit


class FakeReader:
    async def load_hits_by_theme_patterns(self, patterns, *, limit=20):
        return [march_hit()]


class CatalogReader:
    def __init__(self, hits):
        self._hits = hits

    async def load_hits_by_theme_patterns(self, patterns, *, limit=20):
        return list(self._hits)


class StubLLM(LLMProvider):
    async def complete(self, messages, *, max_tokens=1024, temperature=0.0):
        return ChatMessage(role="assistant", content="Depósito Bancário R$ 3.690,00.")

    async def stream(self, messages, *, max_tokens=1024, temperature=0.0):
        yield LLMStreamChunk(delta="Depósito Bancário R$ 3.690,00.")


@pytest.mark.asyncio
async def test_workspace_build_maio_servico_produto_ranking():
    planner = FactPlanner(provider=None)
    resolver = MemoryResolver(FakeReader())
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-05",
        confidence=0.9,
        operation=PublicOperationType.RANKING_DESC.value,
        dimension="servico",
    )
    from orion_mcp_v3.public_chat.tests.phase4.fixtures import maio_hit

    knowledge = ConhecimentoRecuperado(hits=(maio_hit(),))
    workspace = await build_remissive_workspace(
        "quais servicos e produtos venderam mais em maio de 2026?",
        contract=contract,
        knowledge=knowledge,
        planner=planner,
        resolver=resolver,
    )
    assert workspace.has_facts
    assert len(workspace.facts) >= 2
    assert all(fact.fact_key.startswith("dynamic:") for fact in workspace.facts)


@pytest.mark.asyncio
async def test_workspace_build_marco_ranking():
    planner = FactPlanner(provider=None)
    resolver = MemoryResolver(FakeReader())
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-03",
        confidence=0.9,
        operation=PublicOperationType.RANKING_ASC.value,
        dimension="forma_pagamento",
    )
    knowledge = ConhecimentoRecuperado(hits=(march_hit(),))
    workspace = await build_remissive_workspace(
        "Qual a forma de pagamento menos usada em março de 2026?",
        contract=contract,
        knowledge=knowledge,
        planner=planner,
        resolver=resolver,
    )
    assert workspace.has_facts
    assert len(workspace.facts) >= 1
    payload_chars = sum(len(fact.value) + len(fact.label) for fact in workspace.facts)
    assert payload_chars < 500


@pytest.mark.asyncio
async def test_workspace_scopes_period_and_resolves_source_hit_from_planner():
    fixture = load_maio_contract_fixture()
    parcelamento_maio = KnowledgeHit(
        origin_id=37,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:2026-05",
        category="Fechamento Gerencial",
        validated_answer="Parcelamento de cartão em maio.",
        key_metrics={"parcelamento_de_cartao": fixture["key_metrics"]["parcelamento_de_cartao"]},
        score=0.275767,
    )
    faturamento_fevereiro = KnowledgeHit(
        origin_id=18,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:2026-02",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por forma de pagamento em fevereiro.",
        key_metrics={
            "faturamento_por_tipo_de_pagamento": fixture["key_metrics"][
                "faturamento_por_tipo_de_pagamento"
            ],
        },
        score=0.332564,
    )
    faturamento_maio = KnowledgeHit(
        origin_id=33,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:2026-05",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por forma de pagamento em maio.",
        key_metrics={
            "faturamento_por_tipo_de_pagamento": fixture["key_metrics"][
                "faturamento_por_tipo_de_pagamento"
            ],
        },
        score=0.354322,
    )
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-05",
        confidence=0.78,
        operation="comparison",
        dimension=None,
    )

    workspace = await build_remissive_workspace(
        "qual o faturamento em maio de 2026?",
        contract=contract,
        knowledge=ConhecimentoRecuperado(
            hits=(parcelamento_maio, faturamento_fevereiro, faturamento_maio)
        ),
        planner=FactPlanner(provider=None),
        resolver=MemoryResolver(FakeReader()),
    )

    assert workspace.has_facts
    assert workspace.facts[0].origin_id == 33
    assert workspace.requirements[0].source_origin_id == 33


@pytest.mark.asyncio
async def test_workspace_does_not_use_other_period_when_scope_has_no_match():
    fixture = load_maio_contract_fixture()
    fevereiro = KnowledgeHit(
        origin_id=10,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-02",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por tipo de venda em fevereiro.",
        key_metrics={
            "faturamento_por_tipo_de_venda": fixture["key_metrics"]["faturamento_por_tipo_de_venda"],
        },
        score=0.269837,
    )
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-06",
        confidence=0.92,
        operation="summary",
        dimension=None,
    )

    workspace = await build_remissive_workspace(
        "qual o faturamento em junho de 2026?",
        contract=contract,
        knowledge=ConhecimentoRecuperado(hits=(fevereiro,)),
        planner=FactPlanner(provider=None),
        resolver=MemoryResolver(FakeReader()),
    )

    assert not workspace.has_facts
    assert workspace.workspace_confidence == 0.0


@pytest.mark.asyncio
async def test_workspace_comparison_uses_period_filter_as_second_period_not_entity():
    fixture = load_maio_contract_fixture()
    abril = KnowledgeHit(
        origin_id=28,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por tipo de venda em abril.",
        key_metrics={
            "faturamento_por_tipo_de_venda": fixture["key_metrics"]["faturamento_por_tipo_de_venda"],
        },
        score=0.31,
    )
    maio = KnowledgeHit(
        origin_id=34,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por tipo de venda em maio.",
        key_metrics={
            "faturamento_por_tipo_de_venda": fixture["key_metrics"]["faturamento_por_tipo_de_venda"],
        },
        score=0.29,
    )
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-05",
        confidence=0.9,
        operation="comparison",
        dimension=None,
        entity_filters=(EntityFilter(dimension="periodo", value="2026-04", match="exact"),),
    )

    workspace = await build_remissive_workspace(
        "qual o faturamento em maio de 2026 vs abril de 2026?",
        contract=contract,
        knowledge=ConhecimentoRecuperado(hits=(abril, maio)),
        planner=FactPlanner(provider=None),
        resolver=MemoryResolver(FakeReader()),
    )

    assert workspace.has_facts
    assert {fact.origin_id for fact in workspace.facts} == {28, 34}
    assert {req.period for req in workspace.requirements} == {"2026-04", "2026-05"}
    assert all(req.entity is None for req in workspace.requirements)


@pytest.mark.asyncio
async def test_workspace_comparison_loads_missing_period_from_catalog_hits():
    fixture = load_maio_contract_fixture()
    abril = KnowledgeHit(
        origin_id=28,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por tipo de venda em abril.",
        key_metrics={
            "faturamento_por_tipo_de_venda": fixture["key_metrics"]["faturamento_por_tipo_de_venda"],
        },
        score=0.31,
    )
    maio = KnowledgeHit(
        origin_id=34,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por tipo de venda em maio.",
        key_metrics={
            "faturamento_por_tipo_de_venda": fixture["key_metrics"]["faturamento_por_tipo_de_venda"],
        },
        score=0.29,
    )
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-05",
        confidence=0.9,
        operation="comparison",
        dimension=None,
        entity_filters=(EntityFilter(dimension="periodo", value="2026-04", match="exact"),),
    )

    workspace = await build_remissive_workspace(
        "qual o faturamento em maio de 2026 vs abril de 2026?",
        contract=contract,
        knowledge=ConhecimentoRecuperado(hits=(maio,)),
        planner=FactPlanner(provider=None),
        resolver=MemoryResolver(CatalogReader([abril, maio])),
    )

    assert workspace.has_facts
    assert {fact.origin_id for fact in workspace.facts} == {28, 34}


@pytest.mark.asyncio
async def test_analytical_narrator_streams_facts():
    planner = FactPlanner(provider=None)
    resolver = MemoryResolver(FakeReader())
    contract = IntentContract(
        intent="consulta_metrica",
        period="2026-03",
        confidence=0.9,
        operation=PublicOperationType.RANKING_ASC.value,
        dimension="forma_pagamento",
    )
    knowledge = ConhecimentoRecuperado(hits=(march_hit(),))
    workspace = await build_remissive_workspace(
        "pior forma pagamento março",
        contract=contract,
        knowledge=knowledge,
        planner=planner,
        resolver=resolver,
    )
    narrator = AnalyticalNarrator(StubLLM())
    parts: list[str] = []
    async for delta in narrator.stream("pior forma pagamento março", contract=contract, workspace=workspace):
        parts.append(delta)
    assert "Depósito" in "".join(parts) or "3.690" in "".join(parts)
