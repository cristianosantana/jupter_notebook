"""
MemoryComposer (Fase 3.3) — composição pura: blocos prontos → dedupe → allocate → render.

**Não** executa retrieval (repositório, embeddings, retrievers). Use
:class:`~MemoryRetrievalPipeline` para produzir blocos.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from enum import Enum

from orion_mcp_v3.contracts.context_block import ContextBlock
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.budget_allocator import allocate
from orion_mcp_v3.runtime.prompt_render import render_blocks_to_prompt


class MemoryLayer(Enum):
    """Camadas formais de memória (metadados em blocos vindos do pipeline)."""

    WORKING_MEMORY = "working_memory"
    SEMANTIC_MEMORY = "semantic_memory"
    EPISODIC_MEMORY = "episodic_memory"
    ESSENCE_MEMORY = "essence_memory"


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
    new_meta = {**dict(block.metadata), "memory_layer": layer.value}
    return replace(block, metadata=new_meta)


class MemoryComposer:
    """
    Composição async oficial: recebe apenas blocos já recuperados.

    Contrato: ``retrieval != composition``.
    """

    def __init__(
        self,
        *,
        enable_compression: bool = True,
        compression_ratio: float = 0.6,
    ) -> None:
        self._compress = enable_compression
        self._compress_ratio = compression_ratio

    async def compose_blocks(
        self,
        blocks: Sequence[ContextBlock],
        *,
        max_tokens: int,
        policy: AttentionPolicy | None = None,
    ) -> list[ContextBlock]:
        """Dedupe (e compressão opcional) + orçamento de tokens."""
        deduped, _ = _dedupe_blocks(blocks)
        if self._compress:
            final: list[ContextBlock] = []
            for b in deduped:
                final.append(_compress_block(b, target_ratio=self._compress_ratio))
            deduped = final
        fitted = allocate(list(deduped), max_tokens, policy=policy).fitted_blocks
        return list(fitted)

    async def compose(
        self,
        blocks: Sequence[ContextBlock],
        *,
        max_tokens: int,
        policy: AttentionPolicy | None = None,
    ) -> str:
        fitted = await self.compose_blocks(blocks, max_tokens=max_tokens, policy=policy)
        return render_blocks_to_prompt(fitted)
