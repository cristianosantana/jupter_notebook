"""Testes do Fact Planner (5A)."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.fact_semantics_catalog import load_fact_semantics_catalog
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.intent_heuristics import apply_heuristic_enrichment


@pytest.mark.asyncio
async def test_fact_planner_ranking_asc_marco():
    catalog = load_fact_semantics_catalog()
    planner = FactPlanner(provider=None, catalog=catalog)
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
    result = await planner.plan(message, contract=contract)
    assert result.composite is False
    assert len(result.requirements) >= 1
    assert result.requirements[0].fact_key == "ranking_forma_pagamento"
    assert result.requirements[0].semantics.comparator.value == "asc"


@pytest.mark.asyncio
async def test_fact_planner_composite_maio_oficina():
    catalog = load_fact_semantics_catalog()
    planner = FactPlanner(provider=None, catalog=catalog)
    message = "Quanto faturamos em maio e qual o valor no departamento oficina?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-05",
            confidence=0.85,
        ),
        message,
    )
    result = await planner.plan(message, contract=contract)
    fact_keys = {req.fact_key for req in result.requirements}
    assert "faturamento_total_periodo" in fact_keys
    assert result.composite is True
