"""Memória §8 ORDEM_IMPLEMENTAÇÃO — EpisodicRetriever, SemanticRetriever, compose_blocks."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextSource
from orion_mcp_v3.memory import (
    EpisodicRetriever,
    InMemoryConversationStateRepository,
    MemoryComposer,
    MemoryRetrievalPipeline,
    SemanticRetriever,
)


async def test_episodic_retriever_returns_memory_blocks() -> None:
    repo = InMemoryConversationStateRepository()
    await repo.append_message("s", "user", "hi")
    r = EpisodicRetriever(repo)
    bl = await r.retrieve("s", limit=5)
    assert len(bl) == 1
    assert bl[0].source == ContextSource.MEMORY


async def test_semantic_retriever_prefers_matching_content() -> None:
    repo = InMemoryConversationStateRepository()
    await repo.append_message("s", "user", "foo bar")
    await repo.append_message("s", "user", "faturamento clientes vendas")
    sem = SemanticRetriever(repo)
    bl = await sem.retrieve("faturamento clientes", "s", pool_limit=10, top_k=1)
    assert len(bl) >= 1
    assert "faturamento" in bl[0].text.lower()


async def test_compose_blocks_returns_context_blocks_not_string() -> None:
    repo = InMemoryConversationStateRepository()
    await repo.append_message("s", "user", "only episodic")
    blocks = await MemoryRetrievalPipeline(repo).collect_blocks("s")
    fitted = await MemoryComposer().compose_blocks(blocks, max_tokens=8000)
    assert fitted
    assert all(hasattr(b, "text") for b in fitted)


async def test_compose_blocks_with_retrievers_dedupes_by_block_id() -> None:
    repo = InMemoryConversationStateRepository()
    await repo.append_message("s", "user", "analytics revenue top")
    epi = EpisodicRetriever(repo)
    sem = SemanticRetriever(repo)
    blocks = await MemoryRetrievalPipeline(repo).collect_blocks(
        "s",
        recent_limit=5,
        semantic_query="revenue analytics",
        semantic_retriever=sem,
        episodic_retriever=epi,
    )
    merged = await MemoryComposer().compose_blocks(blocks, max_tokens=8000)
    ids = [b.block_id for b in merged if b.block_id]
    assert len(ids) == len(set(ids))
