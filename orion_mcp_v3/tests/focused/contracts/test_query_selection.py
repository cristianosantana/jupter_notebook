from __future__ import annotations

from orion_mcp_v3.contracts.query_selection import QuerySelectionContract


def test_query_selection_contract_parses_mapping() -> None:
    contract = QuerySelectionContract.from_mapping(
        {
            "template_slug": "performance_vendedor",
            "measure": "vendas",
            "dimension": "vendedor",
            "operation": "ranking_desc",
            "confidence": 1.7,
            "reason": "Pergunta pede ranking de vendedores.",
        }
    )

    assert contract.template_slug == "performance_vendedor"
    assert contract.measure == "vendas"
    assert contract.dimension == "vendedor"
    assert contract.operation == "ranking_desc"
    assert contract.confidence == 1.0
    assert contract.as_dict()["reason"] == "Pergunta pede ranking de vendedores."
