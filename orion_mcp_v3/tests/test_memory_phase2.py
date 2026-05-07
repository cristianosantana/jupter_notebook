"""Fase 2 — repositório, blocos, composer, cache de resumos."""

from __future__ import annotations

from unittest.mock import MagicMock

from orion_mcp_v3.contracts.context_block import ContextRole, ContextSource
from orion_mcp_v3.memory import (
    InMemoryConversationStateRepository,
    InMemorySummaryCache,
    MemoryComposer,
    RedisSummaryCache,
    messages_to_context_blocks,
    message_to_context_block,
)


def test_conversation_repository_append_and_recent() -> None:
    repo = InMemoryConversationStateRepository()
    a = repo.append_message(" s1 ", "user", "Olá")
    b = repo.append_message(" s1 ", "assistant", "Oi")
    assert a.message_id < b.message_id
    recent = repo.get_recent("s1", limit=1)
    assert len(recent) == 1
    assert recent[0].role == "assistant"


def test_message_to_blocks_uses_memory_source() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("x", "user", "A")
    m = repo.get_recent("x", limit=10)[0]
    b = message_to_context_block(m, relevance_score=0.42)
    assert b.source == ContextSource.MEMORY
    assert b.role == ContextRole.USER
    assert b.relevance_score == 0.42


def test_messages_order_and_relevance_ramp() -> None:
    repo = InMemoryConversationStateRepository()
    for i in range(3):
        repo.append_message("x", "user", str(i))
    msgs = repo.get_recent("x", limit=10)
    bl = messages_to_context_blocks(msgs)
    assert len(bl) == 3
    scores = [x.relevance_score for x in bl]
    assert scores == sorted(scores)


def test_composer_concatenates_turns() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "preciso dados")
    repo.append_message("s", "assistant", "aquí vai")
    c = MemoryComposer(repo)
    out = c.compose("s", max_tokens=8192)
    assert "USER]" in out
    assert "ASSISTANT]" in out
    assert "dados" in out


def test_summary_cache_prepends_cached_text() -> None:
    repo = InMemoryConversationStateRepository()
    cache = InMemorySummaryCache()
    cache.set_summary("s", "Sumário prévio sobre o projeto.", ttl_seconds=3600)
    c = MemoryComposer(repo, summary_cache=cache)
    out = c.compose("s", max_tokens=8192)
    assert "Sumário prévio" in out


def test_redis_summary_cache_uses_prefixed_keys() -> None:
    mock = MagicMock()
    mock.get.return_value = "cached"
    cache = RedisSummaryCache(mock)
    assert cache.get_summary("abc") == "cached"
    mock.get.assert_called_once_with("orion:v3:summary:abc")
    cache.set_summary("abc", "x", ttl_seconds=60)
    mock.set.assert_called_once()
