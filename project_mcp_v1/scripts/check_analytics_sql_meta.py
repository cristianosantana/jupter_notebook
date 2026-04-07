#!/usr/bin/env python3
"""
Valida cabeçalhos /* @mcp_query_meta */ em todos os mcp_server/query_sql/*.sql
e confirma que o módulo analytics_queries importa sem erro.

Uso: python3 scripts/check_analytics_sql_meta.py
CI: falha com código != 0 se YAML inválido, query_id ≠ stem, ou SQL inválido após o meta.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MCP = _ROOT / "mcp_server"
if str(_MCP) not in sys.path:
    sys.path.insert(0, str(_MCP))

from query_sql_meta import validate_query_sql_dir  # noqa: E402


def main() -> int:
    qdir = _MCP / "query_sql"
    try:
        ids = validate_query_sql_dir(qdir)
    except ValueError as e:
        print("check_analytics_sql_meta:", e, file=sys.stderr)
        return 1

    import analytics_queries  # noqa: E402

    if set(ids) != set(analytics_queries.QUERY_REGISTRY.keys()):
        print("check_analytics_sql_meta: divergência entre validate e QUERY_REGISTRY", file=sys.stderr)
        return 1
    print(f"OK: {len(ids)} queries com meta válido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
