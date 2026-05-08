"""Bloco 7 ORDEM_IMPLEMENTAÇÃO — map-reduce semântico, cobertura, DriftGuard."""

from __future__ import annotations

from orion_mcp_v3.broker import distill_with_semantic_merge, semantic_merge_sections
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.runtime import DriftGuard, merge_coverage_infos, merge_provenance_anchors
from orion_mcp_v3.runtime.provenance import CoverageInfo, ProvenanceAnchor


class _SumSummarizer:
    def summarize_chunk(self, rows: list, chunk_index: int) -> str:
        return f"n={len(rows)}"


def test_semantic_merge_sections_shapes_output() -> None:
    s = semantic_merge_sections(["a", "b"])
    assert "### chunk 0" in s and "a" in s and "### chunk 1" in s


def test_distill_with_semantic_merge_changes_summary() -> None:
    rows = [{"x": i} for i in range(10)]
    d = distill_with_semantic_merge(
        rows,
        _SumSummarizer(),
        max_rows=3,
        max_tokens=100_000,
        semantic_merge=lambda xs: "||".join(xs),
    )
    assert "||" in d.summary
    assert d.aggregation_logic == "map_reduce_semantic_v1"


def test_merge_coverage_infos_layers() -> None:
    a = CoverageInfo(labels={"k": 1}, notes="a")
    b = CoverageInfo(labels={"k": 2}, notes="b")
    m = merge_coverage_infos(a, b)
    assert m.labels["layer_0_k"] == 1
    assert m.labels["layer_1_k"] == 2


def test_merge_provenance_dedupes() -> None:
    p1 = ProvenanceAnchor(artifact_id="x", source="s")
    p2 = ProvenanceAnchor(artifact_id="x", source="s")
    out = merge_provenance_anchors((p1,), (p2,))
    assert len(out) == 1


def test_drift_guard_detects_confidence_drop() -> None:
    g = DriftGuard(confidence_drop_threshold=0.1)
    prev = AnalyticalDigest(summary="a", volume=10, confidence=0.9)
    curr = AnalyticalDigest(summary="b", volume=10, confidence=0.5)
    r = g.evaluate(prev, curr)
    assert r.refresh_recommended is True
    assert any(s.code == "confidence_drop" for s in r.signals)


def test_drift_guard_clean_when_similar() -> None:
    g = DriftGuard(volume_change_ratio=100.0)
    prev = AnalyticalDigest(summary="a", volume=100, confidence=0.8)
    curr = AnalyticalDigest(summary="b", volume=105, confidence=0.79)
    r = g.evaluate(prev, curr)
    assert not r.signals
