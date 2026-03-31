"""Registo MCP: ids legados compactos e novas queries do catálogo."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MCP = _ROOT / "mcp_server"
if str(_MCP) not in sys.path:
    sys.path.insert(0, str(_MCP))

import analytics_queries  # noqa: E402
import sql_params  # noqa: E402


def test_tabular_legacy_has_ten_ids():
    assert len(analytics_queries.TABULAR_LEGACY_QUERY_IDS) == 10
    assert "cross_selling" in analytics_queries.TABULAR_LEGACY_QUERY_IDS
    assert "propenso_compra_hora_dia_servico" in analytics_queries.TABULAR_LEGACY_QUERY_IDS
    assert "performance_vendedor_ano" in analytics_queries.TABULAR_LEGACY_QUERY_IDS


def test_json_batch_not_in_tabular_legacy():
    for qid in (
        "volume_os_concessionaria_mom",
        "volume_os_vendedor_ranking",
        "ticket_medio_concessionaria_agg",
        "ticket_medio_vendedor_top_bottom",
        "taxa_conversao_servicos_os_fechada",
    ):
        assert qid not in analytics_queries.TABULAR_LEGACY_QUERY_IDS
        assert qid in analytics_queries.QUERY_REGISTRY


def test_all_registered_queries_load_and_bind_dates():
    for qid in analytics_queries.QUERY_IDS:
        sql = analytics_queries.get_sql(qid)
        sql_params.apply_placeholders(sql, date_from="2025-01-01", date_to="2025-03-31")
