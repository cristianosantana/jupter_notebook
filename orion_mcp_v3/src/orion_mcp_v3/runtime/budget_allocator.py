"""
Orçação determinística sobre :class:`~orion_mcp_v3.contracts.context_block.ContextBlock`.

Fase 1.3: reserva system, depois essence, ordena relevância, corta excedente.
"""

from __future__ import annotations

import dataclasses
from typing import Iterable, Mapping, Sequence

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy, policy_shares

_CHARS_PER_TOKEN_ESTIMATE: int = 4


def estimate_tokens(text: str) -> int:
    """Heurística alinhada a prompts LLM típicos (≈ caracteres / 4)."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)


def _is_system_block(block: ContextBlock) -> bool:
    return block.role == ContextRole.SYSTEM or block.source == ContextSource.SYSTEM


def _is_essence_block(block: ContextBlock) -> bool:
    return block.source == ContextSource.ESSENCE


def _partition(blocks: Sequence[ContextBlock]) -> tuple[list[ContextBlock], list[ContextBlock], list[ContextBlock]]:
    system: list[ContextBlock] = []
    essence: list[ContextBlock] = []
    other: list[ContextBlock] = []
    for b in blocks:
        if _is_system_block(b):
            system.append(b)
        elif _is_essence_block(b):
            essence.append(b)
        else:
            other.append(b)
    other.sort(key=lambda x: (-x.relevance_score, x.block_id or ""))
    return system, essence, other


def _merge_meta(base: Mapping[str, object], extra: Mapping[str, object]) -> dict[str, object]:
    out: dict[str, object] = dict(base)
    out.update(extra)
    return out


def _truncate_block(block: ContextBlock, max_tokens: int) -> ContextBlock:
    if max_tokens <= 0:
        return dataclasses.replace(block, text="", metadata=_merge_meta(block.metadata, {"truncated": True}))
    max_chars = max_tokens * _CHARS_PER_TOKEN_ESTIMATE
    if len(block.text) <= max_chars:
        return block
    text = block.text[:max_chars]
    return dataclasses.replace(block, text=text, metadata=_merge_meta(block.metadata, {"truncated": True}))


def _pack_tier(blocks: Iterable[ContextBlock], tier_budget_tokens: int) -> tuple[list[ContextBlock], int]:
    """Inclui blocos sequencialmente; trunca se necessário o último bloco concedido."""
    out: list[ContextBlock] = []
    remaining = tier_budget_tokens
    for block in blocks:
        need = estimate_tokens(block.text)
        if remaining <= 0:
            break
        if need <= remaining:
            out.append(block)
            remaining -= need
            continue
        out.append(_truncate_block(block, remaining))
        remaining = 0
        break
    used = tier_budget_tokens - remaining
    return out, used


def allocate(
    blocks: Sequence[ContextBlock],
    max_tokens: int,
    *,
    policy: AttentionPolicy | None = None,
) -> list[ContextBlock]:
    """
    Orçamentos por fração ``system / essence / free`` vindas da política.

    Dentro das fracções ``system`` e ``essence`` mantém-se a ordem original;
    na fracção livre ordena por ``relevance_score`` decrescente.
    """
    if max_tokens <= 0:
        return []

    pol = policy or AttentionPolicy.CONVERSATIONAL
    shares = policy_shares(pol)
    sys_cap = int(max_tokens * shares.system)
    ess_cap = int(max_tokens * shares.essence)
    free_cap = max(0, max_tokens - sys_cap - ess_cap)

    system_blocks, essence_blocks, other_blocks = _partition(blocks)

    tier_system, used_sys = _pack_tier(system_blocks, sys_cap)
    tier_essence, used_ess = _pack_tier(essence_blocks, ess_cap)

    leftover = max(0, free_cap + (sys_cap - used_sys) + (ess_cap - used_ess))
    tier_free, _ = _pack_tier(other_blocks, leftover)

    return [*tier_system, *tier_essence, *tier_free]
