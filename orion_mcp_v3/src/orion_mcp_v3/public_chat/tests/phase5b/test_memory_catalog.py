"""Testes de matching categoria ↔ tema no catálogo de memória."""

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
from orion_mcp_v3.public_chat.domain.memory_catalog import get_memory_catalog


def test_category_matches_theme_accepts_human_readable_category_label() -> None:
    catalog = get_memory_catalog()

    assert catalog.category_matches_theme("fechamento gerencial", "fechamento_gerencial")


def test_category_matches_theme_uses_context_key_category_segment() -> None:
    catalog = get_memory_catalog()
    context_key = "sistema_background:fechamento_gerencial:fechamento_de_maio_de_2026:maio-2026"

    assert catalog.category_matches_theme(
        "categoria irrelevante",
        "fechamento_gerencial",
        context_key=context_key,
    )


def test_fallback_policy_resolves_hit_with_spaced_category_label() -> None:
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
