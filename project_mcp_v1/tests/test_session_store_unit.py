"""Testes unitários da serialização de mensagens para PostgreSQL."""

from uuid import uuid4

from app.session_store import _message_to_db_tuple, _row_to_message


def test_assistant_tool_calls_roundtrip():
    sid = uuid4()
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "list_analytics_queries", "arguments": "{}"},
            }
        ],
    }
    row = _message_to_db_tuple(sid, 0, msg)
    assert row[2] == "assistant"
    restored = _row_to_message(
        row[2],
        row[3],
        row[4],
        row[5],
        row[6],
        row[7],
        row[8],
    )
    assert restored["role"] == "assistant"
    assert restored["tool_calls"][0]["function"]["name"] == "list_analytics_queries"


def test_tool_message_roundtrip():
    sid = uuid4()
    msg = {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"rows":[]}',
        "name": "list_analytics_queries",
    }
    row = _message_to_db_tuple(sid, 0, msg)
    restored = _row_to_message(
        row[2],
        row[3],
        row[4],
        row[5],
        row[6],
        row[7],
        row[8],
    )
    assert restored["role"] == "tool"
    assert restored["tool_call_id"] == "call_1"
    assert restored["name"] == "list_analytics_queries"


def test_hydrate_session_state_preserves_messages():
    import asyncio
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock

    from app.orchestrator import ModularOrchestrator
    from ai_provider.base import ModelProvider

    class Dummy(ModelProvider):
        async def chat(self, messages, tools=None, tool_choice=None, model_override=None):
            return {"role": "assistant", "content": "ok", "tool_calls": None}

    async def _run():
        client = MagicMock()
        client.list_tools = AsyncMock(return_value=[])
        skills = Path(__file__).resolve().parent.parent / "app" / "skills"
        orch = ModularOrchestrator(Dummy(), client, skills_dir=skills)
        await orch.load_tools()
        orch.hydrate_session_state("agregador", [{"role": "user", "content": "Olá"}])
        assert orch.current_agent == "agregador"
        assert len(orch.messages) == 1
        assert orch.messages[0]["content"] == "Olá"

    asyncio.run(_run())
