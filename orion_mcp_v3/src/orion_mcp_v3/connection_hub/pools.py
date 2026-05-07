"""Fábricas de pool/cliente — espelho funcional de orion_mcp_v2 (URLs + lazy optional)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import unquote, urlparse

import asyncpg

_logger = logging.getLogger(__name__)


def _parse_mysql_url(url: str) -> dict[str, Any]:
    u = urlparse(url)
    if u.scheme not in ("mysql", "mysql+asyncmy"):
        raise ValueError("mysql_url must use mysql:// or mysql+asyncmy://")
    db = (u.path or "/").lstrip("/").split("?", 1)[0]
    return {
        "host": u.hostname or "localhost",
        "port": u.port or 3306,
        "user": unquote(u.username or ""),
        "password": unquote(u.password or ""),
        "db": db,
    }


async def create_mysql_pool(
    url: str | None,
    *,
    minsize: int = 1,
    maxsize: int = 10,
) -> Any | None:
    if not url or not url.strip():
        return None
    import asyncmy

    cfg = _parse_mysql_url(url.strip())
    return await asyncmy.create_pool(
        **cfg,
        minsize=minsize,
        maxsize=maxsize,
        autocommit=True,
    )


async def close_mysql_pool(pool: Any | None) -> None:
    if pool is not None:
        pool.close()
        await pool.wait_closed()


async def create_postgres_pool(
    database_url: str | None,
    *,
    min_size: int = 1,
    max_size: int = 10,
    required: bool = False,
) -> asyncpg.Pool | None:
    """
    `required=False`: em falha regista aviso e devolve None (útil em dev).
    `required=True`: propaga excepção.
    """
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
        _logger.warning("PostgreSQL indisponível: %s", exc)
        return None


async def close_postgres_pool(pool: asyncpg.Pool | None) -> None:
    if pool is not None:
        await pool.close()


async def create_redis_client(url: str | None, *, decode_responses: bool = True) -> Any | None:
    """Cliente asyncio redis(s). Devolve None se URL vazia."""
    if not url or not str(url).strip():
        return None
    import redis.asyncio as redis

    return redis.from_url(url.strip(), decode_responses=decode_responses)


async def close_redis_client(client: Any | None) -> None:
    if client is None:
        return
    close = getattr(client, "aclose", None)
    if callable(close):
        await close()
        return
    c = getattr(client, "close", None)
    if callable(c):
        await c() if hasattr(c, "__await__") else c()
