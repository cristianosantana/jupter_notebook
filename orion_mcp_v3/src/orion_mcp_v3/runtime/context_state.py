"""Estado de sessão e fase do ciclo cognitivo (Fase 1.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from orion_mcp_v3.contracts.context_block import ContextBlock
from orion_mcp_v3.contracts.cognitive_plan import IntentType
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy


class CognitivePhase(Enum):
    """Fases coordenadas do turno cognitivo."""

    IDLE = "idle"
    RETRIEVING = "retrieving"
    DISTILLING = "distilling"
    FUSING = "fusing"
    ALLOCATING = "allocating"
    NARRATING = "narrating"


@dataclass
class ContextState:
    """Estado do runtime: intenção activa, pressões analíticas/memória, artefactos recentes."""

    cognitive_phase: CognitivePhase = CognitivePhase.IDLE
    active_policy: AttentionPolicy = AttentionPolicy.BALANCED
    token_budget: int = 4096
    active_blocks: list[ContextBlock] = field(default_factory=list)
    active_intent: IntentType | None = None
    active_entities: tuple[str, ...] = ()
    last_digest: AnalyticalDigest | None = None
    last_query_plan: SemanticQueryPlan | None = None
    memory_pressure: float = 0.0
    analytics_pressure: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def current_phase(self) -> str:
        """Alias legível para logging (slug da fase)."""
        return self.cognitive_phase.value

    @current_phase.setter
    def current_phase(self, value: str | CognitivePhase) -> None:
        if isinstance(value, CognitivePhase):
            self.cognitive_phase = value
        else:
            self.cognitive_phase = CognitivePhase(value)
