"""Amostragem sobre linhas tabulares (Fase 3.4)."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any


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
