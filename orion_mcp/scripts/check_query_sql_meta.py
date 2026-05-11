#!/usr/bin/env python3
"""
Valida cabeçalhos /* @mcp_query_meta */ em ``mcp_adapter/query_sql/*.sql``
e confirma alinhamento com ``SQL_CATALOG``.

Uso (na raiz ``orion_mcp/``): ``PYTHONPATH=src python3 scripts/check_query_sql_meta.py``
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main() -> int:
    from orion_mcp.mcp_adapter.query_sql_meta import validate_query_sql_dir
    from orion_mcp.mcp_adapter.sql_catalog import SQL_CATALOG, query_sql_directory

    qdir = query_sql_directory()
    try:
        ids = validate_query_sql_dir(qdir)
    except ValueError as e:
        print("check_query_sql_meta:", e, file=sys.stderr)
        return 1

    if set(ids) != set(SQL_CATALOG.keys()):
        print(
            "check_query_sql_meta: divergência entre validate_query_sql_dir e SQL_CATALOG",
            file=sys.stderr,
        )
        return 1
    print(f"OK: {len(ids)} queries com meta válido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
