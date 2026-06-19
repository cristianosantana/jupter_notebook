"""Modelos principais do Fact Engine."""

from __future__ import annotations

from dataclasses import dataclass

from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType
from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap
from orion_mcp_v3.public_chat.domain.fact_engine.join_plan import MemoryJoinPlan
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import FactSemantics
from orion_mcp_v3.public_chat.domain.fact_engine.trace import FactTrace


@dataclass(frozen=True, slots=True)
class FactRequirement:
    fact_key: str
    metric: str | None
    dimension: str | None
    entity: str | None
    period: str | None
    operation: str | None
    semantics: FactSemantics

    def as_mapping(self) -> dict[str, object]:
        return {
            "fact_key": self.fact_key,
            "metric": self.metric,
            "dimension": self.dimension,
            "entity": self.entity,
            "period": self.period,
            "operation": self.operation,
            "semantics": self.semantics.as_mapping(),
        }


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    fact_key: str
    label: str
    value: str
    unit: str | None
    fact_type: FactType
    confidence: float
    origin_id: int
    context_key: str
    trace: FactTrace

    def as_mapping(self) -> dict[str, object]:
        return {
            "fact_key": self.fact_key,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "fact_type": self.fact_type.value,
            "confidence": round(self.confidence, 4),
            "origin_id": self.origin_id,
            "context_key": self.context_key,
            "trace": self.trace.as_mapping(),
        }


@dataclass(frozen=True, slots=True)
class RemissiveWorkspace:
    period: str | None
    facts: tuple[ExtractedFact, ...]
    gaps: tuple[FactGap, ...]
    requirements: tuple[FactRequirement, ...]
    join_plan: MemoryJoinPlan | None
    workspace_confidence: float

    @property
    def has_facts(self) -> bool:
        return bool(self.facts)

    def as_prompt_dict(self) -> dict[str, object]:
        return {
            "period": self.period,
            "facts": [fact.as_mapping() for fact in self.facts],
            "gaps": [gap.as_mapping() for gap in self.gaps],
            "requirements": [req.as_mapping() for req in self.requirements],
            "join_plan": self.join_plan.as_mapping() if self.join_plan else None,
            "workspace_confidence": round(self.workspace_confidence, 4),
        }
