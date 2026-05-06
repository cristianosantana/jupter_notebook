from orion_mcp.core.data_engine.pipeline import build_drl_bundle
from orion_mcp.core.data_engine.schema_inference import infer_schema
from orion_mcp.core.data_engine.summary_builder import build_summary
from orion_mcp.core.data_engine.value_extractor import extract_insights


def test_infer_schema_numeric_and_categorical() -> None:
    rows = [
        {"concessionaria_id": "A", "receita": 100.0, "periodo": "2024-01-01"},
        {"concessionaria_id": "B", "receita": 200.0, "periodo": "2024-01-02"},
    ]
    s = infer_schema(rows)
    assert "receita" in s["numeric"]
    assert s.get("primary_metric") == "receita"
    assert "concessionaria_id" in s["categorical"] or "periodo" in s["temporal"]


def test_build_summary_metrics_and_row_count() -> None:
    rows = [{"x": 1, "y": 10}, {"x": 2, "y": 30}]
    schema = infer_schema(rows)
    summ = build_summary(rows, schema)
    assert summ["row_count"] == 2
    assert "y" in summ["metrics"]


def test_extract_insights_non_empty() -> None:
    rows = [{"c": "a", "v": 80}, {"c": "b", "v": 10}, {"c": "c", "v": 10}]
    schema = infer_schema(rows)
    summ = build_summary(rows, schema)
    ins = extract_insights(summ)
    assert isinstance(ins, list)
    assert len(ins) >= 1


def test_build_drl_bundle_has_stable_keys() -> None:
    rows = [{"receita": 50.0, "loja": "L1"}]
    b = build_drl_bundle(rows, query_id="demo_q", log_session_id=None)
    assert "dataset_id" in b
    assert isinstance(b["drl_summary"], dict)
    assert isinstance(b["drl_insights"], list)
    assert isinstance(b["drl_sample"], dict)
    assert isinstance(b["drl_schema"], dict)
