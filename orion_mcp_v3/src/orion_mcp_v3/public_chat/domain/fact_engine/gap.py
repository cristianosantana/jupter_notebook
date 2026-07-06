"""Gaps tipados com reason codes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orion_mcp_v3.public_chat.domain.fact_engine.trace import ResolutionTrace


class GapReason(str, Enum):
    NOT_IN_CATALOG = "not_in_catalog"
    NO_MEMORY_FOUND = "no_memory_found"
    NOT_FOUND = "not_found"
    MEMORY_EXISTS_BUT_NO_MATCH = "memory_exists_but_no_match"
    KEY_METRICS_INDEX_AMBIGUOUS = "key_metrics_index_ambiguous"
    PARTIAL_MATCH_ONLY = "partial_match_only"
    EXTRACTION_FAILED = "extraction_failed"
    LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True, slots=True)
class FactGap:
    fact_key: str
    reason: GapReason
    detail: str | None = None
    origin_ids_attempted: tuple[int, ...] = ()
    attempted_rules: tuple[str, ...] = ()
    resolution_trace: ResolutionTrace | None = None

    def as_mapping(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "fact_key": self.fact_key,
            "reason": self.reason.value,
            "detail": self.detail,
            "origin_ids_attempted": list(self.origin_ids_attempted),
            "attempted_rules": list(self.attempted_rules),
        }
        if self.resolution_trace is not None:
            payload["resolution_trace"] = self.resolution_trace.as_mapping()
        return payload
