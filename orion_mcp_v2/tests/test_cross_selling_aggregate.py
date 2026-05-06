import pytest

from orion_mcp_v2.core.aggregators.cross_selling_aggregate import CrossSellingAggregator


def test_aggregate_valid_rows():
    agg = CrossSellingAggregator(top_n=5)
    rows = [
        {
            "servico_A_id": 1,
            "servico_B_id": 2,
            "frequencia_combo": 1,
            "receita_combo": 10.0,
            "extra_col": 9,
        },
    ]
    out = agg.enrich(rows)
    assert out["top_pairs"][0]["receita_combo"] == 10.0


def test_aggregate_missing_columns():
    agg = CrossSellingAggregator()
    rows = [{"servico_A_id": 1, "servico_B_id": 2}]
    with pytest.raises(ValueError, match="colunas em falta"):
        agg.enrich(rows)
