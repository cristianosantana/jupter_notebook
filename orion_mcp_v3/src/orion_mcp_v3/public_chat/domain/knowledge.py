"""Modelos de conhecimento remissivo recuperado."""

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

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "observation": self.observation,
            "key_finding": self.key_finding,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True, slots=True)
class ConhecimentoRecuperado:
    hits: tuple[KnowledgeHit, ...] = ()
    essence: tuple[EssenceItem, ...] = ()

    @property
    def has_hits(self) -> bool:
        return bool(self.hits)

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "hits": [hit.as_prompt_dict() for hit in self.hits],
            "essence": [item.as_prompt_dict() for item in self.essence],
        }


@dataclass(frozen=True, slots=True)
class AnswerPayload:
    context_keys: tuple[str, ...]
    knowledge_ids: tuple[int, ...]
    essence_themes: tuple[str, ...]
    partial: bool = False
    gap_count: int = 0
    missing_fact_keys: tuple[str, ...] = ()

    def as_mapping(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "context_keys": list(self.context_keys),
            "knowledge_ids": list(self.knowledge_ids),
            "essence_themes": list(self.essence_themes),
        }
        if self.partial or self.gap_count or self.missing_fact_keys:
            payload["partial"] = self.partial
            payload["gap_count"] = self.gap_count
            payload["missing_fact_keys"] = list(self.missing_fact_keys)
        return payload

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> AnswerPayload:
        context_keys = tuple(str(item) for item in (data.get("context_keys") or []))
        knowledge_ids = tuple(int(item) for item in (data.get("knowledge_ids") or []))
        essence_themes = tuple(str(item) for item in (data.get("essence_themes") or []))
        missing_raw = data.get("missing_fact_keys") or []
        missing_fact_keys = tuple(str(item) for item in missing_raw)
        try:
            gap_count = int(data.get("gap_count") or 0)
        except (TypeError, ValueError):
            gap_count = 0
        return cls(
            context_keys=context_keys,
            knowledge_ids=knowledge_ids,
            essence_themes=essence_themes,
            partial=bool(data.get("partial")),
            gap_count=max(0, gap_count),
            missing_fact_keys=missing_fact_keys,
        )


def build_answer_payload(
    knowledge: ConhecimentoRecuperado,
    *,
    partial: bool = False,
    gap_count: int = 0,
    missing_fact_keys: tuple[str, ...] = (),
) -> AnswerPayload:
    return AnswerPayload(
        context_keys=tuple(hit.context_key for hit in knowledge.hits),
        knowledge_ids=tuple(hit.origin_id for hit in knowledge.hits),
        essence_themes=tuple(item.theme for item in knowledge.essence),
        partial=partial,
        gap_count=gap_count,
        missing_fact_keys=missing_fact_keys,
    )
