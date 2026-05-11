"""
Pipeline assíncrono: embed (OpenAI) + INSERT em memory_embeddings.
Usado pelo worker Celery; não faz parte do hot path HTTP.
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from orion_mcp.core.config.settings import Settings, get_settings
from orion_mcp.core.llm.embeddings import embed_text
from orion_mcp.core.memory.long import insert_memory_embedding_row

_logger = logging.getLogger(__name__)


async def run_embed_and_insert(
    *,
    session_id: str,
    content: str,
    metadata: dict[str, Any],
    settings: Settings | None = None,
) -> None:
    """
    Gera embedding do texto e persiste uma linha em memory_embeddings.
    Falhas são registadas e não propagadas (evita poisonar a fila sem dead-letter).
    """
    cfg = settings or get_settings()
    db = (cfg.database_url or "").strip()
    if not db:
        _logger.warning("run_embed_and_insert_skip: sem database_url")
        return
    if not cfg.openai_api_key:
        _logger.warning("run_embed_and_insert_skip: sem openai_api_key")
        return
    text = (content or "").strip()
    if not text:
        return
    text = text[:8000]
    try:
        vec = await embed_text(cfg, text)
        conn = await asyncpg.connect(db)
        try:
            await insert_memory_embedding_row(
                conn,
                session_id=session_id,
                content=text,
                embedding=vec,
                metadata=metadata,
            )
        finally:
            await conn.close()
        _logger.info(
            "memory_embed_inserted",
            extra={"session_id_prefix": session_id[:24], "content_len": len(text)},
        )
    except Exception:
        _logger.exception(
            "run_embed_and_insert_failed",
            extra={"session_id_prefix": (session_id or "")[:24]},
        )
