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


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolutionTrace:
    fact_key: str
    resolved_from: tuple[int, ...]
    context_keys: tuple[str, ...]
    rule_applied: ResolutionRule
    semantics_version: str = "v1"

    def as_mapping(self) -> dict[str, object]:
        return {
            "fact_key": self.fact_key,
            "resolved_from": list(self.resolved_from),
            "context_keys": list(self.context_keys),
            "rule_applied": self.rule_applied.value,
            "semantics_version": self.semantics_version,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class FactTrace(ResolutionTrace):
    extraction_path: ExtractionPath

    def as_mapping(self) -> dict[str, object]:
        return {
            "fact_key": self.fact_key,
            "resolved_from": list(self.resolved_from),
            "context_keys": list(self.context_keys),
            "rule_applied": self.rule_applied.value,
            "semantics_version": self.semantics_version,
            "extraction_path": self.extraction_path.value,
        }


def build_resolution_trace(
    *,
    fact_key: str,
    hit_origin_id: int,
    hit_context_key: str,
    rule: ResolutionRule,
    semantics_version: str = "v1",
) -> ResolutionTrace:
    return ResolutionTrace(
        fact_key=fact_key,
        resolved_from=(hit_origin_id,),
        context_keys=(hit_context_key,),
        rule_applied=rule,
        semantics_version=semantics_version,
    )


def fact_trace_from_resolution(
    resolution: ResolutionTrace,
    extraction_path: ExtractionPath,
) -> FactTrace:
    return FactTrace(
        fact_key=resolution.fact_key,
        resolved_from=resolution.resolved_from,
        context_keys=resolution.context_keys,
        rule_applied=resolution.rule_applied,
        semantics_version=resolution.semantics_version,
        extraction_path=extraction_path,
    )
