from orion_mcp_v2.db.mysql.sql_catalog import QUERY_IDS
from orion_mcp_v2.mcp_server_standalone.server import build_mcp_server


def test_build_mcp_server_factory():
    mcp = build_mcp_server()
    assert mcp.name == "orion-analytics-mcp"


def test_catalog_allowlist_nonempty():
    assert len(QUERY_IDS) >= 3
    assert "ticket_medio_concessionaria_agg" in QUERY_IDS
