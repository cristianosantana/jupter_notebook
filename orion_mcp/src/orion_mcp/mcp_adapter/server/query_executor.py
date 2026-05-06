from __future__ import annotations

import json
import logging
import time
from typing import Any

from orion_mcp.mcp_adapter.queries import ALLOWED_QUERY_IDS, QUERY_REGISTRY

_logger = logging.getLogger(__name__)


_ORION_INTERNAL_SAMPLE_KEY = "_orion_compact_sample_rows"


class QueryExecutor:
    """Executa apenas query_id registados; sem SQL dinâmico externo."""

    def __init__(self, mysql_pool: Any | None, *, compact_sample_rows: int = 20):
        self._pool = mysql_pool
        self._compact_sample_rows = max(1, min(10_000, int(compact_sample_rows)))

    async def run(self, query_id: str, params: dict[str, Any]) -> dict[str, Any]:
        print(f"[ORION_MCP] QueryExecutor.run: INÍCIO query_id={query_id!r}", flush=True)
        if query_id not in ALLOWED_QUERY_IDS:
            print(f"[ORION_MCP] QueryExecutor.run: query_id NÃO permitido {query_id!r}", flush=True)
            raise ValueError(f"query_id não permitido: {query_id}")
        handler = QUERY_REGISTRY[query_id]
        merged = dict(params)
        merged.pop(_ORION_INTERNAL_SAMPLE_KEY, None)
        merged[_ORION_INTERNAL_SAMPLE_KEY] = self._compact_sample_rows
        print("[ORION_MCP] QueryExecutor.run: ANTES handler(pool, params)", flush=True)
        t0 = time.perf_counter()
        out = await handler(self._pool, merged)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        print("[ORION_MCP] QueryExecutor.run: DEPOIS handler — FIM", flush=True)
        rc = out.get("row_count") if isinstance(out, dict) else None
        drl = bool(isinstance(out, dict) and isinstance(out.get("drl_summary"), dict))
        _logger.info(
            "query_executed",
            extra={
                "query_id": query_id,
                "row_count": rc,
                "handler_ms": elapsed_ms,
                "drl": drl,
            },
        )
        return out


def parse_json_object(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as e:
        raise ValueError("args_json inválido") from e
    if not isinstance(data, dict):
        raise ValueError("args_json deve ser um objeto JSON")
    return data
