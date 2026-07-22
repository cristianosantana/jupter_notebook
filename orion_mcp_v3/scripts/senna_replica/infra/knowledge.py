"""Dataclasses de hit remissivo (cópia enxuta)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    origin_id: int
    context_key: str
    category: str
    validated_answer: str
    key_metrics: Mapping[str, Any]
    score: float | None = None

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "origin_id": self.origin_id,
            "context_key": self.context_key,
            "category": self.category,
            "validated_answer": self.validated_answer,
            "key_metrics": dict(self.key_metrics),
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class EssenceItem:
    theme: str
    observation: str | None = None
    key_finding: str | None = None
    recommendation: str | None = None
