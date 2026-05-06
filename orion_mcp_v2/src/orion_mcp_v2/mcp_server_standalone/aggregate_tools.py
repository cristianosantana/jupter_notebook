from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations

from orion_mcp_v2.core.aggregators.aggregator_registry import get_aggregator, registered_query_ids
from orion_mcp_v2.db.mysql.query_executor import AnalyticsQueryExecutor
from orion_mcp_v2.db.mysql.sql_catalog import QUERY_IDS


def register_aggregate_tools(mcp: FastMCP) -> None:
    """Regista tools FastMCP que reutilizam o mesmo registry que o pipeline HTTP."""
    _read_only = ToolAnnotations(readOnlyHint=True, idempotentHint=True)

    @mcp.tool(annotations=_read_only)
    async def list_aggregatable_queries(ctx: Context) -> list[str]:
        """Lista query_id que têm agregador skill registado e existem no catálogo SQL."""
        _ = ctx
        catalog = set(QUERY_IDS)
        return sorted(registered_query_ids() & catalog)

    @mcp.tool(annotations=_read_only)
    async def aggregate_for_query_id(
        ctx: Context,
        query_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Executa a query catalogada e devolve o dict `skill_aggregate` equivalente ao pipeline."""
        catalog = set(QUERY_IDS)
        if query_id not in catalog:
            raise ValueError(f"query_id não está no catálogo: {query_id}")
        allowed_agg = registered_query_ids()
        if query_id not in allowed_agg:
            raise ValueError(
                f"query_id sem agregador registado: {query_id}. "
                f"Use list_aggregatable_queries para ids suportados."
            )

        executor: AnalyticsQueryExecutor = ctx.lifespan_context["executor"]
        payload = await executor.execute(
            query_id,
            {
                "date_from": date_from,
                "date_to": date_to,
                "limit": max(1, min(10000, int(limit))),
                "offset": max(0, int(offset)),
            },
        )
        rows: list[dict[str, Any]] = payload.get("rows") or []
        agg = get_aggregator(query_id)
        if agg is None:
            raise RuntimeError(f"agregador em falta para query_id={query_id}")
        enriched = agg.enrich(rows)
        return {
            "query_id": query_id,
            "row_count": len(rows),
            "aggregate": enriched,
        }
