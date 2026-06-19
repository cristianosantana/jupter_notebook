"""Rastreabilidade de resolução e extracção de facts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResolutionRule(str, Enum):
    CATALOG = "catalog"
    VECTOR_RETRIEVAL = "vector_retrieval"
    LLM_FALLBACK = "llm_fallback"
    JOIN_PLAN = "join_plan"


class ExtractionPath(str, Enum):
    KEY_METRICS = "key_metrics"
    STRUCTURED_PARSER = "structured_parser"
    RANKING_DERIVED = "ranking_derived"
    LLM_EXTRACT = "llm_extract"
    DERIVED_COMPUTE = "derived_compute"


@dataclass(frozen=True, slots=True)
class FactTrace:
    fact_key: str
    resolved_from: tuple[int, ...]
    context_keys: tuple[str, ...]
    rule_applied: ResolutionRule
    extraction_path: ExtractionPath
    semantics_version: str = "v1"

    def as_mapping(self) -> dict[str, object]:
        return {
            "fact_key": self.fact_key,
            "resolved_from": list(self.resolved_from),
            "context_keys": list(self.context_keys),
            "rule_applied": self.rule_applied.value,
            "extraction_path": self.extraction_path.value,
            "semantics_version": self.semantics_version,
        }
