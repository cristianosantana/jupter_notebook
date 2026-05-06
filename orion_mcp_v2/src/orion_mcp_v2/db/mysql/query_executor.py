from __future__ import annotations

import logging
from typing import Any

from orion_mcp_v2.db.mysql.sql_catalog import SQL_CATALOG
from orion_mcp_v2.db.mysql.sql_placeholders import apply_placeholders
from orion_mcp_v2.db.mysql.sql_select import run_catalog_select

_logger = logging.getLogger(__name__)

_MAX_LIMIT = 10000


class AnalyticsQueryExecutor:
    """Executa apenas query_id registados no catálogo."""

    def __init__(self, mysql_pool: Any | None):
        self._pool = mysql_pool

    async def execute(self, query_id: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._pool is None:
            raise ValueError("Pool MySQL não configurado (ORION_V2_MYSQL_URL).")
        if query_id not in SQL_CATALOG:
            raise ValueError(f"query_id não permitido: {query_id}")

        entry = SQL_CATALOG[query_id]
        sql_raw = str(entry["sql_body"])
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        if isinstance(date_from, str):
            date_from = date_from.strip() or None
        if isinstance(date_to, str):
            date_to = date_to.strip() or None

        sql_inner = apply_placeholders(sql_raw, date_from=date_from, date_to=date_to)

        lim = max(1, min(_MAX_LIMIT, int(params.get("limit", 5000))))
        off = max(0, int(params.get("offset", 0)))

        rows = await run_catalog_select(self._pool, sql_inner, limit=lim, offset=off)
        _logger.info(
            "mysql_query_ok",
            extra={"query_id": query_id, "row_count": len(rows)},
        )
        return {
            "query_id": query_id,
            "output_shape": entry["output_shape"],
            "limit": lim,
            "offset": off,
            "row_count": len(rows),
            "rows": rows,
        }
