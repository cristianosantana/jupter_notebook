from orion_mcp.core.tools.data_interpreter import tool_result_to_llm_summary
from orion_mcp.mcp_adapter.queries import ALLOWED_QUERY_IDS


def test_interpreter_catalog_compact_sample() -> None:
    qid = next(iter(ALLOWED_QUERY_IDS))
    raw = {
        "query_id": qid,
        "output_shape": "table",
        "limit": 100,
        "offset": 0,
        "row_count": 2,
        "summarize": True,
        "rows_sample": [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}],
    }
    text = tool_result_to_llm_summary(raw, preview_rows=10, max_chars=5000)
    assert qid in text
    assert "a=1" in text or "1" in text
    assert "Pré-visualização" in text
    assert "row_count" in text or "2" in text


def test_interpreter_many_rows_only_preview() -> None:
    rows = [{"id": i, "v": i * 10} for i in range(50)]
    raw = {
        "query_id": "q",
        "output_shape": "table",
        "limit": 50,
        "offset": 0,
        "row_count": 50,
        "summarize": False,
        "rows": rows,
    }
    text = tool_result_to_llm_summary(raw, preview_rows=5, max_chars=10000)
    assert text.count("id=") <= 8
    assert "…" in text or "5" in text


def test_interpreter_catalog_full_rows_ignores_preview_cap() -> None:
    rows = [{"id": i, "v": i} for i in range(12)]
    raw = {
        "query_id": "q",
        "output_shape": "table",
        "limit": 12,
        "offset": 0,
        "row_count": 12,
        "summarize": False,
        "rows": rows,
    }
    text = tool_result_to_llm_summary(
        raw, preview_rows=3, max_chars=50_000, catalog_full_rows=True
    )
    assert "página completa no payload" in text
    assert "Dados tabulares (página)" in text
    assert text.count("id=") == 12


def test_interpreter_stub_path() -> None:
    raw = {"metric": "demo", "rows": 3, "sum_value": 42, "note": "stub"}
    text = tool_result_to_llm_summary(raw)
    assert "demo" in text
    assert "42" in text


def test_interpreter_degraded() -> None:
    raw = {
        "mcp_degraded": True,
        "tool_name": "run_domain_query",
        "note": "circuit",
        "mcp_error": "unavailable",
        "metric": "demo",
        "rows": 0,
        "sum_value": 0,
    }
    text = tool_result_to_llm_summary(raw)
    assert "MCP" in text or "degradado" in text or "circuit" in text


def test_interpreter_row_count_eq_limit_warning() -> None:
    raw = {
        "query_id": "q",
        "output_shape": "table",
        "limit": 10,
        "offset": 0,
        "row_count": 10,
        "summarize": True,
        "rows_sample": [{"x": 1}],
    }
    text = tool_result_to_llm_summary(raw)
    assert "row_count" in text.lower() or "10" in text
