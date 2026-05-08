"""
Map-reduce analítico (ORDEM_IMPLEMENTAÇÃO §7): chunk summarization, merge semântico,
agregação de cobertura sobre :class:`~AnalyticalDigest`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from orion_mcp_v3.broker.chunking import chunk_rows
from orion_mcp_v3.broker.reducers import ChunkReducer
from orion_mcp_v3.contracts.digest import AnalyticalDigest
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
