"""Execução de SELECT whitelisted com LIMIT/OFFSET (asyncmy), compatível com project_mcp_v1/db."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from asyncmy.cursors import DictCursor


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, datetime):
        return obj.isoformat(sep=" ", timespec="seconds")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.isoformat(timespec="seconds")
    raise TypeError(type(obj))


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        try:
            out[str(k)] = _json_default(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
        except TypeError:
            out[str(k)] = str(v)
    return out


async def run_catalog_select(
    pool: Any,
    sql_inner: str,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    escaped = sql_inner.replace("%", "%%")
    wrapped = f"SELECT * FROM (\n{escaped}\n) AS _mcp_sub LIMIT %s OFFSET %s"

    async with pool.acquire() as conn:
        async with conn.cursor(cursor=DictCursor) as cur:
            await cur.execute(wrapped, (limit, offset))
            rows = await cur.fetchall()

    return [_normalize_row(dict(r)) for r in rows]
