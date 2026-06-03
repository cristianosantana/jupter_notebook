from __future__ import annotations

from orion_mcp_v3.broker.evidence_builder import EvidenceBuilder
from orion_mcp_v3.contracts.evidence_contract import EvidenceContract, EvidenceStatus


def test_evidence_builder_attaches_evidence_contract_for_full_rows() -> None:
    block = EvidenceBuilder().build(
        [{"periodo": "2026-01", "total": 10.0}, {"periodo": "2026-02", "total": 20.0}],
        value_key="total",
        time_key="periodo",
        value_kind="money",
    )

    contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))

    assert contract.status == EvidenceStatus.PRESENT
    assert contract.row_count == 2
    assert contract.safe_for_quantitative_analysis is True
    assert block.metrics["evidence_contract"]["status"] == "present"


def test_evidence_builder_marks_empty_rows_as_empty_result() -> None:
    block = EvidenceBuilder().build([], value_key="total")

    contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))

    assert contract.status == EvidenceStatus.EMPTY_RESULT
    assert contract.safe_for_quantitative_analysis is False
