"""Mapeamento determinístico intent → fact_key."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType

FACT_KEY_RANKING_ASC = "ranking_forma_pagamento"
FACT_KEY_RANKING_DESC = "ranking_forma_pagamento_desc"
FACT_KEY_FATURAMENTO_TOTAL = "faturamento_total_periodo"
FACT_KEY_OFICINA = "faturamento_departamento_oficina"
FACT_KEY_PARTICIPACAO = "participacao_oficina"


def fact_keys_for_contract(contract: IntentContract, message: str = "") -> tuple[str, ...]:
    """Deriva fact_keys candidatos a partir do contrato de intenção."""
    keys: list[str] = []

    if contract.dimension == "forma_pagamento" or _mentions_payment(contract, message):
        if contract.operation == PublicOperationType.RANKING_DESC.value:
            keys.append(FACT_KEY_RANKING_DESC)
        else:
            keys.append(FACT_KEY_RANKING_ASC)

    if _mentions_revenue(contract, message):
        keys.append(FACT_KEY_FATURAMENTO_TOTAL)

    if _mentions_oficina(contract, message):
        keys.append(FACT_KEY_OFICINA)

    if FACT_KEY_FATURAMENTO_TOTAL in keys and FACT_KEY_OFICINA in keys:
        keys.append(FACT_KEY_PARTICIPACAO)

    return tuple(dict.fromkeys(keys))


def is_composite_question(contract: IntentContract, message: str = "") -> bool:
    keys = fact_keys_for_contract(contract, message)
    if FACT_KEY_FATURAMENTO_TOTAL in keys and FACT_KEY_OFICINA in keys:
        return True
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


def _mentions_revenue(contract: IntentContract, message: str = "") -> bool:
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
        for needle in ("faturamento", "faturamos", "receita")
    )


def _mentions_oficina(contract: IntentContract, message: str = "") -> bool:
    text = message.lower()
    if "oficina" in text:
        return True
    for filt in contract.entity_filters:
        if "oficina" in filt.value.lower() or filt.dimension == "departamento":
            return True
    return False
