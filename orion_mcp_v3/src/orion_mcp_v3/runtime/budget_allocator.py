"""
Orçação por atenção sobre :class:`~orion_mcp_v3.contracts.context_block.ContextBlock`.

Fase 1: caps por origem, score de atenção ponderado, resultado estruturado
(:class:`AllocationResult`) e rastreio determinístico.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime.attention_policy import (
    AttentionPolicy,
    AttentionPolicyDefinition,
    elastic_free_tier_params,
    policy_definition,
    policy_shares,
)
from orion_mcp_v3.runtime.token_estimator import estimate_tokens as estimate_tokens_text


def estimate_tokens(text: str) -> int:
    """Compatível com chamadas antigas — delega para :mod:`token_estimator`."""
    return estimate_tokens_text(text)


def _source_bucket(block: ContextBlock) -> str:
    if block.role == ContextRole.SYSTEM or block.source == ContextSource.SYSTEM:
        return "system"
    if block.source == ContextSource.ESSENCE:
        return "essence"
    if block.role in (ContextRole.USER, ContextRole.ASSISTANT) or block.source == ContextSource.USER_INPUT:
        return "user_dialogue"
    if block.source == ContextSource.MEMORY or block.role == ContextRole.CONTEXT:
        return "memory"
    if block.role in (ContextRole.DATA, ContextRole.TOOL) or block.source == ContextSource.BROKER:
        return "data"
    return "other"


def _weighted_attention_score(block: ContextBlock, policy_def: AttentionPolicyDefinition) -> float:
    base = block.compute_attention_score()
    b = _source_bucket(block)
    w = float(policy_def.source_weights.get(b, 1.0))
    return base * w


def _apply_source_caps(
    blocks: Sequence[ContextBlock],
    policy_def: AttentionPolicyDefinition,
    trace: list[str],
) -> tuple[list[ContextBlock], list[ContextBlock]]:
    """Por *bucket*, mantém os melhores blocos até ao teto ``max_blocks_per_source``."""
    by_bucket: dict[str, list[ContextBlock]] = defaultdict(list)
    for b in blocks:
        by_bucket[_source_bucket(b)].append(b)

    kept_ids: set[int] = set()
    dropped: list[ContextBlock] = []

    for bucket, candidates in by_bucket.items():
        limit = int(policy_def.max_blocks_per_source.get(bucket, 9999))
        ranked = sorted(candidates, key=lambda x: (-_weighted_attention_score(x, policy_def), x.block_id or ""))
        for w in ranked[:limit]:
            kept_ids.add(id(w))
        dropped.extend(ranked[limit:])

    if dropped:
        trace.append(f"source_caps:dropped={len(dropped)}")

    survivors = [b for b in blocks if id(b) in kept_ids]
    return survivors, dropped


@dataclass(frozen=True, slots=True)
class AllocationResult:
    """Resultado do *attention allocator* (Fase 1.2)."""

    fitted_blocks: tuple[ContextBlock, ...]
    dropped_blocks: tuple[ContextBlock, ...]
    token_usage: int
    allocation_trace: tuple[str, ...]


def _merge_meta(base: Mapping[str, object], extra: Mapping[str, object]) -> dict[str, object]:
    out: dict[str, object] = dict(base)
    out.update(extra)
    return out


def _truncate_block(block: ContextBlock, max_tokens: int) -> ContextBlock:
    if max_tokens <= 0:
        return dataclasses.replace(block, text="", metadata=_merge_meta(block.metadata, {"truncated": True}))
    max_chars = max_tokens * 4
    if len(block.text) <= max_chars:
        return block
    text = block.text[:max_chars]
    return dataclasses.replace(block, text=text, metadata=_merge_meta(block.metadata, {"truncated": True}))


def _is_system_block(block: ContextBlock) -> bool:
    return block.role == ContextRole.SYSTEM or block.source == ContextSource.SYSTEM


def _is_essence_block(block: ContextBlock) -> bool:
    return block.source == ContextSource.ESSENCE


def _partition(
    blocks: Sequence[ContextBlock],
    policy_def: AttentionPolicyDefinition,
) -> tuple[list[ContextBlock], list[ContextBlock], list[ContextBlock]]:
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
    keyf = lambda x: (-_weighted_attention_score(x, policy_def), x.block_id or "")
    other.sort(key=keyf)
    return system, essence, other


def _pack_tier(blocks: Iterable[ContextBlock], tier_budget_tokens: int) -> tuple[list[ContextBlock], int]:
    out: list[ContextBlock] = []
    remaining = tier_budget_tokens
    for block in blocks:
        need = block.estimate_token_cost()
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
    out: list[ContextBlock] = []
    rem = tier_budget_tokens
    idx = 0
    n = len(blocks)
    while idx < n and rem > 0:
        block = blocks[idx]
        need = block.estimate_token_cost()
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


def _split_free_zones(
    blocks: Sequence[ContextBlock],
    policy_def: AttentionPolicyDefinition,
) -> tuple[list[ContextBlock], list[ContextBlock], list[ContextBlock]]:
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
    keyf = lambda x: (-_weighted_attention_score(x, policy_def), x.block_id or "")
    for lst in (dialogue, data_zone, memory_zone):
        lst.sort(key=keyf)
    return dialogue, data_zone, memory_zone


def _allocate_free_elastic(
    other_blocks: list[ContextBlock],
    free_budget_tokens: int,
    policy: AttentionPolicy,
    policy_def: AttentionPolicyDefinition,
) -> list[ContextBlock]:
    """Orçamenta a fracção ``other`` com diálogo + DATA/MEMORY + spill elástico."""
    if free_budget_tokens <= 0 or not other_blocks:
        return []

    p = elastic_free_tier_params(policy)
    dialogue, data_z, memory_z = _split_free_zones(other_blocks, policy_def)

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


def _block_in_fitted(block: ContextBlock, fitted: Sequence[ContextBlock]) -> bool:
    for f in fitted:
        if block is f:
            return True
        if block.block_id is not None and block.block_id == f.block_id:
            return True
    return False


def _compute_dropped(original: Sequence[ContextBlock], fitted: Sequence[ContextBlock]) -> tuple[ContextBlock, ...]:
    out: list[ContextBlock] = []
    seen: set[int] = set()
    for b in original:
        if not _block_in_fitted(b, fitted):
            i = id(b)
            if i not in seen:
                seen.add(i)
                out.append(b)
    return tuple(out)


def allocate(
    blocks: Sequence[ContextBlock],
    max_tokens: int,
    *,
    policy: AttentionPolicy | None = None,
) -> AllocationResult:
    """
    *Attention allocator*: reserva system/essence, zona livre com competição DATA↔MEMORY,
    ordenação por score de atenção ponderado pela política, caps por origem.
    """
    trace: list[str] = []
    pol = policy or AttentionPolicy.BALANCED
    policy_def = policy_definition(pol)

    blocks_list = list(blocks)

    if max_tokens <= 0:
        trace.append("abort:max_tokens<=0")
        return AllocationResult((), tuple(blocks_list), 0, tuple(trace))

    capped, cap_dropped = _apply_source_caps(blocks_list, policy_def, trace)
    trace.append(f"after_caps:blocks={len(capped)}")

    shares = policy_shares(pol)
    sys_cap = int(max_tokens * shares.system)
    ess_cap = int(max_tokens * shares.essence)
    free_cap = max(0, max_tokens - sys_cap - ess_cap)

    system_blocks, essence_blocks, other_blocks = _partition(capped, policy_def)

    tier_system, used_sys = _pack_tier(system_blocks, sys_cap)
    tier_essence, used_ess = _pack_tier(essence_blocks, ess_cap)

    leftover = max(0, free_cap + (sys_cap - used_sys) + (ess_cap - used_ess))

    _, data_z, memory_z = _split_free_zones(other_blocks, policy_def)
    if data_z or memory_z:
        tier_free = _allocate_free_elastic(other_blocks, leftover, pol, policy_def)
    else:
        tier_free, _ = _pack_tier(other_blocks, leftover)

    fitted = [*tier_system, *tier_essence, *tier_free]
    from_cap_not_fitted = _compute_dropped(capped, fitted)
    dropped = tuple(cap_dropped) + from_cap_not_fitted
    # dedupe mantendo ordem (cap primeiro)
    deduped: list[ContextBlock] = []
    seen: set[int] = set()
    for b in dropped:
        i = id(b)
        if i in seen:
            continue
        seen.add(i)
        deduped.append(b)

    token_usage = sum(b.estimate_token_cost() for b in fitted)
    trace.append(f"fitted={len(fitted)}:tokens={token_usage}")

    return AllocationResult(
        fitted_blocks=tuple(fitted),
        dropped_blocks=tuple(deduped),
        token_usage=token_usage,
        allocation_trace=tuple(trace),
    )
