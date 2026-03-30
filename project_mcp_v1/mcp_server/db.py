"""Pool MySQL assíncrono e execução de SQL whitelisted com LIMIT/OFFSET."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any
from dotenv import load_dotenv
import aiomysql  # pyright: ignore[reportMissingImports]

load_dotenv()

_pool: aiomysql.Pool | None = None


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(type(obj))


async def get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is not None:
        return _pool

    database = os.environ.get("MYSQL_DATABASE", "").strip()
    if not database:
        raise RuntimeError("Defina MYSQL_DATABASE no ambiente para executar análises.")

    _pool = await aiomysql.create_pool(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        db=database,
        minsize=1,
        maxsize=5,
        autocommit=True,
        charset="utf8mb4",
    )
    return _pool


async def run_wrapped_select(
    sql_inner: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int | None]:
    escaped = sql_inner.replace("%", "%%")
    wrapped = f"SELECT * FROM (\n{escaped}\n) AS _mcp_sub LIMIT %s OFFSET %s"

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(wrapped, (limit, offset))
            rows = await cur.fetchall()
            count = cur.rowcount

    return list(rows), count if count >= 0 else None


def rows_to_json_payload(
    rows: list[dict[str, Any]],
    *,
    query_id: str,
    limit: int,
    offset: int,
    summarized: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "query_id": query_id,
        "limit": limit,
        "offset": offset,
        "row_count": len(rows),
        "rows": rows,
    }
    if summarized:
        payload["llm_summary"] = summarized
    return json.dumps(payload, ensure_ascii=False, default=_json_default)
