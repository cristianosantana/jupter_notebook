"""Mapeamento legado intent → fact_key (fora do hot path analítico)."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType

FACT_KEY_RANKING_ASC = "ranking_forma_pagamento"
FACT_KEY_RANKING_DESC = "ranking_forma_pagamento_desc"
FACT_KEY_FORMA_PAGAMENTO = "faturamento_forma_pagamento"
FACT_KEY_FATURAMENTO_TOTAL = "faturamento_total_periodo"


def fact_keys_for_contract(contract: IntentContract, message: str = "") -> tuple[str, ...]:
    """Legado — preferir ``plan_analytical_requirements`` pós-retrieval."""
    keys: list[str] = []

    if contract.dimension == "forma_pagamento" or _mentions_payment(contract, message):
        entity = _entity_from_contract(contract)
        if entity:
            keys.append(FACT_KEY_FORMA_PAGAMENTO)
        elif contract.operation == PublicOperationType.RANKING_DESC.value:
            keys.append(FACT_KEY_RANKING_DESC)
        else:
            keys.append(FACT_KEY_RANKING_ASC)

    if _mentions_revenue(contract, message):
        keys.append(FACT_KEY_FATURAMENTO_TOTAL)

    return tuple(dict.fromkeys(keys))


def is_composite_question(contract: IntentContract, message: str = "") -> bool:
    keys = fact_keys_for_contract(contract, message)
    return len(keys) >= 2


def _mentions_payment(contract: IntentContract, message: str = "") -> bool:
    metric = (contract.metric or "").lower()
    text = message.lower()
    return (
        "pagamento" in metric
        or contract.dimension == "forma_pagamento"
        or "forma de pagamento" in text
        or "formas de pagamento" in text
    )


def _entity_from_contract(contract: IntentContract) -> str | None:
    for filt in contract.entity_filters:
        if filt.value:
            return filt.value
    return None


def _mentions_revenue(contract: IntentContract, message: str = "") -> bool:
    if _entity_from_contract(contract) and contract.dimension == "forma_pagamento":
        return False
    if contract.dimension == "forma_pagamento" and contract.operation in (
        PublicOperationType.RANKING_ASC.value,
        PublicOperationType.RANKING_DESC.value,
    ):
        return False
    metric = (contract.metric or "").lower()
    intent = (contract.intent or "").lower()
    text = message.lower()
    return any(
        needle in metric or needle in intent or needle in text
        for needle in ("faturamento", "faturamos", "receita", "recebemos")
    )
