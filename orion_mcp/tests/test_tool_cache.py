import pytest

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.orchestrator.action_executor import ActionExecutor
from orion_mcp.core.orchestrator.state_manager import StateManager
from orion_mcp.core.orchestrator.orchestrator import Orchestrator
from orion_mcp.core.state.models import State
from orion_mcp.core.strategy import Strategy
from orion_mcp.core.tools.registry import ToolRegistry
from orion_mcp.infra.cache.tool_cache import MemoryToolCache, tool_key
from orion_mcp.infra.db.state_repository import MemoryStateRepository


def test_tool_key_stable() -> None:
    k1 = tool_key("t", {"a": 1, "b": 2})
    k2 = tool_key("t", {"b": 2, "a": 1})
    assert k1 == k2


@pytest.mark.asyncio
async def test_orchestrator_end_to_end_mock_llm() -> None:
    # Evita chamadas reais à OpenAI se o `.env` definir ORION_OPENAI_API_KEY.
    settings = Settings(openai_api_key=None)
    repo = MemoryStateRepository()
    tools = ToolRegistry(settings, MemoryToolCache())
    orch = Orchestrator.build(settings, repo, tools, pool=None)
    r = await orch.handle_chat(session_id="s1", user_input="preciso de dados", strategy=Strategy.fast)
    assert r.metrics["tool_calls"] == 1
    assert r.metrics["llm_calls"] == 1
    assert "body" in r.payload
