from __future__ import annotations

from orion_mcp_v3.contracts.analytics_outcome import AnalyticsOutcome, AnalyticsOutcomeStatus
from orion_mcp_v3.contracts.evidence_contract import EvidenceStatus, PipelineFailure


def test_analytics_outcome_distinguishes_empty_result_from_failure() -> None:
    empty = AnalyticsOutcome.executed_empty(row_count=0)
    failed = AnalyticsOutcome.execution_failure(
        PipelineFailure(
            stage="analytics_execute",
            failure_type="RuntimeError",
            impact="query nao executada",
            analytical_consequence="sem evidencia nova",
            recoverable=True,
        )
    )

    assert empty.status == AnalyticsOutcomeStatus.EXECUTED_EMPTY
    assert empty.evidence_contract.status == EvidenceStatus.EMPTY_RESULT
    assert failed.status == AnalyticsOutcomeStatus.EXECUTION_FAILURE
    assert failed.evidence_contract.status == EvidenceStatus.PIPELINE_FAILURE


def test_executed_outcome_carries_evidence_contract() -> None:
    outcome = AnalyticsOutcome.executed(evidence=None, row_count=12)

    assert outcome.status == AnalyticsOutcomeStatus.EXECUTED
    assert outcome.row_count == 12
    assert outcome.evidence_contract.status == EvidenceStatus.PRESENT
    assert outcome.as_dict()["status"] == "executed"
