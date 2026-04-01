"""Testes do handoff Maestro → especialista (ferramenta virtual route_to_specialist)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from ai_provider.base import ModelProvider
from app.orchestrator import (
    ENTITY_GLOSSARY_MCP_TOOL,
    ModularOrchestrator,
    _messages_with_skill,
)
from app.routing_tools import ROUTE_TO_SPECIALIST_TOOL_NAME
from mcp.types import CallToolResult, TextContent  # pyright: ignore[reportMissingImports]


_SKILLS = Path(__file__).resolve().parent.parent / "app" / "skills"


class FakeModelHandoff(ModelProvider):
    """Primeira chamada: route_to_specialist; segunda: resposta textual."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self,
        messages,
        tools=None,
        tool_choice=None,
    ):
        self.calls += 1
        if self.calls == 1:
            assert tool_choice is not None
            assert tools is not None and len(tools) == 1
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_r1",
                        "type": "function",
                        "function": {
                            "name": ROUTE_TO_SPECIALIST_TOOL_NAME,
                            "arguments": '{"agent": "analise_os", "reason": "test"}',
                        },
                    }
                ],
            }
        return {
            "role": "assistant",
            "content": "Resposta final do especialista.",
            "tool_calls": None,
        }


class FakeModelDirect(ModelProvider):
    """Uma única resposta final (sem roteamento)."""

    async def chat(self, messages, tools=None, tool_choice=None):
        assert tool_choice is None
        return {
            "role": "assistant",
            "content": "Direto.",
            "tool_calls": None,
        }


def _mock_client():
    client = MagicMock()
    client.list_tools = AsyncMock(return_value=[])
    client.call_tool = AsyncMock()
    return client


def test_auto_route_handoff_to_analise_os():
    async def _run():
        client = _mock_client()
        model = FakeModelHandoff()
        orch = ModularOrchestrator(model, client, skills_dir=_SKILLS)
        await orch.load_tools()
        return await orch.run("Volume de OS?", target_agent=None)

    out = asyncio.run(_run())

    assert out["agent"] == "analise_os"
    assert out["tools_used"]
    assert out["tools_used"][0]["name"] == ROUTE_TO_SPECIALIST_TOOL_NAME
    assert "handoff" in (out["tools_used"][0].get("result_preview") or "")
    assert out["assistant"]["content"] == "Resposta final do especialista."


def test_explicit_target_skips_maestro_routing_tools():
    async def _run():
        client = _mock_client()
        model = FakeModelDirect()
        orch = ModularOrchestrator(model, client, skills_dir=_SKILLS)
        await orch.load_tools()
        return await orch.run("Olá", target_agent="visualizador")

    out = asyncio.run(_run())

    assert out["agent"] == "visualizador"
    assert out["assistant"]["content"] == "Direto."


