"""Políticas de atenção fixas (Fase 1.2) — fracções simples sobre o orçamento de tokens."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AttentionPolicy(Enum):
    """Famílias de peso declaradas (sem learner nem feedback)."""

    CONVERSATIONAL = "conversational"
    ANALYTICAL = "analytical"
    PLANNING = "planning"


@dataclass(frozen=True, slots=True)
class AttentionShares:
    """
    Pesos relativos aplicados pelo :func:`budget_allocator.allocate`.

    Os três campos são fracções não negativas cujo ``system + essence + free ≈ 1``.
    """

    system: float
    essence: float
    free: float


_SHARE_TABLE: dict[AttentionPolicy, tuple[float, float, float]] = {
    # (system_share, essence_share, free_share) — soma ≈ 1
    AttentionPolicy.CONVERSATIONAL: (0.12, 0.35, 0.53),
    AttentionPolicy.ANALYTICAL: (0.18, 0.22, 0.60),
    AttentionPolicy.PLANNING: (0.20, 0.28, 0.52),
}


def policy_shares(policy: AttentionPolicy) -> AttentionShares:
    """Fracções típicas alinhadas a cada política nominal."""
    s, e, f = _SHARE_TABLE[policy]
    return AttentionShares(system=s, essence=e, free=f)
