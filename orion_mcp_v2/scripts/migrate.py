#!/usr/bin/env python3
"""Aplica migrações SQL em ordem lexical."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    mig_dir = root / "migrations"
    url = os.environ.get("ORION_V2_DATABASE_URL", "").strip()
    if not url:
        print("ORION_V2_DATABASE_URL não definido", file=sys.stderr)
        sys.exit(1)
    sql_files = sorted(mig_dir.glob("*.sql"))
    if not sql_files:
        print(f"nenhum .sql em {mig_dir}", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _orion_v2_schema_migrations (
              id TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        applied = {r["id"] for r in await conn.fetch("SELECT id FROM _orion_v2_schema_migrations")}
        for path in sql_files:
            mid = path.name
            if mid in applied:
                print(f"skip {mid}")
                continue
            body = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(body)
                await conn.execute(
                    "INSERT INTO _orion_v2_schema_migrations (id) VALUES ($1)",
                    mid,
                )
            print(f"ok {mid}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
