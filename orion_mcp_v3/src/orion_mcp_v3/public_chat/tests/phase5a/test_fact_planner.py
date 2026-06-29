"""Testes do Fact Planner analítico (5A)."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.domain.fact_engine.requirement_kind import RequirementKind
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.intent_heuristics import apply_heuristic_enrichment
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.tests.phase4.fixtures import maio_hit, march_hit


@pytest.mark.asyncio
async def test_fact_planner_ranking_asc_marco():
    planner = FactPlanner(provider=None)
    message = "Qual a forma de pagamento menos usada em março de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-03",
            confidence=0.9,
            operation=PublicOperationType.RANKING_ASC.value,
            dimension="forma_pagamento",
        ),
        message,
    )
    knowledge = ConhecimentoRecuperado(hits=(march_hit(),))
    result = await planner.plan(message, contract=contract, knowledge=knowledge)
    assert result.composite is False
    assert len(result.requirements) >= 1
    assert result.requirements[0].fact_key.startswith("dynamic:")
    assert result.requirements[0].requirement_kind == RequirementKind.LOOKUP
    assert result.requirements[0].matched_key == "faturamento_por_tipo_de_pagamento"


@pytest.mark.asyncio
async def test_fact_planner_composite_servico_produto_maio():
    planner = FactPlanner(provider=None)
    message = "Quais servicos e produtos venderam mais em maio de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-05",
            confidence=0.85,
            operation=PublicOperationType.RANKING_DESC.value,
            dimension="servico",
        ),
        message,
    )
    knowledge = ConhecimentoRecuperado(hits=(maio_hit(),))
    result = await planner.plan(message, contract=contract, knowledge=knowledge)
    fact_keys = {req.fact_key for req in result.requirements}
    matched = {req.matched_key for req in result.requirements}
    assert result.composite is True
    assert "dynamic:producao_por_servico" in fact_keys
    assert "dynamic:producao_por_produto" in fact_keys
    assert matched == {"producao_por_servico", "producao_por_produto"}
    assert result.used_llm_disambiguation is False
