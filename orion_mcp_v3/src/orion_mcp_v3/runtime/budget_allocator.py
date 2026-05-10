"""
Orçação determinística sobre :class:`~orion_mcp_v3.contracts.context_block.ContextBlock`.

Fase 1.3: reserva system, depois essence, ordena relevância, corta excedente.

§10 (ORDEM_IMPLEMENTAÇÃO): na fracção livre, zonas elásticas + competição suave DATA vs MEMORY
(:func:`elastic_free_tier_params`) quando existem blocos nessas zonas; caso contrário mantém-se o
comportamento anterior (ordenar ``other`` só por relevância).
"""

from __future__ import annotations

import dataclasses
from typing import Iterable, Mapping, Sequence

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy, elastic_free_tier_params, policy_shares

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


def _pack_tier_with_remainder(
    blocks: Sequence[ContextBlock], tier_budget_tokens: int
) -> tuple[list[ContextBlock], list[ContextBlock], int]:
    """Como :func:`_pack_tier`, mas devolve blocos não incluídos (para spill entre zonas)."""
    out: list[ContextBlock] = []
    rem = tier_budget_tokens
    idx = 0
    n = len(blocks)
    while idx < n and rem > 0:
        block = blocks[idx]
        need = estimate_tokens(block.text)
        if need <= rem:
            out.append(block)
            rem -= need
            idx += 1
            continue
        out.append(_truncate_block(block, rem))
        rem = 0
        idx += 1
        break
    unpacked = list(blocks[idx:])
    used = tier_budget_tokens - rem
    return out, unpacked, used


def _split_free_zones(blocks: Sequence[ContextBlock]) -> tuple[list[ContextBlock], list[ContextBlock], list[ContextBlock]]:
    """Separa diálogo (turno), zona DATA/analytics e zona MEMORY/contexto."""
    dialogue: list[ContextBlock] = []
    data_zone: list[ContextBlock] = []
    memory_zone: list[ContextBlock] = []
    for b in blocks:
        if b.role in (ContextRole.USER, ContextRole.ASSISTANT):
            dialogue.append(b)
        elif b.source == ContextSource.MEMORY or b.role == ContextRole.CONTEXT:
            memory_zone.append(b)
        elif b.role in (ContextRole.DATA, ContextRole.TOOL):
            data_zone.append(b)
        else:
            data_zone.append(b)
    for lst in (dialogue, data_zone, memory_zone):
        lst.sort(key=lambda x: (-x.relevance_score, x.block_id or ""))
    return dialogue, data_zone, memory_zone


def _allocate_free_elastic(
    other_blocks: list[ContextBlock],
    free_budget_tokens: int,
    policy: AttentionPolicy,
) -> list[ContextBlock]:
    """Orçamenta a fracção ``other`` com diálogo + DATA/MEMORY + spill elástico."""
    if free_budget_tokens <= 0 or not other_blocks:
        return []

    p = elastic_free_tier_params(policy)
    dialogue, data_z, memory_z = _split_free_zones(other_blocks)

    diag_cap = int(free_budget_tokens * p.dialogue_fraction_of_free)
    packed_dial, unpacked_dial, used_dial = _pack_tier_with_remainder(dialogue, diag_cap)
    remaining_after_dialogue = max(0, free_budget_tokens - used_dial)

    spill_ceiling = int(p.elasticity * free_budget_tokens)

    if unpacked_dial and remaining_after_dialogue > 0:
        extra_dial, _still_dial, used_extra = _pack_tier_with_remainder(unpacked_dial, remaining_after_dialogue)
        packed_dial.extend(extra_dial)
        remaining_after_dialogue = max(0, remaining_after_dialogue - used_extra)

    if remaining_after_dialogue <= 0:
        return [*packed_dial]

    rem_share_d = p.data_share_of_remainder
    cap_d = int(remaining_after_dialogue * rem_share_d)
    cap_m = max(0, remaining_after_dialogue - cap_d)

    packed_d, unpacked_d, used_d = _pack_tier_with_remainder(data_z, cap_d)
    packed_m, unpacked_m, used_m = _pack_tier_with_remainder(memory_z, cap_m)

    rem_tokens_d = max(0, cap_d - used_d)
    rem_tokens_m = max(0, cap_m - used_m)

    spill_to_memory = min(rem_tokens_d, spill_ceiling)
    packed_m2, _, _ = _pack_tier_with_remainder(unpacked_m, spill_to_memory)

    spill_to_data = min(rem_tokens_m, spill_ceiling)
    packed_d2, _, _ = _pack_tier_with_remainder(unpacked_d, spill_to_data)

    merged_mem = [*packed_m, *packed_m2]
    merged_data = [*packed_d, *packed_d2]

    return [*packed_dial, *merged_data, *merged_mem]


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

    _dialogue, data_z, memory_z = _split_free_zones(other_blocks)
    if data_z or memory_z:
        tier_free = _allocate_free_elastic(other_blocks, leftover, pol)
    else:
        tier_free, _ = _pack_tier(other_blocks, leftover)

    return [*tier_system, *tier_essence, *tier_free]
