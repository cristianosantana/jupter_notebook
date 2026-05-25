"""Contrato estruturado para seleção semântica de QueryTemplate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class QuerySelectionContract:
    """Saída segura do seletor LLM: escolhe visão analítica, não SQL."""

    template_slug: str
    measure: str | None = None
    dimension: str | None = None
    operation: str | None = None
    confidence: float = 0.0
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "template_slug": self.template_slug,
            "measure": self.measure,
            "dimension": self.dimension,
            "operation": self.operation,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "QuerySelectionContract":
        return cls(
            template_slug=str(raw.get("template_slug") or "").strip(),
            measure=_optional_str(raw.get("measure")),
            dimension=_optional_str(raw.get("dimension")),
            operation=_optional_str(raw.get("operation")),
            confidence=max(0.0, min(1.0, float(raw.get("confidence") or 0.0))),
            reason=str(raw.get("reason") or "").strip(),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    out = str(value).strip()
    return out or None
