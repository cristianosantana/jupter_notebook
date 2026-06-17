"""Leitura read-only de memory_* para o Chat Público."""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from orion_mcp_v3.public_chat.domain.knowledge import EssenceItem, KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.embedding import EmbeddingService, to_pgvector

_SEARCH_ORIGIN_IDS_GLOBAL = """
SELECT "origin_id", MIN("embedding" <=> $1::vector) AS score
FROM "public"."memory_embeddings"
WHERE "origin_type" = 'memory_curta'
  AND ("ttl_expires_at" IS NULL OR "ttl_expires_at" > now())
GROUP BY "origin_id"
ORDER BY score
LIMIT $2
"""

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


class PublicRemissiveReader:
    """SQL read-only sobre memory_* — sem filtro user_id na busca vetorial."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        embedding_service: EmbeddingService,
        *,
        probes: int = 10,
        limit: int = 5,
    ) -> None:
        self._pool = pool
        self._embed = embedding_service
        self._probes = max(1, probes)
        self._limit = max(1, limit)

    async def search_origin_ids(self, query: str) -> list[tuple[int, float | None]]:
        normalized = query.strip()
        if not normalized:
            return []

        vectors = await self._embed.embed([normalized])
        if not vectors:
            return []
        vector = to_pgvector(vectors[0])

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('ivfflat.probes', $1, true)",
                    str(self._probes),
                )
                rows = await conn.fetch(_SEARCH_ORIGIN_IDS_GLOBAL, vector, self._limit)
        return [(int(row["origin_id"]), _optional_float(row["score"])) for row in rows]

    async def load_hits_by_origin_ids(
        self,
        origin_ids: list[int],
        *,
        scores: dict[int, float | None] | None = None,
    ) -> list[KnowledgeHit]:
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


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
