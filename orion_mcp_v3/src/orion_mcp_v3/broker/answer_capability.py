"""Contratos leves para mapear query results em respostas diretas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MeasureCapability:
    """Coluna numérica que uma query consegue usar como métrica de resposta."""

    column: str
    label: str
    kind: str = "number"
    synonyms: tuple[str, ...] = ()
    additive: bool = True
    sortable: bool = True


@dataclass(frozen=True, slots=True)
class DimensionCapability:
    """Coluna categórica/temporal que uma query consegue usar como dimensão."""

    column: str
    label: str
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnswerCapability:
    """Interface semântica exposta por um QueryTemplate."""

    measures: Mapping[str, MeasureCapability]
    dimensions: Mapping[str, DimensionCapability]
    default_measure: str
    default_dimension: str | None = None
    supported_operations: tuple[str, ...] = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")


@dataclass(frozen=True, slots=True)
class AnswerPlan:
    """Plano explícito de como transformar rows SQL em resposta objetiva."""

    template_slug: str
    measure: str
    dimension: str | None
    operation: str
    entity_filters: tuple[Mapping[str, str], ...] = ()
    result_scope: Mapping[str, Any] | None = None
    sort: Mapping[str, str] | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ProjectedAnswer:
    """Resposta objetiva derivada de rows, antes da narração LLM."""

    plan: AnswerPlan
    summary: str
    rows: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    top: Mapping[str, Any] | None = None
    bottom: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan": {
                "template_slug": self.plan.template_slug,
                "measure": self.plan.measure,
                "dimension": self.plan.dimension,
                "operation": self.plan.operation,
                "entity_filters": [dict(item) for item in self.plan.entity_filters],
                "result_scope": dict(self.plan.result_scope) if self.plan.result_scope is not None else None,
                "sort": dict(self.plan.sort) if self.plan.sort is not None else None,
                "reason": self.plan.reason,
            },
            "summary": self.summary,
            "rows": [dict(r) for r in self.rows],
            "top": dict(self.top) if self.top is not None else None,
            "bottom": dict(self.bottom) if self.bottom is not None else None,
        }
