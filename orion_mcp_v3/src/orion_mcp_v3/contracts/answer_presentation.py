"""Contrato estruturado para apresentação de respostas analíticas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AnswerPresentationContract:
    """Saída segura do interpretador LLM: decide escopo e ordenação, não SQL."""

    result_scope: dict[str, Any] | None = None
    sort: dict[str, str] | None = None
    confidence: float = 0.0
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_scope": dict(self.result_scope) if self.result_scope is not None else None,
            "sort": dict(self.sort) if self.sort is not None else None,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AnswerPresentationContract":
        return cls(
            result_scope=_result_scope(raw.get("result_scope")),
            sort=_sort(raw.get("sort")),
            confidence=max(0.0, min(1.0, float(raw.get("confidence") or 0.0))),
            reason=str(raw.get("reason") or "").strip(),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def _result_scope(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    mode = _optional_str(value.get("mode"))
    if mode is None:
        return None
    limit_raw = value.get("limit")
    limit: int | None = None
    if limit_raw not in (None, ""):
        try:
            limit = max(1, int(limit_raw))
        except (TypeError, ValueError):
            limit = None
    return {"mode": mode.lower(), "limit": limit}


def _sort(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    field = _optional_str(value.get("field"))
    direction = _optional_str(value.get("direction"))
    if field is None and direction is None:
        return None
    return {
        "field": field or "",
        "direction": (direction or "desc").lower(),
    }
