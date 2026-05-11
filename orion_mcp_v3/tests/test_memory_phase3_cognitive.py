"""Fase 3 — Memória Cognitiva: scoring episódico, retrieval semântico híbrido, composer inteligente."""

from __future__ import annotations

from datetime import timedelta

from orion_mcp_v3.contracts.context_block import ContextSource
from orion_mcp_v3.memory import (
    EpisodicRetriever,
    EpisodicScore,
    InMemoryConversationStateRepository,
    InMemorySummaryCache,
    LayeredMemoryResult,
    MemoryComposer,
    MemoryLayer,
    SemanticHit,
    SemanticRetriever,
)


# ── 3.1 Episodic Memory Scoring ──────────────────────────────────────


def test_episodic_score_composite_is_weighted_sum() -> None:
    s = EpisodicScore(
        semantic_similarity=1.0,
        recency=1.0,
        intent_match=1.0,
        entity_overlap=1.0,
        importance=1.0,
    )
    assert abs(s.composite - 1.0) < 1e-9


def test_episodic_retriever_returns_scored_blocks() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "faturamento dos clientes top")
    repo.append_message("s", "user", "bom dia como vai")
    r = EpisodicRetriever(repo)
    blocks = r.retrieve("s", limit=5, query="faturamento clientes")
    assert len(blocks) == 2
    assert all(b.source == ContextSource.MEMORY for b in blocks)
    meta = blocks[0].metadata
    assert "episodic_score" in meta
    assert meta["episodic_score"]["composite"] > 0


def test_episodic_retriever_prefers_relevant_query() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "olá mundo bom dia")
    repo.append_message("s", "user", "faturamento total vendas mês")
    r = EpisodicRetriever(repo)
    blocks = r.retrieve("s", limit=1, query="faturamento vendas")
    assert len(blocks) == 1
    assert "faturamento" in blocks[0].text.lower()


def test_episodic_retriever_intent_match_boosts_score() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "alerta anomalia subiu")
    repo.append_message("s", "user", "olá tudo bem")
    r = EpisodicRetriever(repo)
    blocks = r.retrieve("s", limit=2, query="alerta anomalia", intent_type="monitoring")
    scores = {b.text: b.metadata["episodic_score"] for b in blocks}
    assert scores["alerta anomalia subiu"]["intent_match"] > scores["olá tudo bem"]["intent_match"]
    assert blocks[0].text == "alerta anomalia subiu"


def test_episodic_retriever_entity_overlap() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "cliente João comprou")
    repo.append_message("s", "user", "nada a ver com entidades")
    r = EpisodicRetriever(repo)
    blocks = r.retrieve("s", limit=2, entities=["João"])
    assert blocks[0].metadata["episodic_score"]["entity_overlap"] > blocks[1].metadata["episodic_score"]["entity_overlap"]


def test_episodic_retriever_without_query_still_works() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "hello")
    r = EpisodicRetriever(repo)
    blocks = r.retrieve("s", limit=5)
    assert len(blocks) == 1


# ── 3.2 Semantic Retriever Híbrido ───────────────────────────────────


def test_semantic_retriever_returns_scored_blocks() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "faturamento vendas mensal")
    repo.append_message("s", "user", "bom dia como está")
    sem = SemanticRetriever(repo)
    blocks = sem.retrieve("faturamento vendas", "s", top_k=2)
    assert len(blocks) >= 1
    meta = blocks[0].metadata
    assert "semantic_hit" in meta
    assert meta["semantic_hit"]["composite"] > 0


def test_semantic_retriever_prefers_matching_content() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "foo bar baz")
    repo.append_message("s", "user", "faturamento clientes vendas mensal")
    sem = SemanticRetriever(repo)
    blocks = sem.retrieve("faturamento clientes", "s", top_k=1)
    assert len(blocks) >= 1
    assert "faturamento" in blocks[0].text.lower()


def test_semantic_retriever_entity_filter() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "faturamento de João")
    repo.append_message("s", "user", "faturamento de Maria")
    sem = SemanticRetriever(repo)
    blocks = sem.retrieve("faturamento", "s", top_k=5, entities=["Maria"])
    texts = [b.text for b in blocks]
    assert any("Maria" in t for t in texts)


def test_semantic_retriever_intent_filter() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "alerta anomalia spike")
    repo.append_message("s", "user", "bom dia tudo bem")
    sem = SemanticRetriever(repo)
    blocks = sem.retrieve("algo", "s", top_k=5, intent_type="monitoring")
    assert any("alerta" in b.text.lower() or "anomalia" in b.text.lower() for b in blocks)


def test_semantic_retriever_time_window_filter() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "msg recente")
    sem = SemanticRetriever(repo)
    blocks = sem.retrieve("msg", "s", top_k=5, time_window=timedelta(hours=1))
    assert len(blocks) >= 1


# ── 3.3 Memory Composer Inteligente ──────────────────────────────────


def test_memory_layer_enum_values() -> None:
    assert MemoryLayer.WORKING_MEMORY.value == "working_memory"
    assert MemoryLayer.SEMANTIC_MEMORY.value == "semantic_memory"
    assert MemoryLayer.EPISODIC_MEMORY.value == "episodic_memory"
    assert MemoryLayer.ESSENCE_MEMORY.value == "essence_memory"


def test_composer_build_layers_produces_all_layer_keys() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "teste")
    c = MemoryComposer(repo)
    result = c.build_layers("s")
    assert isinstance(result, LayeredMemoryResult)
    for layer in MemoryLayer:
        assert layer.value in result.layers


