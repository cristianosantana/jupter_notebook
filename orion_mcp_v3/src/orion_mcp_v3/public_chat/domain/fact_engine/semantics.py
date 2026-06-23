"""Semântica canónica de facts — Fact Engine Spec v1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AggregationRule(str, Enum):
    SUM = "sum"
    MAX = "max"
    MIN = "min"
    LAST = "last"
    DERIVED = "derived"
    LOOKUP = "lookup"


class Comparator(str, Enum):
    ASC = "asc"
    DESC = "desc"
    NONE = "none"


class SourcePriority(str, Enum):
    KEY_METRICS = "key_metrics"
    STRUCTURED = "structured"
    PARSED_TEXT = "parsed_text"
    LLM = "llm"


@dataclass(frozen=True, slots=True)
class FactSemantics:
    fact_key: str
    aggregation_rule: AggregationRule
    comparator: Comparator
    source_priority: tuple[SourcePriority, ...]
    value_kind: str
    allows_multiple_values: bool = False
    derived_from: tuple[str, ...] = ()
    memory_themes: tuple[str, ...] = ()
    key_metrics_keys: tuple[str, ...] = ()

    def as_mapping(self) -> dict[str, object]:
        return {
            "fact_key": self.fact_key,
            "aggregation_rule": self.aggregation_rule.value,
            "comparator": self.comparator.value,
            "source_priority": [item.value for item in self.source_priority],
            "value_kind": self.value_kind,
            "allows_multiple_values": self.allows_multiple_values,
            "derived_from": list(self.derived_from),
            "memory_themes": list(self.memory_themes),
            "key_metrics_keys": list(self.key_metrics_keys),
        }
