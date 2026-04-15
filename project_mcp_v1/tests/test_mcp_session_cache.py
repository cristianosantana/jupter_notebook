"""Cache MCP — normalização e digest."""

from app.mcp_session_cache import (
    append_cache_entry,
    build_mcp_cache_digest_section,
    find_cache_entry,
    mcp_cache_key,
    normalize_mcp_arguments,
)


def test_normalize_sorts_keys():
    assert normalize_mcp_arguments({"b": 1, "a": 2}) == {"a": 2, "b": 1}


def test_cache_key_stable():
    k1 = mcp_cache_key("run_analytics_query", {"date_to": "2024-01-01", "date_from": "2024-01-01"})
    k2 = mcp_cache_key("run_analytics_query", {"date_from": "2024-01-01", "date_to": "2024-01-01"})
    assert k1 == k2


def test_find_and_append():
    md: dict = {}
    args = {"q": 1}
    ck = mcp_cache_key("t", args)
    append_cache_entry(md, cache_key=ck, tool_name="t", args=args, result_text='{"rows":[]}')
    hit = find_cache_entry(md, ck)
    assert hit is not None
    assert hit.get("tool_name") == "t"


def test_digest_non_empty():
    md = {
        "mcp_tool_cache": {
            "entries": [
                {
                    "tool_name": "list_analytics_queries",
                    "args": {},
                    "result_text": '{"queries":[]}',
                    "row_count": 0,
                }
            ]
        }
    }
    s = build_mcp_cache_digest_section(md)
    assert "list_analytics_queries" in s


def test_digest_run_analytics_warns_not_full_data():
    payload = (
        '{"query_id":"q1","row_count":3943,"columns":["a","b"],'
        '"rows":[{"a":1,"b":2},{"a":3,"b":4}]}'
    )
    md = {
        "mcp_tool_cache": {
            "entries": [
                {
                    "tool_name": "run_analytics_query",
                    "args": {"query_id": "q1"},
                    "result_text": payload,
                    "row_count": 3943,
                }
            ]
        }
    }
    s = build_mcp_cache_digest_section(md)
    assert "run_analytics_query" in s
    assert "3943" in s or "row_count" in s
    assert "analytics_aggregate_session" in s
    assert "context_retrieve_similar" in s
    assert "colunas" in s


def test_digest_includes_analytics_datasets_handles():
    md = {
        "mcp_tool_cache": {"entries": []},
        "analytics_datasets": {
            "by_id": {
                "abc123": {
                    "session_dataset_id": "abc123",
                    "query_id": "servicos_x",
                    "row_count": 100,
                    "columns": ["x", "y"],
                    "sample_only": False,
                }
            },
            "order": ["abc123"],
        },
    }
    s = build_mcp_cache_digest_section(md)
    assert "abc123" in s
    assert "Datasets de analytics" in s
