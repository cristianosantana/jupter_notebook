from unittest.mock import AsyncMock

import pytest

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.state.models import State
from orion_mcp.core.tools.registry import ToolRegistry
from orion_mcp.infra.cache.tool_cache import MemoryToolCache
from orion_mcp.mcp_adapter.queries import ALLOWED_QUERY_IDS


@pytest.mark.asyncio
async def test_execute_default_tool_calls_run_domain_query_with_defaults() -> None:
    qid = next(iter(ALLOWED_QUERY_IDS))
    settings = Settings(
        mcp_grpc_target="127.0.0.1:59999",
        openai_api_key=None,
        tool_domain_default_summarize=True,
    )
    reg = ToolRegistry(settings, MemoryToolCache())
    mock_grpc = AsyncMock()
    mock_grpc.run_tool = AsyncMock(
        return_value={
            "query_id": qid,
            "output_shape": "table",
            "limit": settings.tool_domain_default_limit,
            "offset": 0,
            "row_count": 0,
            "summarize": True,
            "rows_sample": [],
        }
    )
    reg._grpc = mock_grpc

    state = State()
    state.flags["domain_query_id"] = qid
    state.flags["domain_query_extra"] = {}

    key, raw = await reg.execute_default_tool(state)
    assert "run_domain_query" in key or key.startswith("tool:")
    mock_grpc.run_tool.assert_called_once()
    name, payload = mock_grpc.run_tool.call_args[0]
    assert name == "run_domain_query"
    assert payload["query_id"] == qid
    assert payload["summarize"] is True
    assert payload["limit"] == settings.tool_domain_default_limit
    assert payload["offset"] == 0
    assert raw["row_count"] == 0
