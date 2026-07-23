"""Testes do Fact Extractor (5C)."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.direct_answer_parser import parse_validated_answer, ranking_row, find_section_by_needle
from orion_mcp_v3.public_chat.tests.conftest import make_resolved_hit
from orion_mcp_v3.public_chat.domain.fact_engine.models import ExtractedFact, FactRequirement
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


def test_fact_extractor_cross_period_decline_reconstructs_truncated_rows() -> None:
    """Maior queda: rows truncadas + validated_answer → PeriodDelta BAMAQ - OFICINA ~−61%."""
    from orion_mcp_v3.public_chat.domain.analytical_plan import AnalyticalGoal, AnalyticalPlan
    from orion_mcp_v3.public_chat.domain.knowledge_composer import compose_knowledge
    from orion_mcp_v3.public_chat.domain.requirements_graph import build_requirements_graph

    jan_answer = (
        "Comissões por concessionária em PERIODO_2026-01: "
        "SAITAMA - HONDA: R$ 33.828,00 (10,95%); GWM BAMAQ: R$ 30.660,52 (9,92%); "
        "BAMAQ - OFICINA: R$ 1.503,60 (0,49%); XTREME CAR DETAIL: R$ 0,00 (0,00%)."
    )
    mai_answer = (
        "Comissões por concessionária em PERIODO_2026-05: "
        "GWM BAMAQ: R$ 43.584,46 (11,61%); SAITAMA - HONDA: R$ 36.398,90 (9,69%); "
        "BAMAQ - OFICINA: R$ 583,52 (0,16%); XTREME CAR DETAIL: R$ 0,00 (0,00%)."
    )
    jan_hit = KnowledgeHit(
        origin_id=4,
        context_key="sistema_background:fechamento_gerencial:comissao_por_concessionaria:periodo-2026-01",
        category="Fechamento Gerencial",
        validated_answer=jan_answer,
        key_metrics={
            "faturamento_e_comissao_por_concessionaria": {
                "rows": [
                    {"concessionaria": "SAITAMA - HONDA", "valor_comissao": "R$ 33.828,00 (10,95%)"},
                    {"concessionaria": "GWM BAMAQ", "valor_comissao": "R$ 30.660,52 (9,92%)"},
                ],
                "_meta": {
                    "entity_field": "concessionaria",
                    "value_field": "valor_comissao",
                    "total_original_rows": 4,
                    "truncated_head_tail": True,
                },
            }
        },
    )
    mai_hit = KnowledgeHit(
        origin_id=37,
        context_key="sistema_background:fechamento_gerencial:comissao_por_concessionaria:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer=mai_answer,
        key_metrics={
            "faturamento_e_comissao_por_concessionaria": {
                "rows": [
                    {"concessionaria": "GWM BAMAQ", "valor_comissao": "R$ 43.584,46 (11,61%)"},
                    {"concessionaria": "SAITAMA - HONDA", "valor_comissao": "R$ 36.398,90 (9,69%)"},
                ],
                "_meta": {
                    "entity_field": "concessionaria",
                    "value_field": "valor_comissao",
                    "total_original_rows": 4,
                    "truncated_head_tail": True,
                },
            }
        },
    )

    def _req(period: str, origin_id: int) -> FactRequirement:
        key = f"dynamic:faturamento_e_comissao_por_concessionaria@{period}"
        return FactRequirement(
            fact_key=key,
            metric="comissao",
            dimension="concessionaria",
            entity=None,
            period=period,
            operation="period_decline",
            matched_key="faturamento_e_comissao_por_concessionaria",
            source_origin_id=origin_id,
            semantics=FactSemantics(
                fact_key=key,
                aggregation_rule=AggregationRule.MIN,
                comparator=Comparator.ASC,
                source_priority=(SourcePriority.KEY_METRICS,),
                value_kind="currency",
                allows_multiple_values=True,
                key_metrics_keys=("faturamento_e_comissao_por_concessionaria",),
            ),
        )

    req_jan = _req("2026-01", 4)
    req_mai = _req("2026-05", 37)
    resolved = {
        req_jan.fact_key: make_resolved_hit(jan_hit, ResolutionRule.CATALOG, fact_key=req_jan.fact_key),
        req_mai.fact_key: make_resolved_hit(mai_hit, ResolutionRule.CATALOG, fact_key=req_mai.fact_key),
    }
    leaf = FactExtractor().extract((req_jan, req_mai), resolved)
    assert leaf.facts == ()
    plan = AnalyticalPlan(
        goal=AnalyticalGoal.PERIOD_DELTA,
        operation="period_decline",
        dimension="concessionaria",
        metric="comissao",
        periods=("2026-01", "2026-05"),
        sort_direction="asc",
        confidence=0.9,
    )
    graph = build_requirements_graph((req_jan, req_mai), plan)
    composition = compose_knowledge(graph=graph, leaf_facts=leaf.facts, resolved=resolved)
    assert len(composition.facts) == 1
    fact = composition.facts[0]
    assert fact.label == "BAMAQ - OFICINA"
    assert fact.unit == "pct"
    assert "61" in fact.value
    assert fact.trace.extraction_path.value == "ranking_derived"
    assert composition.source_truncated is False
    assert composition.computed[0]["kind"] == "PeriodDelta"


def test_knowledge_composer_leader_change_not_growth() -> None:
    """leader_change materializa líderes por período — nunca @growth%."""
    from orion_mcp_v3.public_chat.domain.analytical_plan import AnalyticalGoal, AnalyticalPlan
    from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType
    from orion_mcp_v3.public_chat.domain.fact_engine.trace import ExtractionPath, FactTrace
    from orion_mcp_v3.public_chat.domain.knowledge_composer import compose_knowledge
    from orion_mcp_v3.public_chat.domain.requirements_graph import build_requirements_graph

    def _req(period: str) -> FactRequirement:
        key = f"dynamic:producao_por_servico@{period}"
        return FactRequirement(
            fact_key=key,
            metric="vendas",
            dimension="servico",
            entity=None,
            period=period,
            operation="leader_change",
            matched_key="producao_por_servico",
            semantics=FactSemantics(
                fact_key=key,
                aggregation_rule=AggregationRule.MAX,
                comparator=Comparator.DESC,
                source_priority=(SourcePriority.KEY_METRICS,),
                value_kind="currency",
                allows_multiple_values=True,
                key_metrics_keys=("producao_por_servico",),
            ),
        )

    req_mai = _req("2026-05")
    req_jun = _req("2026-06")
    leaf_facts = (
        ExtractedFact(
            fact_key=req_mai.fact_key,
            label="PPF REGENERATIVO - FULL - CARRO INTEIRO",
            value="R$ 445.373,50",
            unit="BRL",
            fact_type=FactType.RAW,
            confidence=0.9,
            origin_id=39,
            context_key="maio",
            trace=FactTrace(
                fact_key=req_mai.fact_key,
                resolved_from=(39,),
                context_keys=("maio",),
                rule_applied=ResolutionRule.CATALOG,
                extraction_path=ExtractionPath.KEY_METRICS,
            ),
        ),
        ExtractedFact(
            fact_key=req_jun.fact_key,
            label="PPF REGENERATIVO - FULL - CARRO INTEIRO",
            value="R$ 505.735,00",
            unit="BRL",
            fact_type=FactType.RAW,
            confidence=0.9,
            origin_id=47,
            context_key="junho",
            trace=FactTrace(
                fact_key=req_jun.fact_key,
                resolved_from=(47,),
                context_keys=("junho",),
                rule_applied=ResolutionRule.CATALOG,
                extraction_path=ExtractionPath.KEY_METRICS,
            ),
        ),
    )
    plan = AnalyticalPlan(
        goal=AnalyticalGoal.LEADER_COMPARISON,
        operation="leader_change",
        dimension="servico",
        metric="vendas",
        periods=("2026-05", "2026-06"),
        sort_direction="desc",
        confidence=0.9,
    )
    graph = build_requirements_graph((req_mai, req_jun), plan)
    composition = compose_knowledge(graph=graph, leaf_facts=leaf_facts, resolved={})
    assert composition.computed[0]["kind"] == "LeaderComparison"
    assert composition.computed[0]["changed"] is False
    assert not any("@growth:" in f.fact_key for f in composition.facts)
    assert any("leader_change" in f.fact_key for f in composition.facts)
    assert not any(
        isinstance(item, dict) and item.get("kind") == "PeriodDelta"
        for item in composition.computed
    )


def test_structural_period_delta_from_comparison_cells() -> None:
    """comparison + 2 FactCells mesma entidade/períodos → PeriodDelta sem period_growth."""
    from orion_mcp_v3.public_chat.domain.analytical_plan import AnalyticalGoal, AnalyticalPlan
    from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType
    from orion_mcp_v3.public_chat.domain.fact_engine.trace import ExtractionPath, FactTrace
    from orion_mcp_v3.public_chat.domain.knowledge_composer import compose_knowledge
    from orion_mcp_v3.public_chat.domain.requirements_graph import build_requirements_graph

    def _req(period: str, entity: str) -> FactRequirement:
        slug = entity.lower().replace(" ", "_").replace("á", "a").replace("é", "e")
        key = f"dynamic:faturamento_por_tipo_de_pagamento@{slug}@{period}"
        return FactRequirement(
            fact_key=key,
            metric="faturamento",
            dimension="forma_pagamento",
            entity=entity,
            period=period,
            operation="comparison",
            matched_key="faturamento_por_tipo_de_pagamento",
            semantics=FactSemantics(
                fact_key=key,
                aggregation_rule=AggregationRule.LOOKUP,
                comparator=Comparator.NONE,
                source_priority=(SourcePriority.KEY_METRICS,),
                value_kind="currency",
                key_metrics_keys=("faturamento_por_tipo_de_pagamento",),
            ),
        )

    req_jan = _req("2026-01", "Cartão de Crédito")
    req_jun = _req("2026-06", "Cartão de Crédito")
    leaf = (
        ExtractedFact(
            fact_key=req_jan.fact_key,
            label="Cartão de Crédito",
            value="R$ 1.143.256,71 (53,06%)",
            unit="BRL",
            fact_type=FactType.RAW,
            confidence=0.95,
            origin_id=1,
            context_key="jan",
            trace=FactTrace(
                fact_key=req_jan.fact_key,
                resolved_from=(1,),
                context_keys=("jan",),
                rule_applied=ResolutionRule.CATALOG,
                extraction_path=ExtractionPath.KEY_METRICS,
            ),
        ),
        ExtractedFact(
            fact_key=req_jun.fact_key,
            label="Cartão de Crédito",
            value="R$ 1.168.481,75 (41,97%)",
            unit="BRL",
            fact_type=FactType.RAW,
            confidence=0.95,
            origin_id=2,
            context_key="jun",
            trace=FactTrace(
                fact_key=req_jun.fact_key,
                resolved_from=(2,),
                context_keys=("jun",),
                rule_applied=ResolutionRule.CATALOG,
                extraction_path=ExtractionPath.KEY_METRICS,
            ),
        ),
    )
    plan = AnalyticalPlan(
        goal=AnalyticalGoal.COMPARISON,
        operation="comparison",
        dimension="forma_pagamento",
        metric="faturamento",
        periods=("2026-01", "2026-06"),
        sort_direction=None,
        confidence=0.9,
    )
    graph = build_requirements_graph((req_jan, req_jun), plan)
    composition = compose_knowledge(graph=graph, leaf_facts=leaf, resolved={})
    deltas = [c for c in composition.computed if isinstance(c, dict) and c.get("kind") == "PeriodDelta"]
    assert len(deltas) == 1
    assert deltas[0]["label"] == "Cartão de Crédito"
    assert deltas[0]["period_from"] == "2026-01"
    assert deltas[0]["period_to"] == "2026-06"
    assert abs(deltas[0]["value"] - 2.2064) < 0.01


def test_structural_period_delta_two_entities_comparison() -> None:
    """Cortesia vs Prestação: um PeriodDelta por label (fev→jun)."""
    from orion_mcp_v3.public_chat.domain.analytical_plan import AnalyticalGoal, AnalyticalPlan
    from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType
    from orion_mcp_v3.public_chat.domain.fact_engine.trace import ExtractionPath, FactTrace
    from orion_mcp_v3.public_chat.domain.knowledge_composer import compose_knowledge
    from orion_mcp_v3.public_chat.domain.requirements_graph import build_requirements_graph

    def _req(period: str, entity: str) -> FactRequirement:
        slug = (
            entity.lower()
            .replace(" ", "_")
            .replace("á", "a")
            .replace("ã", "a")
            .replace("ç", "c")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
        )
        key = f"dynamic:faturamento_por_tipo_de_venda@{slug}@{period}"
        return FactRequirement(
            fact_key=key,
            metric="faturamento",
            dimension="tipo_venda",
            entity=entity,
            period=period,
            operation="comparison",
            matched_key="faturamento_por_tipo_de_venda",
            semantics=FactSemantics(
                fact_key=key,
                aggregation_rule=AggregationRule.LOOKUP,
                comparator=Comparator.NONE,
                source_priority=(SourcePriority.KEY_METRICS,),
                value_kind="currency",
                key_metrics_keys=("faturamento_por_tipo_de_venda",),
            ),
        )

    entities = ("Cortesia Concessionária", "Prestação de Serviços")
    periods = ("2026-02", "2026-06")
    values = {
        ("Cortesia Concessionária", "2026-02"): "R$ 114.128,00",
        ("Cortesia Concessionária", "2026-06"): "R$ 150.829,00",
        ("Prestação de Serviços", "2026-02"): "R$ 583.264,04",
        ("Prestação de Serviços", "2026-06"): "R$ 889.298,02",
    }
    reqs: list[FactRequirement] = []
    leaf: list[ExtractedFact] = []
    oid = 1
    for entity in entities:
        for period in periods:
            req = _req(period, entity)
            reqs.append(req)
            leaf.append(
                ExtractedFact(
                    fact_key=req.fact_key,
                    label=entity,
                    value=values[(entity, period)],
                    unit="BRL",
                    fact_type=FactType.RAW,
                    confidence=0.95,
                    origin_id=oid,
                    context_key=period,
                    trace=FactTrace(
                        fact_key=req.fact_key,
                        resolved_from=(oid,),
                        context_keys=(period,),
                        rule_applied=ResolutionRule.CATALOG,
                        extraction_path=ExtractionPath.KEY_METRICS,
                    ),
                )
            )
            oid += 1

    plan = AnalyticalPlan(
        goal=AnalyticalGoal.COMPARISON,
        operation="comparison",
        dimension="tipo_venda",
        metric="faturamento",
        periods=periods,
        sort_direction=None,
        confidence=0.9,
    )
    composition = compose_knowledge(
        graph=build_requirements_graph(tuple(reqs), plan),
        leaf_facts=tuple(leaf),
        resolved={},
    )
    deltas = {
        c["label"]: c
        for c in composition.computed
        if isinstance(c, dict) and c.get("kind") == "PeriodDelta"
    }
    assert set(deltas) == set(entities)
    assert abs(deltas["Cortesia Concessionária"]["value"] - 32.16) < 0.1
    assert abs(deltas["Prestação de Serviços"]["value"] - 52.47) < 0.1

