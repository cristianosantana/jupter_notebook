"""Fábrica de conexão e persistência do Chat Público."""

from __future__ import annotations

import asyncpg

from orion_mcp_v3.public_chat.config.settings import PublicChatSettings, load_settings
from orion_mcp_v3.public_chat.infrastructure.postgres.pool import (
    close_postgres_pool,
    create_postgres_pool,
)
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore


async def create_database_pool(
    settings: PublicChatSettings | None = None,
    *,
    required: bool = False,
) -> asyncpg.Pool | None:
    cfg = settings or load_settings()
    return await create_postgres_pool(
        cfg.postgres_url,
        min_size=cfg.postgres_pool_min,
        max_size=cfg.postgres_pool_max,
        required=required,
    )


def build_response_store(pool: asyncpg.Pool) -> ResponseStore:
    return ResponseStore(pool)


__all__ = [
    "build_response_store",
    "close_postgres_pool",
    "create_database_pool",
]
