"""Contrato semântico produzido pelo interpretador analítico."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class AnalyticalIntentType(str, Enum):
    ANALYTICAL = "analytical"
    COMPARATIVE = "comparative"
    TEMPORAL = "temporal"
    RECALL = "recall"
    MONITORING = "monitoring"
    EXECUTION = "execution"
    HYBRID = "hybrid"
    CONVERSATIONAL = "conversational"


class AnalyticalOperation(str, Enum):
    LIST = "list"
    RANKING_DESC = "ranking_desc"
    RANKING_ASC = "ranking_asc"
    TOP_AND_BOTTOM = "top_and_bottom"
    COMPARISON = "comparison"
    DELTA = "delta"
    SUMMARY = "summary"


class SourcePeriods(str, Enum):
    EXPLICIT = "explicit"
    LAST_ANALYTICAL_TURN = "last_analytical_turn"
    LAST_TWO_ANALYTICAL_TURNS = "last_two_analytical_turns"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class AnalyticalDateRange:
    label: str
    date_from: str
    date_to: str

    def as_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "date_from": self.date_from,
            "date_to": self.date_to,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AnalyticalDateRange":
        return cls(
            label=str(raw.get("label") or ""),
            date_from=str(raw.get("date_from") or ""),
            date_to=str(raw.get("date_to") or ""),
        )


@dataclass(frozen=True, slots=True)
class AnalyticalIntentContract:
    intent_type: AnalyticalIntentType
    operation: AnalyticalOperation
    needs_analytics: bool
    needs_memory: bool
    needs_comparison: bool
    template_slug: str | None = None
    metric: str | None = None
    dimension: str | None = None
    date_ranges: tuple[AnalyticalDateRange, ...] = ()
    source_periods: SourcePeriods = SourcePeriods.NONE
    inherits_from_previous: tuple[str, ...] = ()
    entity_filters: tuple[dict[str, str], ...] = ()
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_type": self.intent_type.value,
            "operation": self.operation.value,
            "needs_analytics": self.needs_analytics,
            "needs_memory": self.needs_memory,
            "needs_comparison": self.needs_comparison,
            "template_slug": self.template_slug,
            "metric": self.metric,
            "dimension": self.dimension,
            "date_ranges": [r.as_dict() for r in self.date_ranges],
            "source_periods": self.source_periods.value,
            "inherits_from_previous": list(self.inherits_from_previous),
            "entity_filters": [dict(item) for item in self.entity_filters],
            "confidence": self.confidence,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AnalyticalIntentContract":
        date_ranges_raw = raw.get("date_ranges") or ()
        if not isinstance(date_ranges_raw, (list, tuple)):
            date_ranges_raw = ()
        return cls(
            intent_type=AnalyticalIntentType(str(raw.get("intent_type") or "conversational")),
            operation=AnalyticalOperation(str(raw.get("operation") or "summary")),
            needs_analytics=bool(raw.get("needs_analytics")),
            needs_memory=bool(raw.get("needs_memory")),
            needs_comparison=bool(raw.get("needs_comparison")),
            template_slug=_optional_str(raw.get("template_slug")),
            metric=_optional_str(raw.get("metric")),
            dimension=_optional_str(raw.get("dimension")),
            date_ranges=tuple(
                AnalyticalDateRange.from_mapping(item)
                for item in date_ranges_raw
                if isinstance(item, Mapping)
            ),
            source_periods=SourcePeriods(str(raw.get("source_periods") or "none")),
            inherits_from_previous=tuple(
                str(v)
                for v in (raw.get("inherits_from_previous") or ())
                if str(v).strip()
            ),
            entity_filters=_entity_filters(raw.get("entity_filters")),
            confidence=max(0.0, min(1.0, float(raw.get("confidence") or 0.0))),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def _entity_filters(value: Any) -> tuple[dict[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        dimension = _optional_str(item.get("dimension"))
        filter_value = _optional_str(item.get("value"))
        if dimension is None or filter_value is None:
            continue
        match = str(item.get("match") or "contains").strip().lower() or "contains"
        out.append({"dimension": dimension, "value": filter_value, "match": match})
    return tuple(out)
