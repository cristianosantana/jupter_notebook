from __future__ import annotations

from orion_mcp_v3.contracts.evidence_contract import (
    EvidenceContract,
    EvidencePriority,
    EvidenceStatus,
    OperationalConfidence,
    PipelineFailure,
)


def test_evidence_contract_defaults_are_conservative() -> None:
    contract = EvidenceContract()

    assert contract.status == EvidenceStatus.UNAVAILABLE
    assert contract.preview_is_non_authoritative is True
    assert contract.safe_for_quantitative_analysis is False
    assert contract.safe_for_record_level_claims is False
    assert contract.source_priority == EvidencePriority.VALIDATED_SUMMARY


def test_evidence_contract_round_trip_dict() -> None:
    contract = EvidenceContract(
        status=EvidenceStatus.PRESENT,
        full_dataset_available=True,
        aggregates_are_authoritative=True,
        safe_for_quantitative_analysis=True,
        safe_for_record_level_claims=True,
        data_scope="full",
        row_count=67,
        source_priority=EvidencePriority.DIRECT_ANSWER,
        operational_confidence=OperationalConfidence(
            data_coverage=0.8,
            aggregation_reliability=0.9,
            pipeline_integrity=1.0,
            narrative_confidence=0.75,
        ),
    )

    raw = contract.as_dict()
    restored = EvidenceContract.from_mapping(raw)

    assert restored == contract
    assert raw["operational_confidence"]["pipeline_integrity"] == 1.0


def test_pipeline_failure_maps_to_contract() -> None:
    failure = PipelineFailure(
        stage="analytics_merge",
        failure_type="aggregation_exception",
        impact="evidencia indisponivel",
        analytical_consequence="nao e seguro responder quantitativamente",
        recoverable=True,
    )
    contract = EvidenceContract.pipeline_failure(failure)

    assert contract.status == EvidenceStatus.PIPELINE_FAILURE
    assert contract.failure == failure
    assert contract.safe_for_quantitative_analysis is False
    assert contract.operational_confidence.pipeline_integrity < 0.5
