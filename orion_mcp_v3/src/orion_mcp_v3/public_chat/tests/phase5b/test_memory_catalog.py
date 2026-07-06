"""Testes de matching tema via ``context_key`` canónico."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import FallbackPolicy
from orion_mcp_v3.public_chat.domain.fact_engine.gap import GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionRule
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


def test_fallback_policy_prefers_vector_order_over_catalog_sql_order() -> None:
    """Catalog filtra elegibilidade; vector search define qual hit usar."""
    catalog = get_memory_catalog()
    hit_comissao = KnowledgeHit(
        origin_id=67,
        context_key="sistema_background:fechamento_gerencial:comissao_por_concessionaria:2026-05",
        category="Fechamento Gerencial",
        validated_answer="GWM BAMAQ: R$ 43.584,46",
        key_metrics={"faturamento_e_comissao_por_concessionaria": {"rows": [], "_meta": {}}},
        score=0.13,
    )
    hit_taxas = KnowledgeHit(
        origin_id=70,
        context_key="sistema_background:fechamento_gerencial:taxas_cartao_credito:2026-05",
        category="Fechamento Gerencial",
        validated_answer="MFP: R$ 775,07",
        key_metrics={"taxas_cartao_credito": {"rows": [], "_meta": {}}},
        score=0.44,
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_e_comissao_por_concessionaria",
        metric="comissoes",
        dimension="concessionaria",
        entity=None,
        period="2026-05",
        operation="ranking_desc",
        semantics=FactSemantics(
            fact_key="dynamic:faturamento_e_comissao_por_concessionaria",
            aggregation_rule=AggregationRule.MAX,
            comparator=Comparator.DESC,
            source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
            value_kind="currency",
            allows_multiple_values=True,
            memory_themes=("fechamento_gerencial", "fechamento_gerencial_mensal"),
            key_metrics_keys=("faturamento_e_comissao_por_concessionaria",),
            key_metrics_entity_field="concessionaria",
            key_metrics_value_field="valor_comissao",
        ),
    )

    # SQL ORDER BY id DESC colocaria taxas (70) antes de comissão (67)
    catalog_hits = [hit_taxas, hit_comissao]
    # Vector search ranqueou comissão como mais relevante
    vector_hits = [hit_comissao, hit_taxas]

    result = FallbackPolicy().resolve_from_hits(
        requirement,
        catalog_hits=catalog_hits,
        vector_hits=vector_hits,
        catalog=catalog,
    )

    assert result.hit is not None
    assert result.hit.hit.origin_id == 67
    assert result.hit.rule == ResolutionRule.VECTOR_RETRIEVAL


def test_fallback_policy_filters_catalog_by_required_key_metrics_key() -> None:
    catalog = get_memory_catalog()
    hit_taxas = KnowledgeHit(
        origin_id=32,
        context_key="sistema_background:fechamento_gerencial:taxas_cartao_credito:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Taxas de cartão em abril.",
        key_metrics={"taxas_cartao_credito": {"rows": [], "_meta": {}}},
        score=None,
    )
    hit_faturamento = KnowledgeHit(
        origin_id=28,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por tipo de venda em abril.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
        score=None,
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_por_tipo_de_venda:2026-04",
        metric="faturamento",
        dimension="tipo_de_venda",
        entity=None,
        period="2026-04",
        operation="comparison",
        matched_key="faturamento_por_tipo_de_venda",
        semantics=FactSemantics(
            fact_key="dynamic:faturamento_por_tipo_de_venda:2026-04",
            aggregation_rule=AggregationRule.LOOKUP,
            comparator=Comparator.NONE,
            source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
            value_kind="currency",
            memory_themes=("fechamento_gerencial", "fechamento_gerencial_mensal"),
            key_metrics_keys=("faturamento_por_tipo_de_venda",),
            key_metrics_entity_field="tipo",
            key_metrics_value_field="valor",
        ),
    )

    result = FallbackPolicy().resolve_from_hits(
        requirement,
        catalog_hits=[hit_taxas, hit_faturamento],
        vector_hits=[],
        catalog=catalog,
    )

    assert result.hit is not None
    assert result.hit.hit.origin_id == 28
    assert result.hit.rule == ResolutionRule.CATALOG


def test_fallback_policy_rejects_vector_hit_from_wrong_period() -> None:
    catalog = get_memory_catalog()
    maio = KnowledgeHit(
        origin_id=34,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por tipo de venda em maio.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
        score=0.12,
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_por_tipo_de_venda:2026-04",
        metric="faturamento",
        dimension="tipo_de_venda",
        entity=None,
        period="2026-04",
        operation="comparison",
        matched_key="faturamento_por_tipo_de_venda",
        semantics=FactSemantics(
            fact_key="dynamic:faturamento_por_tipo_de_venda:2026-04",
            aggregation_rule=AggregationRule.LOOKUP,
            comparator=Comparator.NONE,
            source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
            value_kind="currency",
            memory_themes=("fechamento_gerencial", "fechamento_gerencial_mensal"),
            key_metrics_keys=("faturamento_por_tipo_de_venda",),
        ),
    )

    result = FallbackPolicy().resolve_from_hits(
        requirement,
        catalog_hits=[],
        vector_hits=[maio],
        catalog=catalog,
    )

    assert result.hit is None
    assert result.gap is not None
    assert result.gap.reason.value == "memory_exists_but_no_match"


def test_fallback_policy_rejects_origin_id_70_for_comissao_requirement() -> None:
    """Regressão: taxas (70) não pode satisfazer requirement de comissão por concessionária."""
    catalog = get_memory_catalog()
    hit_taxas = KnowledgeHit(
        origin_id=70,
        context_key="sistema_background:fechamento_gerencial:taxas_cartao_credito:2026-05",
        category="Fechamento Gerencial",
        validated_answer="MFP: R$ 775,07",
        key_metrics={"taxas_cartao_credito": {"rows": [], "_meta": {}}},
        score=0.44,
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_e_comissao_por_concessionaria",
        metric="comissoes",
        dimension="concessionaria",
        entity=None,
        period="2026-05",
        operation="ranking_desc",
        matched_key="faturamento_e_comissao_por_concessionaria",
        semantics=FactSemantics(
            fact_key="dynamic:faturamento_e_comissao_por_concessionaria",
            aggregation_rule=AggregationRule.MAX,
            comparator=Comparator.DESC,
            source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
            value_kind="currency",
            allows_multiple_values=True,
            memory_themes=("fechamento_gerencial", "fechamento_gerencial_mensal"),
            key_metrics_keys=("faturamento_e_comissao_por_concessionaria",),
            key_metrics_entity_field="concessionaria",
            key_metrics_value_field="valor_comissao",
        ),
    )

    result = FallbackPolicy().resolve_from_hits(
        requirement,
        catalog_hits=[hit_taxas],
        vector_hits=[hit_taxas],
        catalog=catalog,
    )

    assert result.hit is None
    assert result.gap is not None
    assert result.gap.reason == GapReason.MEMORY_EXISTS_BUT_NO_MATCH
    assert "vector_retrieval" in result.gap.attempted_rules
