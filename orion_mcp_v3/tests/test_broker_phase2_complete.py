"""Fase 2 — broker cognitivo completo (planner semântico, samplers, reducers, map-reduce, evidence)."""

from __future__ import annotations

from orion_mcp_v3.broker import (
    AnomalyReducer,
    ComparisonReducer,
    EvidenceBuilder,
    RankingReducer,
    RecentSampler,
    TopKSampler,
    TrendReducer,
    build_semantic_retrieval_plan,
    distill_by_analytics_strategy,
    infer_retrieval_mode_flags,
    order_primary_retrieval_steps,
)
from orion_mcp_v3.contracts import SemanticRetrievalPlan
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy


class _StubSummarizer:
    def summarize_chunk(self, rows: list[dict], chunk_index: int) -> str:
        return f"c{chunk_index}:{len(rows)}"


def test_build_semantic_retrieval_plan_queda_de_vendas_chain() -> None:
    cp = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        needs_temporal_context=True,
    )
    srp = build_semantic_retrieval_plan(
        cp,
        query_text="queda de vendas nos últimos 3 meses",
        correlation_id="t2-queda",
    )
    assert isinstance(srp, SemanticRetrievalPlan)
    assert srp.trend_analysis is True
    assert srp.anomaly_scan is True
    assert "temporal_series" in srp.primary_steps
    assert srp.query_plan.hints.get("primary_steps")
    assert srp.query_plan.hints.get("retrieval_modes")


def test_infer_retrieval_mode_flags_ranking_only() -> None:
    cp = CognitivePlan(intent_type=IntentType.ANALYTICAL, needs_analytics=True)
    flags = infer_retrieval_mode_flags(cp, {"aggregation_kind": "ranking"}, query_text="top 5 clientes")
    assert flags["ranking"] is True
    steps = order_primary_retrieval_steps(flags)
    assert "ranking" in steps


def test_recent_sampler_class_metadata() -> None:
    rows = [
        {"d": "2024-01-01", "x": 1},
        {"d": "2024-03-01", "x": 2},
    ]
    r = RecentSampler(time_key="d", k=1).sample(rows)
    assert r.sample_strategy == "recent"
    assert r.omitted_rows == 1
    assert r.coverage.labels.get("picked") == 1


def test_top_k_sampler_class() -> None:
    rows = [{"id": 1, "v": 10.0}, {"id": 2, "v": 20.0}]
    r = TopKSampler(value_key="v", k=1).sample(rows)
    assert len(r.rows) == 1
    assert r.rows[0]["v"] == 20.0


def test_trend_reducer_digest_provenance() -> None:
    rows = [
        {"d": "2024-01-10", "amt": 1.0},
        {"d": "2024-02-05", "amt": 2.0},
    ]
    d = TrendReducer().reduce(rows, time_key="d", value_key="amt")
    assert "2024-01" in d.summary and "2024-02" in d.summary
    assert d.aggregation_logic == "trend_reducer_v1"
    assert d.source_refs
    assert d.confidence is not None


def test_ranking_reducer() -> None:
    rows = [{"id": 1, "rev": 5.0}, {"id": 2, "rev": 50.0}]
    d = RankingReducer().reduce(rows, value_key="rev", n=1)
    assert "50" in d.summary or "50.0" in d.summary


def test_comparison_reducer() -> None:
    rows = [
        {"d": "2024-01-01", "x": 10.0},
        {"d": "2024-02-01", "x": 20.0},
    ]
    d = ComparisonReducer().reduce(rows, time_key="d", value_key="x")
    assert "Comparação" in d.summary


def test_distill_by_analytics_strategy_trend() -> None:
    rows = [{"d": "2024-01-01", "amt": 1.0}, {"d": "2024-02-01", "amt": 3.0}]
    d = distill_by_analytics_strategy(
        rows,
        _StubSummarizer(),
        strategy=AnalyticsStrategy.TREND,
        time_key="d",
        value_key="amt",
        max_rows=50,
        max_tokens=2000,
    )
    assert d.aggregation_logic == "trend_reducer_v1"


def test_distill_by_analytics_strategy_fallback_map_reduce() -> None:
    rows = [{"a": float(i)} for i in range(15)]
    d = distill_by_analytics_strategy(
        rows,
        _StubSummarizer(),
        strategy=AnalyticsStrategy.TREND,
        time_key=None,
        value_key="a",
        max_rows=5,
        max_tokens=500,
    )
    assert d.aggregation_logic is not None and "map_reduce" in d.aggregation_logic


def test_evidence_comparisons_and_scoring_metrics() -> None:
    rows = [
        {"id": 1, "created_at": "2024-01-15", "amt": 100.0},
        {"id": 2, "created_at": "2024-02-10", "amt": 150.0},
    ]
    b = EvidenceBuilder().build(rows, value_key="amt", time_key="created_at")
    assert b.insights["comparisons"]["status"] == "ok"
    assert "confidence_scoring" in b.metrics
    assert "coverage_scoring" in b.metrics


def test_anomaly_reducer_smoke() -> None:
    rows = [{"v": 0.0}, {"v": 0.0}, {"v": 99.0}]
    d = AnomalyReducer().reduce(rows, value_key="v", k=2)
    assert d.aggregation_logic == "anomaly_reducer_v1"
    assert len(d.sample) >= 1
