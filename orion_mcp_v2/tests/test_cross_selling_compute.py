from orion_mcp_v2.core.aggregators.cross_selling_compute import compute_cross_selling_aggregate


def test_compute_groups_pairs_and_top_n():
    rows = [
        {
            "servico_A_id": 1,
            "servico_B_id": 2,
            "frequencia_combo": 2,
            "receita_combo": 100.0,
        },
        {
            "servico_A_id": 1,
            "servico_B_id": 2,
            "frequencia_combo": 1,
            "receita_combo": 50.0,
        },
        {
            "servico_A_id": 3,
            "servico_B_id": 4,
            "frequencia_combo": 1,
            "receita_combo": 300.0,
        },
    ]
    out = compute_cross_selling_aggregate(rows, top_n=2)
    assert out["totals"]["pairs_distinct"] == 2
    assert out["totals"]["receita_total"] == 450.0
    assert len(out["top_pairs"]) == 2
    assert out["top_pairs"][0]["servico_A_id"] == 3
    assert out["top_pairs"][0]["receita_combo"] == 300.0
    assert out["concentration_top_n_pct_receita"] == 100.0


def test_compute_empty_rows():
    out = compute_cross_selling_aggregate([], top_n=10)
    assert out["top_pairs"] == []
    assert out["totals"]["pairs_distinct"] == 0
