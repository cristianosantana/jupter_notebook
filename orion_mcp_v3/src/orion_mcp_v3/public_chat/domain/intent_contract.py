"""Contrato de intenção do Chat Público."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class PublicIntentType(str, Enum):
    CONSULTA_METRICA = "consulta_metrica"
    COMPARACAO = "comparacao"
    RECALL = "recall"
    GERAL = "geral"


class PublicOperationType(str, Enum):
    RANKING_ASC = "ranking_asc"
    RANKING_DESC = "ranking_desc"
    LIST = "list"
    SUMMARY = "summary"
    COMPARISON = "comparison"


@dataclass(frozen=True, slots=True)
class EntityFilter:
    dimension: str
    value: str
    match: str = "contains"

    def as_mapping(self) -> dict[str, str]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "match": self.match,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> EntityFilter:
        return cls(
            dimension=str(data.get("dimension") or "").strip(),
            value=str(data.get("value") or "").strip(),
            match=str(data.get("match") or "contains").strip() or "contains",
        )


@dataclass(frozen=True, slots=True)
class IntentContract:
    intent: str
    metric: str | None = None
    period: str | None = None
    domain: str | None = None
    entity_filters: tuple[EntityFilter, ...] = ()
    confidence: float = 0.0
    operation: str | None = None
    dimension: str | None = None
    sort_direction: str | None = None

    @classmethod
    def geral(cls, *, confidence: float = 0.0) -> IntentContract:
        return cls(
            intent=PublicIntentType.GERAL.value,
            confidence=confidence,
        )

    def as_mapping(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "metric": self.metric,
            "period": self.period,
            "domain": self.domain,
            "entity_filters": [item.as_mapping() for item in self.entity_filters],
            "confidence": self.confidence,
            "operation": self.operation,
            "dimension": self.dimension,
            "sort_direction": self.sort_direction,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> IntentContract:
        raw_filters = data.get("entity_filters") or []
        filters: list[EntityFilter] = []
        if isinstance(raw_filters, Sequence) and not isinstance(raw_filters, (str, bytes)):
            for item in raw_filters:
                if isinstance(item, Mapping):
                    filters.append(EntityFilter.from_mapping(item))
        confidence_raw = data.get("confidence", 0.0)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        metric = _optional_str(data.get("metric"))
        period = _optional_str(data.get("period"))
        domain = _optional_str(data.get("domain"))
        intent = _optional_str(data.get("intent")) or PublicIntentType.GERAL.value
        operation = _optional_str(data.get("operation"))
        dimension = _optional_str(data.get("dimension"))
        sort_direction = _optional_str(data.get("sort_direction"))
        return cls(
            intent=intent,
            metric=metric,
            period=period,
            domain=domain,
            entity_filters=tuple(filters),
            confidence=max(0.0, min(1.0, confidence)),
            operation=operation,
            dimension=dimension,
            sort_direction=sort_direction,
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