def test_composer_build_layers_tags_metadata() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "teste")
    c = MemoryComposer(repo)
    result = c.build_layers("s")
    for b in result.all_blocks:
        assert "memory_layer" in b.metadata


def test_composer_essence_layer() -> None:
    repo = InMemoryConversationStateRepository()
    cache = InMemorySummaryCache()
    cache.set_summary("s", "Essência da conversa", ttl_seconds=3600)
    c = MemoryComposer(repo, summary_cache=cache)
    result = c.build_layers("s")
    essence = result.layers[MemoryLayer.ESSENCE_MEMORY.value]
    assert len(essence) == 1
    assert "Essência" in essence[0].text
    assert essence[0].metadata.get("memory_layer") == "essence_memory"


def test_composer_semantic_layer_with_retriever() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "faturamento vendas total")
    sem = SemanticRetriever(repo)
    c = MemoryComposer(repo)
    result = c.build_layers("s", semantic_query="faturamento", semantic_retriever=sem)
    sem_blocks = result.layers[MemoryLayer.SEMANTIC_MEMORY.value]
    assert len(sem_blocks) >= 1
    assert sem_blocks[0].metadata.get("memory_layer") == "semantic_memory"


def test_composer_episodic_layer_with_retriever() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "hello world")
    epi = EpisodicRetriever(repo)
    c = MemoryComposer(repo)
    result = c.build_layers("s", episodic_retriever=epi)
    epi_blocks = result.layers[MemoryLayer.EPISODIC_MEMORY.value]
    assert len(epi_blocks) >= 1
    assert epi_blocks[0].metadata.get("memory_layer") == "episodic_memory"


def test_composer_dedupe_internal() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "duplicada")
    epi = EpisodicRetriever(repo)
    sem = SemanticRetriever(repo)
    c = MemoryComposer(repo)
    result = c.build_layers(
        "s",
        semantic_query="duplicada",
        semantic_retriever=sem,
        episodic_retriever=epi,
    )
    ids = [b.block_id for b in result.all_blocks if b.block_id]
    assert len(ids) == len(set(ids))
    assert result.dedupe_dropped >= 1


def test_composer_compression() -> None:
    repo = InMemoryConversationStateRepository()
    long_text = "palavra " * 200
    repo.append_message("s", "user", long_text)
    c = MemoryComposer(repo, enable_compression=True, compression_ratio=0.5)
    result = c.build_layers("s")
    compressed = [b for b in result.all_blocks if b.metadata.get("compressed")]
    assert len(compressed) >= 1
    assert result.compressed_count >= 1
    assert len(compressed[0].text) < len(long_text)


def test_composer_no_compression_when_disabled() -> None:
    repo = InMemoryConversationStateRepository()
    long_text = "palavra " * 200
    repo.append_message("s", "user", long_text)
    c = MemoryComposer(repo, enable_compression=False)
    result = c.build_layers("s")
    assert result.compressed_count == 0


def test_composer_compose_blocks_backwards_compatible() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "preciso dados")
    repo.append_message("s", "assistant", "aqui vai")
    c = MemoryComposer(repo)
    blocks = c.compose_blocks("s", max_tokens=8000)
    assert blocks
    assert all(hasattr(b, "text") for b in blocks)


def test_composer_compose_text_backwards_compatible() -> None:
    repo = InMemoryConversationStateRepository()
    repo.append_message("s", "user", "preciso dados")
    repo.append_message("s", "assistant", "aqui vai")
    c = MemoryComposer(repo)
    out = c.compose("s", max_tokens=8192)
    assert "USER]" in out
    assert "ASSISTANT]" in out
    assert "dados" in out


def test_composer_summary_cache_prepends() -> None:
    repo = InMemoryConversationStateRepository()
    cache = InMemorySummaryCache()
    cache.set_summary("s", "Sumário prévio sobre o projeto.", ttl_seconds=3600)
    c = MemoryComposer(repo, summary_cache=cache)
    out = c.compose("s", max_tokens=8192)
    assert "Sumário prévio" in out


def test_composer_full_pipeline_with_all_layers() -> None:
    repo = InMemoryConversationStateRepository()
    cache = InMemorySummaryCache()
    cache.set_summary("s", "Essência: projecto de analytics.", ttl_seconds=3600)
    repo.append_message("s", "user", "faturamento vendas mensal top clientes")
    repo.append_message("s", "assistant", "Aqui estão os dados de vendas")
    repo.append_message("s", "user", "olá bom dia como está")

    epi = EpisodicRetriever(repo)
    sem = SemanticRetriever(repo)

    c = MemoryComposer(repo, summary_cache=cache)
    result = c.build_layers(
        "s",
        semantic_query="faturamento vendas",
        semantic_retriever=sem,
        episodic_retriever=epi,
        intent_type="analytical",
    )
    assert result.layers[MemoryLayer.ESSENCE_MEMORY.value]
    assert result.layers[MemoryLayer.SEMANTIC_MEMORY.value]
    assert result.layers[MemoryLayer.EPISODIC_MEMORY.value]
    assert len(result.all_blocks) >= 3

    blocks = c.compose_blocks(
        "s",
        max_tokens=8000,
        semantic_query="faturamento vendas",
        semantic_retriever=sem,
        episodic_retriever=epi,
        intent_type="analytical",
    )
    assert len(blocks) >= 1
