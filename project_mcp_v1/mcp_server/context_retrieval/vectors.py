from __future__ import annotations

import math
from typing import Any, Sequence


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def json_vec_to_list(raw: object) -> list[float]:
    if isinstance(raw, list):
        return [float(x) for x in raw]
    if isinstance(raw, str):
        import json

        data = json.loads(raw)
        if isinstance(data, list):
            return [float(x) for x in data]
    return []


def merge_message_vectors_for_retrieve(
    msgs: list[dict[str, Any]],
    *,
    cached: dict[int, list[float]],
    fresh: dict[int, list[float]],
    query_dim: int,
) -> tuple[list[list[float]], int, int] | None:
    """
    Vectores na ordem de ``msgs``. Hit = vector em ``cached`` com dimensão ``query_dim``;
    miss = entrada em ``fresh`` com a mesma dimensão. Devolve ``None`` se faltar vector.
    """
    mvecs: list[list[float]] = []
    hits = 0
    misses = 0
    for m in msgs:
        mid = int(m["id"])
        v = cached.get(mid)
        if v is not None and len(v) == query_dim:
            mvecs.append(v)
            hits += 1
            continue
        fv = fresh.get(mid)
        if fv is None or len(fv) != query_dim:
            return None
        mvecs.append(fv)
        misses += 1
    return mvecs, hits, misses
