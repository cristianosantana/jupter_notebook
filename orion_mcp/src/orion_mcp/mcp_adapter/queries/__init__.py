from __future__ import annotations

from typing import Any

from orion_mcp.mcp_adapter.queries import analytics_sql, demo

QUERY_REGISTRY: dict[str, Any] = {}


def load_query_registry() -> dict[str, Any]:
    reg: dict[str, Any] = {}
    demo.register_queries(reg)
    analytics_sql.register_queries(reg)
    return reg


QUERY_REGISTRY.update(load_query_registry())

ALLOWED_QUERY_IDS = frozenset(QUERY_REGISTRY.keys())
