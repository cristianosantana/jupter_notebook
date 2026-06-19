"""Pool PostgreSQL do Chat Público — sem depender de connection_hub."""

from __future__ import annotations

import logging

import asyncpg

_logger = logging.getLogger(__name__)


async def create_postgres_pool(
    database_url: str | None,
    *,
    min_size: int = 1,
    max_size: int = 10,
    required: bool = False,
) -> asyncpg.Pool | None:
    if not database_url or not database_url.strip():
        return None
    try:
        return await asyncpg.create_pool(
            database_url.strip(),
            min_size=min_size,
            max_size=max_size,
        )
    except Exception as exc:
        if required:
            raise
        _logger.warning("public_chat PostgreSQL indisponível: %s", exc)
        return None


async def close_postgres_pool(pool: asyncpg.Pool | None) -> None:
    if pool is not None:
        await pool.close()
