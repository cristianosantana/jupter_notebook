"""Resultado estruturado da execução analítica."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.evidence_contract import EvidenceContract, PipelineFailure


class AnalyticsOutcomeStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    NO_PLAN = "no_plan"
    EXECUTED_EMPTY = "executed_empty"
    EXECUTED = "executed"
    EXECUTION_FAILURE = "execution_failure"
    AGGREGATION_FAILURE = "aggregation_failure"


@dataclass(frozen=True, slots=True)
class AnalyticsOutcome:
    status: AnalyticsOutcomeStatus
    evidence: EvidenceBlock | None = None
    evidence_contract: EvidenceContract = EvidenceContract()
    row_count: int = 0
    plan_count: int = 0
    failure: PipelineFailure | None = None

    @classmethod
    def not_required(cls) -> "AnalyticsOutcome":
        return cls(status=AnalyticsOutcomeStatus.NOT_REQUIRED)

    @classmethod
    def no_plan(cls) -> "AnalyticsOutcome":
        return cls(status=AnalyticsOutcomeStatus.NO_PLAN)

    @classmethod
    def executed_empty(cls, *, row_count: int = 0, plan_count: int = 0) -> "AnalyticsOutcome":
        return cls(
            status=AnalyticsOutcomeStatus.EXECUTED_EMPTY,
            evidence_contract=EvidenceContract.empty_result(row_count=row_count),
            row_count=max(0, int(row_count or 0)),
            plan_count=max(0, int(plan_count or 0)),
        )

    @classmethod
    def executed(
        cls,
        *,
        evidence: EvidenceBlock | None,
        row_count: int,
        plan_count: int = 0,
        evidence_contract: EvidenceContract | None = None,
    ) -> "AnalyticsOutcome":
        return cls(
            status=AnalyticsOutcomeStatus.EXECUTED,
            evidence=evidence,
            evidence_contract=evidence_contract or EvidenceContract.present(row_count=row_count),
            row_count=max(0, int(row_count or 0)),
            plan_count=max(0, int(plan_count or 0)),
        )

    @classmethod
    def execution_failure(cls, failure: PipelineFailure, *, plan_count: int = 0) -> "AnalyticsOutcome":
        return cls(
            status=AnalyticsOutcomeStatus.EXECUTION_FAILURE,
            evidence_contract=EvidenceContract.pipeline_failure(failure),
            plan_count=max(0, int(plan_count or 0)),
            failure=failure,
        )

    @classmethod
    def aggregation_failure(cls, failure: PipelineFailure, *, row_count: int = 0) -> "AnalyticsOutcome":
        return cls(
            status=AnalyticsOutcomeStatus.AGGREGATION_FAILURE,
            evidence_contract=EvidenceContract.pipeline_failure(failure),
            row_count=max(0, int(row_count or 0)),
            failure=failure,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "row_count": self.row_count,
            "plan_count": self.plan_count,
            "has_evidence": self.evidence is not None,
            "evidence_contract": self.evidence_contract.as_dict(),
            "failure": self.failure.as_dict() if self.failure is not None else None,
        }
