"""Pool MySQL assíncrono e execução de SQL whitelisted com LIMIT/OFFSET."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import aiomysql  # pyright: ignore[reportMissingImports]


def _load_dotenv_for_mcp_process() -> None:
    """
    O subprocesso MCP herda ``MYSQL_*`` do pai; ``load_dotenv()`` sem ``override`` não corrige.

    Carrega o primeiro ``.env`` existente entre a raiz do projecto (pai de ``mcp_server/``) e
    ``Path.cwd()``, com ``override=True`` para o ficheiro mandar sobre o ambiente herdado.
    """
    for candidate in (
        Path(__file__).resolve().parent.parent / ".env",
        Path.cwd() / ".env",
    ):
        if candidate.is_file():
            load_dotenv(candidate, override=True)
            return
    load_dotenv()


_load_dotenv_for_mcp_process()

_pool: aiomysql.Pool | None = None


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


async def get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is not None:
        return _pool

    try:
        from app.config import get_settings, sync_mysql_env_from_settings

        sync_mysql_env_from_settings(get_settings())
    except Exception:
        pass

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


# Amostra devolvida em modo summarize (evita encher o contexto do LLM com até 10k linhas).
_COMPACT_SAMPLE_DEFAULT = 20


def rows_to_compact_json_payload(
    rows: list[dict[str, Any]],
    *,
    query_id: str,
    limit: int,
    offset: int,
    summarized: str | None = None,
    sample_size: int = _COMPACT_SAMPLE_DEFAULT,
) -> str:
    """JSON enxuto para summarize=true: metadados, amostra de linhas e opcionalmente llm_summary."""
    n = max(0, min(int(sample_size), len(rows)))
    sample = rows[:n]
    payload: dict[str, Any] = {
        "query_id": query_id,
        "limit": limit,
        "offset": offset,
        "row_count": len(rows),
        "rows_sample": sample,
        "rows_sample_note": (
            f"Payload compacto: rows_sample tem {len(sample)} de {len(rows)} linhas desta página "
            f"(limit={limit} offset={offset}). "
            "Para análises tabular legacy, summarize=false continua compacto (não recebe todas as linhas aqui). "
            "Para performance_vendedor_mes/ano e outras não legacy, summarize=false devolve o campo rows completo da página."
        ),
    }
    if summarized:
        payload["llm_summary"] = summarized
    else:
        payload["llm_summary"] = None
        payload["note"] = (
            "Resumo MCP indisponível. Não trates rows_sample como ranking global nem dataset completo. "
            "Se precisares de todas as linhas, usa query_id fora do conjunto tabular legacy com summarize=false "
            "(ou paginação offset); ver list_analytics_queries."
        )
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


def rows_to_sampling_preview_payload(
    rows: list[dict[str, Any]],
    *,
    query_id: str,
    sample_size: int = 40,
) -> str:
    """JSON curto só para pedido de resumo MCP (sampling), sem notas longas ao modelo."""
    n = max(0, min(int(sample_size), len(rows)))
    payload = {
        "query_id": query_id,
        "row_count": len(rows),
        "rows_sample": rows[:n],
    }
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


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
        "payload_note": (
            "Campo rows contém todas as linhas desta página (até limit). "
            "Se row_count == limit, pode haver mais dados: usar offset na próxima chamada."
        ),
    }
    if summarized:
        payload["llm_summary"] = summarized
    return json.dumps(payload, ensure_ascii=False, default=_json_default)
