"""Testes de matching tema via ``context_key`` canónico."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import FallbackPolicy
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import (
    AggregationRule,
    Comparator,
    FactSemantics,
    SourcePriority,
)
from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit
from orion_mcp_v3.public_chat.domain.memory_catalog import context_key_theme_slug, get_memory_catalog


def test_context_key_theme_slug_reads_canonical_segment() -> None:
    context_key = "sistema_background:fechamento_gerencial:fechamento_de_maio_de_2026:maio-2026"

    assert context_key_theme_slug(context_key) == "fechamento_gerencial"


def test_context_key_matches_theme_uses_context_key_not_category_label() -> None:
    catalog = get_memory_catalog()
    context_key = "sistema_background:fechamento_gerencial:fechamento_de_maio_de_2026:maio-2026"

    assert catalog.context_key_matches_theme(context_key, "fechamento_gerencial")


def test_context_key_matches_theme_ignores_misleading_category_metadata() -> None:
    catalog = get_memory_catalog()
    context_key = "sistema_background:fechamento_gerencial:fechamento_de_maio_de_2026:maio-2026"

    assert catalog.context_key_matches_theme(context_key, "fechamento_gerencial")
    assert not catalog.context_key_matches_theme(context_key, "vendas_departamento")


def test_fallback_policy_resolves_hit_from_context_key_when_category_is_human_label() -> None:
    catalog = get_memory_catalog()
    hit = KnowledgeHit(
        origin_id=1,
        context_key="sistema_background:fechamento_gerencial:fechamento_de_maio_de_2026:maio-2026",
        category="fechamento gerencial",
        validated_answer="PIX: R$ 394.350,70",
        key_metrics={},
        score=0.85,
    )
    requirement = FactRequirement(
        fact_key="ranking_forma_pagamento",
        metric="faturamento",
        dimension="forma_pagamento",
        entity="PIX",
        period="2026-05",
        operation="summary",
        semantics=FactSemantics(
            fact_key="ranking_forma_pagamento",
            aggregation_rule=AggregationRule.MIN,
            comparator=Comparator.ASC,
            source_priority=(SourcePriority.STRUCTURED, SourcePriority.PARSED_TEXT),
            value_kind="currency",
            allows_multiple_values=True,
        ),
    )

    result = FallbackPolicy().resolve_from_hits(
        requirement,
        catalog_hits=[],
        vector_hits=[hit],
        catalog=catalog,
    )

    assert result.hit is not None
    assert result.hit.hit.origin_id == 1
    assert result.gap is None


def test_fallback_policy_does_not_match_when_only_category_label_aligns() -> None:
    catalog = get_memory_catalog()
    hit = KnowledgeHit(
        origin_id=2,
        context_key="sistema_background:vendas_departamento:oficina:2026-05",
        category="fechamento gerencial",
        validated_answer="n/d",
        key_metrics={},
        score=0.9,
    )
    requirement = FactRequirement(
        fact_key="ranking_forma_pagamento",
        metric="faturamento",
        dimension="forma_pagamento",
        entity=None,
        period="2026-05",
        operation="summary",
        semantics=FactSemantics(
            fact_key="ranking_forma_pagamento",
            aggregation_rule=AggregationRule.MIN,
            comparator=Comparator.ASC,
            source_priority=(SourcePriority.STRUCTURED,),
            value_kind="currency",
            allows_multiple_values=True,
        ),
    )

    result = FallbackPolicy().resolve_from_hits(
        requirement,
        catalog_hits=[],
        vector_hits=[hit],
        catalog=catalog,
    )

    assert result.hit is None
    assert result.gap is not None
    assert result.gap.reason.value == "memory_exists_but_no_match"
