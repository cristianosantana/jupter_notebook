"""
Plano cognitivo declarativo — separa *entendimento* de *execução* (Cognitive Foundation).

Heurísticas produzem :class:`CognitivePlan`; SQL/planos semânticos são camadas seguintes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from orion_mcp_v3.contracts.query_plan import RetrievalStrategy


class IntentType(Enum):
    """Classificação grossa da intenção do utilizador."""

    ANALYTICAL = "analytical"
    CONVERSATIONAL = "conversational"
    COMPARATIVE = "comparative"
    TEMPORAL = "temporal"
    RECALL = "recall"
    MONITORING = "monitoring"
    EXECUTION = "execution"
    HYBRID = "hybrid"


class AttentionProfile(Enum):
    """
    Preferência de atenção / orçamento (alinhável a :class:`~AttentionPolicy` em runtime).

    Mantido em ``contracts`` para não acoplar este tipo a ``runtime``.
    """

    ANALYTICAL = "analytical"
    BALANCED = "balanced"
    MEMORY_FOCUSED = "memory_focused"
    CONVERSATIONAL = "conversational"
    PLANNING = "planning"
    HYBRID = "hybrid"
    MONITORING = "monitoring"
    EXECUTION = "execution"


@dataclass(frozen=True, slots=True)
class CognitivePlan:
    """
    Resultado de análise heurística da mensagem — sem LLM.

    ``confidence`` ∈ [0, 1] é estimativa da resolução heurística (não probabilidade calibrada).
    """

    intent_type: IntentType
    needs_memory: bool = False
    needs_analytics: bool = False
    needs_comparison: bool = False
    needs_temporal_context: bool = False
    needs_baseline: bool = False
    needs_trend_analysis: bool = False
    needs_entity_resolution: bool = False
    confidence: float = 0.0
    entities: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    time_scope: str | None = None
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.BROKER_FANOUT
    attention_profile: AttentionProfile = AttentionProfile.CONVERSATIONAL
    hints: Mapping[str, Any] = field(default_factory=dict)
