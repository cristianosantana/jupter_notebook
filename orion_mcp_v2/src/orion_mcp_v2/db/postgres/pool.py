from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from orion_mcp_v2.config.settings import Settings

_logger = logging.getLogger(__name__)


async def create_pool(settings: "Settings") -> asyncpg.Pool | None:
    if not settings.database_url:
        return None
    try:
        return await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
    except Exception as exc:
        if settings.db_required or settings.is_production:
            raise
        _logger.warning("PostgreSQL indisponível (dev): %s", exc)
        return None


async def close_pool(pool: asyncpg.Pool | None) -> None:
    if pool is not None:
        await pool.close()
