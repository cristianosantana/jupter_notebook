"""Agregações tabulares em memória (Fase 3.3) + saídas cognitivas (bloco 5)."""

from __future__ import annotations

import calendar
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from orion_mcp_v3.contracts.cognitive_artifact import (
    CognitiveArtifact,
    artifact_provenance_anchor,
    heuristic_confidence_from_volume,
)
from orion_mcp_v3.runtime.provenance import CoverageInfo


def group_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[Any, list[dict[str, Any]]]:
    """Agrupa linhas pelo valor de ``key`` (valor deve ser hashable para chave estável)."""
    out: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if key not in row:
            raise KeyError(key)
        out[row[key]].append(dict(row))
    return dict(out)


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if len(s) == 7 and s[4] == "-":
            try:
                y, m = int(s[0:4]), int(s[5:7])
                return datetime(y, m, 1)
            except ValueError:
                return None
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            try:
                y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
                return datetime(y, m, d)
            except ValueError:
                return None
    return None


def _bucket_month(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _bucket_day(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


_GRAIN_BUCKETERS: dict[str, Any] = {
    "month": _bucket_month,
    "day": _bucket_day,
}


def time_series(
    rows: Sequence[Mapping[str, Any]],
    *,
    time_key: str,
    value_key: str,
    grain: str = "month",
) -> list[dict[str, Any]]:
    """Soma ``value_key`` por bucket temporal. Suporta grains ``month`` e ``day``."""
    bucketer = _GRAIN_BUCKETERS.get(grain)
    if bucketer is None:
        raise ValueError(f"grain não suportado: {grain!r}")

    sums: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if time_key not in row or value_key not in row:
            raise KeyError(f"{time_key=} ou {value_key=} em falta numa linha")
        dt = _parse_time(row[time_key])
        if dt is None:
            continue
        bucket = bucketer(dt)
        v = row[value_key]
        try:
            sums[bucket] += float(v)
        except (TypeError, ValueError):
            continue
        counts[bucket] += 1

    out: list[dict[str, Any]] = []
    for period in sorted(sums.keys()):
        out.append(
            {
                "period": period,
                "total": sums[period],
                "count": counts[period],
            }
        )
    return out


def top_n(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_key: str,
    n: int,
    group_key: str | None = None,
    descending: bool = True,
) -> list[dict[str, Any]]:
    """
    Ordena por ``value_key`` e devolve as primeiras ``n`` linhas (cópias).

    Se ``group_key`` for dado, primeiro agrega somando ``value_key`` por esse grupo.
    """
    if n <= 0:
        return []

    if group_key is None:
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            if value_key not in row:
                raise KeyError(value_key)
            try:
                val = float(row[value_key])
            except (TypeError, ValueError):
                val = float("nan")
            scored.append((val, dict(row)))
        scored.sort(key=lambda x: x[0], reverse=descending)
        return [r for _, r in scored[:n]]

    grouped = group_by(rows, group_key)
    aggregates: list[dict[str, Any]] = []
    for gval, group_rows in grouped.items():
        total = 0.0
        for r in group_rows:
            if value_key not in r:
                raise KeyError(value_key)
            try:
                total += float(r[value_key])
            except (TypeError, ValueError):
                pass
        aggregates.append({group_key: gval, "total": total})

    aggregates.sort(key=lambda x: float(x["total"]), reverse=descending)
    return aggregates[:n]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Utilitário: primeiro e último dia do mês (date)."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def aggregate_groups(
    rows: Sequence[Mapping[str, Any]],
    key: str,
    *,
    artifact_step: str = "group_by",
    source: str = "broker.aggregators",
) -> CognitiveArtifact:
    """
    Agrupa por ``key`` e devolve apenas cardinalidades e metadados — **sem** listar linhas crus.
    """
    partitioned = group_by(rows, key)
    cardinality = {str(k): len(v) for k, v in partitioned.items()}
    summary: dict[str, Any] = {
        "group_key": key,
        "cardinality_by_group": cardinality,
        "distinct_groups": len(cardinality),
        "input_rows": len(rows),
    }
    cov = CoverageInfo(
        labels={"distinct_groups": len(cardinality), "rows_in": len(rows)},
        notes="aggregation.group_by",
    )
    prov = (
        artifact_provenance_anchor(kind="aggregation.group_by", step=artifact_step, source=source),
    )
    return CognitiveArtifact(
        kind="aggregation.group_by",
        summary=summary,
        confidence=heuristic_confidence_from_volume(len(rows)),
        coverage=cov,
        provenance=prov,
    )


def aggregate_temporal_series(
    rows: Sequence[Mapping[str, Any]],
    *,
    time_key: str,
    value_key: str,
    grain: str = "month",
    artifact_step: str = "time_series",
    source: str = "broker.aggregators",
) -> CognitiveArtifact:
    """Série temporal agregada (buckets), sem devolver linhas de entrada."""
    periods = time_series(rows, time_key=time_key, value_key=value_key, grain=grain)
    parsed_ok = sum(
        1
        for row in rows
        if time_key in row and value_key in row and _parse_time(row[time_key]) is not None
    )
    summary: dict[str, Any] = {
        "grain": grain,
        "time_key": time_key,
        "value_key": value_key,
        "periods": periods,
        "period_count": len(periods),
        "rows_parseable": parsed_ok,
        "input_rows": len(rows),
    }
    cov = CoverageInfo(
        labels={"periods": len(periods), "rows_used": parsed_ok},
        notes="aggregation.time_series",
    )
    prov = (
        artifact_provenance_anchor(
            kind="aggregation.time_series",
            step=artifact_step,
            source=source,
        ),
    )
    conf = heuristic_confidence_from_volume(parsed_ok)
    return CognitiveArtifact(
        kind="aggregation.time_series",
        summary=summary,
        confidence=conf,
        coverage=cov,
        provenance=prov,
    )


def aggregate_ranking(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_key: str,
    n: int,
    group_key: str | None = None,
    rank_id_key: str | None = None,
    artifact_step: str = "top_n",
    source: str = "broker.aggregators",
) -> CognitiveArtifact:
    """
    Ranking: com ``group_key`` devolve totais por grupo; sem grupo, rankeia por valor com referências opcionais.
    """
    ranked_rows = top_n(rows, value_key=value_key, n=n, group_key=group_key)
    if group_key is None:
        slim: list[dict[str, Any]] = []
        for i, row in enumerate(ranked_rows):
            entry: dict[str, Any] = {"rank": i + 1, "score": float(row.get(value_key, 0))}
            if rank_id_key and rank_id_key in row:
                entry["ref"] = row[rank_id_key]
            slim.append(entry)
        summary = {
            "mode": "row_ranking",
            "value_key": value_key,
            "n": n,
            "ranked": slim,
        }
    else:
        summary = {
            "mode": "group_totals",
            "group_key": group_key,
            "value_key": value_key,
            "n": n,
            "groups": ranked_rows,
        }

    cov = CoverageInfo(
        labels={"rank_slots": min(n, len(ranked_rows)), "input_rows": len(rows)},
        notes="aggregation.ranking",
    )
    prov = (
        artifact_provenance_anchor(kind="aggregation.ranking", step=artifact_step, source=source),
    )
    return CognitiveArtifact(
        kind="aggregation.ranking",
        summary=summary,
        confidence=heuristic_confidence_from_volume(len(rows)),
        coverage=cov,
        provenance=prov,
    )


def normalize_metrics(
    rows: Sequence[Mapping[str, Any]],
    value_keys: Sequence[str],
    *,
    artifact_step: str = "normalize_metrics",
    source: str = "broker.aggregators",
) -> CognitiveArtifact:
    """Estatísticas normalizadas (min / max / média) por coluna numérica pedida."""
    stats_out: dict[str, dict[str, float]] = {}
    for vk in value_keys:
        vals: list[float] = []
        for row in rows:
            if vk not in row:
                continue
            try:
                vals.append(float(row[vk]))
            except (TypeError, ValueError):
                continue
        if not vals:
            continue
        stats_out[vk] = {
            "min": float(min(vals)),
            "max": float(max(vals)),
            "mean": float(statistics.fmean(vals)),
            "count": float(len(vals)),
        }
    summary = {"metrics": stats_out, "input_rows": len(rows)}
    cov = CoverageInfo(
        labels={"fields": len(stats_out), "rows_seen": len(rows)},
        notes="aggregation.normalize_metrics",
    )
    prov = (
        artifact_provenance_anchor(
            kind="aggregation.normalize_metrics",
            step=artifact_step,
            source=source,
        ),
    )
    return CognitiveArtifact(
        kind="aggregation.normalize_metrics",
        summary=summary,
        confidence=heuristic_confidence_from_volume(len(rows)),
        coverage=cov,
        provenance=prov,
    )
