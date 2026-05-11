from __future__ import annotations

from typing import Any

from orion_mcp.mcp_adapter.sql_catalog import SQL_CATALOG
from orion_mcp.mcp_adapter.sql_placeholders import apply_placeholders
from orion_mcp.mcp_adapter.sql_select import run_catalog_select

_COMPACT_SAMPLE_DEFAULT = 20
_MAX_LIMIT = 10000
_ORION_INTERNAL_SAMPLE_KEY = "_orion_compact_sample_rows"


def register_queries(reg: dict[str, Any]) -> None:
    for qid in SQL_CATALOG:
        reg[qid] = _make_sql_handler(qid)


def _make_sql_handler(query_id: str):
    entry = SQL_CATALOG[query_id]
    output_shape = str(entry["output_shape"])

    async def _run(pool: Any, params: dict[str, Any]) -> dict[str, Any]:
        if pool is None:
            raise ValueError(
                "Pool MySQL não configurado; defina ORION_MCP_MYSQL_URL no processo do serviço MCP."
            )

        sql_raw = str(entry["sql_body"])
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        if isinstance(date_from, str):
            date_from = date_from.strip() or None
        if isinstance(date_to, str):
            date_to = date_to.strip() or None

        sql_inner = apply_placeholders(sql_raw, date_from=date_from, date_to=date_to)

        lim = max(1, min(_MAX_LIMIT, int(params.get("limit", 10000))))
        off = max(0, int(params.get("offset", 0)))
        summarize = bool(params.get("summarize", False))

        raw_cap = params.get(_ORION_INTERNAL_SAMPLE_KEY)
        try:
            sample_cap = int(raw_cap) if raw_cap is not None else _COMPACT_SAMPLE_DEFAULT
        except (TypeError, ValueError):
            sample_cap = _COMPACT_SAMPLE_DEFAULT
        sample_cap = max(1, min(_MAX_LIMIT, sample_cap))

        rows = await run_catalog_select(pool, sql_inner, limit=lim, offset=off)

        if summarize:
            return _compact_payload(
                query_id, output_shape, rows, lim, off, sample_rows=sample_cap
            )
        return _full_payload(query_id, output_shape, rows, lim, off)

    return _run


def _full_payload(
    query_id: str,
    output_shape: str,
    rows: list[dict[str, Any]],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "output_shape": output_shape,
        "limit": limit,
        "offset": offset,
        "row_count": len(rows),
        "rows": rows,
        "payload_note": (
            "Campo rows contém todas as linhas desta página (até limit). "
            "Se row_count == limit, pode haver mais dados: usar offset na próxima chamada."
        ),
    }


def _compact_payload(
    query_id: str,
    output_shape: str,
    rows: list[dict[str, Any]],
    limit: int,
    offset: int,
    *,
    sample_rows: int,
) -> dict[str, Any]:
    cap = max(1, min(_MAX_LIMIT, int(sample_rows)))
    n = max(0, min(cap, len(rows)))
    sample = rows[:n]
    return {
        "query_id": query_id,
        "output_shape": output_shape,
        "limit": limit,
        "offset": offset,
        "row_count": len(rows),
        "rows_sample": sample,
        "summarize": True,
        "llm_summary": None,
        "note": (
            f"Modo compacto: rows_sample com até {cap} linhas desta página (ORION_TOOL_LLM_PREVIEW_ROWS "
            "no processo MCP). Para todas as linhas da página na resposta, summarize=false."
        ),
    }
