from __future__ import annotations

from orion_mcp_v3.contracts.answer_presentation import AnswerPresentationContract


def test_answer_presentation_contract_parses_mapping() -> None:
    contract = AnswerPresentationContract.from_mapping(
        {
            "result_scope": {"mode": "all", "limit": None},
            "sort": {"field": "vendas", "direction": "desc"},
            "confidence": 1.7,
            "reason": "Usuário pediu todos os registros ordenados.",
        }
    )

    assert contract.result_scope == {"mode": "all", "limit": None}
    assert contract.sort == {"field": "vendas", "direction": "desc"}
    assert contract.confidence == 1.0
    assert contract.as_dict()["result_scope"] == {"mode": "all", "limit": None}
