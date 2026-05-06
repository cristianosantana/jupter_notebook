from __future__ import annotations

from typing import Any

QueryHandler = Any  # async (pool, params) -> dict


async def demo_ping(pool: Any, params: dict[str, Any]) -> dict[str, Any]:
    """
    Query mínima de contrato: SELECT 1.
    Sem pool MySQL, devolve resultado sintético (paridade CI/dev).
    """
    _ = params
    if pool is None:
        return {"ping": 1, "note": "mysql_pool_disabled"}
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1 AS ping")
            row = await cur.fetchone()
            return {"ping": int(row[0]) if row else 0}


def register_queries(reg: dict[str, QueryHandler]) -> None:
    reg["demo_ping"] = demo_ping
