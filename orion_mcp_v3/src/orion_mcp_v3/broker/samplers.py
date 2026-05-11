"""Amostragem sobre linhas tabulares (Fase 3.4) + artefactos cognitivos (bloco 5)."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from dataclasses import dataclass

from orion_mcp_v3.broker.aggregators import top_n
from orion_mcp_v3.contracts.cognitive_artifact import (
    CognitiveArtifact,
    artifact_provenance_anchor,
    heuristic_confidence_from_volume,
)
from orion_mcp_v3.runtime.provenance import CoverageInfo


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        s = value.strip()
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            try:
                y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
                return datetime(y, m, d)
            except ValueError:
                return None
    return None


def recent_sampler(
    rows: Sequence[Mapping[str, Any]],
    *,
    time_key: str,
    k: int,
) -> list[dict[str, Any]]:
    """Ordena por tempo decrescente e devolve até ``k`` linhas."""
    if k <= 0:
        return []
    scored: list[tuple[Any, dict[str, Any]]] = []
    for row in rows:
        if time_key not in row:
            raise KeyError(time_key)
        t = _parse_time(row[time_key])
        scored.append((t, dict(row)))
    scored.sort(key=lambda x: (x[0] is not None, x[0] or 0), reverse=True)
    return [r for _, r in scored[:k]]


def outlier_sampler(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_key: str,
    k: int,
    method: str = "zscore",
) -> list[dict[str, Any]]:
    """
    Seleciona até ``k`` linhas com maior desvio em relação à média (valor absoluto do z-score).

    Ignora valores não numéricos. Com menos de 2 valores válidos, devolve lista vazia.
    """
    if k <= 0:
        return []
    if method != "zscore":
        raise ValueError(f"método não suportado: {method!r}")

    nums: list[float] = []
    for row in rows:
        if value_key not in row:
            raise KeyError(value_key)
        try:
            nums.append(float(row[value_key]))
        except (TypeError, ValueError):
            continue
    if len(nums) < 2:
        return []

    mean = statistics.fmean(nums)
    stdev = statistics.pstdev(nums)
    if stdev == 0:
        return [dict(r) for r in rows[:k]]

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        if value_key not in row:
            continue
        try:
            v = float(row[value_key])
        except (TypeError, ValueError):
            continue
        z = (v - mean) / stdev
        scored.append((abs(z), dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:k]]


def sample_recent_structured(
    rows: Sequence[Mapping[str, Any]],
    *,
    time_key: str,
    k: int,
    projection_keys: Sequence[str] | None = None,
    artifact_step: str = "recent",
    source: str = "broker.samplers",
) -> CognitiveArtifact:
    """
    Amostra temporal recente; ``summary`` contém apenas projeções mínimas ou contagens — não replica o lote SQL completo.
    """
    picked = recent_sampler(rows, time_key=time_key, k=k)
    keys = tuple(projection_keys) if projection_keys else ()
    slim: list[Mapping[str, Any]] = []
    for row in picked:
        if keys:
            slim.append({pk: row[pk] for pk in keys if pk in row})
        else:
            slim.append({time_key: row[time_key]})

    summary: dict[str, Any] = {
        "method": "recent",
        "time_key": time_key,
        "k_requested": k,
        "picked_count": len(picked),
        "projection_keys": list(keys) if keys else [time_key],
        "sample_projection": slim,
    }
    cov = CoverageInfo(
        labels={"picked": len(picked), "pool_rows": len(rows)},
        notes="sample.recent",
    )
    prov = (
        artifact_provenance_anchor(kind="sample.recent", step=artifact_step, source=source),
    )
    return CognitiveArtifact(
        kind="sample.recent",
        summary=summary,
        confidence=heuristic_confidence_from_volume(len(picked)),
        coverage=cov,
        provenance=prov,
    )


def sample_outliers_structured(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_key: str,
    k: int,
    method: str = "zscore",
    projection_keys: Sequence[str] | None = None,
    artifact_step: str = "outlier",
    source: str = "broker.samplers",
) -> CognitiveArtifact:
    """Destaca outliers; projecção opcional para não expor linhas completas."""
    picked = outlier_sampler(rows, value_key=value_key, k=k, method=method)
    keys = tuple(projection_keys) if projection_keys else (value_key,)
    slim = [{pk: row.get(pk) for pk in keys if pk in row} for row in picked]

    summary = {
        "method": method,
        "value_key": value_key,
        "k_requested": k,
        "picked_count": len(picked),
        "projection_keys": list(keys),
        "sample_projection": slim,
    }
    cov = CoverageInfo(
        labels={"picked": len(picked), "pool_rows": len(rows)},
        notes="sample.outlier",
    )
    prov = (
        artifact_provenance_anchor(kind="sample.outlier", step=artifact_step, source=source),
    )
    return CognitiveArtifact(
        kind="sample.outlier",
        summary=summary,
        confidence=heuristic_confidence_from_volume(len(picked)),
        coverage=cov,
        provenance=prov,
    )


def sample_stratified_keys(
    rows: Sequence[Mapping[str, Any]],
    *,
    strata_key: str,
    per_stratum: int,
    artifact_step: str = "stratified",
    source: str = "broker.samplers",
) -> CognitiveArtifact:
    """Até ``per_stratum`` ids por valor de ``strata_key`` (primeiras ocorrências na sequência)."""
    seen: dict[Any, list[Any]] = {}
    order: list[Any] = []
    for row in rows:
        if strata_key not in row:
            continue
        sk = row[strata_key]
        if sk not in seen:
            seen[sk] = []
            order.append(sk)
        if len(seen[sk]) < per_stratum:
            rid = row.get("id", row.get(strata_key))
            seen[sk].append(rid)

    summary = {
        "method": "stratified_keys",
        "strata_key": strata_key,
        "per_stratum": per_stratum,
        "strata_refs": {str(k): v for k, v in seen.items()},
        "strata_count": len(seen),
    }
    cov = CoverageInfo(labels={"strata": len(seen), "rows_in": len(rows)}, notes="sample.stratified")
    prov = (
        artifact_provenance_anchor(kind="sample.stratified", step=artifact_step, source=source),
    )
    return CognitiveArtifact(
        kind="sample.stratified",
        summary=summary,
        confidence=heuristic_confidence_from_volume(len(rows)),
        coverage=cov,
        provenance=prov,
    )


@dataclass(frozen=True, slots=True)
class SampleBatchResult:
    """Resultado de amostragem (Fase 2.2) com cobertura e linhas omitidas."""

    rows: tuple[dict[str, Any], ...]
    sample_strategy: str
    coverage: CoverageInfo
    omitted_rows: int


class RecentSampler:
    """Amostra temporal recente (últimas ``k`` linhas por ``time_key``)."""

    def __init__(self, *, time_key: str, k: int) -> None:
        self._time_key = time_key
        self._k = k

    def sample(self, rows: Sequence[Mapping[str, Any]]) -> SampleBatchResult:
        picked = recent_sampler(rows, time_key=self._time_key, k=self._k)
        omitted = max(0, len(rows) - len(picked))
        cov = CoverageInfo(
            labels={"picked": len(picked), "pool_rows": len(rows)},
            notes="sampler.recent",
        )
        return SampleBatchResult(
            rows=tuple(picked),
            sample_strategy="recent",
            coverage=cov,
            omitted_rows=omitted,
        )


class OutlierSampler:
    """Amostra por maior |z-score| sobre ``value_key``."""

    def __init__(self, *, value_key: str, k: int, method: str = "zscore") -> None:
        self._value_key = value_key
        self._k = k
        self._method = method

    def sample(self, rows: Sequence[Mapping[str, Any]]) -> SampleBatchResult:
        picked = outlier_sampler(rows, value_key=self._value_key, k=self._k, method=self._method)
        omitted = max(0, len(rows) - len(picked))
        cov = CoverageInfo(
            labels={"picked": len(picked), "pool_rows": len(rows)},
            notes="sampler.outlier",
        )
        return SampleBatchResult(
            rows=tuple(picked),
            sample_strategy=f"outlier:{self._method}",
            coverage=cov,
            omitted_rows=omitted,
        )


class StratifiedSampler:
    """Até ``per_stratum`` linhas completas por valor de ``strata_key`` (ordem de entrada)."""

    def __init__(self, *, strata_key: str, per_stratum: int) -> None:
        self._strata_key = strata_key
        self._per_stratum = per_stratum

    def sample(self, rows: Sequence[Mapping[str, Any]]) -> SampleBatchResult:
        counts: dict[Any, int] = {}
        picked: list[dict[str, Any]] = []
        for row in rows:
            if self._strata_key not in row:
                continue
            sk = row[self._strata_key]
            n = counts.get(sk, 0)
            if n < self._per_stratum:
                picked.append(dict(row))
                counts[sk] = n + 1
        omitted = max(0, len(rows) - len(picked))
        cov = CoverageInfo(
            labels={"strata_distinct": len(counts), "picked": len(picked), "pool_rows": len(rows)},
            notes="sampler.stratified",
        )
        return SampleBatchResult(
            rows=tuple(picked),
            sample_strategy="stratified",
            coverage=cov,
            omitted_rows=omitted,
        )


class TopKSampler:
    """Top-K por métrica (opcionalmente agregada por ``group_key``)."""

    def __init__(self, *, value_key: str, k: int, group_key: str | None = None) -> None:
        self._value_key = value_key
        self._k = k
        self._group_key = group_key

    def sample(self, rows: Sequence[Mapping[str, Any]]) -> SampleBatchResult:
        ranked = top_n(rows, value_key=self._value_key, n=self._k, group_key=self._group_key)
        picked = [dict(r) for r in ranked]
        omitted = max(0, len(rows) - len(picked))
        cov = CoverageInfo(
            labels={"picked": len(picked), "pool_rows": len(rows), "grouped": self._group_key is not None},
            notes="sampler.top_k",
        )
        return SampleBatchResult(
            rows=tuple(picked),
            sample_strategy="top_k",
            coverage=cov,
            omitted_rows=omitted,
        )
