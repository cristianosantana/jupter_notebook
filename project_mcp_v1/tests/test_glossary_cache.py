"""Cache do glossário por session_id (uma chamada MCP por sessão quando possível)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mcp.types import CallToolResult, TextContent  # pyright: ignore[reportMissingImports]

from ai_provider.base import ModelProvider
from app.config import Settings, get_settings
from app.orchestrator import ModularOrchestrator

_SKILLS = Path(__file__).resolve().parent.parent / "app" / "skills"
_GLOSSARY_TOOL = Settings().entity_glossary_mcp_tool


class _FakeDirect(ModelProvider):
    async def chat(self, messages, tools=None, tool_choice=None, model_override=None):
        return {
            "role": "assistant",
            "content": "ok",
            "tool_calls": None,
        }


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    yield
    get_settings.cache_clear()


def test_glossary_session_cache_second_run_skips_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_GLOSSARY_ENABLED", "true")
    monkeypatch.setenv("ENTITY_GLOSSARY_SESSION_CACHE_ENABLED", "true")
    get_settings.cache_clear()

    sid = uuid4()
    glossary_calls: list[int] = []
    glossary_payload = json.dumps({"markdown": "## CachedGloss\n", "stats": {}}, ensure_ascii=False)

    async def call_tool_impl(name: str, args: object):
        if name == _GLOSSARY_TOOL:
            glossary_calls.append(1)
            return CallToolResult(
                content=[TextContent(type="text", text=glossary_payload)],
                isError=False,
            )
        return CallToolResult(
            content=[TextContent(type="text", text="{}")],
            isError=False,
        )

    async def _run() -> int:
        client = MagicMock()
        client.list_tools = AsyncMock(return_value=[])
        client.session = object()
        client.call_tool = AsyncMock(side_effect=call_tool_impl)
        orch = ModularOrchestrator(_FakeDirect(), client, skills_dir=_SKILLS)
        await orch.load_tools()
        await orch.run("Primeira", target_agent="analise_os", session_id=sid)
        assert len(glossary_calls) == 1
        msgs = list(orch.messages)
        orch.hydrate_session_state("analise_os", msgs, session_id=sid)
        assert "CachedGloss" in orch._build_system_text_sync()
        await orch.run("Segunda", target_agent=None, session_id=sid)
        return len(glossary_calls)

    assert asyncio.run(_run()) == 1


def test_glossary_session_cache_disabled_refetches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTITY_GLOSSARY_ENABLED", "true")
    monkeypatch.setenv("ENTITY_GLOSSARY_SESSION_CACHE_ENABLED", "false")
    get_settings.cache_clear()

    sid = uuid4()
    glossary_calls: list[int] = []
    glossary_payload = json.dumps({"markdown": "## G\n", "stats": {}}, ensure_ascii=False)

    async def call_tool_impl(name: str, args: object):
        if name == _GLOSSARY_TOOL:
            glossary_calls.append(1)
            return CallToolResult(
                content=[TextContent(type="text", text=glossary_payload)],
                isError=False,
            )
        return CallToolResult(
            content=[TextContent(type="text", text="{}")],
            isError=False,
        )

    async def _run() -> int:
        client = MagicMock()
        client.list_tools = AsyncMock(return_value=[])
        client.session = object()
        client.call_tool = AsyncMock(side_effect=call_tool_impl)
        orch = ModularOrchestrator(_FakeDirect(), client, skills_dir=_SKILLS)
        await orch.load_tools()
        await orch.run("Primeira", target_agent="analise_os", session_id=sid)
        msgs = list(orch.messages)
        orch.hydrate_session_state("analise_os", msgs, session_id=sid)
        await orch.run("Segunda", target_agent=None, session_id=sid)
        return len(glossary_calls)

    assert asyncio.run(_run()) == 2
