import importlib.util

import pytest

from orion_mcp_v2.core.data_engine.sklearn_enrichment import (
    isolation_forest_outlier_counts,
    tabular_summary_light,
    tabular_summary_pandas,
)


def test_tabular_summary_light_empty():
    assert tabular_summary_light([])["row_count"] == 0


def test_tabular_summary_pandas_two_rows():
    r = tabular_summary_pandas([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    assert r.get("row_count") == 2
    if importlib.util.find_spec("pandas") is None:
        assert r.get("pandas") is False
        pytest.skip("pandas opcional (extras analytics)")
    assert r.get("pandas") is True


def test_isolation_forest_returns_counts_only():
    rows = [{"metric": float(i)} for i in range(40)]
    r = isolation_forest_outlier_counts(rows, column="metric")
    if importlib.util.find_spec("sklearn") is None or importlib.util.find_spec("pandas") is None:
        assert r.get("available") is False
        pytest.skip("scikit-learn/pandas opcional (extras analytics)")
    assert r.get("available") is True
    assert isinstance(r.get("outliers"), int)
