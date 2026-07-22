"""Leitura SQL-only de memory_curta (vendored, sem embedding)."""

from __future__ import annotations

import json
import time
from typing import Any

import asyncpg

from .knowledge import EssenceItem, KnowledgeHit
from .noop_trace import log_public_chat_event

_LOAD_CURTA_BY_IDS = """
SELECT "id", "category", "context_key", "validated_answer", "key_metrics"
FROM "public"."memory_curta"
WHERE "id" = ANY($1::int[])
"""

_LOAD_ESSENCE_BY_THEMES = """
SELECT "theme", "observation", "key_finding", "recommendation"
FROM "public"."memory_essence"
WHERE "theme" = ANY($1::text[])
"""

_LOAD_CURTA_BY_CONTEXT_KEY_THEME = """
SELECT "id", "category", "context_key", "validated_answer", "key_metrics"
FROM "public"."memory_curta"
WHERE LOWER("context_key") LIKE $1
ORDER BY "id" DESC
LIMIT $2
"""


class SennaRemissiveReader:
    """SQL read-only — path Senna: patterns por context_key / theme."""

    def __init__(self, pool: asyncpg.Pool, *, limit: int = 20) -> None:
        self._pool = pool
        self._limit = max(1, limit)

    async def load_hits_by_origin_ids(
        self,
        origin_ids: list[int],
        *,
        scores: dict[int, float | None] | None = None,
    ) -> list[KnowledgeHit]:
        t0 = time.monotonic()
        log_public_chat_event(
            etapa="senna.reader.load_hits",
            fase="pre",
            dados={"origin_id_count": len(origin_ids)},
        )
        if not origin_ids:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_LOAD_CURTA_BY_IDS, origin_ids)
        hits: list[KnowledgeHit] = []
        for row in rows:
            origin_id = int(row["id"])
            hits.append(
                KnowledgeHit(
                    origin_id=origin_id,
                    context_key=str(row["context_key"]),
                    category=str(row["category"]),
                    validated_answer=str(row["validated_answer"]),
                    key_metrics=_json_mapping(row["key_metrics"]),
                    score=(scores or {}).get(origin_id),
                )
            )
        order = {origin_id: index for index, origin_id in enumerate(origin_ids)}
        hits.sort(key=lambda hit: order.get(hit.origin_id, len(origin_ids)))
        log_public_chat_event(
            etapa="senna.reader.load_hits",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "hit_count": len(hits),
            },
        )
        return hits

    async def load_essence_by_themes(self, themes: list[str]) -> list[EssenceItem]:
        normalized = [theme.strip() for theme in themes if theme.strip()]
        if not normalized:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_LOAD_ESSENCE_BY_THEMES, normalized)
        return [
            EssenceItem(
                theme=str(row["theme"]),
                observation=row["observation"],
                key_finding=row["key_finding"],
                recommendation=row["recommendation"],
            )
            for row in rows
        ]

    async def load_hits_by_theme_patterns(
        self,
        patterns: list[str],
        *,
        limit: int | None = None,
    ) -> list[KnowledgeHit]:
        lim = limit if limit is not None else self._limit
        normalized = [pattern.strip().lower() for pattern in patterns if pattern.strip()]
        if not normalized:
            return []
        hits_by_id: dict[int, KnowledgeHit] = {}
        async with self._pool.acquire() as conn:
            for pattern in normalized:
                like = f"%:{pattern}%"
                rows = await conn.fetch(_LOAD_CURTA_BY_CONTEXT_KEY_THEME, like, lim)
                for row in rows:
                    origin_id = int(row["id"])
                    if origin_id in hits_by_id:
                        continue
                    hits_by_id[origin_id] = KnowledgeHit(
                        origin_id=origin_id,
                        context_key=str(row["context_key"]),
                        category=str(row["category"]),
                        validated_answer=str(row["validated_answer"]),
                        key_metrics=_json_mapping(row["key_metrics"]),
                        score=None,
                    )
        return list(hits_by_id.values())

    async def load_hits_by_context_key_patterns(
        self,
        patterns: list[str],
        *,
        limit: int | None = None,
    ) -> list[KnowledgeHit]:
        lim = limit if limit is not None else self._limit
        normalized = [pattern.strip().lower() for pattern in patterns if pattern.strip()]
        if not normalized:
            return []
        hits_by_id: dict[int, KnowledgeHit] = {}
        async with self._pool.acquire() as conn:
            for pattern in normalized:
                rows = await conn.fetch(_LOAD_CURTA_BY_CONTEXT_KEY_THEME, pattern, lim)
                for row in rows:
                    origin_id = int(row["id"])
                    if origin_id in hits_by_id:
                        continue
                    hits_by_id[origin_id] = KnowledgeHit(
                        origin_id=origin_id,
                        context_key=str(row["context_key"]),
                        category=str(row["category"]),
                        validated_answer=str(row["validated_answer"]),
                        key_metrics=_json_mapping(row["key_metrics"]),
                        score=None,
                    )
        return list(hits_by_id.values())


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}
