"""
Redução map-reduce: chunks → mini-resumos → digest fundido (Fase 4.3–4.4)
e fusão de artefactos cognitivos (bloco 5).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Mapping, Sequence

from orion_mcp_v3.broker.chunking import chunk_rows
from orion_mcp_v3.broker.aggregators import time_series, top_n
from orion_mcp_v3.broker.samplers import outlier_sampler
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


# --- Fase 2.3 — reducers cognitivos → :class:`AnalyticalDigest` com proveniência explícita ---


class TrendReducer:
    """Série temporal agregada → digest (destilação de tendência)."""

    def __init__(self, *, aggregation_logic: str = "trend_reducer_v1") -> None:
        self._aggregation_logic = aggregation_logic

    def reduce(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        time_key: str,
        value_key: str,
        grain: str = "month",
        sample_limit: int = 8,
    ) -> AnalyticalDigest:
        periods = time_series(rows, time_key=time_key, value_key=value_key, grain=grain)
        lines = [f"{p['period']}: total={p['total']:.4g} (n={p['count']})" for p in periods]
        summary = "Tendência agregada:\n" + "\n".join(lines) if lines else "Sem períodos numéricos agregados."
        vol = sum(int(p.get("count", 0) or 0) for p in periods) or len(rows)
        refs = tuple(f"period:{p['period']}" for p in periods)
        cov = CoverageInfo(
            labels={"period_count": len(periods), "rows_in": len(rows)},
            notes="reducer.trend",
        )
        conf = heuristic_confidence_from_volume(vol)
        sample_rows: list[Mapping[str, Any]] = [dict(p) for p in periods[:sample_limit]]
        return AnalyticalDigest(
            summary=summary,
            volume=vol,
            sample=tuple(sample_rows),
            coverage=cov,
            source_refs=refs,
            aggregation_logic=self._aggregation_logic,
            confidence=min(0.95, conf + 0.05 * min(len(periods), 5)),
        )


class RankingReducer:
    """Ranking por métrica → digest."""

    def __init__(self, *, aggregation_logic: str = "ranking_reducer_v1") -> None:
        self._aggregation_logic = aggregation_logic

    def reduce(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        value_key: str,
        n: int,
        group_key: str | None = None,
        label_key: str | None = None,
    ) -> AnalyticalDigest:
        ranked = top_n(rows, value_key=value_key, n=n, group_key=group_key)
        lines: list[str] = []
        refs: list[str] = []
        for i, r in enumerate(ranked, start=1):
            lbl = r.get(label_key) if label_key and label_key in r else r.get(group_key or "ref", i)
            score = r.get("total", r.get(value_key))
            lines.append(f"#{i} {lbl!s} → {value_key}={score!s}")
            refs.append(f"rank:{i}:{lbl!s}")
        summary = "Ranking:\n" + "\n".join(lines) if lines else "Ranking vazio."
        cov = CoverageInfo(labels={"ranked": len(ranked), "rows_in": len(rows)}, notes="reducer.ranking")
        conf = heuristic_confidence_from_volume(len(rows))
        return AnalyticalDigest(
            summary=summary,
            volume=len(rows),
            sample=tuple(dict(x) for x in ranked),
            coverage=cov,
            source_refs=tuple(refs),
            aggregation_logic=self._aggregation_logic,
            confidence=min(0.95, conf),
        )


class AnomalyReducer:
    """Destila linhas mais extremas (z-score) como digest de anomalias."""

    def __init__(self, *, aggregation_logic: str = "anomaly_reducer_v1") -> None:
        self._aggregation_logic = aggregation_logic

    def reduce(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        value_key: str,
        k: int = 12,
    ) -> AnalyticalDigest:
        picked = outlier_sampler(rows, value_key=value_key, k=k, method="zscore")
        lines = [f"ref={row.get('id', '?')}: {value_key}={row.get(value_key)!s}" for row in picked[: k]]
        summary = "Candidatos a anomalia (|z| elevado):\n" + "\n".join(lines) if lines else "Sem outliers destacados."
        refs = tuple(f"row:{row.get('id', i)}" for i, row in enumerate(picked))
        cov = CoverageInfo(
            labels={"outliers_picked": len(picked), "rows_in": len(rows)},
            notes="reducer.anomaly",
        )
        conf = heuristic_confidence_from_volume(len(picked) if picked else max(1, len(rows) // 3))
        return AnalyticalDigest(
            summary=summary,
            volume=len(rows),
            sample=tuple(dict(r) for r in picked),
            coverage=cov,
            source_refs=refs,
            aggregation_logic=self._aggregation_logic,
            confidence=min(0.95, 0.4 + 0.04 * len(picked)),
        )


class ComparisonReducer:
    """Compara extremos temporais (primeiro vs último período) ou totais globais."""

    def __init__(self, *, aggregation_logic: str = "comparison_reducer_v1") -> None:
        self._aggregation_logic = aggregation_logic

    def reduce(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        time_key: str,
        value_key: str,
        grain: str = "month",
    ) -> AnalyticalDigest:
        periods = time_series(rows, time_key=time_key, value_key=value_key, grain=grain)
        if len(periods) >= 2:
            first, last = periods[0], periods[-1]
            a, b = float(first["total"]), float(last["total"])
            delta = (b - a) / abs(a) if a else None
            if delta is not None:
                summary = (
                    f"Comparação: {first['period']} total={a:.4g} vs {last['period']} total={b:.4g}. "
                    f"Variação relativa: {delta:.2%}."
                )
            else:
                summary = (
                    f"Comparação: {first['period']} total={a:.4g} vs {last['period']} total={b:.4g}."
                )
            refs = (f"compare:{first['period']}", f"compare:{last['period']}")
        elif periods:
            summary = f"Apenas um período agregado ({periods[0]['period']}); comparação limitada."
            refs = (f"compare:{periods[0]['period']}",)
        else:
            summary = "Sem dados temporais para comparação."
            refs = ()
        cov = CoverageInfo(labels={"periods": len(periods), "rows_in": len(rows)}, notes="reducer.comparison")
        conf = heuristic_confidence_from_volume(len(rows))
        return AnalyticalDigest(
            summary=summary,
            volume=len(rows),
            sample=tuple(dict(p) for p in periods[:6]),
            coverage=cov,
            source_refs=refs,
            aggregation_logic=self._aggregation_logic,
            confidence=min(0.95, conf),
        )
