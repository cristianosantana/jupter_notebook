"""
Redução map-reduce: chunks → mini-resumos → digest fundido (Fase 4.3–4.4).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from orion_mcp_v3.broker.chunking import chunk_rows
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.protocols.summarizer import SummarizerProtocol
from orion_mcp_v3.runtime.provenance import CoverageInfo


class ChunkReducer:
    """
    Para cada chunk gera um mini-resumo via :class:`SummarizerProtocol`;
    concatena num único texto de digest e regista proveniência.
    """

    def __init__(
        self,
        summarizer: SummarizerProtocol,
        *,
        aggregation_logic: str = "map_reduce_concat_v1",
        merge_separator: str = "\n\n---\n\n",
    ) -> None:
        self._summarizer = summarizer
        self._aggregation_logic = aggregation_logic
        self._merge_separator = merge_separator

    def reduce(
        self,
        chunks: Sequence[Sequence[Mapping[str, Any]]],
        *,
        base_coverage: CoverageInfo | None = None,
        sample_limit: int = 5,
    ) -> AnalyticalDigest:
        summaries: list[str] = []
        refs: list[str] = []
        volume = 0
        for i, chunk in enumerate(chunks):
            rows = [dict(r) for r in chunk]
            volume += len(rows)
            summaries.append(self._summarizer.summarize_chunk(rows, i))
            refs.append(f"chunk:{i}")

        merged = self._merge_separator.join(summaries)

        flat_sample: list[Mapping[str, Any]] = []
        for ch in chunks:
            for r in ch:
                flat_sample.append(dict(r))
                if len(flat_sample) >= sample_limit:
                    break
            if len(flat_sample) >= sample_limit:
                break

        labels: dict[str, Any] = {}
        if base_coverage:
            labels.update(base_coverage.labels)
        labels.setdefault("chunk_count", len(chunks))
        labels.setdefault("row_total", volume)
        cov = CoverageInfo(
            labels=labels,
            notes=(base_coverage.notes if base_coverage else None),
        )

        return AnalyticalDigest(
            summary=merged,
            volume=volume,
            sample=tuple(flat_sample[:sample_limit]),
            coverage=cov,
            source_refs=tuple(refs),
            aggregation_logic=self._aggregation_logic,
        )

    def distill(
        self,
        rows: list[dict[str, Any]],
        *,
        max_rows: int,
        max_tokens: int,
        base_coverage: CoverageInfo | None = None,
    ) -> AnalyticalDigest:
        """Particiona com :func:`~chunking.chunk_rows` e reduz."""
        chunks = chunk_rows(rows, max_rows=max_rows, max_tokens=max_tokens)
        return self.reduce(chunks, base_coverage=base_coverage)
