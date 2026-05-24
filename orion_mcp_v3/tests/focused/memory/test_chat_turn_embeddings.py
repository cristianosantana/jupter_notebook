"""Testes do indexador ``chat_turn_embeddings``."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion_mcp_v3.config.settings import get_settings_uncached

from orion_mcp_v3.memory.chat_turn_embedding_store import ChatTurnEmbeddingStore
from orion_mcp_v3.memory.repositories.conversation_state import ConversationMessage
from orion_mcp_v3.runtime.session_manager import SessionManager


def _msg(*, content: str = "olá", message_id: int = 1) -> ConversationMessage:
    return ConversationMessage(
        session_id="sess-1",
        role="user",
        content=content,
        message_id=message_id,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_index_turn_inserts_with_content_column() -> None:
    embed = AsyncMock()
    embed.embed.return_value = [[0.1] * 8]

    conn = AsyncMock()
    conn.execute.return_value = "INSERT 0 1"

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    store = ChatTurnEmbeddingStore(pool, embed)
    ok = await store.index_turn("sess-1", _msg())
    assert ok is True
    embed.embed.assert_awaited_once()
    conn.execute.assert_awaited()


@pytest.mark.asyncio
async def test_index_turn_skips_empty_content() -> None:
    embed = AsyncMock()
    pool = MagicMock()
    store = ChatTurnEmbeddingStore(pool, embed)
    ok = await store.index_turn("sess-1", _msg(content="   "))
    assert ok is False
    embed.embed.assert_not_called()


@pytest.mark.asyncio
async def test_search_reuses_query_cache_after_index() -> None:
    embed = AsyncMock()
    embed.embed.return_value = [[0.2] * 4]

    conn = AsyncMock()
    conn.execute.return_value = "INSERT 0 1"
    conn.fetch.return_value = []

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    store = ChatTurnEmbeddingStore(pool, embed)
    msg = _msg(content="mesma pergunta")
    await store.index_turn("sess-1", msg)
    await store.search("sess-1", "mesma pergunta", top_k=3)
    assert embed.embed.await_count == 1


def test_embedding_mode_settings() -> None:
    off = get_settings_uncached(embedding_mode="off", embedding_enabled=False, _env_file=None)
    assert off.effective_embedding_mode == "off"
    assert not off.embedding_should_index
    assert not off.embedding_should_retrieve

    legacy = get_settings_uncached(embedding_mode="off", embedding_enabled=True, llm_api_key="k", _env_file=None)
    assert legacy.effective_embedding_mode == "retrieve"
    assert legacy.embedding_should_retrieve

    idx = get_settings_uncached(embedding_mode="index_only", llm_api_key="k", _env_file=None)
    assert idx.embedding_should_index
    assert not idx.embedding_should_retrieve


@pytest.mark.asyncio
async def test_session_manager_indexes_when_store_in_slot() -> None:
    store = AsyncMock()
    store.index_turn.return_value = True
    slot: dict = {"chat_turn_embedding_store": store}
    sm = SessionManager(shared_conversation_repository_slot=slot)
    session = sm.get_or_create("conv-a")
    settings = get_settings_uncached(embedding_mode="index_only", llm_api_key="k", _env_file=None)
    with patch("orion_mcp_v3.runtime.session_manager.get_settings", return_value=settings):
        await sm.record_user_message(session, "pergunta de teste")
    store.index_turn.assert_awaited_once()
    args = store.index_turn.await_args
    assert args.args[0] == "conv-a"
    assert args.args[1].content == "pergunta de teste"
