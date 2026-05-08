"""
Redução map-reduce: chunks → mini-resumos → digest fundido (Fase 4.3–4.4)
e fusão de artefactos cognitivos (bloco 5).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping, Sequence

from orion_mcp_v3.broker.chunking import chunk_rows
from orion_mcp_v3.contracts.cognitive_artifact import (
    CognitiveArtifact,
    artifact_provenance_anchor,
    heuristic_confidence_from_volume,
)
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
        semantic_merge: Callable[[list[str]], str] | None = None,
    ) -> None:
        self._summarizer = summarizer
        self._aggregation_logic = aggregation_logic
        self._merge_separator = merge_separator
        self._semantic_merge = semantic_merge

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

        if self._semantic_merge is not None:
            merged = self._semantic_merge(summaries)
        else:
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

        digest_confidence = heuristic_confidence_from_volume(volume)

        return AnalyticalDigest(
            summary=merged,
            volume=volume,
            sample=tuple(flat_sample[:sample_limit]),
            coverage=cov,
            source_refs=tuple(refs),
            aggregation_logic=self._aggregation_logic,
            confidence=digest_confidence,
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


def merge_cognitive_artifacts(
    *artifacts: CognitiveArtifact,
    merge_step: str = "merge",
    source: str = "broker.reducers",
) -> CognitiveArtifact:
    """Funde vários :class:`~CognitiveArtifact` num único sumário com cobertura agregada."""
    if not artifacts:
        return CognitiveArtifact(
            kind="reduction.empty",
            summary={"parts": []},
            confidence=0.35,
            coverage=CoverageInfo(labels={}, notes="reduction.merge_empty"),
            provenance=(),
        )

    parts = [dict(a.summary) for a in artifacts]
    labels: dict[str, Any] = {"merged_count": len(artifacts)}
    for i, a in enumerate(artifacts):
        labels[f"kind_{i}"] = a.kind
        labels.update({f"cov_{i}_{k}": v for k, v in dict(a.coverage.labels).items()})

    merged_prov = tuple(p for a in artifacts for p in a.provenance)
    merged_prov += (
        artifact_provenance_anchor(kind="reduction.merge", step=merge_step, source=source),
    )

    mean_conf = sum(a.confidence for a in artifacts) / len(artifacts)
    cov = CoverageInfo(labels=labels, notes="reduction.merge")

    return CognitiveArtifact(
        kind="reduction.merge",
        summary={"parts": parts},
        confidence=min(0.95, mean_conf),
        coverage=cov,
        provenance=merged_prov,
    )


def insights_from_numeric_spread(
    *,
    label: str,
    low: float,
    high: float,
    mean: float,
    artifact_step: str = "spread",
    source: str = "broker.reducers",
) -> CognitiveArtifact:
    """Exemplo de reducer semântico: interpretação simples de dispersão."""
    spread = high - low
    ratio = spread / mean if mean else float("inf")
    direction = "alta_variabilidade" if ratio > 1.5 else "moderada"
    summary = {
        "label": label,
        "spread": spread,
        "mean": mean,
        "interpretation": direction,
    }
    conf = min(0.9, 0.45 + 0.02 * min(spread / max(abs(mean), 1e-6), 10))
    cov = CoverageInfo(labels={"metric": label}, notes="reduction.insights_numeric")
    prov = (
        artifact_provenance_anchor(kind="reduction.insight", step=artifact_step, source=source),
    )
    return CognitiveArtifact(
        kind="reduction.insight",
        summary=summary,
        confidence=conf,
        coverage=cov,
        provenance=prov,
    )
