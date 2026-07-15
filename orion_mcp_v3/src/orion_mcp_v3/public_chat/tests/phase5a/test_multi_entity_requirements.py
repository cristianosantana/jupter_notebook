"""Testes multi-entity e expansão period×entity no Fact Planner."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.domain.fact_engine.gap import GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import (
    AggregationRule,
    Comparator,
    FactSemantics,
    SourcePriority,
)
from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionRule
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_extractor import FactExtractor
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.tests.conftest import make_resolved_hit
from orion_mcp_v3.public_chat.tests.phase4.fixtures import load_maio_contract_fixture


def _payment_hit(*, origin_id: int, period: str, month_slug: str) -> KnowledgeHit:
    fixture = load_maio_contract_fixture()
    return KnowledgeHit(
        origin_id=origin_id,
        context_key=f"sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:periodo-{period}",
        category="Fechamento Gerencial",
        validated_answer=f"Faturamento por forma de pagamento em {month_slug}.",
        key_metrics={
            "faturamento_por_tipo_de_pagamento": fixture["key_metrics"][
                "faturamento_por_tipo_de_pagamento"
            ],
        },
        score=0.35,
    )


def _commission_hit(*, origin_id: int = 28) -> KnowledgeHit:
    return KnowledgeHit(
        origin_id=origin_id,
        context_key="sistema_background:fechamento_gerencial:comissao_tipo_os:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer="Comissão por tipo de OS e concessionária em maio.",
        key_metrics={
            "comissao_por_tipo_de_os_por_concessionaria": {
                "_meta": {
                    "dimension": "tipo_os",
                    "entity_field": "tipo_os",
                    "value_field": "valor_comissao",
                    "metric_kind": "commission",
                    "schema": "table",
                    "subdimension": "concessionaria",
                },
                "table_rows_sample": [
                    "Venda Normal - GWM BAMAQ: R$ 12.340,00",
                    "Financiamento - GWM BAMAQ: R$ 0,00",
                    "Venda Normal - Outra Loja: R$ 4.500,00",
                ],
            },
        },
        score=0.42,
    )


@pytest.mark.asyncio
async def test_planner_pix_and_cartao_same_period_two_entity_requirements():
    planner = FactPlanner(provider=None)
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-05",
        confidence=0.9,
        operation=PublicOperationType.COMPARISON.value,
        dimension="forma_pagamento",
        entity_filters=(
            EntityFilter(dimension="forma_pagamento", value="PIX"),
            EntityFilter(dimension="forma_pagamento", value="Cartão de Crédito"),
        ),
    )
    knowledge = ConhecimentoRecuperado(hits=(_payment_hit(origin_id=33, period="2026-05", month_slug="maio"),))

    result = await planner.plan(
        "compare PIX e cartão de crédito em maio de 2026",
        contract=contract,
        knowledge=knowledge,
    )

    assert len(result.requirements) == 2
    assert all(req.matched_key == "faturamento_por_tipo_de_pagamento" for req in result.requirements)
    assert all(req.source_origin_id == 33 for req in result.requirements)
    fact_keys = {req.fact_key for req in result.requirements}
    assert any("@pix" in key for key in fact_keys)
    assert any("cartao" in key for key in fact_keys)
    entities = {req.entity for req in result.requirements}
    assert entities == {"PIX", "Cartão de Crédito"}


@pytest.mark.asyncio
async def test_planner_venda_normal_financiamento_scope_concessionaria():
    planner = FactPlanner(provider=None)
    contract = IntentContract(
        intent="consulta_metrica",
        metric="commission",
        period="2026-05",
        confidence=0.88,
        operation=PublicOperationType.SUMMARY.value,
        dimension="tipo_os",
        entity_filters=(
            EntityFilter(dimension="concessionaria", value="GWM BAMAQ"),
            EntityFilter(dimension="tipo_os", value="Venda Normal"),
            EntityFilter(dimension="tipo_os", value="Financiamento"),
        ),
    )
    knowledge = ConhecimentoRecuperado(hits=(_commission_hit(),))

    result = await planner.plan(
        "comissão de venda normal e financiamento na GWM BAMAQ em maio",
        contract=contract,
        knowledge=knowledge,
    )

    assert len(result.requirements) == 2
    assert all(
        req.matched_key == "comissao_por_tipo_de_os_por_concessionaria"
        for req in result.requirements
    )
    assert all(
        req.scope_entities == (("concessionaria", "GWM BAMAQ"),)
        for req in result.requirements
    )
    matched_keys = {req.matched_key for req in result.requirements}
    assert "faturamento_e_comissao_por_concessionaria" not in matched_keys
    entities = {req.entity for req in result.requirements}
    assert entities == {"Venda Normal", "Financiamento"}


@pytest.mark.asyncio
async def test_planner_q7_expands_periods_without_collapsing_origin_id():
    planner = FactPlanner(provider=None)
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period=None,
        confidence=0.82,
        operation=PublicOperationType.COMPARISON.value,
        dimension="forma_pagamento",
        entity_filters=(
            EntityFilter(dimension="forma_pagamento", value="PIX"),
            EntityFilter(dimension="forma_pagamento", value="Cartão de Crédito"),
        ),
    )
    periods = ("2026-01", "2026-02", "2026-03", "2026-04", "2026-05")
    hits = tuple(
        _payment_hit(origin_id=10 + index, period=period, month_slug=period)
        for index, period in enumerate(periods)
    )
    knowledge = ConhecimentoRecuperado(hits=hits)

    result = await planner.plan(
        "em quais meses o PIX ultrapassou o cartão de crédito?",
        contract=contract,
        knowledge=knowledge,
    )

    assert len(result.requirements) == 10
    assert result.gaps == ()
    assert result.composite is True
    periods_found = {req.period for req in result.requirements}
    assert periods_found == set(periods)
    origin_ids = {req.source_origin_id for req in result.requirements}
    assert len(origin_ids) == 5
    assert all(req.period is not None for req in result.requirements)
    ambiguous = [
        gap for gap in result.gaps if gap.reason == GapReason.KEY_METRICS_INDEX_AMBIGUOUS
    ]
    assert not ambiguous


def _commission_matrix_hit(*, origin_id: int = 28) -> KnowledgeHit:
    return KnowledgeHit(
        origin_id=origin_id,
        context_key="sistema_background:fechamento_gerencial:comissao_por_concessionaria_tipo_os:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Comissão por tipo de OS e concessionária em abril.",
        key_metrics={
            "comissao_por_tipo_de_os_por_concessionaria": {
                "_meta": {
                    "dimension": "tipo_os",
                    "entity_field": "tipo_os",
                    "value_field": "valor_comissao",
                    "metric_kind": "commission",
                    "schema": "table",
                    "subdimension": "concessionaria",
                },
                "table_rows_sample": [
                    "GWM BAMAQ | Venda Normal: R$ 38.162,34 | Financiamento: R$ 0,00 | Total comissão: R$ 38.162,34",
                ],
            },
        },
        score=0.42,
    )


def test_extractor_financiamento_zero_matrix_format():
    hit = _commission_matrix_hit()
    requirement = FactRequirement(
        fact_key="dynamic:comissao_por_tipo_de_os_por_concessionaria@financiamento@2026-04",
        metric="comissao",
        dimension="tipo_os",
        entity="Financiamento",
        period="2026-04",
        operation="comparison",
        matched_key="comissao_por_tipo_de_os_por_concessionaria",
        scope_entities=(("concessionaria", "GWM BAMAQ"),),
        semantics=FactSemantics(
            fact_key="dynamic:comissao_por_tipo_de_os_por_concessionaria@financiamento@2026-04",
            aggregation_rule=AggregationRule.LOOKUP,
            comparator=Comparator.NONE,
            source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
            value_kind="currency",
            key_metrics_keys=("comissao_por_tipo_de_os_por_concessionaria",),
            key_metrics_entity_field="tipo_os",
            key_metrics_value_field="valor_comissao",
        ),
    )
    resolved = {
        requirement.fact_key: make_resolved_hit(
            hit,
            ResolutionRule.CATALOG,
            fact_key=requirement.fact_key,
        ),
    }

    result = FactExtractor().extract((requirement,), resolved)

    assert result.gaps == ()
    assert len(result.facts) == 1
    assert result.facts[0].value == "R$ 0,00"
    assert "Financiamento" in result.facts[0].label


def test_extractor_ranked_list_zero_value():
    fixture = load_maio_contract_fixture()
    hit = KnowledgeHit(
        origin_id=9,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:periodo-2026-02",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por forma de pagamento.",
        key_metrics={"faturamento_por_tipo_de_pagamento": fixture["key_metrics"]["faturamento_por_tipo_de_pagamento"]},
        score=0.3,
    )
    requirement = FactRequirement(
        fact_key="dynamic:faturamento_por_tipo_de_pagamento@cheque",
        metric="faturamento",
        dimension="forma_pagamento",
        entity="Cheque",
        period="2026-02",
        operation="lookup",
        matched_key="faturamento_por_tipo_de_pagamento",
        semantics=FactSemantics(
            fact_key="dynamic:faturamento_por_tipo_de_pagamento@cheque",
            aggregation_rule=AggregationRule.LOOKUP,
            comparator=Comparator.NONE,
            source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
            value_kind="currency",
            key_metrics_keys=("faturamento_por_tipo_de_pagamento",),
            key_metrics_entity_field="tipo",
            key_metrics_value_field="valor",
        ),
    )
    resolved = {
        requirement.fact_key: make_resolved_hit(
            hit,
            ResolutionRule.CATALOG,
            fact_key=requirement.fact_key,
        ),
    }

    result = FactExtractor().extract((requirement,), resolved)

    assert result.gaps == ()
    assert len(result.facts) == 1
    assert result.facts[0].value == "R$ 0,00"
    assert "Cheque" in result.facts[0].label


def test_extractor_financiamento_zero_with_scope():
    hit = _commission_hit()
    requirement = FactRequirement(
        fact_key="dynamic:comissao_por_tipo_de_os_por_concessionaria@financiamento@2026-05",
        metric="commission",
        dimension="tipo_os",
        entity="Financiamento",
        period="2026-05",
        operation="summary",
        matched_key="comissao_por_tipo_de_os_por_concessionaria",
        scope_entities=(("concessionaria", "GWM BAMAQ"),),
        semantics=FactSemantics(
            fact_key="dynamic:comissao_por_tipo_de_os_por_concessionaria@financiamento@2026-05",
            aggregation_rule=AggregationRule.LOOKUP,
            comparator=Comparator.NONE,
            source_priority=(SourcePriority.KEY_METRICS, SourcePriority.PARSED_TEXT),
            value_kind="currency",
            key_metrics_keys=("comissao_por_tipo_de_os_por_concessionaria",),
            key_metrics_entity_field="tipo_os",
            key_metrics_value_field="valor_comissao",
        ),
    )
    resolved = {
        requirement.fact_key: make_resolved_hit(
            hit,
            ResolutionRule.CATALOG,
            fact_key=requirement.fact_key,
        ),
    }

    result = FactExtractor().extract((requirement,), resolved)

    assert len(result.facts) == 1
    assert result.facts[0].value == "R$ 0,00"
    assert "Financiamento" in result.facts[0].label


@pytest.mark.asyncio
async def test_planner_ticket_medio_no_entity_from_predicate_filter():
    planner = FactPlanner(provider=None)
    contract = IntentContract(
        intent="consulta_metrica",
        metric="ticket_medio_comissao",
        period="2026-05",
        confidence=0.8,
        operation=PublicOperationType.LIST.value,
        dimension="concessionaria",
        entity_filters=(EntityFilter(dimension="comissao_financiamento", value=">0"),),
    )
    fixture = load_maio_contract_fixture()
    knowledge = ConhecimentoRecuperado(
        hits=(
            KnowledgeHit(
                origin_id=35,
                context_key="sistema_background:fechamento_gerencial:faturamento_por_concessionaria:periodo-2026-05",
                category="Fechamento Gerencial",
                validated_answer="Faturamento por concessionária em maio.",
                key_metrics={
                    "faturamento_e_comissao_por_concessionaria": fixture["key_metrics"][
                        "faturamento_e_comissao_por_concessionaria"
                    ],
                },
                score=0.31,
            ),
        ),
    )

    result = await planner.plan(
        "ticket médio de comissão por concessionária em maio com financiamento maior que zero",
        contract=contract,
        knowledge=knowledge,
    )

    assert all(req.entity != ">0" for req in result.requirements)
    assert all(req.entity is None for req in result.requirements)
    assert all(req.dimension == "concessionaria" for req in result.requirements)


def _parcelamento_hit(*, origin_id: int = 7) -> KnowledgeHit:
    return KnowledgeHit(
        origin_id=origin_id,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-01",
        category="Fechamento Gerencial",
        validated_answer="Parcelamento de cartão em janeiro.",
        key_metrics={
            "parcelamento_de_cartao": {
                "_meta": {
                    "dimension": "parcelas",
                    "entity_field": "parcelas",
                    "value_field": "valor",
                    "metric_kind": "revenue",
                    "schema": "ranked_list",
                },
                "rows": [
                    {"rank": "1", "parcelas": "10X", "valor": "R$ 681.772,80"},
                    {"rank": "2", "parcelas": "1X", "valor": "R$ 157.701,01"},
                ],
            },
        },
        score=0.29,
    )


@pytest.mark.asyncio
async def test_planner_parcelamento_discards_invalid_scope_dimensions():
    planner = FactPlanner(provider=None)
    contract = IntentContract(
        intent="comparacao",
        metric="vendas",
        period="2026-01",
        confidence=0.9,
        operation=PublicOperationType.COMPARISON.value,
        dimension="parcelas",
        entity_filters=(
            EntityFilter(dimension="forma_pagamento", value="cartao_de_credito"),
            EntityFilter(dimension="parcelas", value="1X"),
            EntityFilter(dimension="periodo", value="2026-06", match="exact"),
        ),
    )
    knowledge = ConhecimentoRecuperado(hits=(_parcelamento_hit(),))

    result = await planner.plan(
        "parcelas em cartão de crédito em janeiro",
        contract=contract,
        knowledge=knowledge,
    )

    assert len(result.requirements) >= 1
    requirement = result.requirements[0]
    assert requirement.matched_key == "parcelamento_de_cartao"
    scope_dims = {item[0] for item in requirement.scope_entities}
    assert "forma_pagamento" not in scope_dims
    assert "parcelas" not in scope_dims
    discarded_dims = {item["dimension"] for item in requirement.discarded_scope}
    assert "forma_pagamento" in discarded_dims


def test_extractor_parcelamento_ignores_forma_pagamento_scope():
    from orion_mcp_v3.public_chat.domain.key_metrics_introspection import (
        build_dynamic_requirement,
        build_key_metrics_index_from_hits,
    )

    hit = _parcelamento_hit()
    entry = build_key_metrics_index_from_hits((hit,))[0]
    contract = IntentContract(
        intent="comparacao",
        metric="vendas",
        period="2026-01",
        confidence=0.9,
        operation=PublicOperationType.COMPARISON.value,
        dimension="parcelas",
        entity_filters=(
            EntityFilter(dimension="forma_pagamento", value="cartao_de_credito"),
            EntityFilter(dimension="parcelas", value="1X"),
        ),
    )
    requirement = build_dynamic_requirement(
        entry,
        contract=contract,
        entity="1X",
        scope_entities=(
            ("forma_pagamento", "cartao_de_credito"),
            ("parcelas", "1X"),
        ),
        exclude_scope_dimensions=("parcelas",),
    )

    scope_dims = {item[0] for item in requirement.scope_entities}
    assert "forma_pagamento" not in scope_dims
    assert any(
        item.get("reason") == "not_in_schema"
        for item in requirement.discarded_scope
        if item.get("dimension") == "forma_pagamento"
    )

    resolved = {
        requirement.fact_key: make_resolved_hit(
            hit,
            ResolutionRule.CATALOG,
            fact_key=requirement.fact_key,
        ),
    }
    result = FactExtractor().extract((requirement,), resolved)

    assert len(result.facts) == 1
    assert result.facts[0].value == "R$ 157.701,01"
    assert result.gaps == ()
