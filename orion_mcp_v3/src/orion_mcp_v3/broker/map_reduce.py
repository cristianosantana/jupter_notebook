"""
Map-reduce analítico (ORDEM_IMPLEMENTAÇÃO §7): chunk summarization, merge semântico,
agregação de cobertura sobre :class:`~AnalyticalDigest`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from orion_mcp_v3.broker.chunking import chunk_rows
from orion_mcp_v3.broker.reducers import (
    AnomalyReducer,
    ChunkReducer,
    ComparisonReducer,
    RankingReducer,
    TrendReducer,
)
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy
from orion_mcp_v3.protocols.summarizer import SummarizerProtocol
from orion_mcp_v3.runtime.provenance import CoverageInfo, merge_coverage_infos


def semantic_merge_sections(summaries: list[str], *, header: str = "###") -> str:
    """Fusão semântica por defeito: secções etiquetadas (substituível por modelo ou regras)."""
    parts = [f"{header} chunk {i}\n{s}" for i, s in enumerate(summaries)]
    return "\n\n".join(parts)


def distill_with_semantic_merge(
    rows: list[dict[str, Any]],
    summarizer: SummarizerProtocol,
    *,
    max_rows: int,
    max_tokens: int,
    semantic_merge: Callable[[list[str]], str] | None = None,
    base_coverage: CoverageInfo | None = None,
    extra_coverages: Sequence[CoverageInfo] | None = None,
    aggregation_logic: str | None = None,
) -> AnalyticalDigest:
    """
    Partição em chunks → mini-resumos → fusão (concat ou ``semantic_merge``) → digest.

    Se ``extra_coverages`` for dado, funde com a cobertura do digest via
    :func:`orion_mcp_v3.runtime.provenance.merge_coverage_infos`.
    """
    chunks = chunk_rows(rows, max_rows=max_rows, max_tokens=max_tokens)
    logic = aggregation_logic or (
        "map_reduce_semantic_v1" if semantic_merge is not None else "map_reduce_concat_v1"
    )
    reducer = ChunkReducer(
        summarizer,
        aggregation_logic=logic,
        semantic_merge=semantic_merge,
    )
    digest = reducer.reduce(chunks, base_coverage=base_coverage)
    if extra_coverages:
        cov = merge_coverage_infos(*extra_coverages, digest.coverage)
        digest = replace(digest, coverage=cov)
    return digest


def distill_by_analytics_strategy(
    rows: list[dict[str, Any]],
    summarizer: SummarizerProtocol,
    *,
    strategy: AnalyticsStrategy,
    time_key: str | None = None,
    value_key: str = "amount",
    group_key: str | None = None,
    rank_n: int = 8,
    max_rows: int = 500,
    max_tokens: int = 8000,
    semantic_merge: Callable[[list[str]], str] | None = None,
    base_coverage: CoverageInfo | None = None,
    extra_coverages: Sequence[CoverageInfo] | None = None,
    aggregation_logic_fallback: str | None = None,
) -> AnalyticalDigest:
    """
    Escolhe reducer cognitivo (Fase 2.3–2.4) conforme :class:`~AnalyticsStrategy`;
    recai em :func:`distill_with_semantic_merge` quando não houver chaves suficientes.
    """
    digest: AnalyticalDigest
    if strategy in (AnalyticsStrategy.TREND, AnalyticsStrategy.TEMPORAL) and time_key:
        digest = TrendReducer().reduce(rows, time_key=time_key, value_key=value_key)
    elif strategy == AnalyticsStrategy.RANKING:
        digest = RankingReducer().reduce(rows, value_key=value_key, n=rank_n, group_key=group_key)
    elif strategy == AnalyticsStrategy.ANOMALY:
        digest = AnomalyReducer().reduce(rows, value_key=value_key, k=max(rank_n, 12))
    elif strategy == AnalyticsStrategy.COMPARISON and time_key:
        digest = ComparisonReducer().reduce(rows, time_key=time_key, value_key=value_key)
    else:
        digest = distill_with_semantic_merge(
            rows,
            summarizer,
            max_rows=max_rows,
            max_tokens=max_tokens,
            semantic_merge=semantic_merge,
            base_coverage=base_coverage,
            extra_coverages=None,
            aggregation_logic=aggregation_logic_fallback,
        )
        if extra_coverages:
            digest = replace(digest, coverage=merge_coverage_infos(*extra_coverages, digest.coverage))
        return digest

    if extra_coverages:
        digest = replace(digest, coverage=merge_coverage_infos(*extra_coverages, digest.coverage))
    return digest
