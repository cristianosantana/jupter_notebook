"""Fase 4 — chunking, summarizer protocol, ChunkReducer, digest com proveniência."""

from __future__ import annotations

from orion_mcp_v3.broker.chunking import chunk_rows, estimate_chunk_tokens
from orion_mcp_v3.broker.reducers import ChunkReducer
from orion_mcp_v3.runtime.provenance import CoverageInfo


class _FakeSummarizer:
    def summarize_chunk(self, rows, chunk_index: int) -> str:
        return f"c{chunk_index}:n={len(rows)}"


def test_chunk_rows_by_row_cap() -> None:
    rows = [{"i": i} for i in range(10)]
    chunks = chunk_rows(rows, max_rows=3, max_tokens=100_000)
    assert len(chunks) == 4
    assert len(chunks[0]) == 3 and len(chunks[-1]) == 1


def test_chunk_rows_splits_on_token_budget() -> None:
    fat = "x" * 800
    rows = [{"a": fat}, {"b": "y"}, {"c": "z"}]
    tok_fat = estimate_chunk_tokens([rows[0]])
    chunks = chunk_rows(list(rows), max_rows=10, max_tokens=tok_fat)
    assert len(chunks) >= 2


def test_chunk_reducer_merge_and_provenance() -> None:
    chunks = [[{"v": 1}], [{"v": 2}, {"v": 3}]]
    r = ChunkReducer(_FakeSummarizer(), aggregation_logic="test_logic")
    d = r.reduce(chunks, base_coverage=CoverageInfo(labels={"src": "mysql"}))
    assert "c0:n=1" in d.summary and "c1:n=2" in d.summary
    assert d.volume == 3
    assert d.source_refs == ("chunk:0", "chunk:1")
    assert d.aggregation_logic == "test_logic"
    assert d.coverage.labels.get("chunk_count") == 2
    assert d.confidence is not None and 0.0 <= d.confidence <= 1.0


def test_distill_end_to_end() -> None:
    rows = [{"i": i} for i in range(20)]
    r = ChunkReducer(_FakeSummarizer())
    d = r.distill(rows, max_rows=5, max_tokens=10_000)
    assert d.volume == 20
    assert len(d.source_refs) >= 2
