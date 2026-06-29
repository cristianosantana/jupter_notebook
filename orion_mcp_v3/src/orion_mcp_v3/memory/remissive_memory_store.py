"""Persistência da visão remissiva materializada em ``memory_*``."""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from orion_mcp_v3.memory.remissive_models import (
    CompressionLogEntry,
    RemissiveEssenceItem,
    RemissiveKnowledgeItem,
    SupervisedMemoryBatch,
)
from orion_mcp_v3.protocols.embedding import EmbeddingService
from orion_mcp_v3.providers.openai_embedding import OpenAIEmbeddingService


_UPSERT_MEMORY_CURTA = """
INSERT INTO "public"."memory_curta" (
    "user_id",
    "category",
    "context_key",
    "validated_answer",
    "recent_questions",
    "key_metrics",
    "consolidated_at",
    "last_seen_at",
    "ttl_expires_at",
    "metric_kind",
    "dimension"
)
VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, COALESCE($7, now()), now(), $8, $9, $10)
ON CONFLICT ("context_key")
DO UPDATE SET
    "user_id" = EXCLUDED."user_id",
    "category" = EXCLUDED."category",
    "validated_answer" = EXCLUDED."validated_answer",
    "recent_questions" = EXCLUDED."recent_questions",
    "key_metrics" = EXCLUDED."key_metrics",
    "consolidated_at" = EXCLUDED."consolidated_at",
    "last_seen_at" = now(),
    "ttl_expires_at" = EXCLUDED."ttl_expires_at",
    "metric_kind" = EXCLUDED."metric_kind",
    "dimension" = EXCLUDED."dimension"
RETURNING "id"
"""

_DELETE_INDEX = """
DELETE FROM "public"."memory_embeddings"
WHERE "origin_id" = $1 AND "origin_type" = 'memory_curta'
"""

_INSERT_INDEX = """
INSERT INTO "public"."memory_embeddings" (
    "user_id",
    "origin_id",
    "origin_type",
    "text",
    "embedding",
    "category",
    "ttl_expires_at"
)
VALUES ($1, $2, 'memory_curta', $3, $4::vector, $5, $6)
"""

_UPSERT_ESSENCE = """
INSERT INTO "public"."memory_essence" (
    "user_id",
    "theme",
    "observation",
    "key_finding",
    "recommendation",
    "stable_metrics",
    "last_updated",
    "confidence"
)
VALUES ($1, $2, $3, $4, $5, $6::jsonb, COALESCE($7, now()), $8)
ON CONFLICT ("user_id", "theme")
DO UPDATE SET
    "observation" = EXCLUDED."observation",
    "key_finding" = EXCLUDED."key_finding",
    "recommendation" = EXCLUDED."recommendation",
    "stable_metrics" = EXCLUDED."stable_metrics",
    "last_updated" = EXCLUDED."last_updated",
    "confidence" = EXCLUDED."confidence"
"""

_INSERT_COMPRESSION_LOG = """
INSERT INTO "public"."memory_compression_log" (
    "batch_key",
    "user_id",
    "from_state",
    "to_state",
    "messages_compressed",
    "compression_ratio",
    "what_was_kept",
    "what_was_dropped",
    "compressed_at"
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, COALESCE($9, now()))
ON CONFLICT ("batch_key")
DO UPDATE SET
    "user_id" = EXCLUDED."user_id",
    "from_state" = EXCLUDED."from_state",
    "to_state" = EXCLUDED."to_state",
    "messages_compressed" = EXCLUDED."messages_compressed",
    "compression_ratio" = EXCLUDED."compression_ratio",
    "what_was_kept" = EXCLUDED."what_was_kept",
    "what_was_dropped" = EXCLUDED."what_was_dropped",
    "compressed_at" = EXCLUDED."compressed_at"
"""


_SEARCH_ORIGIN_IDS = """
SELECT "origin_id"
FROM "public"."memory_embeddings"
WHERE "user_id" = $2
  AND "origin_type" = 'memory_curta'
  AND ("ttl_expires_at" IS NULL OR "ttl_expires_at" > now())
ORDER BY "embedding" <=> $1::vector
LIMIT $3
"""


_DELETE_STALE_MEMORY_CURTA = """
DELETE FROM "public"."memory_curta"
WHERE "last_seen_at" < now() - ($1::int * INTERVAL '1 day')
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class RemissiveMemoryStore:
    """Grava conteúdo validado e repovoa o índice remissivo por ``origin_id``."""

    def __init__(self, pool: asyncpg.Pool, embedding_service: EmbeddingService) -> None:
        self._pool = pool
        self._embed = embedding_service

    async def upsert_knowledge(self, item: RemissiveKnowledgeItem) -> int:
        questions = [q.strip() for q in item.index_questions if q.strip()]

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                origin_id = await conn.fetchval(
                    _UPSERT_MEMORY_CURTA,
                    item.user_id,
                    item.category,
                    item.context_key,
                    item.validated_answer,
                    _json(list(item.recent_questions)),
                    _json(dict(item.key_metrics)),
                    item.consolidated_at,
                    item.ttl_expires_at,
                    item.metric_kind,
                    item.dimension,
                )
                origin_id = int(origin_id)

                await conn.execute(_DELETE_INDEX, origin_id)

                if not questions:
                    return origin_id

                vectors = await self._embed.embed(questions)
                for question, vector in zip(questions, vectors, strict=False):
                    await conn.execute(
                        _INSERT_INDEX,
                        item.user_id,
                        origin_id,
                        question,
                        OpenAIEmbeddingService.to_pgvector(vector),
                        item.category,
                        item.ttl_expires_at,
                    )
                return origin_id

    async def upsert_essence(self, item: RemissiveEssenceItem) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                _UPSERT_ESSENCE,
                item.user_id,
                item.theme,
                item.observation,
                item.key_finding,
                item.recommendation,
                _json(dict(item.stable_metrics)),
                item.last_updated,
                item.confidence,
            )

    async def write_compression_log(self, entry: CompressionLogEntry) -> None:
        batch_key = entry.batch_key or f"{entry.user_id}:{entry.from_state}:{entry.to_state}"
        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_COMPRESSION_LOG,
                batch_key,
                entry.user_id,
                entry.from_state,
                entry.to_state,
                entry.messages_compressed,
                entry.compression_ratio,
                entry.what_was_kept,
                entry.what_was_dropped,
                entry.compressed_at,
            )

    async def search_origin_ids(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 5,
        probes: int = 10,
    ) -> list[int]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        vectors = await self._embed.embed([normalized_query])
        if not vectors:
            return []
        vector = OpenAIEmbeddingService.to_pgvector(vectors[0])

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT set_config('ivfflat.probes', $1, true)", str(max(1, probes)))
                rows = await conn.fetch(_SEARCH_ORIGIN_IDS, vector, user_id, max(1, limit))
        return [int(row["origin_id"]) for row in rows]

    async def delete_stale_knowledge(self, *, days: int = 90) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(_DELETE_STALE_MEMORY_CURTA, max(1, days))
        parts = result.split()
        if len(parts) == 2 and parts[0].upper() == "DELETE" and parts[1].isdigit():
            return int(parts[1])
        return 0

    async def persist_batch(self, batch: SupervisedMemoryBatch) -> list[int]:
        origin_ids: list[int] = []
        for item in batch.knowledge:
            origin_ids.append(await self.upsert_knowledge(item))
        for item in batch.essence:
            await self.upsert_essence(item)
        if batch.compression_log is not None:
            await self.write_compression_log(batch.compression_log)
        return origin_ids
