"""Catálogo de análises SQL em ``mcp_adapter/query_sql/*.sql`` (metadados @mcp_query_meta)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orion_mcp.mcp_adapter.query_sql_meta import parse_sql_file


def query_sql_directory() -> Path:
    return Path(__file__).resolve().parent / "query_sql"


def _build_catalog() -> tuple[dict[str, dict[str, Any]], frozenset[str]]:
    reg: dict[str, dict[str, Any]] = {}
    tabular: set[str] = set()
    qdir = query_sql_directory()
    paths = sorted(qdir.glob("*.sql"), key=lambda p: p.name)
    if not paths:
        raise RuntimeError(f"nenhum ficheiro .sql em {qdir}")

    for path in paths:
        meta, sql_core = parse_sql_file(path)
        qid = meta["query_id"]
        if qid in reg:
            raise RuntimeError(f"query_id duplicado: {qid}")
        if meta["output_shape"] == "tabular_multiline":
            tabular.add(qid)

        entry: dict[str, Any] = {
            "filename": path.name,
            "resource_description": meta["resource_description"],
            "when_to_use": meta["when_to_use"],
            "output_shape": meta["output_shape"],
            "sql_body": sql_core,
        }
        if meta.get("not_confused_with"):
            entry["not_confused_with"] = list(meta["not_confused_with"])
        reg[qid] = entry

    return reg, frozenset(tabular)


SQL_CATALOG, TABULAR_MULTIROW_QUERY_IDS = _build_catalog()

QUERY_IDS: tuple[str, ...] = tuple(sorted(SQL_CATALOG.keys()))


def get_sql(query_id: str) -> str:
    if query_id not in SQL_CATALOG:
        raise KeyError(f"query_id desconhecido: {query_id}")
    return str(SQL_CATALOG[query_id]["sql_body"])
