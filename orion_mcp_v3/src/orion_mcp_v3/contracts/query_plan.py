"""Plano semântico de recuperação/consulta (Fase 0.5 — sem compilador SQL)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class RetrievalStrategy(Enum):
    """Modo declarado de obtenção de evidência."""

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    EXACT_LOOKUP = "exact_lookup"
    BROKER_FANOUT = "broker_fanout"


class AnalyticsStrategy(Enum):
    """
    Modo de análise cognitiva endereçável (MySQL integrado — separa digest de query engine).

    Valores alinhados ao guia de implementação (trend, ranking, temporal, comparison, anomaly).
    """

    TREND = "trend"
    RANKING = "ranking"
    TEMPORAL = "temporal"
    COMPARISON = "comparison"
    ANOMALY = "anomaly"


@dataclass(frozen=True, slots=True)
class SemanticQueryPlan:
    """
    Intenção recuperável já normalizada ao domínio de produto.

    Não inclui texto SQL nem árvores de compilador — só estratégia + metadados.
    """

    intent_slug: str
    strategy: RetrievalStrategy
    target_collections: tuple[str, ...] = ()
    hints: Mapping[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    analytics_strategy: AnalyticsStrategy | None = None
