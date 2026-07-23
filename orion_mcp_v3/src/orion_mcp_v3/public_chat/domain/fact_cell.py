"""FactCell — unidade universal de evidência (Requirement resolvido)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.public_chat.domain.fact_engine.models import ExtractedFact
from orion_mcp_v3.public_chat.domain.fact_engine.trace import FactTrace


@dataclass(frozen=True, slots=True)
class FactCell:
    """Célula tipada: evidência literal de um leaf requirement."""

    fact_key: str
    label: str
    value: str
    numeric_value: float | None
    unit: str | None
    period: str | None
    dimension: str | None
    matched_key: str | None
    confidence: float
    origin_id: int
    context_key: str
    trace: FactTrace

    def as_mapping(self) -> dict[str, Any]:
        return {
            "fact_key": self.fact_key,
            "label": self.label,
            "value": self.value,
            "numeric_value": self.numeric_value,
            "unit": self.unit,
            "period": self.period,
            "dimension": self.dimension,
            "matched_key": self.matched_key,
            "confidence": round(self.confidence, 4),
            "origin_id": self.origin_id,
            "context_key": self.context_key,
            "trace": self.trace.as_mapping(),
        }

    def to_extracted_fact(self, *, fact_type_value: str = "raw") -> ExtractedFact:
        from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType

        fact_type = FactType(fact_type_value) if fact_type_value in FactType._value2member_map_ else FactType.RAW
        return ExtractedFact(
            fact_key=self.fact_key,
            label=self.label,
            value=self.value,
            unit=self.unit,
            fact_type=fact_type,
            confidence=self.confidence,
            origin_id=self.origin_id,
            context_key=self.context_key,
            trace=self.trace,
        )


def cell_from_extracted_fact(
    fact: ExtractedFact,
    *,
    period: str | None = None,
    dimension: str | None = None,
    matched_key: str | None = None,
    numeric_value: float | None = None,
) -> FactCell:
    return FactCell(
        fact_key=fact.fact_key,
        label=fact.label,
        value=fact.value,
        numeric_value=numeric_value if numeric_value is not None else _try_parse_number(fact.value),
        unit=fact.unit,
        period=period,
        dimension=dimension,
        matched_key=matched_key,
        confidence=fact.confidence,
        origin_id=fact.origin_id,
        context_key=fact.context_key,
        trace=fact.trace,
    )


def _try_parse_number(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    # percent
    if text.endswith("%"):
        try:
            return float(text[:-1].replace(",", ".").strip())
        except ValueError:
            return None
    # currency-ish: keep digits
    cleaned = text.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None
