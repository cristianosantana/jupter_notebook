"""Fase 3 — planner, compilador SQL, agregadores, samplers, digest."""

from __future__ import annotations

import pytest

from orion_mcp_v3.broker import (
    SqlAllowlist,
    SqlCompilationError,
    build_query_plan,
    compile_select,
    group_by,
    infer_aggregation_hints,
    infer_analytics_strategy,
    outlier_sampler,
    plan_from_natural_language,
    recent_sampler,
    time_series,
    top_n,
)
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy, RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.runtime.provenance import CoverageInfo


def test_planner_temporal_pt() -> None:
    h = infer_aggregation_hints("mostre os últimos 3 meses de vendas")
    assert h.get("aggregation_kind") == "temporal"
    assert h.get("time_grain") == "month"
    assert h.get("lookback_months") == 3


def test_planner_ranking_en() -> None:
    h = infer_aggregation_hints("top 10 customers by revenue")
    assert h.get("aggregation_kind") == "ranking"
    assert h.get("rank_dimension") == "client"
    assert h.get("top_n") == 10


def test_plan_from_nl_sets_broker_fanout() -> None:
    p = plan_from_natural_language("últimos meses")
    assert p.strategy == RetrievalStrategy.BROKER_FANOUT
    assert p.hints.get("aggregation_kind") == "temporal"
    assert p.analytics_strategy == AnalyticsStrategy.TEMPORAL


def test_build_query_plan_from_cognitive_temporal() -> None:
    cp = CognitivePlan(
        intent_type=IntentType.TEMPORAL,
        needs_temporal_context=True,
        needs_analytics=False,
    )
    p = build_query_plan(cp, query_text="últimos 2 meses", intent_slug="analytics.generic")
    assert p.analytics_strategy == AnalyticsStrategy.TEMPORAL
    assert p.hints.get("lookback_months") == 2


def test_infer_analytics_strategy_ranking_from_nl_hints() -> None:
    cp = CognitivePlan(intent_type=IntentType.ANALYTICAL, needs_analytics=True)
    h = infer_aggregation_hints("top 5 clientes")
    assert infer_analytics_strategy(cp, h) == AnalyticsStrategy.RANKING


def test_infer_analytics_strategy_monitoring_anomaly() -> None:
    cp = CognitivePlan(intent_type=IntentType.MONITORING, needs_analytics=False)
    assert infer_analytics_strategy(cp, {}) == AnalyticsStrategy.ANOMALY


def test_infer_analytics_strategy_comparison() -> None:
    cp = CognitivePlan(
        intent_type=IntentType.COMPARATIVE,
        needs_comparison=True,
        needs_analytics=True,
    )
    assert infer_analytics_strategy(cp, {}) == AnalyticsStrategy.COMPARISON


def test_compile_select_basic() -> None:
    allow = SqlAllowlist(
        tables=frozenset({"sales"}),
        columns_by_table={"sales": frozenset({"id", "amount", "day"})},
    )
    plan = SemanticQueryPlan(
        intent_slug="x",
        strategy=RetrievalStrategy.EXACT_LOOKUP,
        hints={
            "sql_table": "sales",
            "sql_columns": ("day", "amount"),
            "limit": 50,
        },
    )
    c = compile_select(plan, allow)
    assert "SELECT" in c.sql and "FROM" in c.sql
    assert "LIMIT %s" in c.sql
    assert c.params[-1] == 50


def test_compile_select_rejects_unknown_table() -> None:
    allow = SqlAllowlist(
        tables=frozenset({"sales"}),
        columns_by_table={"sales": frozenset({"amount"})},
    )
    plan = SemanticQueryPlan(
        intent_slug="x",
        strategy=RetrievalStrategy.EXACT_LOOKUP,
        hints={"sql_table": "other", "sql_columns": ("amount",)},
    )
    with pytest.raises(SqlCompilationError):
        compile_select(plan, allow)


def test_compile_select_where_in() -> None:
    allow = SqlAllowlist(
        tables=frozenset({"sales"}),
        columns_by_table={"sales": frozenset({"region", "amount"})},
    )
    plan = SemanticQueryPlan(
        intent_slug="x",
        strategy=RetrievalStrategy.EXACT_LOOKUP,
        hints={
            "sql_table": "sales",
            "sql_columns": ("amount",),
            "sql_filters": [{"column": "region", "op": "IN", "value": ["N", "S"]}],
            "limit": 10,
        },
    )
    c = compile_select(plan, allow)
    assert " IN " in c.sql
    assert c.params[:-1] == ("N", "S")


def test_group_by() -> None:
    rows = [
        {"k": "a", "v": 1},
        {"k": "a", "v": 2},
        {"k": "b", "v": 3},
    ]
    g = group_by(rows, "k")
    assert set(g.keys()) == {"a", "b"}
    assert len(g["a"]) == 2


def test_time_series_month() -> None:
    rows = [
        {"d": "2024-01-15", "amt": 10},
        {"d": "2024-01-20", "amt": 5},
        {"d": "2024-02-01", "amt": 7},
    ]
    ts = time_series(rows, time_key="d", value_key="amt", grain="month")
    assert [x["period"] for x in ts] == ["2024-01", "2024-02"]
    assert ts[0]["total"] == 15.0


def test_top_n_grouped() -> None:
    rows = [
        {"client": "A", "rev": 10},
        {"client": "A", "rev": 5},
        {"client": "B", "rev": 30},
    ]
    out = top_n(rows, value_key="rev", n=2, group_key="client")
    assert out[0]["client"] == "B"
    assert out[0]["total"] == 30.0
    assert out[1]["total"] == 15.0


def test_recent_sampler() -> None:
    rows = [
        {"d": "2024-01-01", "x": 1},
        {"d": "2024-03-01", "x": 2},
        {"d": "2024-02-01", "x": 3},
    ]
    s = recent_sampler(rows, time_key="d", k=2)
    assert [r["x"] for r in s] == [2, 3]


def test_outlier_sampler_zscore() -> None:
    rows = [{"v": 0.0}, {"v": 0.0}, {"v": 100.0}]
    o = outlier_sampler(rows, value_key="v", k=1)
    assert len(o) == 1
    assert o[0]["v"] == 100.0


def test_analytical_digest_contract() -> None:
    cov = CoverageInfo(labels={"table": "sales"}, notes="partial")
    d = AnalyticalDigest(
        summary="média 42",
        volume=1000,
        sample=({"a": 1},),
        coverage=cov,
    )
    assert d.volume == 1000
    assert d.coverage.labels["table"] == "sales"
