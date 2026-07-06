"""Filtra hits recuperados por período do contrato."""

from __future__ import annotations

import re

from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.domain.period_utils import period_in_context_key

_MONTH_SLUGS = {
    1: ("janeiro", "jan"),
    2: ("fevereiro", "fev"),
    3: ("marco", "março", "mar"),
    4: ("abril", "abr"),
    5: ("maio", "mai"),
    6: ("junho", "jun"),
    7: ("julho", "jul"),
    8: ("agosto", "ago"),
    9: ("setembro", "set"),
    10: ("outubro", "out"),
    11: ("novembro", "nov"),
    12: ("dezembro", "dez"),
}


def scope_knowledge(
    knowledge: ConhecimentoRecuperado,
    *,
    period: str | None,
) -> tuple[ConhecimentoRecuperado, bool]:
    """Reduz hits ao período pedido; retorna (scoped, degraded)."""
    if not knowledge.hits or not period:
        return knowledge, False

    matched = tuple(hit for hit in knowledge.hits if _hit_matches_period(hit, period))
    if matched:
        return ConhecimentoRecuperado(hits=matched, essence=knowledge.essence), False

    if not any(_hit_has_period_hint(hit) for hit in knowledge.hits):
        return knowledge, False

    return ConhecimentoRecuperado(hits=(), essence=knowledge.essence), True


def scope_knowledge_to_periods(
    knowledge: ConhecimentoRecuperado,
    *,
    periods: tuple[str, ...],
) -> tuple[ConhecimentoRecuperado, bool]:
    if not periods:
        return knowledge, False
    if len(periods) == 1:
        return scope_knowledge(knowledge, period=periods[0])

    matched = tuple(
        hit for hit in knowledge.hits if any(_hit_matches_period(hit, period) for period in periods)
    )
    if matched:
        return ConhecimentoRecuperado(hits=matched, essence=knowledge.essence), False
    if not any(_hit_has_period_hint(hit) for hit in knowledge.hits):
        return knowledge, False
    return ConhecimentoRecuperado(hits=(), essence=knowledge.essence), True


def _hit_matches_period(hit: KnowledgeHit, period: str) -> bool:
    return period_in_context_key(hit.context_key, period)


def _hit_has_period_hint(hit: KnowledgeHit) -> bool:
    key = hit.context_key.lower()
    if re.search(r"20\d{2}[-_/](0[1-9]|1[0-2])", key):
        return True
    return any(slug in key for slugs in _MONTH_SLUGS.values() for slug in slugs)


def _best_scored_hit(hits: tuple[KnowledgeHit, ...]) -> KnowledgeHit | None:
    if not hits:
        return None
    scored = [hit for hit in hits if hit.score is not None]
    if scored:
        return min(scored, key=lambda item: item.score or 0.0)
    return hits[0]
