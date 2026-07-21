"""Fact Engine remissivo — contratos e tipos partilhados (Fase 5)."""

from orion_mcp_v3.public_chat.domain.fact_engine.confidence import (
    EXTRACTION_CONFIDENCE,
    MIN_CACHE_STORE_CONFIDENCE,
    MIN_DERIVE_CONFIDENCE,
    MIN_FACT_CONFIDENCE,
    confidence_for_path,
)
from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType
from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap, GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.join_plan import MemoryJoinPlan, MemorySourceRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.models import (
    ExtractedFact,
    FactRequirement,
    RemissiveWorkspace,
)
from orion_mcp_v3.public_chat.domain.fact_engine.requirement_kind import RequirementKind
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import (
    AggregationRule,
    Comparator,
    FactSemantics,
    SourcePriority,
)
from orion_mcp_v3.public_chat.domain.fact_engine.trace import (
    ExtractionPath,
    FactTrace,
    ResolutionRule,
    ResolutionTrace,
    build_resolution_trace,
    fact_trace_from_resolution,
)

__all__ = [
    "AggregationRule",
    "Comparator",
    "EXTRACTION_CONFIDENCE",
    "ExtractedFact",
    "ExtractionPath",
    "FactGap",
    "FactRequirement",
    "FactSemantics",
    "FactTrace",
    "FactType",
    "GapReason",
    "MIN_CACHE_STORE_CONFIDENCE",
    "MIN_DERIVE_CONFIDENCE",
    "MIN_FACT_CONFIDENCE",
    "MemoryJoinPlan",
    "MemorySourceRequirement",
    "RemissiveWorkspace",
    "RequirementKind",
    "ResolutionRule",
    "ResolutionTrace",
    "SourcePriority",
    "build_resolution_trace",
    "fact_trace_from_resolution",
    "confidence_for_path",
]
