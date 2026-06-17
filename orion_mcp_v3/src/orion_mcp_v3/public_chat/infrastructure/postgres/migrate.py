"""Aplicação de migrações SQL do Chat Público."""

from __future__ import annotations

from importlib import resources

import asyncpg


def migrations_package() -> str:
    return "orion_mcp_v3.public_chat.infrastructure.postgres.migrations"


def list_migration_files() -> list[str]:
    root = resources.files(migrations_package())
    return sorted(path.name for path in root.iterdir() if path.name.endswith(".sql"))


def read_migration(filename: str) -> str:
    root = resources.files(migrations_package())
    return root.joinpath(filename).read_text(encoding="utf-8")


def split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped and not buf:
            continue
        if stripped.startswith("--") and not buf:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            block = "\n".join(buf).strip()
            buf = []
            if block:
                statements.append(block)
    if buf:
        block = "\n".join(buf).strip()
        if block:
            statements.append(block)
    return statements


async def apply_migrations(conn: asyncpg.Connection) -> list[str]:
    applied: list[str] = []
    for filename in list_migration_files():
        text = read_migration(filename)
        for stmt in split_sql_statements(text):
            await conn.execute(stmt)
        applied.append(filename)
    return applied
