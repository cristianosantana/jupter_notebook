"""Testes E2E do workspace pipeline (5D)."""

from __future__ import annotations

import pytest

from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider, LLMStreamChunk
from orion_mcp_v3.public_chat.application.workspace_pipeline import build_remissive_workspace
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.infrastructure.analytical_narrator import AnalyticalNarrator
from orion_mcp_v3.public_chat.infrastructure.memory_resolver import MemoryResolver
from orion_mcp_v3.public_chat.tests.phase4.fixtures import march_hit


class FakeReader:
    async def load_hits_by_theme_patterns(self, patterns, *, limit=20):
        return [march_hit()]


class StubLLM(LLMProvider):
    async def complete(self, messages, *, max_tokens=1024, temperature=0.0):
        return ChatMessage(role="assistant", content="Depósito Bancário R$ 3.690,00.")

    async def stream(self, messages, *, max_tokens=1024, temperature=0.0):
        yield LLMStreamChunk(delta="Depósito Bancário R$ 3.690,00.")


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
