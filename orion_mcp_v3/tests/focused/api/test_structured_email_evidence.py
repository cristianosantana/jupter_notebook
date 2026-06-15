from __future__ import annotations

from orion_mcp_v3.api.email.structured_evidence import structured_email_evidence_from
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.provenance import CoverageInfo


def test_structured_email_evidence_uses_evidence_summary_when_no_full_summary() -> None:
    evidence = EvidenceBlock(
        summary="## Faturamento por tipo de pagamento\n1. PIX: R$ 10,00",
        insights={},
        metrics={},
        confidence=0.9,
        coverage=CoverageInfo(),
    )

    assert structured_email_evidence_from(evidence) == "## Faturamento por tipo de pagamento\n1. PIX: R$ 10,00"
    assert structured_email_evidence_from(None) is None


def test_structured_email_evidence_prefers_full_summary_over_scoped_summary() -> None:
    scoped = "Resposta direta: maior total liquido por tipo de pagamento: Cartão de Crédito (R$ 1.755.398,76)."
    full = (
        "Resposta direta: total liquido por tipo de pagamento:\n"
        "1. Cartão de Crédito: R$ 1.755.398,76\n"
        "2. PIX: R$ 382.387,40"
    )
    evidence = EvidenceBlock(
        summary=scoped,
        insights={},
        metrics={},
        confidence=0.9,
        coverage=CoverageInfo(),
        supporting_data={"direct_answer": {"summary": scoped, "full_summary": full}},
    )

    assert structured_email_evidence_from(evidence) == full
