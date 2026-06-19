#!/usr/bin/env python3
"""Aplica migrações SQL do Chat Público sem depender do script global do Orion."""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlparse

import asyncpg

from orion_mcp_v3.public_chat.config.settings import load_settings
from orion_mcp_v3.public_chat.infrastructure.postgres.migrate import apply_migrations


async def _run() -> None:
    settings = load_settings()
    if not settings.postgres_enabled:
        print(
            "Defina PUBLIC_CHAT_POSTGRES_URL ou PUBLIC_CHAT_DATABASE_URL "
            "em public_chat/.env ou orion_mcp_v3/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    dsn = settings.postgres_url
    try:
        conn = await asyncpg.connect(dsn)
    except OSError as exc:
        _print_connect_help(dsn, exc)
        sys.exit(1)
    except Exception as exc:
        print(f"Erro ao ligar ao Postgres: {exc}", file=sys.stderr)
        _print_connect_help(dsn, exc)
        sys.exit(1)

    try:
        applied = await apply_migrations(conn)
        for name in applied:
            print(f"-- {name}")
        print("OK: migrações do Chat Público aplicadas.")
    finally:
        await conn.close()


def _print_connect_help(dsn: str, exc: BaseException) -> None:
    print(f"Detalhe: {exc}", file=sys.stderr)
    try:
        host = urlparse(dsn.replace("postgresql+asyncpg://", "postgresql://")).hostname
    except Exception:
        host = None
    print(
        "\nUse uma URL acessível da máquina onde corre o script, por exemplo:\n"
        "  postgresql://postgres:secret@127.0.0.1:5432/dev\n",
        file=sys.stderr,
    )
    if host:
        print(f"Hostname actual na URL: {host!r}\n", file=sys.stderr)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
