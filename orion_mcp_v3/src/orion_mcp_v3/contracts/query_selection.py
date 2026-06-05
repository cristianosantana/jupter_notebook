"""Contrato estruturado para seleção semântica de QueryTemplate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class QuerySelectionContract:
    """Saída segura do seletor LLM: escolhe visão analítica, não SQL."""

    template_slug: str | None = None
    collection_slug: str | None = None
    selection_kind: str = "template"
    measure: str | None = None
    dimension: str | None = None
    operation: str | None = None
    entity_filters: tuple[dict[str, str], ...] = ()
    confidence: float = 0.0
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "selection_kind": self.selection_kind,
            "template_slug": self.template_slug,
            "collection_slug": self.collection_slug,
            "measure": self.measure,
            "dimension": self.dimension,
            "operation": self.operation,
            "entity_filters": [dict(item) for item in self.entity_filters],
            "confidence": self.confidence,
            "reason": self.reason,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "QuerySelectionContract":
        collection_slug = _optional_str(raw.get("collection_slug"))
        template_slug = _optional_str(raw.get("template_slug"))
        selection_kind = _optional_str(raw.get("selection_kind"))
        if selection_kind is None:
            selection_kind = "collection" if collection_slug is not None else "template"
        return cls(
            template_slug=template_slug,
            collection_slug=collection_slug,
            selection_kind=selection_kind,
            measure=_optional_str(raw.get("measure")),
            dimension=_optional_str(raw.get("dimension")),
            operation=_optional_str(raw.get("operation")),
            entity_filters=_entity_filters(raw.get("entity_filters")),
            confidence=max(0.0, min(1.0, float(raw.get("confidence") or 0.0))),
            reason=str(raw.get("reason") or "").strip(),
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
