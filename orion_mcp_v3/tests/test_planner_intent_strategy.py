"""Contratos planner: ``CognitivePlan`` → ``SemanticQueryPlan`` / ``AnalyticsStrategy``."""

from __future__ import annotations

from orion_mcp_v3.broker.planner import build_query_plan, infer_analytics_strategy
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy, RetrievalStrategy
from orion_mcp_v3.runtime.intent_resolver import IntentResolver


def _resolve_and_plan(message: str):
    cognitive = IntentResolver().resolve(message)
    plan = build_query_plan(cognitive, query_text=message)
    return cognitive, plan


def test_ranking_question_maps_to_ranking_strategy() -> None:
    cognitive, plan = _resolve_and_plan("Quais os top 5 clientes por faturamento nos últimos 3 meses?")
    assert cognitive.needs_analytics
    assert plan.analytics_strategy == AnalyticsStrategy.RANKING
    assert plan.strategy == RetrievalStrategy.BROKER_FANOUT
    assert plan.hints.get("rank_dimension") == "client"
    assert plan.hints.get("time_grain") == "month"


def test_decline_question_signals_comparison_or_trend() -> None:
    cognitive, plan = _resolve_and_plan("Houve queda de vendas no último mês versus o anterior?")
    assert cognitive.needs_analytics or cognitive.needs_comparison or cognitive.needs_trend_analysis
    strat = plan.analytics_strategy
    assert strat in (
        AnalyticsStrategy.COMPARISON,
        AnalyticsStrategy.TREND,
        AnalyticsStrategy.TEMPORAL,
        AnalyticsStrategy.RANKING,
    )


def test_monitoring_intent_prefers_anomaly_strategy() -> None:
    cognitive = CognitivePlan(
        intent_type=IntentType.MONITORING,
        needs_analytics=True,
        confidence=0.7,
    )
    strat = infer_analytics_strategy(cognitive, {})
    assert strat == AnalyticsStrategy.ANOMALY


def test_conversational_plan_avoids_broker_fanout() -> None:
    cognitive = CognitivePlan(
        intent_type=IntentType.CONVERSATIONAL,
        needs_analytics=False,
        needs_memory=True,
        confidence=0.6,
        retrieval_strategy=RetrievalStrategy.KEYWORD,
    )
    plan = build_query_plan(cognitive, query_text="Olá, como estás?")
    assert plan.strategy == RetrievalStrategy.KEYWORD
    assert plan.analytics_strategy is None
