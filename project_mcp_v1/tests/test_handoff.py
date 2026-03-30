"""Testes do handoff Maestro → especialista (ferramenta virtual route_to_specialist)."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from ai_provider.base import ModelProvider
from app.orchestrator import ModularOrchestrator
from app.routing_tools import ROUTE_TO_SPECIALIST_TOOL_NAME


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
