"""Políticas de atenção fixas (Fase 1.2) — fracções simples sobre o orçamento de tokens."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AttentionPolicy(Enum):
    """Famílias de peso declaradas (sem learner nem feedback)."""

    CONVERSATIONAL = "conversational"
    ANALYTICAL = "analytical"
    PLANNING = "planning"
    HYBRID = "hybrid"
    MONITORING = "monitoring"
    EXECUTION = "execution"


@dataclass(frozen=True, slots=True)
class AttentionShares:
    """
    Pesos relativos aplicados pelo :func:`budget_allocator.allocate`.

    Os três campos são fracções não negativas cujo ``system + essence + free ≈ 1``.
    """

    system: float
    essence: float
    free: float


@dataclass(frozen=True, slots=True)
class ElasticFreeTierParams:
    """
    Parte livre do orçamento (após system/essence) com zonas elásticas e competição DATA vs MEMORY.

    * ``dialogue_fraction_of_free`` — parcela do *free tier* para USER/ASSISTANT (turno).
    * ``data_share_of_remainder`` — após diálogo, fração do restante para blocos DATA/analytics;
      memória ocupa ``1 - data_share_of_remainder``.
    * ``elasticity`` — tecto de *spill* entre zonas DATA↔MEMORY como fração do free tier total.
    """

    dialogue_fraction_of_free: float
    data_share_of_remainder: float
    elasticity: float


_SHARE_TABLE: dict[AttentionPolicy, tuple[float, float, float]] = {
    # (system_share, essence_share, free_share) — soma ≈ 1
    AttentionPolicy.CONVERSATIONAL: (0.12, 0.35, 0.53),
    AttentionPolicy.ANALYTICAL: (0.18, 0.22, 0.60),
    AttentionPolicy.PLANNING: (0.20, 0.28, 0.52),
    AttentionPolicy.HYBRID: (0.15, 0.25, 0.60),
    AttentionPolicy.MONITORING: (0.14, 0.18, 0.68),
    AttentionPolicy.EXECUTION: (0.22, 0.18, 0.60),
}


def policy_shares(policy: AttentionPolicy) -> AttentionShares:
    """Fracções típicas alinhadas a cada política nominal."""
    s, e, f = _SHARE_TABLE[policy]
    return AttentionShares(system=s, essence=e, free=f)


_ELASTIC_TABLE: dict[AttentionPolicy, tuple[float, float, float]] = {
    # (dialogue_fraction_of_free, data_share_of_remainder, elasticity)
    AttentionPolicy.CONVERSATIONAL: (0.32, 0.38, 0.14),
    AttentionPolicy.ANALYTICAL: (0.10, 0.72, 0.16),
    AttentionPolicy.PLANNING: (0.18, 0.55, 0.12),
    AttentionPolicy.HYBRID: (0.22, 0.52, 0.14),
    AttentionPolicy.MONITORING: (0.14, 0.48, 0.18),
    AttentionPolicy.EXECUTION: (0.12, 0.58, 0.12),
}


def elastic_free_tier_params(policy: AttentionPolicy) -> ElasticFreeTierParams:
    """Hiperparâmetros da zona livre elástica (§10 ORDEM_IMPLEMENTAÇÃO) por política de atenção."""
    d, ds, e = _ELASTIC_TABLE[policy]
    return ElasticFreeTierParams(
        dialogue_fraction_of_free=d,
        data_share_of_remainder=ds,
        elasticity=e,
    )
