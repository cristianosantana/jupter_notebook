"""Testes do Memory Resolver (5B)."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import FallbackPolicy, ResolvedMemoryHit
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import FactSemantics, AggregationRule, Comparator, SourcePriority
from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionRule
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.domain.memory_catalog import get_memory_catalog
from orion_mcp_v3.public_chat.infrastructure.memory_resolver import MemoryResolver
from orion_mcp_v3.public_chat.tests.phase4.fixtures import load_maio_contract_fixture, march_hit, other_month_hit


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


@pytest.mark.asyncio
async def test_memory_resolver_prefers_requirement_source_origin_id_over_vector_order():
    fixture = load_maio_contract_fixture()
    parcelamento = KnowledgeHit(
        origin_id=37,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:2026-05",
        category="Fechamento Gerencial",
        validated_answer="Parcelamento de cartão em maio.",
        key_metrics={"parcelamento_de_cartao": fixture["key_metrics"]["parcelamento_de_cartao"]},
        score=0.275767,
    )
    faturamento = KnowledgeHit(
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
    semantics = FactSemantics(
        fact_key="dynamic:faturamento_por_tipo_de_pagamento",
        aggregation_rule=AggregationRule.LOOKUP,
        comparator=Comparator.NONE,
        source_priority=(SourcePriority.KEY_METRICS,),
        value_kind="currency",
        memory_themes=("fechamento_gerencial",),
        key_metrics_keys=("faturamento_por_tipo_de_pagamento",),
        key_metrics_entity_field="tipo",
        key_metrics_value_field="valor",
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_por_tipo_de_pagamento",
        metric="faturamento",
        dimension="forma_pagamento",
        entity=None,
        period="2026-05",
        operation="comparison",
        matched_key="faturamento_por_tipo_de_pagamento",
        source_origin_id=33,
        source_context_key=faturamento.context_key,
        semantics=semantics,
    )

    resolver = MemoryResolver(FakeReader(), catalog=get_memory_catalog(), fallback=FallbackPolicy())
    result = await resolver.resolve(
        (requirement,),
        ConhecimentoRecuperado(hits=(parcelamento, faturamento)),
    )

    resolved = result.resolved["dynamic:faturamento_por_tipo_de_pagamento"]
    assert resolved.hit.origin_id == 33
    assert result.traces[0].rule_applied == ResolutionRule.CATALOG
    trace_payload = result.traces[0].as_mapping()
    assert "extraction_path" not in trace_payload


@pytest.mark.asyncio
async def test_memory_resolver_trace_is_resolution_only():
    fixture = load_maio_contract_fixture()
    faturamento = KnowledgeHit(
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
    semantics = FactSemantics(
        fact_key="dynamic:faturamento_por_tipo_de_pagamento",
        aggregation_rule=AggregationRule.LOOKUP,
        comparator=Comparator.NONE,
        source_priority=(SourcePriority.KEY_METRICS,),
        value_kind="currency",
        memory_themes=("fechamento_gerencial",),
        key_metrics_keys=("faturamento_por_tipo_de_pagamento",),
        key_metrics_entity_field="tipo",
        key_metrics_value_field="valor",
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_por_tipo_de_pagamento",
        metric="faturamento",
        dimension="forma_pagamento",
        entity=None,
        period="2026-05",
        operation="comparison",
        matched_key="faturamento_por_tipo_de_pagamento",
        source_origin_id=33,
        source_context_key=faturamento.context_key,
        semantics=semantics,
    )

    resolver = MemoryResolver(FakeReader(), catalog=get_memory_catalog(), fallback=FallbackPolicy())
    result = await resolver.resolve((requirement,), ConhecimentoRecuperado(hits=(faturamento,)))

    assert len(result.traces) == 1
    assert set(result.traces[0].as_mapping().keys()) == {
        "fact_key",
        "resolved_from",
        "context_keys",
        "rule_applied",
        "semantics_version",
    }
    assert result.traces[0].rule_applied == ResolutionRule.CATALOG


@pytest.mark.asyncio
async def test_memory_resolver_source_origin_id_with_meta_exact_uses_catalog_rule():
    hit = KnowledgeHit(
        origin_id=31,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="10X parcelas",
        key_metrics={"parcelamento_de_cartao": {"rows": [], "_meta": {}}},
        score=None,
    )
    semantics = FactSemantics(
        fact_key="dynamic:parcelamento_de_cartao",
        aggregation_rule=AggregationRule.LOOKUP,
        comparator=Comparator.NONE,
        source_priority=(SourcePriority.KEY_METRICS,),
        value_kind="currency",
        key_metrics_keys=("parcelamento_de_cartao",),
    )
    requirement = FactRequirement(
        fact_key="dynamic:parcelamento_de_cartao",
        metric="faturamento",
        dimension="parcelas",
        entity="10X",
        period="2026-04",
        operation="summary",
        matched_key="parcelamento_de_cartao",
        match_method="meta_exact",
        source_origin_id=31,
        source_context_key=hit.context_key,
        semantics=semantics,
    )

    resolver = MemoryResolver(FakeReader(), catalog=get_memory_catalog(), fallback=FallbackPolicy())
    result = await resolver.resolve((requirement,), ConhecimentoRecuperado(hits=(hit,)))

    assert result.traces[0].rule_applied == ResolutionRule.CATALOG
    assert result.traces[0].as_mapping()["rule_applied"] == "catalog"
