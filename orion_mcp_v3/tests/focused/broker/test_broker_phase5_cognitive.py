"""Bloco 5 ORDEM_IMPLEMENTAÇÃO — aggregators/samplers/reducers como estruturas cognitivas."""

from __future__ import annotations

from orion_mcp_v3.broker import (
    aggregate_groups,
    aggregate_ranking,
    aggregate_temporal_series,
    insights_from_numeric_spread,
    merge_cognitive_artifacts,
    normalize_metrics,
    sample_outliers_structured,
    sample_recent_structured,
    sample_stratified_keys,
)
from orion_mcp_v3.contracts.cognitive_artifact import CognitiveArtifact


def test_aggregate_groups_no_raw_rows_in_summary() -> None:
    rows = [{"k": "a", "v": 1}, {"k": "a", "v": 2}, {"k": "b", "v": 3}]
    art = aggregate_groups(rows, "k")
    assert isinstance(art, CognitiveArtifact)
    assert art.kind == "aggregation.group_by"
    assert art.summary["cardinality_by_group"] == {"a": 2, "b": 1}
    assert "rows" not in art.summary
    assert 0.35 <= art.confidence <= 0.95
    assert art.coverage.labels.get("rows_in") == 3
    assert len(art.provenance) == 1


def test_aggregate_temporal_series() -> None:
    rows = [
        {"d": "2024-01-15", "amt": 10},
        {"d": "2024-02-01", "amt": 7},
    ]
    art = aggregate_temporal_series(rows, time_key="d", value_key="amt")
    assert art.summary["period_count"] == 2
    assert art.confidence > 0.35


def test_aggregate_ranking_slim_without_full_rows() -> None:
    rows = [
        {"id": 1, "rev": 10.0},
        {"id": 2, "rev": 99.0},
        {"id": 3, "rev": 5.0},
    ]
    art = aggregate_ranking(rows, value_key="rev", n=2, rank_id_key="id")
    ranked = art.summary["ranked"]
    assert ranked[0]["rank"] == 1 and ranked[0]["ref"] == 2
    assert set(ranked[0].keys()) <= {"rank", "score", "ref"}


def test_normalize_metrics() -> None:
    rows = [{"x": 1}, {"x": 3}, {"x": 5}]
    art = normalize_metrics(rows, ("x",))
    assert art.summary["metrics"]["x"]["mean"] == 3.0


def test_sample_recent_structured_projection() -> None:
    rows = [
        {"d": "2024-01-01", "id": 1},
        {"d": "2024-03-01", "id": 2},
        {"d": "2024-02-01", "id": 3},
    ]
    art = sample_recent_structured(rows, time_key="d", k=2, projection_keys=("id",))
    assert len(art.summary["sample_projection"]) == 2
    assert all("id" in p for p in art.summary["sample_projection"])


def test_sample_outliers_structured() -> None:
    rows = [{"v": 0.0}, {"v": 0.0}, {"v": 100.0}]
    art = sample_outliers_structured(rows, value_key="v", k=1)
    assert art.summary["picked_count"] == 1


def test_sample_stratified_keys() -> None:
    rows = [{"region": "N", "id": 1}, {"region": "N", "id": 2}, {"region": "S", "id": 3}]
    art = sample_stratified_keys(rows, strata_key="region", per_stratum=1)
    assert art.summary["strata_count"] == 2


def test_merge_cognitive_artifacts() -> None:
    a = aggregate_groups([{"k": "x"}], "k")
    b = normalize_metrics([{"z": 1.0}], ("z",))
    m = merge_cognitive_artifacts(a, b)
    assert m.kind == "reduction.merge"
    assert len(m.summary["parts"]) == 2


def test_insights_from_numeric_spread() -> None:
    art = insights_from_numeric_spread(label="rev", low=1.0, high=100.0, mean=10.0)
    assert art.summary["interpretation"] == "alta_variabilidade"

