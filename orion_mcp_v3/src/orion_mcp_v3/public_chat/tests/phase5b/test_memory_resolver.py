"""Testes do Memory Resolver (5B)."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import FallbackPolicy, ResolvedMemoryHit
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import FactSemantics, AggregationRule, Comparator, SourcePriority
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.domain.memory_catalog import get_memory_catalog
from orion_mcp_v3.public_chat.infrastructure.memory_resolver import MemoryResolver
from orion_mcp_v3.public_chat.tests.phase4.fixtures import march_hit, other_month_hit


class FakeReader:
    async def load_hits_by_theme_patterns(self, patterns, *, limit=20):
        return [
            march_hit(origin_id=4),
            other_month_hit(origin_id=5, month_slug="maio_2026", period="2026-05-01-to-2026-05-31"),
        ]


@pytest.mark.asyncio
async def test_memory_resolver_join_marco():
    catalog = get_memory_catalog()
    resolver = MemoryResolver(FakeReader(), catalog=catalog, fallback=FallbackPolicy())
    planner = FactPlanner(provider=None)
    contract = IntentContract(
        intent="consulta_metrica",
        period="2026-03",
        confidence=0.9,
        operation=PublicOperationType.RANKING_ASC.value,
        dimension="forma_pagamento",
    )
    knowledge = ConhecimentoRecuperado(hits=(march_hit(),))
    plan = await planner.plan("pior forma pagamento março", contract=contract, knowledge=knowledge)
    knowledge = ConhecimentoRecuperado(hits=(march_hit(),))
    result = await resolver.resolve(plan.requirements, knowledge)
    assert result.join_plan is not None
    assert result.join_plan.period == "2026-03"
    assert any(key.startswith("dynamic:") for key in result.resolved)


@pytest.mark.asyncio
async def test_memory_resolver_gap_when_no_match():
    policy = FallbackPolicy()
    semantics = FactSemantics(
        fact_key="faturamento_departamento_oficina",
        aggregation_rule=AggregationRule.LOOKUP,
        comparator=Comparator.NONE,
        source_priority=(SourcePriority.KEY_METRICS,),
        value_kind="currency",
        memory_themes=("vendas_departamento",),
    )
    requirement = FactRequirement(
        fact_key="faturamento_departamento_oficina",
        metric=None,
        dimension=None,
        entity="oficina",
        period="2026-05",
        operation=None,
        semantics=semantics,
    )
    catalog = get_memory_catalog()
    result = policy.resolve_from_hits(
        requirement,
        catalog_hits=[march_hit()],
        vector_hits=[],
        catalog=catalog,
    )
    assert result.hit is None
    assert result.gap is not None
    assert result.gap.reason.value == "memory_exists_but_no_match"
