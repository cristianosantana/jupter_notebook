from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from orion_mcp.core.config.settings import Settings

_logger = logging.getLogger(__name__)


async def retrieve_memory(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    query_embedding: list[float],
    settings: Settings,
    metadata_filters: dict[str, Any] | None = None,
    k: int = 3,
) -> list[str]:
    if not settings.enable_long_memory:
        return []
    vec_lit = "[" + ",".join(str(float(x)) for x in query_embedding) + "]"
    metadata_filters = metadata_filters or {}
    try:
        async with pool.acquire() as conn:
            if metadata_filters:
                rows = await conn.fetch(
                    """
                    SELECT content
                    FROM memory_embeddings
                    WHERE session_id = $1
                      AND metadata @> $4::jsonb
                    ORDER BY embedding <=> $2::vector
                    LIMIT $3
                    """,
                    session_id,
                    vec_lit,
                    k,
                    json.dumps(metadata_filters, ensure_ascii=False),
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT content
                    FROM memory_embeddings
                    WHERE session_id = $1
                    ORDER BY embedding <=> $2::vector
                    LIMIT $3
                    """,
                    session_id,
                    vec_lit,
                    k,
                )
    except Exception:
        _logger.warning("retrieve_memory_failed", exc_info=True)
        return []
    return [r["content"] for r in rows]


async def insert_memory_embedding_row(
    conn: asyncpg.Connection,
    *,
    session_id: str,
    content: str,
    embedding: list[float],
    metadata: dict[str, Any],
) -> None:
    vec_lit = "[" + ",".join(str(float(x)) for x in embedding) + "]"
    await conn.execute(
        """
        INSERT INTO memory_embeddings (session_id, content, embedding, metadata)
        VALUES ($1, $2, $3::vector, $4::jsonb)
        """,
        session_id,
        content,
        vec_lit,
        json.dumps(metadata, ensure_ascii=False),
    )


async def insert_memory_embedding(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    content: str,
    embedding: list[float],
    metadata: dict[str, Any],
) -> None:
    async with pool.acquire() as conn:
        await insert_memory_embedding_row(
            conn,
            session_id=session_id,
            content=content,
            embedding=embedding,
            metadata=metadata,
        )
