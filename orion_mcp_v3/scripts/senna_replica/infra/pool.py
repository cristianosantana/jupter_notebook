"""Pool PostgreSQL isolado para o harness Senna."""

from __future__ import annotations

import logging
import os

import asyncpg

_logger = logging.getLogger(__name__)

from pathlib import Path

_SENNA_ROOT = Path(__file__).resolve().parents[1]  # scripts/senna_replica
_REPO_ROOT = _SENNA_ROOT.parents[1]  # orion_mcp_v3
_PUBLIC_CHAT_ENV = _REPO_ROOT / "src" / "orion_mcp_v3" / "public_chat" / ".env"
_ROOT_ENV = _REPO_ROOT / ".env"

def _load_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # public_chat primeiro (PUBLIC_CHAT_POSTGRES_URL); raiz depois sem sobrescrever
    if _PUBLIC_CHAT_ENV.is_file():
        load_dotenv(_PUBLIC_CHAT_ENV)
    if _ROOT_ENV.is_file():
        load_dotenv(_ROOT_ENV, override=False)

def _resolve_database_url(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    _load_env_files()
    for key in (
        "DATABASE_URL",
        "PUBLIC_CHAT_POSTGRES_URL",
        "PUBLIC_CHAT_DATABASE_URL",
        "ORION_POSTGRES_URL",
    ):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""

async def create_postgres_pool(
    database_url: str | None = None,
    *,
    min_size: int = 1,
    max_size: int = 5,
    required: bool = False,
) -> asyncpg.Pool | None:
    url = _resolve_database_url(database_url)
    if not url:
        if required:
            raise RuntimeError("DATABASE_URL ausente — necessário para --from-db")
        return None
    # asyncpg espera postgresql:// (não +asyncpg)
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        return await asyncpg.create_pool(url, min_size=min_size, max_size=max_size)
    except Exception as exc:
        if required:
            raise
        _logger.warning("Senna PostgreSQL indisponível: %s", exc)
        return None


async def close_postgres_pool(pool: asyncpg.Pool | None) -> None:
    if pool is not None:
        await pool.close()
