"""Memória §8 ORDEM_IMPLEMENTAÇÃO — EpisodicRetriever, SemanticRetriever, compose_blocks."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextSource
from orion_mcp_v3.memory import (
    EpisodicRetriever,
    InMemoryConversationStateRepository,
    MemoryComposer,
    SemanticRetriever,
)


def test_episodic_retriever_returns_memory_blocks() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "hi")
    r = EpisodicRetriever(repo)
    bl = r.retrieve("s", limit=5)
    assert len(bl) == 1
    assert bl[0].source == ContextSource.MEMORY


def test_semantic_retriever_prefers_matching_content() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "foo bar")
    repo.append_message("s", "user", "faturamento clientes vendas")
    sem = SemanticRetriever(repo)
    bl = sem.retrieve("faturamento clientes", "s", pool_limit=10, top_k=1)
    assert len(bl) >= 1
    assert "faturamento" in bl[0].text.lower()


def test_compose_blocks_returns_context_blocks_not_string() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "only episodic")
    c = MemoryComposer(repo)
    blocks = c.compose_blocks("s", max_tokens=8000)
    assert blocks
    assert all(hasattr(b, "text") for b in blocks)


def test_compose_blocks_with_retrievers_dedupes_by_block_id() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "analytics revenue top")
    epi = EpisodicRetriever(repo)
    sem = SemanticRetriever(repo)
    c = MemoryComposer(repo)
    merged = c.compose_blocks(
        "s",
        max_tokens=8000,
        recent_limit=5,
        semantic_query="revenue analytics",
        semantic_retriever=sem,
        episodic_retriever=epi,
    )
    ids = [b.block_id for b in merged if b.block_id]
    assert len(ids) == len(set(ids))
