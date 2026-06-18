"""Leitura read-only de memory_* para o Chat Público."""

from __future__ import annotations

import json
import time
from typing import Any

import asyncpg

from orion_mcp_v3.public_chat.domain.knowledge import EssenceItem, KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.embedding import EmbeddingService, to_pgvector
from orion_mcp_v3.public_chat.infrastructure.pipeline_snapshots import (
    log_memory_accessed,
    snapshot_knowledge_hit,
    snapshot_vector_matches,
)
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event, preview_message

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
        t0 = time.monotonic()
        normalized = query.strip()
        log_public_chat_event(
            etapa="reader.search_origin_ids",
            fase="pre",
            dados={**preview_message(normalized), "limit": self._limit, "probes": self._probes},
        )
        if not normalized:
            log_public_chat_event(
                etapa="reader.search_origin_ids",
                fase="post",
                dados={"latency_ms": round((time.monotonic() - t0) * 1000.0, 2), "match_count": 0},
            )
            return []

        vectors = await self._embed.embed([normalized])
        if not vectors:
            log_public_chat_event(
                etapa="reader.search_origin_ids",
                fase="post",
                dados={"latency_ms": round((time.monotonic() - t0) * 1000.0, 2), "match_count": 0, "embed_empty": True},
            )
            return []
        vector = to_pgvector(vectors[0])

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('ivfflat.probes', $1, true)",
                    str(self._probes),
                )
                rows = await conn.fetch(_SEARCH_ORIGIN_IDS_GLOBAL, vector, self._limit)
        matches = [(int(row["origin_id"]), _optional_float(row["score"])) for row in rows]
        log_public_chat_event(
            etapa="reader.search_origin_ids",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "match_count": len(matches),
                "vector_matches": snapshot_vector_matches(matches),
                "source": "memory_embeddings",
            },
        )
        return matches

    async def load_hits_by_origin_ids(
        self,
        origin_ids: list[int],
        *,
        scores: dict[int, float | None] | None = None,
    ) -> list[KnowledgeHit]:
        t0 = time.monotonic()
        log_public_chat_event(
            etapa="reader.load_hits",
            fase="pre",
            dados={"origin_id_count": len(origin_ids)},
        )
        if not origin_ids:
            log_public_chat_event(
                etapa="reader.load_hits",
                fase="post",
                dados={"latency_ms": round((time.monotonic() - t0) * 1000.0, 2), "hit_count": 0},
            )
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
            etapa="reader.load_hits",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "hit_count": len(hits),
                "source": "memory_curta",
                "memory_curta_hits": [snapshot_knowledge_hit(hit) for hit in hits],
            },
        )
        return hits

    async def load_essence_by_themes(self, themes: list[str]) -> list[EssenceItem]:
        t0 = time.monotonic()
        normalized = [theme.strip() for theme in themes if theme.strip()]
        log_public_chat_event(
            etapa="reader.load_essence",
            fase="pre",
            dados={"theme_count": len(normalized)},
        )
        if not normalized:
            log_public_chat_event(
                etapa="reader.load_essence",
                fase="post",
                dados={"latency_ms": round((time.monotonic() - t0) * 1000.0, 2), "essence_count": 0},
            )
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_LOAD_ESSENCE_BY_THEMES, normalized)
        items = [
            EssenceItem(
                theme=str(row["theme"]),
                observation=row["observation"],
                key_finding=row["key_finding"],
                recommendation=row["recommendation"],
            )
            for row in rows
        ]
        log_public_chat_event(
            etapa="reader.load_essence",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "essence_count": len(items),
                "source": "memory_essence",
                "themes": [item.theme for item in items],
            },
        )
        return items


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
