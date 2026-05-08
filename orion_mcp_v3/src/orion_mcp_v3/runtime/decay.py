"""
Decaimento mínimo de :class:`~ContextBlock.relevance_score` (idade e redundância).

Sem persistência — usado pela governança de contexto antes de alocação de orçamento.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from orion_mcp_v3.contracts.context_block import ContextBlock


def resolve_age_seconds(block: ContextBlock, *, now: float) -> float:
    """
    Deriva idade em segundos a partir de ``metadata["created_at"]`` (unix epoch, ``int`` ou ``float``).
    Se ausente ou inválido, devolve ``0.0``.
    """
    raw = block.metadata.get("created_at")
    if isinstance(raw, (int, float)):
        return max(0.0, float(now) - float(raw))
    return 0.0


def apply_decay(
    block: ContextBlock,
    *,
    age_seconds: float = 0.0,
    half_life_seconds: float | None = 3600.0,
    redundancy_penalty: float = 0.0,
    min_score: float = 0.0,
) -> ContextBlock:
    """
    Aplica decaimento exponencial por idade (meia-vida) e subtrai penalização de redundância.

    - Se ``half_life_seconds`` for ``None`` ou ``<= 0``, não há decaimento por idade.
    - Multiplicador por idade: ``0.5 ** (age_seconds / half_life_seconds)`` (após uma meia-vida, metade do score).
    - ``redundancy_penalty`` é subtraído depois do factor de idade.
    - O score final não desce abaixo de ``min_score``.
    """
    s = float(block.relevance_score)
    if half_life_seconds is not None and half_life_seconds > 0.0 and age_seconds > 0.0:
        s *= 0.5 ** (age_seconds / half_life_seconds)
    s -= redundancy_penalty
    if s < min_score:
        s = min_score
    return replace(block, relevance_score=s)


def apply_decay_with_clock(
    block: ContextBlock,
    *,
    now: float,
    half_life_seconds: float | None = 3600.0,
    redundancy_penalty: float = 0.0,
    min_score: float = 0.0,
) -> ContextBlock:
    """Variante que usa ``resolve_age_seconds`` com o relógio ``now``."""
    age = resolve_age_seconds(block, now=now)
    return apply_decay(
        block,
        age_seconds=age,
        half_life_seconds=half_life_seconds,
        redundancy_penalty=redundancy_penalty,
        min_score=min_score,
    )


def apply_decay_to_sequence(
    blocks: Sequence[ContextBlock],
    *,
    ages_seconds: Sequence[float] | None = None,
    half_life_seconds: float | None = 3600.0,
    redundancy_penalty: float = 0.0,
    min_score: float = 0.0,
) -> tuple[ContextBlock, ...]:
    """Aplica :func:`apply_decay` a cada bloco; ``ages_seconds`` alinha por índice com ``blocks``."""
    out: list[ContextBlock] = []
    for i, b in enumerate(blocks):
        age = 0.0 if ages_seconds is None else (ages_seconds[i] if i < len(ages_seconds) else 0.0)
        out.append(
            apply_decay(
                b,
                age_seconds=age,
                half_life_seconds=half_life_seconds,
                redundancy_penalty=redundancy_penalty,
                min_score=min_score,
            )
        )
    return tuple(out)
