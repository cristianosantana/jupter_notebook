"""Estado ``orchestrator_state`` e chave de tool."""

from app.mcp_session_cache import mcp_cache_key
from app.orchestrator_state import (
    ORCHESTRATOR_STATE_KEY,
    ensure_orchestrator_state_block,
    find_tool_result_text,
    put_tool_result,
)


def test_put_and_find_roundtrip():
    md: dict = {}
    ensure_orchestrator_state_block(md)
    put_tool_result(
        md[ORCHESTRATOR_STATE_KEY],
        "run_analytics_query",
        {"query_id": 1},
        '{"rows":[]}',
        is_error=False,
    )
    hit = find_tool_result_text(
        md[ORCHESTRATOR_STATE_KEY],
        "run_analytics_query",
        {"query_id": 1},
    )
    assert hit is not None
    text, err = hit
    assert not err
    assert "rows" in text


def test_same_key_different_arg_order():
    md: dict = {}
    ensure_orchestrator_state_block(md)
    k1 = mcp_cache_key("t", {"a": 1, "b": 2})
    k2 = mcp_cache_key("t", {"b": 2, "a": 1})
    assert k1 == k2
