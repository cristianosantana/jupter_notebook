from __future__ import annotations

from orion_mcp.mcp_adapter.queries import ALLOWED_QUERY_IDS, QUERY_REGISTRY
from orion_mcp.mcp_adapter.sql_catalog import QUERY_IDS, SQL_CATALOG, TABULAR_MULTIROW_QUERY_IDS


def test_catalog_has_seventeen_sql_queries() -> None:
    assert len(SQL_CATALOG) == 17
    assert len(QUERY_IDS) == 17


def test_registry_includes_demo_and_catalog() -> None:
    assert "demo_ping" in QUERY_REGISTRY
    assert len(ALLOWED_QUERY_IDS) == 18
    for qid in QUERY_IDS:
        assert qid in QUERY_REGISTRY
        assert qid in ALLOWED_QUERY_IDS


def test_tabular_subset_of_catalog() -> None:
    assert TABULAR_MULTIROW_QUERY_IDS <= frozenset(SQL_CATALOG.keys())
