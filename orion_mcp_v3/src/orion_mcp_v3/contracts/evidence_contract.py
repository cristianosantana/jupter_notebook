"""Contratos estruturados para qualidade, escopo e falhas da evidência."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class EvidenceStatus(str, Enum):
    PRESENT = "present"
    EMPTY_RESULT = "empty_result"
    PIPELINE_FAILURE = "pipeline_failure"
    NOT_REQUIRED = "not_required"
    UNAVAILABLE = "unavailable"


class EvidencePriority(str, Enum):
    DIRECT_ANSWER = "direct_answer"
    FRESH_SQL_EVIDENCE = "fresh_sql_evidence"
    AGGREGATED_METRICS = "aggregated_metrics"
    VALIDATED_SUMMARY = "validated_summary"
    PREVIEW = "preview"
    COMPATIBLE_MEMORY = "compatible_memory"
    CONVERSATIONAL_MEMORY = "conversational_memory"


@dataclass(frozen=True, slots=True)
class OperationalConfidence:
    data_coverage: float = 0.0
    aggregation_reliability: float = 0.0
    pipeline_integrity: float = 0.0
    narrative_confidence: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "data_coverage": _clamp01(self.data_coverage),
            "aggregation_reliability": _clamp01(self.aggregation_reliability),
            "pipeline_integrity": _clamp01(self.pipeline_integrity),
            "narrative_confidence": _clamp01(self.narrative_confidence),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "OperationalConfidence":
        if not isinstance(raw, Mapping):
            return cls()
        return cls(
            data_coverage=_float(raw.get("data_coverage")),
            aggregation_reliability=_float(raw.get("aggregation_reliability")),
            pipeline_integrity=_float(raw.get("pipeline_integrity")),
            narrative_confidence=_float(raw.get("narrative_confidence")),
        )


@dataclass(frozen=True, slots=True)
class PipelineFailure:
    stage: str
    failure_type: str
    impact: str
    analytical_consequence: str
    recoverable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "failure_type": self.failure_type,
            "impact": self.impact,
            "analytical_consequence": self.analytical_consequence,
            "recoverable": self.recoverable,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "PipelineFailure | None":
        if not isinstance(raw, Mapping):
            return None
        stage = str(raw.get("stage") or "").strip()
        failure_type = str(raw.get("failure_type") or "").strip()
        if not stage or not failure_type:
            return None
        return cls(
            stage=stage,
            failure_type=failure_type,
            impact=str(raw.get("impact") or "").strip(),
            analytical_consequence=str(raw.get("analytical_consequence") or "").strip(),
            recoverable=bool(raw.get("recoverable")),
        )


@dataclass(frozen=True, slots=True)
class EvidenceContract:
    status: EvidenceStatus = EvidenceStatus.UNAVAILABLE
    full_dataset_available: bool = False
    aggregates_are_authoritative: bool = False
    preview_is_non_authoritative: bool = True
    truncated_payload_detected: bool = False
    safe_for_quantitative_analysis: bool = False
    safe_for_record_level_claims: bool = False
    data_scope: str = "unknown"
    row_count: int = 0
    source_priority: EvidencePriority = EvidencePriority.VALIDATED_SUMMARY
    operational_confidence: OperationalConfidence = OperationalConfidence()
    failure: PipelineFailure | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "full_dataset_available": self.full_dataset_available,
            "aggregates_are_authoritative": self.aggregates_are_authoritative,
            "preview_is_non_authoritative": self.preview_is_non_authoritative,
            "truncated_payload_detected": self.truncated_payload_detected,
            "safe_for_quantitative_analysis": self.safe_for_quantitative_analysis,
            "safe_for_record_level_claims": self.safe_for_record_level_claims,
            "data_scope": self.data_scope,
            "row_count": max(0, int(self.row_count or 0)),
            "source_priority": self.source_priority.value,
            "operational_confidence": self.operational_confidence.as_dict(),
            "failure": self.failure.as_dict() if self.failure is not None else None,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "EvidenceContract":
        if not isinstance(raw, Mapping):
            return cls()
        status = _enum(raw.get("status"), EvidenceStatus, EvidenceStatus.UNAVAILABLE)
        priority = _enum(raw.get("source_priority"), EvidencePriority, EvidencePriority.VALIDATED_SUMMARY)
        return cls(
            status=status,
            full_dataset_available=bool(raw.get("full_dataset_available")),
            aggregates_are_authoritative=bool(raw.get("aggregates_are_authoritative")),
            preview_is_non_authoritative=bool(raw.get("preview_is_non_authoritative", True)),
            truncated_payload_detected=bool(raw.get("truncated_payload_detected")),
            safe_for_quantitative_analysis=bool(raw.get("safe_for_quantitative_analysis")),
            safe_for_record_level_claims=bool(raw.get("safe_for_record_level_claims")),
            data_scope=str(raw.get("data_scope") or "unknown"),
            row_count=max(0, int(raw.get("row_count") or 0)),
            source_priority=priority,
            operational_confidence=OperationalConfidence.from_mapping(raw.get("operational_confidence")),
            failure=PipelineFailure.from_mapping(raw.get("failure")),
        )

    @classmethod
    def present(
        cls,
        *,
        row_count: int,
        full_dataset_available: bool = True,
        source_priority: EvidencePriority = EvidencePriority.FRESH_SQL_EVIDENCE,
        operational_confidence: OperationalConfidence | None = None,
        safe_for_record_level_claims: bool | None = None,
    ) -> "EvidenceContract":
        row_count = max(0, int(row_count or 0))
        full = bool(full_dataset_available)
        return cls(
            status=EvidenceStatus.PRESENT,
            full_dataset_available=full,
            aggregates_are_authoritative=True,
            preview_is_non_authoritative=True,
            truncated_payload_detected=not full,
            safe_for_quantitative_analysis=row_count > 0,
            safe_for_record_level_claims=full if safe_for_record_level_claims is None else safe_for_record_level_claims,
            data_scope="full" if full else "partial",
            row_count=row_count,
            source_priority=source_priority,
            operational_confidence=operational_confidence
            or OperationalConfidence(
                data_coverage=1.0 if full else 0.65,
                aggregation_reliability=0.9,
                pipeline_integrity=1.0,
                narrative_confidence=0.8,
            ),
        )

    @classmethod
    def empty_result(cls, *, row_count: int = 0) -> "EvidenceContract":
        return cls(
            status=EvidenceStatus.EMPTY_RESULT,
            full_dataset_available=True,
            aggregates_are_authoritative=True,
            safe_for_quantitative_analysis=False,
            safe_for_record_level_claims=True,
            data_scope="empty",
            row_count=max(0, int(row_count or 0)),
            source_priority=EvidencePriority.FRESH_SQL_EVIDENCE,
            operational_confidence=OperationalConfidence(
                data_coverage=1.0,
                aggregation_reliability=1.0,
                pipeline_integrity=1.0,
                narrative_confidence=0.7,
            ),
        )

    @classmethod
    def pipeline_failure(cls, failure: PipelineFailure) -> "EvidenceContract":
        return cls(
            status=EvidenceStatus.PIPELINE_FAILURE,
            data_scope="unavailable",
            source_priority=EvidencePriority.VALIDATED_SUMMARY,
            operational_confidence=OperationalConfidence(
                data_coverage=0.0,
                aggregation_reliability=0.0,
                pipeline_integrity=0.2 if failure.recoverable else 0.0,
                narrative_confidence=0.35,
            ),
            failure=failure,
        )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _float(value: Any) -> float:
    try:
        return _clamp01(float(value))
    except (TypeError, ValueError):
        return 0.0


def _enum(value: Any, enum_type: type[Enum], default: Any) -> Any:
    try:
        return enum_type(str(value))
    except (TypeError, ValueError):
        return default