class FakeModelTriesDelegateFromSpecialist(ModelProvider):
    """Especialista tenta route_to_specialist; deve ser bloqueado no orquestrador."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, tool_choice=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "bad_delegate",
                        "type": "function",
                        "function": {
                            "name": ROUTE_TO_SPECIALIST_TOOL_NAME,
                            "arguments": '{"agent": "projecoes"}',
                        },
                    }
                ],
            }
        return {
            "role": "assistant",
            "content": "Resposta após bloqueio de delegação.",
            "tool_calls": None,
        }


def test_specialist_cannot_call_route_to_specialist():
    async def _run():
        client = _mock_client()
        model = FakeModelTriesDelegateFromSpecialist()
        orch = ModularOrchestrator(model, client, skills_dir=_SKILLS)
        await orch.load_tools()
        return await orch.run("Síntese", target_agent="agregador")

    out = asyncio.run(_run())

    assert out["agent"] == "agregador"
    assert out["assistant"]["content"] == "Resposta após bloqueio de delegação."
    assert out["tools_used"]
    blocked = out["tools_used"][0]
    assert blocked["name"] == ROUTE_TO_SPECIALIST_TOOL_NAME
    assert blocked["ok"] is False
    assert "Maestro" in (blocked.get("error") or "")


class FakeModelHandoffThenSecondTurn(ModelProvider):
    """
    Run 1: Maestro (tool_choice) → handoff; especialista responde só texto.
    Run 2: primeira chat não deve ser Maestro (tool_choice None).
    """

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, tool_choice=None):
        self.calls += 1
        if self.calls == 1:
            assert tool_choice is not None
            assert tools is not None and len(tools) == 1
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_r1",
                        "type": "function",
                        "function": {
                            "name": ROUTE_TO_SPECIALIST_TOOL_NAME,
                            "arguments": '{"agent": "analise_os", "reason": "test"}',
                        },
                    }
                ],
            }
        if self.calls == 2:
            assert tool_choice is None
            return {
                "role": "assistant",
                "content": "Qual período pretendes analisar?",
                "tool_calls": None,
            }
        assert self.calls == 3
        assert tool_choice is None
        return {
            "role": "assistant",
            "content": "Segue a análise para o período indicado.",
            "tool_calls": None,
        }


def test_auto_route_continues_specialist_on_second_message():
    """Segundo POST sem target_agent não volta ao Maestro nem limpa o contexto relevante."""

    async def _run():
        client = _mock_client()
        model = FakeModelHandoffThenSecondTurn()
        orch = ModularOrchestrator(model, client, skills_dir=_SKILLS)
        await orch.load_tools()
        out1 = await orch.run("Volume de OS?", target_agent=None)
        assert orch.current_agent == "analise_os"
        assert len(orch.messages) > 0
        out2 = await orch.run("Último trimestre.", target_agent=None)
        return out1, out2, model.calls

    out1, out2, n_calls = asyncio.run(_run())

    assert out1["agent"] == "analise_os"
    assert "Qual período" in (out1["assistant"].get("content") or "")
    assert out2["agent"] == "analise_os"
    assert out2["assistant"]["content"] == "Segue a análise para o período indicado."
    assert n_calls == 3


def test_reset_conversation_clears_and_returns_to_maestro():
    async def _run():
        client = _mock_client()
        model = FakeModelHandoff()
        orch = ModularOrchestrator(model, client, skills_dir=_SKILLS)
        await orch.load_tools()
        await orch.run("Volume de OS?", target_agent=None)
        assert orch.current_agent == "analise_os"
        await orch.reset_conversation()
        assert orch.current_agent == "maestro"
        assert len(orch.messages) == 0
        return orch

    asyncio.run(_run())


def test_run_strips_orch_anchor_after_finally():
    async def _run():
        client = _mock_client()
        model = FakeModelDirect()
        orch = ModularOrchestrator(model, client, skills_dir=_SKILLS)
        await orch.load_tools()
        await orch.run("Olá", target_agent="visualizador")
        for m in orch.messages:
            assert "_orch_anchor" not in m

    asyncio.run(_run())


def test_messages_with_skill_omits_orch_internal_keys():
    msgs = [{"role": "user", "content": "pergunta", "_orch_anchor": True}]
    out = _messages_with_skill("SKILL", msgs)
    assert not any("_orch_anchor" in m for m in out)
    user_part = [m for m in out if m.get("role") == "user"]
    assert user_part[0]["content"] == "pergunta"


def test_prompt_skill_text_merges_glossary_block():
    client = _mock_client()
    orch = ModularOrchestrator(FakeModelDirect(), client, skills_dir=_SKILLS)
    orch.current_skill = "CORPO_SKILL"
    orch._entity_glossary = "## Glossário\n- id=1: X"
    merged = orch._prompt_skill_text()
    assert "CORPO_SKILL" in merged
    assert "## Glossário" in merged


def test_refresh_entity_glossary_disabled_leaves_empty(monkeypatch):
    monkeypatch.setenv("ENTITY_GLOSSARY_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()

    async def _run():
        client = _mock_client()
        orch = ModularOrchestrator(FakeModelDirect(), client, skills_dir=_SKILLS)
        orch._entity_glossary = "old"
        await orch._refresh_entity_glossary()
        assert orch._entity_glossary == ""

    asyncio.run(_run())
    get_settings.cache_clear()


def test_refresh_entity_glossary_uses_mcp_tool(monkeypatch):
    monkeypatch.setenv("ENTITY_GLOSSARY_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    payload = json.dumps(
        {"markdown": "## Glossário MCP\n- ok", "stats": {"concessionarias_count": 2}},
        ensure_ascii=False,
    )
    mcp_res = CallToolResult(
        content=[TextContent(type="text", text=payload)],
        isError=False,
    )

    async def _run():
        client = MagicMock()
        client.session = object()
        client.call_tool = AsyncMock(return_value=mcp_res)
        orch = ModularOrchestrator(FakeModelDirect(), client, skills_dir=_SKILLS)
        await orch._refresh_entity_glossary()
        assert "Glossário MCP" in orch._entity_glossary
        client.call_tool.assert_awaited_once()
        call = client.call_tool.await_args
        assert call is not None
        assert call.args[0] == ENTITY_GLOSSARY_MCP_TOOL
        assert "max_chars" in (call.args[1] or {})

    asyncio.run(_run())
    get_settings.cache_clear()
