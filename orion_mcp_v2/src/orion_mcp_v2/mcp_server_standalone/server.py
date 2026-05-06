from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from dotenv import find_dotenv, load_dotenv
from fastmcp import FastMCP
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from orion_mcp_v2.db.mysql.mysql_pool import close_mysql_pool, create_mysql_pool
from orion_mcp_v2.db.mysql.query_executor import AnalyticsQueryExecutor
from orion_mcp_v2.db.mysql.sql_catalog import QUERY_IDS
from orion_mcp_v2.mcp_server_standalone.aggregate_tools import register_aggregate_tools


def _load_dotenv() -> None:
    """Carrega `.env` (busca a partir do cwd). Com pacote em site-packages, não depende de `__file__`."""
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path)


def _mysql_url_from_env() -> str:
    return (
        os.environ.get("ORION_V2_MCP_SRV_MYSQL_URL") or os.environ.get("ORION_V2_MYSQL_URL") or ""
    ).strip()


def build_mcp_server() -> FastMCP:
    _load_dotenv()

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        _ = server
        url = _mysql_url_from_env()
        pool = await create_mysql_pool(url or None)
        if pool is None:
            raise RuntimeError(
                "MySQL obrigatório para o MCP server: ORION_V2_MCP_SRV_MYSQL_URL ou ORION_V2_MYSQL_URL"
            )
        executor = AnalyticsQueryExecutor(pool)
        try:
            yield {"executor": executor}
        finally:
            await close_mysql_pool(pool)

    mcp = FastMCP("orion-analytics-mcp", lifespan=lifespan)
    register_aggregate_tools(mcp)

    _read_only = ToolAnnotations(readOnlyHint=True, idempotentHint=True)

    @mcp.tool(annotations=_read_only)
    async def run_analytics_query(
        ctx: Context,
        query_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Executa uma query catalogada (read-only)."""
        if query_id not in QUERY_IDS:
            raise ValueError(f"query_id não permitido: {query_id}")
        executor: AnalyticsQueryExecutor = ctx.lifespan_context["executor"]
        return await executor.execute(
            query_id,
            {
                "date_from": date_from,
                "date_to": date_to,
                "limit": max(1, min(10000, int(limit))),
                "offset": max(0, int(offset)),
            },
        )

    @mcp.tool(annotations=_read_only)
    async def list_analytics_queries(ctx: Context) -> list[str]:
        """Lista ids allowlisted do catálogo SQL."""
        _ = ctx
        return sorted(QUERY_IDS)

    return mcp
