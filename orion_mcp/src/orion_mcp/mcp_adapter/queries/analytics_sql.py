from __future__ import annotations

from typing import Any

from orion_mcp.core.data_engine import build_drl_bundle, pop_log_session_id
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

        log_sid = pop_log_session_id(params)

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
        drl = build_drl_bundle(rows, query_id=query_id, log_session_id=log_sid)
        include_raw = bool(params.get("include_raw_rows", False))

        if summarize:
            return _compact_payload(
                query_id,
                output_shape,
                rows,
                lim,
                off,
                sample_rows=sample_cap,
                drl=drl,
                include_raw_rows=include_raw,
            )
        return _full_payload(query_id, output_shape, rows, lim, off, drl=drl)

    return _run


def _full_payload(
    query_id: str,
    output_shape: str,
    rows: list[dict[str, Any]],
    limit: int,
    offset: int,
    *,
    drl: dict[str, Any],
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "query_id": query_id,
        "output_shape": output_shape,
        "limit": limit,
        "offset": offset,
        "row_count": len(rows),
        "rows": rows,
        "payload_note": (
            "Campo rows contém todas as linhas desta página (até limit). "
            "Se row_count == limit, pode haver mais dados: usar offset na próxima chamada. "
            "Campos drl_* são resumo determinístico (Data Representation Layer)."
        ),
    }
    base.update(drl)
    return base


def _compact_payload(
    query_id: str,
    output_shape: str,
    rows: list[dict[str, Any]],
    limit: int,
    offset: int,
    *,
    sample_rows: int,
    drl: dict[str, Any],
    include_raw_rows: bool = False,
) -> dict[str, Any]:
    cap = max(1, min(_MAX_LIMIT, int(sample_rows)))
    n = max(0, min(cap, len(rows)))
    sample = rows[:n] if include_raw_rows else None
    base: dict[str, Any] = {
        "query_id": query_id,
        "output_shape": output_shape,
        "limit": limit,
        "offset": offset,
        "row_count": len(rows),
        "summarize": True,
        "include_raw_rows": include_raw_rows,
        "rows_omitted": not include_raw_rows,
        "note": (
            "Modo compacto via DRL: usar drl_summary, drl_insights, drl_sample e dataset_id. "
            + (
                f"rows_sample incluído até {n} linhas (include_raw_rows=true)."
                if include_raw_rows
                else "Sem rows/rows_sample no envelope (include_raw_rows=false)."
            )
        ),
        **drl,
    }
    if include_raw_rows and sample is not None:
        base["rows_sample"] = sample
    return base
