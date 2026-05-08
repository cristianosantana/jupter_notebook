"""Agregações tabulares em memória (Fase 3.3)."""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any


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
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            try:
                y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
                return datetime(y, m, d)
            except ValueError:
                return None
    return None


def _bucket_month(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def time_series(
    rows: Sequence[Mapping[str, Any]],
    *,
    time_key: str,
    value_key: str,
    grain: str = "month",
) -> list[dict[str, Any]]:
    """
    Soma ``value_key`` por bucket temporal.

    ``grain`` suportado: apenas ``month`` (string ``YYYY-MM``).
    """
    if grain != "month":
        raise ValueError(f"grain não suportado: {grain!r}")

    sums: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if time_key not in row or value_key not in row:
            raise KeyError(f"{time_key=} ou {value_key=} em falta numa linha")
        dt = _parse_time(row[time_key])
        if dt is None:
            continue
        bucket = _bucket_month(dt)
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
