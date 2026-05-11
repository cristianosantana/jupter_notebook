"""Políticas de atenção (Fase 1) — definições operacionais para o runtime e o allocator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class AttentionPolicy(Enum):
    """
    Políticas canónicas (Fase 1.3) + perfis legados (compatibilidade).

    Canónicas: ``ANALYTICAL``, ``BALANCED``, ``MEMORY_FOCUSED``, ``MONITORING``, ``EXECUTION``.
    """

    ANALYTICAL = "analytical"
    BALANCED = "balanced"
    MEMORY_FOCUSED = "memory_focused"
    MONITORING = "monitoring"
    EXECUTION = "execution"
    # legado — mantidos para não quebrar chamadas existentes
    CONVERSATIONAL = "conversational"
    PLANNING = "planning"
    HYBRID = "hybrid"


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


@dataclass(frozen=True, slots=True)
class AttentionPolicyDefinition:
    """
    Definição operacional de uma política: fracções globais, zona livre elástica,
    pesos por *bucket* de origem, tetos de blocos e fontes obrigatórias.
    """

    shares: AttentionShares
    elastic: ElasticFreeTierParams
    source_weights: Mapping[str, float]
    max_blocks_per_source: Mapping[str, int]
    token_ratio_per_source: Mapping[str, float]
    mandatory_sources: frozenset[str]


def _ro(m: dict[str, float | int]) -> MappingProxyType[str, float | int]:
    return MappingProxyType(dict(m))


_POLICY_DEFS: dict[AttentionPolicy, AttentionPolicyDefinition] = {}

# defaults de bucket (chaves: system, essence, user_dialogue, memory, data, other)
_DEFAULT_WEIGHTS: dict[str, float] = {
    "system": 1.0,
    "essence": 1.05,
    "user_dialogue": 1.12,
    "memory": 1.08,
    "data": 1.1,
    "other": 1.0,
}
_DEFAULT_MAX: dict[str, int] = {
    "system": 99,
    "essence": 99,
    "user_dialogue": 48,
    "memory": 48,
    "data": 48,
    "other": 99,
}
_DEFAULT_TOKEN_RATIO: dict[str, float] = {
    "system": 0.12,
    "essence": 0.22,
    "user_dialogue": 0.22,
    "memory": 0.22,
    "data": 0.22,
    "other": 0.1,
}


def _defn(
    s: tuple[float, float, float],
    e: tuple[float, float, float],
    *,
    weights: dict[str, float] | None = None,
    max_blocks: dict[str, int] | None = None,
    token_ratio: dict[str, float] | None = None,
    mandatory: frozenset[str] | None = None,
) -> AttentionPolicyDefinition:
    sh = AttentionShares(system=s[0], essence=s[1], free=s[2])
    el = ElasticFreeTierParams(
        dialogue_fraction_of_free=e[0],
        data_share_of_remainder=e[1],
        elasticity=e[2],
    )
    w = {**_DEFAULT_WEIGHTS, **(weights or {})}
    mb = {**_DEFAULT_MAX, **(max_blocks or {})}
    tr = {**_DEFAULT_TOKEN_RATIO, **(token_ratio or {})}
    return AttentionPolicyDefinition(
        shares=sh,
        elastic=el,
        source_weights=MappingProxyType({k: float(v) for k, v in w.items()}),
        max_blocks_per_source=MappingProxyType({k: int(v) for k, v in mb.items()}),
        token_ratio_per_source=MappingProxyType({k: float(v) for k, v in tr.items()}),
        mandatory_sources=mandatory or frozenset(),
    )


_POLICY_DEFS[AttentionPolicy.ANALYTICAL] = _defn(
    (0.18, 0.22, 0.60),
    (0.10, 0.72, 0.16),
    weights={"data": 1.22, "memory": 0.92},
    max_blocks={"data": 56, "memory": 12, "user_dialogue": 36},
    token_ratio={"data": 0.45, "memory": 0.12, "user_dialogue": 0.18},
)
_POLICY_DEFS[AttentionPolicy.BALANCED] = _defn(
    (0.12, 0.35, 0.53),
    (0.32, 0.38, 0.14),
    weights={"memory": 1.1, "data": 1.06, "user_dialogue": 1.18},
)
_POLICY_DEFS[AttentionPolicy.MEMORY_FOCUSED] = _defn(
    (0.10, 0.38, 0.52),
    (0.28, 0.22, 0.18),
    weights={"memory": 1.35, "data": 0.88, "essence": 1.12},
    max_blocks={"memory": 64, "data": 14, "user_dialogue": 40},
    token_ratio={"memory": 0.42, "data": 0.14, "user_dialogue": 0.24},
)
_POLICY_DEFS[AttentionPolicy.MONITORING] = _defn(
    (0.14, 0.18, 0.68),
    (0.14, 0.48, 0.18),
    weights={"data": 1.18, "memory": 1.02},
    max_blocks={"data": 40, "memory": 20},
)
_POLICY_DEFS[AttentionPolicy.EXECUTION] = _defn(
    (0.22, 0.18, 0.60),
    (0.12, 0.58, 0.12),
    weights={"user_dialogue": 1.22, "data": 1.12},
)
# legado — espelham políticas canónicas
_POLICY_DEFS[AttentionPolicy.CONVERSATIONAL] = _POLICY_DEFS[AttentionPolicy.BALANCED]
_POLICY_DEFS[AttentionPolicy.PLANNING] = _defn(
    (0.20, 0.28, 0.52),
    (0.18, 0.55, 0.12),
    weights={"data": 1.1, "user_dialogue": 1.1},
)
_POLICY_DEFS[AttentionPolicy.HYBRID] = _defn(
    (0.15, 0.25, 0.60),
    (0.22, 0.52, 0.14),
    weights={"data": 1.12, "memory": 1.12},
)


def policy_definition(policy: AttentionPolicy) -> AttentionPolicyDefinition:
    """Definição completa usada pelo allocator e por tracers."""
    return _POLICY_DEFS[policy]


def policy_shares(policy: AttentionPolicy) -> AttentionShares:
    """Fracções típicas alinhadas a cada política nominal."""
    return policy_definition(policy).shares


def elastic_free_tier_params(policy: AttentionPolicy) -> ElasticFreeTierParams:
    """Hiperparâmetros da zona livre elástica por política de atenção."""
    return policy_definition(policy).elastic
