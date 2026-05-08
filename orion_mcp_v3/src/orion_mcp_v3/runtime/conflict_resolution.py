"""
Resolução mínima de conflitos entre :class:`~ContextBlock` (duplicados / competição).

Sem persistência — apenas regras determinísticas para governança de contexto.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource


@dataclass(frozen=True, slots=True)
class ConflictResolutionResult:
    """Resultado de uma passagem de resolução."""

    blocks: tuple[ContextBlock, ...]
    dropped_ids: tuple[str, ...]
    notes: str | None = None


def _key_for_dedupe(b: ContextBlock) -> str:
    if b.block_id:
        return f"id:{b.block_id}"
    return f"{b.role.name}:{b.source.name}:{hash(b.text) & 0xFFFF_FFFF}"


def resolve_duplicate_blocks(blocks: Sequence[ContextBlock]) -> ConflictResolutionResult:
    """
    Para cada chave de deduplicação mantém o bloco com maior ``relevance_score``.

    Preserva a ordem da primeira ocorrência vencedora na sequência original.
    """
    best_score: dict[str, float] = {}
    winner_by_key: dict[str, ContextBlock] = {}
    for b in blocks:
        k = _key_for_dedupe(b)
        sc = b.relevance_score
        if k not in best_score or sc > best_score[k]:
            best_score[k] = sc
            winner_by_key[k] = b

    out: list[ContextBlock] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for b in blocks:
        k = _key_for_dedupe(b)
        win = winner_by_key[k]
        if b is not win:
            if b.block_id:
                dropped.append(b.block_id)
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(win)

    return ConflictResolutionResult(
        blocks=tuple(out),
        dropped_ids=tuple(dropped),
        notes="dedupe_max_relevance_per_key",
    )


def _is_system_block(b: ContextBlock) -> bool:
    return b.role == ContextRole.SYSTEM or b.source == ContextSource.SYSTEM


def cap_system_blocks(
    blocks: Sequence[ContextBlock],
    *,
    max_blocks: int = 3,
) -> ConflictResolutionResult:
    """
    Mantém no máximo ``max_blocks`` blocos de sistema, por ``relevance_score`` decrescente;
    a ordem final segue a ordem original (remove apenas índices de sistema não seleccionados).
    """
    sys_idx = [i for i, b in enumerate(blocks) if _is_system_block(b)]
    if len(sys_idx) <= max_blocks:
        return ConflictResolutionResult(blocks=tuple(blocks), dropped_ids=(), notes=None)

    ranked = sorted(sys_idx, key=lambda i: blocks[i].relevance_score, reverse=True)
    keep_idx = set(ranked[:max_blocks])
    out: list[ContextBlock] = []
    dropped_ids: list[str] = []
    for i, b in enumerate(blocks):
        if _is_system_block(b) and i not in keep_idx:
            if b.block_id:
                dropped_ids.append(b.block_id)
            continue
        out.append(b)

    return ConflictResolutionResult(
        blocks=tuple(out),
        dropped_ids=tuple(dropped_ids),
        notes=f"cap_system_blocks_max_{max_blocks}",
    )
