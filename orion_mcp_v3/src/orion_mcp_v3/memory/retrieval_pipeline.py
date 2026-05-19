"""
Pipeline de recuperação de memória — produz :class:`~ContextBlock` (sem composição).

Responsabilidade: episódica, semântica, essência e prefix → blocos prontos para o
:class:`~MemoryComposer` (dedupe, allocate, render).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.memory.blocks import messages_to_context_blocks
from orion_mcp_v3.memory.composer import MemoryLayer, _compress_block, _dedupe_blocks, _tag_layer
from orion_mcp_v3.memory.episodic_retriever import EpisodicRetriever
from orion_mcp_v3.memory.repositories.conversation_state import ConversationStateRepository
from orion_mcp_v3.memory.semantic_retriever import SemanticRetriever
from orion_mcp_v3.memory.summary_cache import NullSummaryCache, SummaryCachePort
from orion_mcp_v3.memory.vector_retriever import VectorRetriever


@dataclass(frozen=True, slots=True)
class LayeredMemoryResult:
    """Blocos organizados por camada antes do allocator."""

    layers: dict[str, list[ContextBlock]]
    all_blocks: tuple[ContextBlock, ...]
    dedupe_dropped: int
    compressed_count: int


class MemoryRetrievalPipeline:
    """Recupera blocos de memória; não aplica orçamento de tokens."""

    def __init__(
        self,
        repository: ConversationStateRepository,
        *,
        summary_cache: SummaryCachePort | None = None,
        enable_compression: bool = True,
        compression_ratio: float = 0.6,
    ) -> None:
        self._repo = repository
        self._summ: SummaryCachePort = summary_cache if summary_cache is not None else NullSummaryCache()
        self._compress = enable_compression
        self._compress_ratio = compression_ratio

    async def collect_layers(
        self,
        session_id: str,
        *,
        recent_limit: int = 60,
        prefix_blocks: Sequence[ContextBlock] = (),
        semantic_query: str | None = None,
        semantic_retriever: SemanticRetriever | None = None,
        vector_retriever: VectorRetriever | None = None,
        vector_top_k: int = 5,
        episodic_retriever: EpisodicRetriever | None = None,
        intent_type: str | None = None,
        entities: Sequence[str] = (),
    ) -> LayeredMemoryResult:
        """Monta blocos por camada, dedupe e compressão opcional (sem ``allocate``)."""
        layers: dict[str, list[ContextBlock]] = {l.value: [] for l in MemoryLayer}

        for b in prefix_blocks:
            layers[MemoryLayer.WORKING_MEMORY.value].append(
                _tag_layer(b, MemoryLayer.WORKING_MEMORY)
            )

        cached = self._summ.get_summary(session_id)
        if cached and cached.strip():
            ess = ContextBlock(
                text=cached.strip(),
                role=ContextRole.NEUTRAL,
                source=ContextSource.ESSENCE,
                block_id="summary:cache",
                metadata={"origin": "summary_cache"},
                relevance_score=0.35,
                information_density=0.9,
                compressibility=0.2,
            )
            layers[MemoryLayer.ESSENCE_MEMORY.value].append(
                _tag_layer(ess, MemoryLayer.ESSENCE_MEMORY)
            )

        if semantic_query and vector_retriever is not None:
            vec_blocks = await vector_retriever.retrieve(
                semantic_query.strip(), session_id, top_k=vector_top_k
            )
            for b in vec_blocks:
                tagged = _tag_layer(b, MemoryLayer.SEMANTIC_MEMORY)
                layers[MemoryLayer.SEMANTIC_MEMORY.value].append(tagged)

        if semantic_query and semantic_retriever is not None and not layers[MemoryLayer.SEMANTIC_MEMORY.value]:
            sem_blocks = await semantic_retriever.retrieve(
                semantic_query.strip(),
                session_id,
                intent_type=intent_type,
                entities=entities,
            )
            for b in sem_blocks:
                tagged = _tag_layer(b, MemoryLayer.SEMANTIC_MEMORY)
                new_meta = {**dict(tagged.metadata), "retrieval": "semantic_lexical"}
                layers[MemoryLayer.SEMANTIC_MEMORY.value].append(
                    replace(tagged, metadata=new_meta, relevance_score=max(b.relevance_score, 0.55))
                )

        if episodic_retriever is not None:
            epi_blocks = await episodic_retriever.retrieve(
                session_id,
                limit=recent_limit,
                query=semantic_query,
                intent_type=intent_type,
                entities=entities,
            )
            for b in epi_blocks:
                layers[MemoryLayer.EPISODIC_MEMORY.value].append(
                    _tag_layer(b, MemoryLayer.EPISODIC_MEMORY)
                )
        else:
            recent = await self._repo.get_recent(session_id, limit=recent_limit)
            for b in messages_to_context_blocks(recent):
                layers[MemoryLayer.EPISODIC_MEMORY.value].append(
                    _tag_layer(b, MemoryLayer.EPISODIC_MEMORY)
                )

        merged: list[ContextBlock] = []
        for layer_name in [
            MemoryLayer.ESSENCE_MEMORY.value,
            MemoryLayer.WORKING_MEMORY.value,
            MemoryLayer.SEMANTIC_MEMORY.value,
            MemoryLayer.EPISODIC_MEMORY.value,
        ]:
            merged.extend(layers[layer_name])

        deduped, drop_count = _dedupe_blocks(merged)

        compressed_count = 0
        if self._compress:
            final: list[ContextBlock] = []
            for b in deduped:
                c = _compress_block(b, target_ratio=self._compress_ratio)
                if c is not b:
                    compressed_count += 1
                final.append(c)
            deduped = final

        return LayeredMemoryResult(
            layers=layers,
            all_blocks=tuple(deduped),
            dedupe_dropped=drop_count,
            compressed_count=compressed_count,
        )

    async def collect_blocks(
        self,
        session_id: str,
        *,
        recent_limit: int = 60,
        prefix_blocks: Sequence[ContextBlock] = (),
        semantic_query: str | None = None,
        semantic_retriever: SemanticRetriever | None = None,
        vector_retriever: VectorRetriever | None = None,
        vector_top_k: int = 5,
        episodic_retriever: EpisodicRetriever | None = None,
        intent_type: str | None = None,
        entities: Sequence[str] = (),
    ) -> list[ContextBlock]:
        """Lista plana de blocos recuperados (entrada típica do composer)."""
        layered = await self.collect_layers(
            session_id,
            recent_limit=recent_limit,
            prefix_blocks=prefix_blocks,
            semantic_query=semantic_query,
            semantic_retriever=semantic_retriever,
            vector_retriever=vector_retriever,
            vector_top_k=vector_top_k,
            episodic_retriever=episodic_retriever,
            intent_type=intent_type,
            entities=entities,
        )
        return list(layered.all_blocks)
