"""Motor de agregação host-only."""

from app.analytics_aggregate_engine import run_analytics_aggregate


def test_sum_group_by():
    rows = [
        {"loja": "A", "qtd": 2, "val": 10.0},
        {"loja": "A", "qtd": 3, "val": 5.0},
        {"loja": "B", "qtd": 1, "val": 7.0},
    ]
    r = run_analytics_aggregate(
        rows,
        group_by=["loja"],
        aggregations=[{"column": "qtd", "op": "sum"}, {"column": "", "op": "count"}],
        top_k=10,
        sort_by="sum_qtd",
        sort_dir="desc",
    )
    assert r["ok"] is True
    assert r["row_count"] == 2
    assert r["rows"][0]["loja"] == "A"
    assert r["rows"][0]["sum_qtd"] == 5


def test_top_k_and_filter():
    rows = [{"g": 1, "x": 10}, {"g": 1, "x": 5}, {"g": 2, "x": 100}]
    r = run_analytics_aggregate(
        rows,
        group_by=["g"],
        aggregations=[{"column": "x", "op": "sum"}],
        filters=[{"column": "x", "op": "gte", "value": 10}],
        top_k=1,
        sort_by="sum_x",
        sort_dir="desc",
    )
    assert r["ok"] is True
    assert r["row_count"] == 1
    assert r["rows"][0]["g"] == 2
