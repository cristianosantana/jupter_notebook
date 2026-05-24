"""Assinatura semântica mínima para compatibilidade de contexto analítico."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock


@dataclass(frozen=True, slots=True)
class AnalyticalSignature:
    """Identifica o que uma evidência/pergunta analítica pretende responder."""

    template_slug: str | None = None
    measure: str | None = None
    dimension: str | None = None
    operation: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    entities: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "template_slug": self.template_slug,
            "measure": self.measure,
            "dimension": self.dimension,
            "operation": self.operation,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "entities": list(self.entities),
        }

    @property
    def has_analytical_shape(self) -> bool:
        return any((self.template_slug, self.measure, self.dimension, self.operation))


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _entities(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence):
        out: list[str] = []
        for item in value:
            s = _string_or_none(item)
            if s:
                out.append(s)
        return tuple(out)
    return ()


def _time_scope_bounds(plan: CognitivePlan) -> tuple[str | None, str | None]:
    hints = plan.hints or {}
    date_from = _string_or_none(hints.get("date_from")) if isinstance(hints, Mapping) else None
    date_to = _string_or_none(hints.get("date_to")) if isinstance(hints, Mapping) else None
    if date_from or date_to:
        return date_from, date_to
    if isinstance(plan.time_scope, str) and "/" in plan.time_scope:
        left, right = plan.time_scope.split("/", 1)
        return _string_or_none(left), _string_or_none(right)
    return None, None


def signature_from_plan(plan: CognitivePlan) -> AnalyticalSignature:
    """Cria assinatura preliminar a partir do plano cognitivo."""

    date_from, date_to = _time_scope_bounds(plan)
    measure = plan.metrics[0] if plan.metrics else None
    dimension = plan.entities[0] if plan.entities else None
    return AnalyticalSignature(
        measure=measure,
        dimension=dimension,
        date_from=date_from,
        date_to=date_to,
        entities=tuple(plan.entities),
    )


def _plan_mapping_from_evidence(evidence: EvidenceBlock) -> Mapping[str, Any] | None:
    for carrier in (evidence.metrics, evidence.insights, evidence.supporting_data):
        if not isinstance(carrier, Mapping):
            continue
        answer_plan = carrier.get("answer_plan")
        if isinstance(answer_plan, Mapping):
            return answer_plan
        direct_answer = carrier.get("direct_answer")
        if isinstance(direct_answer, Mapping):
            plan = direct_answer.get("plan")
            if isinstance(plan, Mapping):
                return plan
    return None


def signature_from_evidence(evidence: EvidenceBlock, *, fallback: CognitivePlan | None = None) -> AnalyticalSignature:
    """Extrai assinatura da evidência atual, preferindo o `ProjectedAnswer.plan`."""

    base = signature_from_plan(fallback) if fallback is not None else AnalyticalSignature()
    plan = _plan_mapping_from_evidence(evidence)
    if plan is None:
        return base
    return AnalyticalSignature(
        template_slug=_string_or_none(plan.get("template_slug")) or base.template_slug,
        measure=_string_or_none(plan.get("measure")) or base.measure,
        dimension=_string_or_none(plan.get("dimension")) or base.dimension,
        operation=_string_or_none(plan.get("operation")) or base.operation,
        date_from=base.date_from,
        date_to=base.date_to,
        entities=base.entities,
    )


def signature_from_metadata(metadata: Mapping[str, Any]) -> AnalyticalSignature | None:
    """Lê assinatura analítica de metadados de bloco, quando disponível."""

    raw = metadata.get("analytical_signature")
    if isinstance(raw, Mapping):
        return AnalyticalSignature(
            template_slug=_string_or_none(raw.get("template_slug")),
            measure=_string_or_none(raw.get("measure")),
            dimension=_string_or_none(raw.get("dimension")),
            operation=_string_or_none(raw.get("operation")),
            date_from=_string_or_none(raw.get("date_from")),
            date_to=_string_or_none(raw.get("date_to")),
            entities=_entities(raw.get("entities")),
        )
    plan = metadata.get("answer_plan")
    if isinstance(plan, Mapping):
        return AnalyticalSignature(
            template_slug=_string_or_none(plan.get("template_slug")),
            measure=_string_or_none(plan.get("measure")),
            dimension=_string_or_none(plan.get("dimension")),
            operation=_string_or_none(plan.get("operation")),
        )
    return None


def signatures_compatible(current: AnalyticalSignature, historical: AnalyticalSignature) -> bool:
    """Compatibilidade conservadora para reutilizar contexto analítico histórico."""

    if not historical.has_analytical_shape:
        return False
    if current.measure and historical.measure and current.measure != historical.measure:
        return False
    if current.dimension and historical.dimension and current.dimension != historical.dimension:
        return False
    if current.template_slug and historical.template_slug and current.template_slug != historical.template_slug:
        return False
    if current.date_from and historical.date_from and current.date_from != historical.date_from:
        return False
    if current.date_to and historical.date_to and current.date_to != historical.date_to:
        return False
    return True
