from orion_mcp_v2.db.mysql.sql_catalog import QUERY_IDS, SQL_CATALOG


def test_catalog_non_empty():
    assert len(QUERY_IDS) >= 1
    assert "ticket_medio_concessionaria_agg" in SQL_CATALOG
