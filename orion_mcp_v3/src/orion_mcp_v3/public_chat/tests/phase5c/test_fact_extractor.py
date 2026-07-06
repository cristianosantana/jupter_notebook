"""Testes do Fact Extractor (5C)."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.direct_answer_parser import parse_validated_answer, ranking_row, find_section_by_needle
from orion_mcp_v3.public_chat.tests.conftest import make_resolved_hit
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import FactSemantics, AggregationRule, Comparator, SourcePriority
from orion_mcp_v3.public_chat.domain.fact_engine.gap import GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionRule
from orion_mcp_v3.public_chat.domain.fact_extractor import FactExtractor
from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit
from orion_mcp_v3.public_chat.tests.phase4.fixtures import FECHAMENTO_MARCO_2026, march_hit


def test_direct_answer_parser_ranking_asc():
    sections = parse_validated_answer(FECHAMENTO_MARCO_2026)
    section = find_section_by_needle(sections, "formas de pagamento", "forma de pagamento")
    assert section is not None
    row = ranking_row(section, ascending=True)
    assert row is not None
    assert "Depósito Bancário" in row.label or "Deposito Bancario" in row.label
    assert row.value == 3690.0


def test_fact_extractor_ranking_forma_pagamento():
    hit = march_hit()
    semantics = FactSemantics(
        fact_key="ranking_forma_pagamento",
        aggregation_rule=AggregationRule.MIN,
        comparator=Comparator.ASC,
        source_priority=(SourcePriority.STRUCTURED, SourcePriority.PARSED_TEXT),
        value_kind="currency",
        allows_multiple_values=True,
    )
    requirement = FactRequirement(
        fact_key="ranking_forma_pagamento",
        metric="faturamento",
        dimension="forma_pagamento",
        entity=None,
        period="2026-03",
        operation="ranking_asc",
        semantics=semantics,
    )
    resolved = {
        "ranking_forma_pagamento": make_resolved_hit(
            hit, ResolutionRule.CATALOG, fact_key="ranking_forma_pagamento"
        ),
    }
    result = FactExtractor().extract((requirement,), resolved)
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert "Depósito Bancário" in fact.label or "Deposito" in fact.label
    assert fact.confidence >= 0.65
    assert fact.trace.extraction_path.value == "ranking_derived"


def test_fact_extractor_faturamento_total_key_metrics():
    hit = march_hit()
    semantics = FactSemantics(
        fact_key="faturamento_total_periodo",
        aggregation_rule=AggregationRule.LOOKUP,
        comparator=Comparator.NONE,
        source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
        value_kind="currency",
        key_metrics_keys=("faturamento_liquido",),
    )
    requirement = FactRequirement(
        fact_key="faturamento_total_periodo",
        metric="faturamento",
        dimension=None,
        entity=None,
        period="2026-03",
        operation=None,
        semantics=semantics,
    )
    resolved = {
        "faturamento_total_periodo": make_resolved_hit(
            hit, ResolutionRule.CATALOG, fact_key="faturamento_total_periodo"
        ),
    }
    result = FactExtractor().extract((requirement,), resolved)
    assert len(result.facts) == 1
    assert result.facts[0].confidence == 0.95


def test_fact_extractor_sums_cortesia_group_from_tipo_venda_key_metrics():
    hit = KnowledgeHit(
        origin_id=42,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-06",
        category="Fechamento Gerencial",
        validated_answer="",
        key_metrics={
            "faturamento_por_tipo_de_venda": {
                "rows": [
                    {"tipo": "Venda Normal", "valor": "R$ 1.609.424,25 (57,76%)", "percentual": "57,76%"},
                    {"tipo": "Prestação de Serviços", "valor": "R$ 889.298,02 (31,91%)", "percentual": "31,91%"},
                    {"tipo": "Cortesia Concessionária", "valor": "R$ 150.829,00 (5,41%)", "percentual": "5,41%"},
                    {"tipo": "Financiamento", "valor": "R$ 130.880,00 (4,70%)", "percentual": "4,70%"},
                    {"tipo": "Cortesia Funcionário", "valor": "R$ 6.028,60 (0,22%)", "percentual": "0,22%"},
                ],
                "_meta": {
                    "schema": "ranked_list",
                    "dimension": "tipo_de_venda",
                    "metric_kind": "revenue",
                    "value_field": "valor",
                    "entity_field": "tipo",
                },
            },
        },
    )
    semantics = FactSemantics(
        fact_key="dynamic:faturamento_por_tipo_de_venda",
        aggregation_rule=AggregationRule.LOOKUP,
        comparator=Comparator.NONE,
        source_priority=(SourcePriority.KEY_METRICS,),
        value_kind="currency",
        key_metrics_keys=("faturamento_por_tipo_de_venda",),
        key_metrics_entity_field="tipo",
        key_metrics_value_field="valor",
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_por_tipo_de_venda",
        metric="faturamento",
        dimension="tipo_de_venda",
        entity="cortesias",
        period="2026-06",
        operation="summary",
        semantics=semantics,
    )

    result = FactExtractor().extract(
        (requirement,),
        {
            "dynamic:faturamento_por_tipo_de_venda": make_resolved_hit(
                hit,
                ResolutionRule.VECTOR_RETRIEVAL,
                fact_key="dynamic:faturamento_por_tipo_de_venda",
            )
        },
    )

    assert len(result.facts) == 1
    assert result.facts[0].label == "cortesias"
    assert result.facts[0].value == "R$ 156.857,60"


def test_fact_extractor_lookup_parcelas_5x_from_parcelamento_key_metrics():
    hit = KnowledgeHit(
        origin_id=31,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="",
        key_metrics={
            "parcelamento_de_cartao": {
                "rows": [
                    {"parcelas": "10X", "valor": "R$ 682.982,00 (62,58%)", "percentual": "62,58%"},
                    {"parcelas": "5X", "valor": "R$ 29.515,90 (2,70%)", "percentual": "2,70%"},
                ],
                "_meta": {
                    "schema": "ranked_list",
                    "dimension": "parcelas",
                    "metric_kind": "revenue",
                    "value_field": "valor",
                    "entity_field": "parcelas",
                },
            },
        },
    )
    semantics = FactSemantics(
        fact_key="dynamic:parcelamento_de_cartao",
        aggregation_rule=AggregationRule.LOOKUP,
        comparator=Comparator.NONE,
        source_priority=(SourcePriority.KEY_METRICS,),
        value_kind="currency",
        key_metrics_keys=("parcelamento_de_cartao",),
        key_metrics_entity_field="parcelas",
        key_metrics_value_field="valor",
    )
    requirement = FactRequirement(
        fact_key="dynamic:parcelamento_de_cartao",
        metric="faturamento",
        dimension="parcelas",
        entity="5X",
        period="2026-04",
        operation="summary",
        semantics=semantics,
    )

    result = FactExtractor().extract(
        (requirement,),
        {
            "dynamic:parcelamento_de_cartao": make_resolved_hit(
                hit,
                ResolutionRule.VECTOR_RETRIEVAL,
                fact_key="dynamic:parcelamento_de_cartao",
            )
        },
    )

    assert len(result.facts) == 1
    assert result.facts[0].label == "5X"
    assert result.facts[0].value == "R$ 29.515,90 (2,70%)"
    assert result.facts[0].trace.extraction_path.value == "key_metrics"
    assert result.facts[0].trace.rule_applied == ResolutionRule.VECTOR_RETRIEVAL


def test_fact_extractor_gap_includes_attempted_rules_from_resolution_trace():
    hit = KnowledgeHit(
        origin_id=70,
        context_key="sistema_background:fechamento_gerencial:taxas_cartao_credito:2026-05",
        category="Fechamento Gerencial",
        validated_answer="Taxas de cartão.",
        key_metrics={"taxas_cartao_credito": {"rows": [], "_meta": {}}},
    )
    semantics = FactSemantics(
        fact_key="dynamic:faturamento_e_comissao_por_concessionaria",
        aggregation_rule=AggregationRule.MAX,
        comparator=Comparator.DESC,
        source_priority=(SourcePriority.KEY_METRICS,),
        value_kind="currency",
        key_metrics_keys=("faturamento_e_comissao_por_concessionaria",),
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_e_comissao_por_concessionaria",
        metric="comissoes",
        dimension="concessionaria",
        entity=None,
        period="2026-05",
        operation="ranking_desc",
        matched_key="faturamento_e_comissao_por_concessionaria",
        semantics=semantics,
    )
    resolved = {
        requirement.fact_key: make_resolved_hit(
            hit,
            ResolutionRule.CATALOG,
            fact_key=requirement.fact_key,
        ),
    }

    result = FactExtractor().extract((requirement,), resolved)

    assert not result.facts
    assert len(result.gaps) == 1
    gap = result.gaps[0]
    assert gap.reason == GapReason.MEMORY_EXISTS_BUT_NO_MATCH
    assert gap.attempted_rules == ("catalog",)
    assert gap.resolution_trace is not None
    assert gap.resolution_trace.rule_applied == ResolutionRule.CATALOG
