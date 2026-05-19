"""
MemoryComposer inteligente (Fase 3.3): camadas formais, dedupe interno, compressão contextual.

Camadas:
- ``WORKING_MEMORY`` — turno atual + blocos prefix
- ``SEMANTIC_MEMORY`` — hits do retriever semântico
- ``EPISODIC_MEMORY`` — turnos recentes via retriever episódico ou repo
- ``ESSENCE_MEMORY`` — resumo/essência pré-computado

Blocos de todas as camadas passam por dedupe (block_id + texto normalizado),
compressão contextual opcional e orçamento via :func:`allocate`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.memory.blocks import messages_to_context_blocks
from orion_mcp_v3.memory.episodic_retriever import EpisodicRetriever
from orion_mcp_v3.memory.repositories.conversation_state import ConversationStateRepository
from orion_mcp_v3.memory.semantic_retriever import SemanticRetriever
from orion_mcp_v3.memory.summary_cache import NullSummaryCache, SummaryCachePort
from orion_mcp_v3.runtime import AttentionPolicy
from orion_mcp_v3.runtime.budget_allocator import allocate
from orion_mcp_v3.runtime.prompt_render import render_blocks_to_prompt


class MemoryLayer(Enum):
    """Camadas formais de memória (Fase 3.3)."""

    WORKING_MEMORY = "working_memory"
    SEMANTIC_MEMORY = "semantic_memory"
    EPISODIC_MEMORY = "episodic_memory"
    ESSENCE_MEMORY = "essence_memory"


@dataclass(frozen=True, slots=True)
class LayeredMemoryResult:
    """Blocos organizados por camada antes do allocator."""

    layers: dict[str, list[ContextBlock]]
    all_blocks: tuple[ContextBlock, ...]
    dedupe_dropped: int
    compressed_count: int


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _dedupe_blocks(blocks: Sequence[ContextBlock]) -> tuple[list[ContextBlock], int]:
    """Remove duplicados por block_id e por texto normalizado, mantém primeiro visto."""
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    out: list[ContextBlock] = []
    dropped = 0
    for b in blocks:
        if b.block_id is not None and b.block_id in seen_ids:
            dropped += 1
            continue
        norm = _normalize_text(b.text)
        if norm and norm in seen_texts:
            dropped += 1
            continue
        if b.block_id is not None:
            seen_ids.add(b.block_id)
        if norm:
            seen_texts.add(norm)
        out.append(b)
    return out, dropped


_CHARS_PER_TOKEN: int = 4
_COMPRESS_MIN_CHARS: int = 600


def _compress_block(block: ContextBlock, *, target_ratio: float = 0.6) -> ContextBlock:
    """
    Compressão contextual leve: trunca blocos longos e pouco densos.

    Preserva os primeiros ``target_ratio`` do texto e marca ``compressed=True`` em metadata.
    Apenas aplica a blocos com ``compressibility >= 0.4`` e texto >= ``_COMPRESS_MIN_CHARS``.
    """
    if len(block.text) < _COMPRESS_MIN_CHARS:
        return block
    if block.compressibility < 0.4:
        return block
    target_len = max(200, int(len(block.text) * target_ratio))
    if len(block.text) <= target_len:
        return block
    truncated = block.text[:target_len].rsplit(" ", 1)[0] + " [...]"
    new_meta = {**dict(block.metadata), "compressed": True, "original_length": len(block.text)}
    return replace(block, text=truncated, metadata=new_meta)


def _tag_layer(block: ContextBlock, layer: MemoryLayer) -> ContextBlock:
    """Adiciona ``memory_layer`` aos metadados."""
    new_meta = {**dict(block.metadata), "memory_layer": layer.value}
    return replace(block, metadata=new_meta)


class MemoryComposer:
    """
    Orquestra 4 camadas de memória + dedupe + compressão + orçamento de tokens.

    Compatível com a interface anterior; novos parâmetros são opcionais.
    """

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

    async def build_layers(
        self,
        session_id: str,
        *,
        recent_limit: int = 60,
        prefix_blocks: Sequence[ContextBlock] = (),
        semantic_query: str | None = None,
        semantic_retriever: SemanticRetriever | None = None,
        episodic_retriever: EpisodicRetriever | None = None,
        intent_type: str | None = None,
        entities: Sequence[str] = (),
    ) -> LayeredMemoryResult:
        """Monta blocos por camada, dedupe e compressão, sem aplicar o allocator."""
        layers: dict[str, list[ContextBlock]] = {l.value: [] for l in MemoryLayer}

        # WORKING_MEMORY — prefix + user blocks directos
        for b in prefix_blocks:
            layers[MemoryLayer.WORKING_MEMORY.value].append(
                _tag_layer(b, MemoryLayer.WORKING_MEMORY)
            )

        # ESSENCE_MEMORY — resumo/essência
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

        # SEMANTIC_MEMORY — hits semânticos
        if semantic_query and semantic_retriever is not None:
            sem_blocks = await semantic_retriever.retrieve(
                semantic_query.strip(),
                session_id,
                intent_type=intent_type,
                entities=entities,
            )
            for b in sem_blocks:
                tagged = _tag_layer(b, MemoryLayer.SEMANTIC_MEMORY)
                new_meta = {**dict(tagged.metadata), "retrieval": "semantic"}
                layers[MemoryLayer.SEMANTIC_MEMORY.value].append(
                    replace(tagged, metadata=new_meta, relevance_score=max(b.relevance_score, 0.55))
                )

        # EPISODIC_MEMORY — turnos recentes
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

        # Merge: ESSENCE → WORKING → SEMANTIC → EPISODIC (prioridade decrescente)
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

    async def compose_blocks(
        self,
        session_id: str,
        *,
        max_tokens: int,
        recent_limit: int = 60,
        policy: AttentionPolicy | None = None,
        prefix_blocks: Sequence[ContextBlock] = (),
        semantic_query: str | None = None,
        semantic_retriever: SemanticRetriever | None = None,
        episodic_retriever: EpisodicRetriever | None = None,
        intent_type: str | None = None,
        entities: Sequence[str] = (),
    ) -> list[ContextBlock]:
        layered = await self.build_layers(
            session_id,
            recent_limit=recent_limit,
            prefix_blocks=prefix_blocks,
            semantic_query=semantic_query,
            semantic_retriever=semantic_retriever,
            episodic_retriever=episodic_retriever,
            intent_type=intent_type,
            entities=entities,
        )
        fitted = allocate(list(layered.all_blocks), max_tokens, policy=policy).fitted_blocks
        return list(fitted)

    async def compose(
        self,
        session_id: str,
        *,
        max_tokens: int,
        recent_limit: int = 60,
        policy: AttentionPolicy | None = None,
        prefix_blocks: Sequence[ContextBlock] = (),
        semantic_query: str | None = None,
        semantic_retriever: SemanticRetriever | None = None,
        episodic_retriever: EpisodicRetriever | None = None,
        intent_type: str | None = None,
        entities: Sequence[str] = (),
    ) -> str:
        fitted = await self.compose_blocks(
            session_id,
            max_tokens=max_tokens,
            recent_limit=recent_limit,
            policy=policy,
            prefix_blocks=prefix_blocks,
            semantic_query=semantic_query,
            semantic_retriever=semantic_retriever,
            episodic_retriever=episodic_retriever,
            intent_type=intent_type,
            entities=entities,
        )
        return render_blocks_to_prompt(fitted)
