"""
Resolução de conflitos entre :class:`~ContextBlock` (duplicação, turnos repetidos,
sobreposição memória/digest, analytics redundante).

Estratégias declarativas (Fase 1.5) — determinístico, sem persistência.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource


class ConflictStrategy(Enum):
    """Estratégia aplicável por tipo de conflito."""

    KEEP_HIGHEST_RELEVANCE = "keep_highest_relevance"
    KEEP_MOST_RECENT = "keep_most_recent"
    MERGE_CONTEXT = "merge_context"
    DROP_DUPLICATE = "drop_duplicate"


@dataclass(frozen=True, slots=True)
class ConflictResolutionResult:
    """Resultado de uma passagem de resolução."""

    blocks: tuple[ContextBlock, ...]
    dropped_ids: tuple[str, ...]
    notes: str | None = None


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


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


def resolve_semantic_duplicates(
    blocks: Sequence[ContextBlock],
    *,
    strategy: ConflictStrategy = ConflictStrategy.KEEP_HIGHEST_RELEVANCE,
) -> ConflictResolutionResult:
    """Texto normalizado igual → um vencedor conforme a estratégia."""
    if strategy not in (ConflictStrategy.KEEP_HIGHEST_RELEVANCE, ConflictStrategy.KEEP_MOST_RECENT):
        strategy = ConflictStrategy.KEEP_HIGHEST_RELEVANCE

    groups: dict[str, list[ContextBlock]] = {}
    for b in blocks:
        key = _normalize_text(b.text)
        if not key:
            key = f"__empty__:{id(b)}"
        groups.setdefault(key, []).append(b)

    winners: dict[str, ContextBlock] = {}
    for key, lst in groups.items():
        if len(lst) == 1:
            winners[key] = lst[0]
            continue
        if strategy == ConflictStrategy.KEEP_MOST_RECENT:
            winners[key] = lst[-1]
        else:
            winners[key] = max(lst, key=lambda x: (x.relevance_score, x.block_id or ""))

    out: list[ContextBlock] = []
    dropped_ids: list[str] = []
    seen_keys: set[str] = set()
    for b in blocks:
        key = _normalize_text(b.text) or f"__empty__:{id(b)}"
        win = winners[key]
        if b is not win:
            if b.block_id:
                dropped_ids.append(b.block_id)
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(win)

    return ConflictResolutionResult(
        blocks=tuple(out),
        dropped_ids=tuple(dropped_ids),
        notes=f"semantic_duplicates:{strategy.value}",
    )


def resolve_repeated_user_turns(blocks: Sequence[ContextBlock]) -> ConflictResolutionResult:
    """
    Vários blocos USER / USER_INPUT com o mesmo texto → mantém o mais recente
    (``metadata["turn_seq"]`` descrescente ou última ocorrência na lista).
    """
    candidates = [
        (i, b)
        for i, b in enumerate(blocks)
        if b.role == ContextRole.USER and b.source == ContextSource.USER_INPUT
    ]
    by_text: dict[str, list[tuple[int, ContextBlock]]] = {}
    for i, b in candidates:
        by_text.setdefault(_normalize_text(b.text), []).append((i, b))

    winner_idx: dict[str, int] = {}
    for text, lst in by_text.items():
        if len(lst) < 2:
            continue

        def _turn_seq(b: ContextBlock) -> float:
            raw = b.metadata.get("turn_seq")
            try:
                return float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return float("-inf")

        best_i, best_b = max(lst, key=lambda t: (_turn_seq(t[1]), t[0]))
        winner_idx[text] = best_i

    if not winner_idx:
        return ConflictResolutionResult(blocks=tuple(blocks), dropped_ids=(), notes=None)

    out: list[ContextBlock] = []
    dropped_ids: list[str] = []
    for i, b in enumerate(blocks):
        if b.role == ContextRole.USER and b.source == ContextSource.USER_INPUT:
            t = _normalize_text(b.text)
            if t in winner_idx and i != winner_idx[t]:
                if b.block_id:
                    dropped_ids.append(b.block_id)
                continue
        out.append(b)

    return ConflictResolutionResult(
        blocks=tuple(out),
        dropped_ids=tuple(dropped_ids),
        notes="repeated_user_turns:keep_most_recent",
    )


def resolve_memory_digest_redundancy(
    blocks: Sequence[ContextBlock],
) -> ConflictResolutionResult:
    """
    Quando um digest/evidência broker e um bloco MEMORY partilham grande sobreposição lexical,
    mantém o de maior relevância (evita eco digest↔memória).
    """
    digest_like: list[tuple[int, ContextBlock]] = []
    memory_like: list[tuple[int, ContextBlock]] = []
    for i, b in enumerate(blocks):
        fk = b.metadata.get("fusion_kind") if isinstance(b.metadata, dict) else None
        if b.source == ContextSource.BROKER and b.role == ContextRole.DATA and fk in ("digest", "evidence"):
            digest_like.append((i, b))
        if b.source == ContextSource.MEMORY or b.role == ContextRole.CONTEXT:
            memory_like.append((i, b))

    drop_idx: set[int] = set()
    for i, d in digest_like:
        dn = _normalize_text(d.text)
        if len(dn) < 12:
            continue
        for j, m in memory_like:
            mn = _normalize_text(m.text)
            if len(mn) < 12:
                continue
            shorter, longer = (dn, mn) if len(dn) <= len(mn) else (mn, dn)
            if shorter not in longer:
                continue
                if d.relevance_score >= m.relevance_score:
                    drop_idx.add(j)
                else:
                    drop_idx.add(i)

    out = [b for k, b in enumerate(blocks) if k not in drop_idx]
    dropped_ids_list: list[str] = []
    for k in sorted(drop_idx):
        bid = blocks[k].block_id
        if bid:
            dropped_ids_list.append(bid)

    return ConflictResolutionResult(
        blocks=tuple(out),
        dropped_ids=tuple(dropped_ids_list),
        notes="memory_digest_redundancy",
    )


def resolve_redundant_analytics(blocks: Sequence[ContextBlock]) -> ConflictResolutionResult:
    """Dois blocos DATA broker com mesmo prefixo longo → mantém maior relevância."""
    data_brokers = [(i, b) for i, b in enumerate(blocks) if b.role == ContextRole.DATA and b.source == ContextSource.BROKER]
    prefixes: dict[str, list[tuple[int, ContextBlock]]] = {}
    for i, b in data_brokers:
        pref = b.text[:240] if b.text else ""
        if len(pref) < 32:
            continue
        prefixes.setdefault(pref, []).append((i, b))

    drop_idx: set[int] = set()
    for pref, lst in prefixes.items():
        if len(lst) < 2:
            continue
        keeper = max(lst, key=lambda t: (t[1].relevance_score, -t[0]))[0]
        for i, _ in lst:
            if i != keeper:
                drop_idx.add(i)

    out = [b for k, b in enumerate(blocks) if k not in drop_idx]
    dropped_ids = tuple(
        blocks[k].block_id for k in sorted(drop_idx) if blocks[k].block_id
    )
    return ConflictResolutionResult(
        blocks=tuple(out),
        dropped_ids=dropped_ids,
        notes="redundant_analytics_prefix",
    )


def resolve_cognitive_conflicts(blocks: Sequence[ContextBlock]) -> ConflictResolutionResult:
    """Pipeline único: dedupe por id → turnos user → digest/memória → analytics → semântica genérica."""
    cur = tuple(blocks)
    notes: list[str] = []
    for step in (
        resolve_duplicate_blocks,
        resolve_repeated_user_turns,
        resolve_memory_digest_redundancy,
        resolve_redundant_analytics,
        lambda seq: resolve_semantic_duplicates(seq, strategy=ConflictStrategy.KEEP_HIGHEST_RELEVANCE),
    ):
        r = step(cur)
        cur = r.blocks
        if r.notes:
            notes.append(r.notes)
    return ConflictResolutionResult(
        blocks=cur,
        dropped_ids=(),
        notes=";".join(notes) if notes else "cognitive_pipeline",
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
