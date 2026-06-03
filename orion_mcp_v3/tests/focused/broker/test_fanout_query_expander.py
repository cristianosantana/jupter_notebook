"""Fan-out heurístico: QueryExpander, execute_plan, EvidenceAggregator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from orion_mcp_v3.broker import (
    ANALYTICS_TEMPLATES,
    AnalyticsExecutor,
    AnalyticsResult,
    EvidenceAggregator,
    QueryExpander,
    build_query_plan,
    dedupe_plans,
)
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST
from orion_mcp_v3.broker.query_collections import QueryCollection, QueryCollectionCatalog, QueryCollectionItem
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan


@pytest.fixture
def allowlist():
    return ANALYTICS_ALLOWLIST


def test_high_confidence_single_plan(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        confidence=0.85,
        metrics=("revenue",),
    )
    plans = QueryExpander().expand(cp, allowlist)
    assert len(plans) == 1
    assert plans[0].intent_slug == "primary"


def test_medium_confidence_comparison(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.COMPARATIVE,
        needs_analytics=True,
        needs_comparison=True,
        needs_temporal_context=True,
        confidence=0.55,
        metrics=("revenue",),
    )
    plans = QueryExpander().expand(cp, allowlist)
    assert len(plans) == 2
    slugs = {p.intent_slug for p in plans}
    assert slugs == {"primary", "prior_period"}


def test_low_confidence_multi_metric(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        needs_temporal_context=True,
        confidence=0.3,
        metrics=("revenue", "ticket", "sales"),
    )
    plans = QueryExpander().expand(cp, allowlist)
    assert 3 <= len(plans) <= 4
    slugs = [p.intent_slug for p in plans]
    assert slugs[0] == "primary"
    assert "prior_period" in slugs
    assert "metric.ticket" in slugs


def test_baseline_angle(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        needs_baseline=True,
        confidence=0.55,
        metrics=("revenue",),
    )
    plans = QueryExpander().expand(cp, allowlist)
    assert len(plans) == 2
    assert {p.intent_slug for p in plans} == {"primary", "baseline"}


def test_dedupe_prevents_duplicates(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        confidence=0.85,
        metrics=("revenue",),
    )
    p = build_query_plan(cp, intent_slug="primary")
    dupes = [p, p]
    out = dedupe_plans(dupes, allowlist)
    assert len(out) == 1


def test_max_cap_four_plans(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.COMPARATIVE,
        needs_analytics=True,
        needs_comparison=True,
        needs_temporal_context=True,
        needs_baseline=True,
        confidence=0.2,
        metrics=("revenue", "ticket", "sales"),
    )
    plans = QueryExpander(max_plans=4).expand(cp, allowlist)
    assert len(plans) <= 4


def test_llm_query_selector_template_skips_generic_fanout(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        confidence=0.2,
        metrics=("vendas", "ticket_medio_os"),
        entities=("concessionaria",),
        hints={
            "template_slug": "performance_concessionaria",
            "selected_metric": "vendas",
            "selected_dimension": "concessionaria",
            "selected_operation": "ranking_desc",
            "semantic_reason": "llm_query_selector",
        },
    )

    plans = QueryExpander(registry=ANALYTICS_TEMPLATES).expand(
        cp,
        allowlist,
        query_text="cruze faturamento das concessionárias de janeiro a março",
    )

    assert len(plans) == 1
    assert plans[0].intent_slug == "template.performance_concessionaria"
    assert plans[0].hints["semantic_reason"] == "llm_query_selector"
    assert plans[0].hints["selected_dimension"] == "concessionaria"


def test_custom_query_collection_expands_two_templates_before_preferred_slug(allowlist) -> None:
    catalog = QueryCollectionCatalog(
        (
            QueryCollection(
                slug="colecao_generica",
                descriptions=("colecao analitica",),
                items=(
                    QueryCollectionItem("itens_vendidos"),
                    QueryCollectionItem("performance_concessionaria"),
                ),
            ),
        )
    )
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        confidence=0.8,
        hints={"template_slug": "itens_vendidos"},
    )

    plans = QueryExpander(registry=ANALYTICS_TEMPLATES, collections=catalog).expand(
        cp,
        allowlist,
        query_text="rode a colecao analitica completa",
    )

    assert [p.hints["template_slug"] for p in plans] == ["itens_vendidos", "performance_concessionaria"]
    assert {p.hints["collection_slug"] for p in plans} == {"colecao_generica"}


def test_llm_query_selector_template_propagates_result_scope_and_sort(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        confidence=0.8,
        metrics=("vendas",),
        entities=("item",),
        hints={
            "template_slug": "itens_vendidos",
            "selected_metric": "vendas",
            "selected_dimension": "item",
            "selected_operation": "ranking_desc",
            "result_scope": {"mode": "all", "limit": None},
            "sort": {"field": "vendas", "direction": "desc"},
            "semantic_reason": "llm_query_selector",
        },
    )

    plans = QueryExpander(registry=ANALYTICS_TEMPLATES).expand(
        cp,
        allowlist,
        query_text="total vendido, ordene do maior para o menor e inclua todos",
    )

    assert len(plans) == 1
    assert plans[0].hints["result_scope"] == {"mode": "all", "limit": None}
    assert plans[0].hints["sort"] == {"field": "vendas", "direction": "desc"}


def test_execute_plan_method(allowlist) -> None:
    mysql = MagicMock()
    mysql.select = AsyncMock(return_value=[{"id": 1, "total_faturamento": 42.0}])
    ex = AnalyticsExecutor(mysql, allowlist, default_limit=1000)
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        confidence=0.9,
        metrics=("revenue",),
    )
    plan = build_query_plan(cp, intent_slug="primary")

    async def run() -> None:
        r = await ex.execute_plan(plan)
        assert r.row_count == 1
        assert "SELECT" in r.sql
        assert r.plan.intent_slug == "primary"

    asyncio.run(run())


def test_evidence_aggregator_single_result(allowlist) -> None:
    cp = CognitivePlan(intent_type=IntentType.ANALYTICAL, needs_analytics=True, confidence=0.9)
    plan = build_query_plan(cp, intent_slug="primary")
    rows = [{"id": 1, "total_faturamento": 10.0}]
    ar = AnalyticsResult(plan=plan, sql="SELECT 1", rows=rows, row_count=1)
    block = EvidenceAggregator().merge([ar], value_key="total_faturamento", time_key=None)
    assert "total_faturamento" in block.summary or "Métrica" in block.summary


def test_evidence_aggregator_multiple_results(allowlist) -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        confidence=0.5,
        metrics=("revenue",),
    )
    p1 = build_query_plan(cp, intent_slug="primary")
    p2 = build_query_plan(cp, intent_slug="prior_period")
    p2 = SemanticQueryPlan(
        intent_slug="prior_period",
        strategy=p2.strategy,
        hints={**dict(p2.hints), "fanout_angle": "prior_period"},
        correlation_id=p2.correlation_id,
        analytics_strategy=p2.analytics_strategy,
    )
    r1 = AnalyticsResult(plan=p1, sql="A", rows=[{"id": 1, "total_faturamento": 100.0}], row_count=2)
    r2 = AnalyticsResult(plan=p2, sql="B", rows=[{"id": 2, "total_faturamento": 50.0}], row_count=3)
    block = EvidenceAggregator().merge([r1, r2], value_key="total_faturamento", time_key=None)
    assert "[primary]" in block.summary and "[prior_period]" in block.summary
    assert "fanout" in block.insights
    assert block.metrics.get("fanout", {}).get("total_input_rows") == 5
    assert block.coverage.labels


def test_full_fanout_pipeline(allowlist) -> None:
    mysql = MagicMock()
    mysql.select = AsyncMock(
        return_value=[
            {"id": 1, "cliente_id": 1, "total_faturamento": 100.0, "ticket_count": 3.0},
        ]
    )
    ex = AnalyticsExecutor(mysql, allowlist, default_limit=1000)
    cp = CognitivePlan(
        intent_type=IntentType.COMPARATIVE,
        needs_analytics=True,
        needs_comparison=True,
        needs_temporal_context=True,
        confidence=0.35,
        metrics=("revenue", "ticket"),
    )
    expander = QueryExpander()
    plans = expander.expand(cp, allowlist, query_text="últimos 3 meses")
    assert len(plans) >= 2

    async def run() -> None:
        results = await asyncio.gather(*[ex.execute_plan(p) for p in plans])
        block = EvidenceAggregator().merge(results, value_key="total_faturamento", time_key=None)
        assert len(block.summary) > 20
        assert "fanout" in block.metrics

    asyncio.run(run())
