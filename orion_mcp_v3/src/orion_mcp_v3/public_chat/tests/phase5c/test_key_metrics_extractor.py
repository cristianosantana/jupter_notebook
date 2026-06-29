"""Testes de leitura nativa de key_metrics e extração dimensional."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.fact_engine.requirement_kind import RequirementKind
from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import ResolvedMemoryHit
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import (
    AggregationRule,
    Comparator,
    FactSemantics,
    SourcePriority,
)
from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionRule
from orion_mcp_v3.public_chat.domain.fact_extractor import FactExtractor
from orion_mcp_v3.public_chat.domain.fact_requirements import fact_keys_for_contract
from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract
from orion_mcp_v3.public_chat.domain.key_metrics_reader import lookup_entity, rows_from_key_metrics_entry
from orion_mcp_v3.public_chat.tests.phase4.fixtures import maio_hit


def test_rows_from_array_parses_dimensional_payment_metrics() -> None:
    hit = maio_hit()
    rows = rows_from_key_metrics_entry(
        "faturamento_por_tipo_de_pagamento",
        hit.key_metrics["faturamento_por_tipo_de_pagamento"],
    )

    assert len(rows) == 8
    pix = lookup_entity(rows, "PIX")
    assert pix is not None
    assert pix.value == 394350.70


def test_fact_extractor_lookup_pix_from_key_metrics_dynamic() -> None:
    hit = maio_hit()
    from orion_mcp_v3.public_chat.domain.key_metrics_introspection import build_dynamic_requirement, build_key_metrics_index

    index = build_key_metrics_index(hit.key_metrics)
    payment = next(entry for entry in index if entry.key == "faturamento_por_tipo_de_pagamento")
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        dimension="forma_pagamento",
        period="2026-05",
        operation="summary",
        entity_filters=(EntityFilter(dimension="forma_pagamento", value="PIX"),),
        confidence=0.95,
    )
    requirement = build_dynamic_requirement(payment, contract=contract)
    resolved = {
        requirement.fact_key: ResolvedMemoryHit(hit=hit, rule=ResolutionRule.VECTOR_RETRIEVAL),
    }

    result = FactExtractor().extract((requirement,), resolved)

    assert len(result.facts) == 1
    assert result.facts[0].label == "PIX"
    assert "394.350,70" in result.facts[0].value
    assert result.facts[0].trace.extraction_path.value == "key_metrics"
    assert not result.gaps
    assert requirement.requirement_kind == RequirementKind.LOOKUP


def test_fact_extractor_lookup_pix_from_key_metrics() -> None:
    hit = maio_hit()
    semantics = FactSemantics(
        fact_key="faturamento_forma_pagamento",
        aggregation_rule=AggregationRule.LOOKUP,
        comparator=Comparator.NONE,
        source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
        value_kind="currency",
        key_metrics_keys=("faturamento_por_tipo_de_pagamento",),
        key_metrics_entity_field="tipo",
        key_metrics_value_field="valor",
    )
    requirement = FactRequirement(
        fact_key="faturamento_forma_pagamento",
        metric="faturamento",
        dimension="forma_pagamento",
        entity="PIX",
        period="2026-05",
        operation="summary",
        semantics=semantics,
    )
    resolved = {
        "faturamento_forma_pagamento": ResolvedMemoryHit(hit=hit, rule=ResolutionRule.VECTOR_RETRIEVAL),
    }

    result = FactExtractor().extract((requirement,), resolved)

    assert len(result.facts) == 1
    assert result.facts[0].label == "PIX"
    assert "394.350,70" in result.facts[0].value
    assert result.facts[0].trace.extraction_path.value == "key_metrics"
    assert not result.gaps


def test_fact_extractor_ranking_from_key_metrics_array() -> None:
    hit = maio_hit()
    semantics = FactSemantics(
        fact_key="ranking_forma_pagamento",
        aggregation_rule=AggregationRule.MIN,
        comparator=Comparator.ASC,
        source_priority=(SourcePriority.KEY_METRICS, SourcePriority.STRUCTURED),
        value_kind="currency",
        allows_multiple_values=True,
        key_metrics_keys=("faturamento_por_tipo_de_pagamento",),
    )
    requirement = FactRequirement(
        fact_key="ranking_forma_pagamento",
        metric="faturamento",
        dimension="forma_pagamento",
        entity=None,
        period="2026-05",
        operation="ranking_asc",
        semantics=semantics,
    )
    resolved = {
        "ranking_forma_pagamento": ResolvedMemoryHit(hit=hit, rule=ResolutionRule.VECTOR_RETRIEVAL),
    }

    result = FactExtractor().extract((requirement,), resolved)

    assert len(result.facts) == 1
    assert result.facts[0].label == "Permuta"
    assert result.facts[0].trace.extraction_path.value == "key_metrics"


def test_fact_keys_for_pix_question_plans_lookup_not_ranking() -> None:
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        dimension="forma_pagamento",
        period="2026-05",
        operation="summary",
        entity_filters=(EntityFilter(dimension="forma_pagamento", value="PIX"),),
        confidence=0.95,
    )

    keys = fact_keys_for_contract(contract, "quanto recebemos por PIX em maio de 2026?")

    assert keys == ("faturamento_forma_pagamento",)
