"""
Partição de linhas tabulares para destilação map-reduce (Fase 4.1).

Limites: número máximo de linhas por chunk e estimativa de tokens (JSON serializado).
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from orion_mcp_v3.runtime.budget_allocator import estimate_tokens


def rows_blob(rows: Sequence[Mapping[str, Any]]) -> str:
    """Representação estável para estimativa de tamanho."""
    return json.dumps([dict(r) for r in rows], ensure_ascii=False, sort_keys=True, default=str)


def estimate_chunk_tokens(rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    return estimate_tokens(rows_blob(rows))


def chunk_rows(
    rows: list[dict[str, Any]],
    *,
    max_rows: int,
    max_tokens: int,
) -> list[list[dict[str, Any]]]:
    """
    Agrupa linhas em chunks greedy: cada chunk tem no máximo ``max_rows`` linhas e
    ``estimate_chunk_tokens(chunk) <= max_tokens``.

    Se uma única linha exceder ``max_tokens``, essa linha forma um chunk isolado.
    """
    if max_rows <= 0:
        raise ValueError("max_rows deve ser > 0")
    if max_tokens <= 0:
        raise ValueError("max_tokens deve ser > 0")

    out: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []

    for row in rows:
        d = dict(row)
        trial = cur + [d]
        fits = len(trial) <= max_rows and estimate_chunk_tokens(trial) <= max_tokens
        if fits:
            cur = trial
            continue

        if cur:
            out.append(cur)
            cur = []

        if estimate_chunk_tokens([d]) > max_tokens:
            out.append([d])
            continue

        cur = [d]

    if cur:
        out.append(cur)

    return out
