"""Persistência do transcript completo incluindo turnos só com Maestro (process_chat)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import main as main_mod


def test_replace_conversation_messages_called_when_agent_is_maestro(monkeypatch: pytest.MonkeyPatch):
    """Com PG activo, `replace_conversation_messages` deve correr também quando `agent_used == maestro`."""
    replace = AsyncMock()
    touch = AsyncMock()
    update_meta = AsyncMock()
    merge_meta = AsyncMock()
    upsert = AsyncMock()
    create_session = AsyncMock()

    store = MagicMock()
    store.replace_conversation_messages = replace
    store.touch_session = touch
    store.update_session_metadata = update_meta
    store.merge_session_metadata = merge_meta
    store.upsert_user = upsert
    store.create_session = create_session

    async def fake_run(*_a, **_k):
        return {
            "assistant": {"content": "Resposta maestro", "role": "assistant"},
            "tools_used": [],
            "agent": "maestro",
            "trace_run_id": None,
        }

    orch = MagicMock()
    orch.run = fake_run
    orch.reset_conversation = AsyncMock()
    orch.messages = [{"role": "user", "content": "Olá"}, {"role": "assistant", "content": "Resposta maestro"}]

    monkeypatch.setattr(main_mod, "agent", orch)
    monkeypatch.setattr(main_mod, "session_store", store)

    # `session_id=None` cria sessão nova (mesmo ramo usado em primeiro contacto com PG).
    req = main_mod.ChatRequest(
        message="Olá",
        target_agent=None,
        new_conversation=False,
        user_id="u1",
        session_id=None,
    )

    asyncio.run(main_mod.process_chat(req))

    replace.assert_awaited_once()
    args, _ = replace.await_args
    assert args[1] == orch.messages
    # sid = primeiro argumento de create_session
    assert create_session.await_args[0][0] == args[0]
    touch.assert_awaited_once_with(args[0], "maestro")
