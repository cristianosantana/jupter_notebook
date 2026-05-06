from __future__ import annotations

import logging

import asyncpg

from orion_mcp.core.config.settings import Settings

_logger = logging.getLogger(__name__)


async def create_pool(settings: Settings) -> asyncpg.Pool | None:
    if not settings.database_url:
        return None
    try:
        return await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
    except Exception:
        if settings.db_required or settings.is_production:
            raise
        _logger.warning("PostgreSQL unavailable; using in-memory state (dev only).", exc_info=True)
        return None
