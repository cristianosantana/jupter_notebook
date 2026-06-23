"""Testes do Fact Extractor (5C)."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.direct_answer_parser import parse_validated_answer, ranking_row, find_section_by_needle
from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import ResolvedMemoryHit
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import FactSemantics, AggregationRule, Comparator, SourcePriority
from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionRule
from orion_mcp_v3.public_chat.domain.fact_extractor import FactExtractor
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
        "ranking_forma_pagamento": ResolvedMemoryHit(hit=hit, rule=ResolutionRule.CATALOG),
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
        "faturamento_total_periodo": ResolvedMemoryHit(hit=hit, rule=ResolutionRule.CATALOG),
    }
    result = FactExtractor().extract((requirement,), resolved)
    assert len(result.facts) == 1
    assert result.facts[0].confidence == 0.95
