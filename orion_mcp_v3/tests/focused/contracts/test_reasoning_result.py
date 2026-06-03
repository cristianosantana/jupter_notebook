from __future__ import annotations

from orion_mcp_v3.contracts.evidence_contract import EvidenceContract, EvidenceStatus
from orion_mcp_v3.contracts.reasoning_result import AnalyticalReasoningResult, AnswerMode


def test_reasoning_result_serializes_compact_state() -> None:
    result = AnalyticalReasoningResult(
        facts=("Resposta direta disponível.",),
        insights=("Use a resposta direta sem ranking complementar.",),
        risks=(),
        limitations=("Sem segurança para afirmações registro a registro.",),
        evidence_contract=EvidenceContract(status=EvidenceStatus.PRESENT, row_count=10),
        answer_mode=AnswerMode.LITERAL,
        should_narrate=True,
    )

    raw = result.as_dict()

    assert raw["answer_mode"] == "literal"
    assert raw["evidence_contract"]["status"] == "present"
    assert raw["facts"] == ["Resposta direta disponível."]
