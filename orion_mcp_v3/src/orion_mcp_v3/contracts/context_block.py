"""Unidade formal de contexto — ROADMAP_EXECUTÁVEL Fase 0.2 (`ContextSource`, `ContextRole`, `ContextBlock`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ContextSource(Enum):
    """Origem coarse do texto (rastreio e políticas futuras)."""

    USER_INPUT = "user_input"
    SYSTEM = "system"
    MEMORY = "memory"
    ESSENCE = "essence"
    TOOL = "tool"
    BROKER = "broker"
    OTHER = "other"


class ContextRole(Enum):
    """Papel semântico ao montar prompts ou registos estruturados."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    NEUTRAL = "neutral"
    DATA = "data"
    CONTEXT = "context"


_CHARS_PER_TOKEN_ESTIMATE: int = 4


@dataclass(frozen=True, slots=True)
class ContextBlock:
    """
    Bloco autocontido de contexto textual + metadados leves.

    ``relevance_score`` alimenta o scheduler e o orçamento; campos de governação
    (Fase 1) permitem competição explícita entre memória, dados, digest e sistema.
    """

    text: str
    role: ContextRole
    source: ContextSource
    block_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    relevance_score: float = 0.0
    confidence: float = 1.0
    source_priority: float = 1.0
    cognitive_weight: float = 1.0
    information_density: float = 1.0
    token_cost: int | None = None
    compressibility: float = 0.5
    recency_score: float = 1.0

    def estimate_token_cost(self) -> int:
        """Custo em tokens (override ``token_cost`` ou heurística local, espelhada em ``token_estimator``)."""
        if self.token_cost is not None:
            return max(0, int(self.token_cost))
        if not self.text:
            return 0
        return max(1, len(self.text) // _CHARS_PER_TOKEN_ESTIMATE)

    def compute_attention_score(self) -> float:
        """
        Score de atenção bruto (Fase 1 — governança cognitiva):

        ``relevance × recency × confidence × source_priority × information_density``
        com ``cognitive_weight`` como ganho multiplicativo leve.
        """
        rel = max(0.0, float(self.relevance_score))
        rec = max(0.0, float(self.recency_score))
        conf = max(0.0, min(1.0, float(self.confidence)))
        sp = max(0.0, float(self.source_priority))
        dens = max(0.0, float(self.information_density))
        cw = max(0.0, float(self.cognitive_weight))
        base = rel * rec * conf * sp * dens
        if cw <= 0.0:
            return base
        return base * cw
